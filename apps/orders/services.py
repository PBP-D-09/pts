import math
from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import F, Sum

from apps.accounts.models import EcoPointActivity, Tenant, UserProfile
from apps.accounts.services import record_eco_points
from apps.catalog.models import MenuItem

from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    ReusableContainerStock,
    format_rupiah,
)

# Id keranjang guest disimpan di data session (bukan session_key), karena Django
# mengganti session_key saat login sehingga keranjang lama tidak bisa ditemukan.
GUEST_CART_SESSION_KEY = "orders_guest_cart_id"

# Ongkir = biaya dasar + per km (dibulatkan ke atas) dari tenant terjauh.
DELIVERY_BASE_FEE = 4000
DELIVERY_FEE_PER_KM = 1000
DELIVERY_FALLBACK_FEE = 8000
ETA_BASE_MINUTES = 15
ETA_MINUTES_PER_KM = 2.5
ETA_FALLBACK_MINUTES = 30

# Eco Points tambahan untuk setiap wadah reusable yang dikembalikan.
CONTAINER_RETURN_POINTS = 10


@dataclass(frozen=True)
class DeliveryQuote:
    fee: int
    eta_minutes: int

    @property
    def formatted_fee(self) -> str:
        return format_rupiah(self.fee)


# ==========================================
# CART
# ==========================================


def _guest_cart(request) -> Cart | None:
    cart_id = request.session.get(GUEST_CART_SESSION_KEY)
    if not cart_id:
        return None
    return Cart.objects.filter(id=cart_id, user__isnull=True).first()


def _merge_cart(source: Cart, target: Cart) -> None:
    for item in source.items.all():
        existing = target.items.filter(menu_item=item.menu_item).first()
        if existing:
            existing.quantity += item.quantity
            existing.save(update_fields=["quantity"])
        else:
            item.cart = target
            item.save(update_fields=["cart"])
    source.delete()


def get_or_create_cart(request) -> Cart:
    """Mengambil atau membuat Cart untuk user yang login atau pengunjung guest.
    Jika guest baru saja login dan memiliki keranjang di sesi sebelumnya,
    keranjang sesi akan otomatis digabungkan (merge) ke keranjang user.
    """
    if request.user.is_authenticated:
        user_cart, _ = Cart.objects.get_or_create(user=request.user)
        guest_cart = _guest_cart(request)
        if guest_cart:
            _merge_cart(guest_cart, user_cart)
            request.session.pop(GUEST_CART_SESSION_KEY, None)
        return user_cart

    cart = _guest_cart(request)
    if cart is None:
        if not request.session.session_key:
            request.session.create()
        cart = Cart.objects.create(session_key=request.session.session_key)
        request.session[GUEST_CART_SESSION_KEY] = str(cart.id)
    return cart


def count_cart_items(request) -> int:
    """Jumlah item di keranjang tanpa membuat keranjang baru (untuk badge header)."""
    carts = Cart.objects.none()
    if request.user.is_authenticated:
        carts = Cart.objects.filter(user=request.user)
    guest_cart_id = request.session.get(GUEST_CART_SESSION_KEY)
    if guest_cart_id:
        carts = carts | Cart.objects.filter(id=guest_cart_id, user__isnull=True)
    total = CartItem.objects.filter(cart__in=carts).aggregate(total=Sum("quantity"))
    return total["total"] or 0


def add_item_to_cart(cart: Cart, menu_item: MenuItem, quantity: int = 1) -> CartItem:
    """Menambahkan item ke keranjang atau menambah kuantitasnya jika sudah ada."""
    quantity = max(quantity, 1)
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        menu_item=menu_item,
        defaults={"quantity": quantity},
    )
    if not created:
        cart_item.quantity += quantity
        cart_item.save(update_fields=["quantity"])
    return cart_item


def update_cart_item_quantity(cart: Cart, item_id, quantity: int) -> CartItem | None:
    """Mengubah kuantitas item di keranjang. Jika quantity <= 0, item akan dihapus."""
    cart_item = CartItem.objects.filter(cart=cart, id=item_id).first()
    if not cart_item:
        return None
    if quantity <= 0:
        cart_item.delete()
        return None
    cart_item.quantity = quantity
    cart_item.save(update_fields=["quantity"])
    return cart_item


def remove_cart_item(cart: Cart, item_id) -> bool:
    """Menghapus item spesifik dari keranjang."""
    deleted_count, _ = CartItem.objects.filter(cart=cart, id=item_id).delete()
    return deleted_count > 0


def get_cart_items(cart: Cart) -> list:
    return list(
        cart.items.select_related("menu_item__tenantId__location").order_by("added_at")
    )


def get_cart_tenants(items) -> list:
    """Tenant unik dari daftar CartItem, sesuai urutan kemunculannya."""
    tenants = {}
    for item in items:
        tenant = item.menu_item.tenantId
        if tenant is not None:
            tenants.setdefault(tenant.pk, tenant)
    return list(tenants.values())


def tenant_area(tenant: Tenant | None) -> str:
    """Area tenant dari modul map, misalnya 'Margonda' atau 'Depok'."""
    location = _tenant_location(tenant)
    if location is None:
        return ""
    return location.district or location.city


def _tenant_location(tenant: Tenant | None):
    if tenant is None:
        return None
    try:
        return tenant.location
    except ObjectDoesNotExist:
        return None


# ==========================================
# CHECKOUT: ONGKIR, KEMASAN, STOK
# ==========================================


def quote_delivery(address, tenants) -> DeliveryQuote:
    """Ongkir dan estimasi waktu dari tenant terjauh ke alamat pengiriman."""
    distances = [
        location.distance_from(address.latitude, address.longitude)
        for location in map(_tenant_location, tenants)
        if location is not None
    ]
    if not distances:
        return DeliveryQuote(
            fee=DELIVERY_FALLBACK_FEE, eta_minutes=ETA_FALLBACK_MINUTES
        )
    distance = max(distances)
    fee = DELIVERY_BASE_FEE + DELIVERY_FEE_PER_KM * max(1, math.ceil(distance))
    eta = ETA_BASE_MINUTES + ETA_MINUTES_PER_KM * distance
    return DeliveryQuote(fee=fee, eta_minutes=5 * math.ceil(eta / 5))


def get_reusable_stocks(tenants) -> list:
    return list(
        ReusableContainerStock.objects.filter(tenant__in=tenants).select_related(
            "tenant"
        )
    )


def format_address(address) -> str:
    lines = [
        f"{address.label}: {address.recipient_name} ({address.phone_number})",
        address.address,
    ]
    if address.landmark:
        lines.append(f"Patokan: {address.landmark}")
    return "\n".join(lines)


def _user_profile(user) -> UserProfile | None:
    return UserProfile.objects.filter(user=user).first()


def _record_points(user, points: int, activity_type: str, description: str) -> None:
    profile = _user_profile(user)
    if profile is None or points == 0:
        return
    record_eco_points(
        profile=profile,
        points=points,
        activity_type=activity_type,
        description=description,
    )


def _change_reusable_stock(tenant_ids, delta: int) -> None:
    ReusableContainerStock.objects.filter(tenant_id__in=tenant_ids).update(
        quantity=F("quantity") + delta
    )


@transaction.atomic
def create_order_from_cart(
    user,
    cart: Cart,
    packaging_type: str,
    address,
    delivery_notes: str = "",
) -> Order:
    """Membuat Order baru dari isi keranjang dan mengosongkan keranjang tersebut.

    Biaya kemasan, ongkir, Eco Points, dan stok wadah reusable dihitung ulang di
    server, sehingga angka dari browser tidak pernah dipercaya.
    """
    items = get_cart_items(cart)
    if not items:
        raise ValueError("Your cart is empty.")

    tenants = get_cart_tenants(items)
    reusable_containers = 0
    if packaging_type == Order.PackagingType.REUSABLE:
        stocks = ReusableContainerStock.objects.select_for_update().filter(
            tenant__in=tenants
        )
        for stock in stocks.select_related("tenant"):
            if stock.quantity < 1:
                raise ValueError(
                    f"Reusable containers are sold out at {stock.tenant.name} today."
                )
        _change_reusable_stock([tenant.pk for tenant in tenants], -1)
        reusable_containers = max(1, len(tenants))

    quote = quote_delivery(address, tenants)
    subtotal = sum(item.subtotal for item in items)
    packaging_fee = Order.PACKAGING_FEES[packaging_type]
    order = Order.objects.create(
        user=user,
        packaging_type=packaging_type,
        delivery_address=format_address(address),
        delivery_notes=delivery_notes.strip() if delivery_notes else "",
        delivery_eta_minutes=quote.eta_minutes,
        subtotal=subtotal,
        packaging_fee=packaging_fee,
        delivery_fee=quote.fee,
        total_price=subtotal + packaging_fee + quote.fee,
        eco_points=Order.PACKAGING_ECO_POINTS[packaging_type],
        reusable_containers=reusable_containers,
        status=Order.Status.PENDING,
    )

    OrderItem.objects.bulk_create(
        OrderItem(
            order=order,
            menu_item=item.menu_item,
            tenant=item.menu_item.tenantId,
            item_name=item.menu_item.name,
            tenant_name=item.menu_item.tenantId.name if item.menu_item.tenantId else "",
            price=item.menu_item.price,
            quantity=item.quantity,
            subtotal=item.subtotal,
        )
        for item in items
    )

    _record_points(
        user,
        order.eco_points,
        EcoPointActivity.ActivityType.PACKAGING,
        f"{order.get_packaging_type_display()} untuk pesanan {order.order_code}",
    )

    # Kosongkan keranjang belanja
    cart.items.all().delete()
    return order


def _order_tenant_ids(order: Order) -> list:
    return list(
        order.items.exclude(tenant__isnull=True)
        .values_list("tenant_id", flat=True)
        .distinct()
    )


@transaction.atomic
def cancel_order(order: Order) -> Order:
    """Membatalkan pesanan Pending: wadah reusable dan Eco Points dikembalikan."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_cancel:
        raise ValueError("This order is already being prepared and can't be cancelled.")

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    if order.reusable_containers:
        _change_reusable_stock(_order_tenant_ids(order), 1)
    _record_points(
        order.user,
        -order.eco_points,
        EcoPointActivity.ActivityType.ADJUSTMENT,
        f"Pembatalan pesanan {order.order_code}",
    )
    return order


@transaction.atomic
def mark_containers_returned(order: Order) -> bool:
    """Wadah reusable dari pesanan Delivered dikembalikan ke tenant (+Eco Points)."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if (
        order.status != Order.Status.DELIVERED
        or order.packaging_type != Order.PackagingType.REUSABLE
        or order.reusable_returned
    ):
        return False

    order.reusable_returned = True
    order.save(update_fields=["reusable_returned", "updated_at"])
    _change_reusable_stock(_order_tenant_ids(order), 1)
    _record_points(
        order.user,
        CONTAINER_RETURN_POINTS * order.reusable_containers,
        EcoPointActivity.ActivityType.PACKAGING,
        f"Pengembalian wadah reusable pesanan {order.order_code}",
    )
    return True


def reorder_items_to_cart(order: Order, cart: Cart) -> int:
    """Memasukkan kembali menu-menu dari pesanan lama ke dalam keranjang aktif."""
    added_count = 0
    for order_item in order.items.all():
        if order_item.menu_item:
            add_item_to_cart(cart, order_item.menu_item, order_item.quantity)
            added_count += 1
    return added_count


def get_user_unreturned_containers_count(user) -> int:
    """Menghitung wadah reusable yang belum dikembalikan dari pesanan Delivered."""
    if not user.is_authenticated:
        return 0
    total = Order.objects.filter(
        user=user,
        status=Order.Status.DELIVERED,
        packaging_type=Order.PackagingType.REUSABLE,
        reusable_returned=False,
    ).aggregate(total=Sum("reusable_containers"))
    return total["total"] or 0
