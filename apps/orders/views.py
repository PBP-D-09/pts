import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import UserProfile
from apps.catalog.models import MenuItem
from apps.map.models import DeliveryAddress
from apps.map.selectors import DEFAULT_CENTER

from .forms import CheckoutForm, OrderNoteForm
from .models import Cart, Order, ReusableContainerStock, format_rupiah
from .services import (
    CONTAINER_RETURN_POINTS,
    add_item_to_cart,
    cancel_order,
    create_order_from_cart,
    get_cart_items,
    get_cart_tenants,
    get_or_create_cart,
    get_reusable_stocks,
    get_user_unreturned_containers_count,
    quote_delivery,
    remove_cart_item,
    reorder_items_to_cart,
    tenant_area,
    update_cart_item_quantity,
)

PACKAGING_DESCRIPTIONS = {
    Order.PackagingType.REUSABLE: "Return it on your next order. Deposit refunded.",
    Order.PackagingType.COMPOSTABLE: "Plant-fibre box. Breaks down in home compost.",
}
ORDERS_PER_PAGE = 10
DATE_RANGES = {
    "today": "Today",
    "7_days": "Last 7 days",
    "30_days": "Last 30 days",
}


def _is_ajax(request: HttpRequest) -> bool:
    """Helper untuk mendeteksi apakah request berupa AJAX / JSON."""
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
        or request.content_type == "application/json"
    )


def _parse_int(value):
    """int() untuk input form/JSON; None jika bukan angka bulat."""
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _request_data(request: HttpRequest) -> dict:
    """Data dari body JSON (klien seperti Flutter) atau form POST biasa."""
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return request.POST


def _cart_to_dict(cart: Cart) -> dict:
    """Serialisasi data Cart ke dictionary untuk response JSON."""
    items = get_cart_items(cart)
    subtotal = sum(item.subtotal for item in items)
    return {
        "cart_id": str(cart.id),
        "total_items": sum(item.quantity for item in items),
        "tenant_count": len(get_cart_tenants(items)),
        "subtotal": subtotal,
        "formatted_subtotal": format_rupiah(subtotal),
        "items": [
            {
                "id": str(item.id),
                "menu_item_id": str(item.menu_item.id),
                "name": item.menu_item.name,
                "tenant_name": (
                    item.menu_item.tenantId.name if item.menu_item.tenantId else ""
                ),
                "price": item.menu_item.price,
                "formatted_price": item.formatted_price,
                "quantity": item.quantity,
                "subtotal": item.subtotal,
                "formatted_subtotal": item.formatted_subtotal,
            }
            for item in items
        ],
    }


def _order_to_dict(order: Order) -> dict:
    """Serialisasi data Order ke dictionary untuk response JSON."""
    items_data = [
        {
            "id": str(item.id),
            "menu_item_id": str(item.menu_item_id) if item.menu_item_id else None,
            "item_name": item.item_name,
            "tenant_name": item.tenant_name,
            "price": item.price,
            "formatted_price": item.formatted_price,
            "quantity": item.quantity,
            "subtotal": item.subtotal,
            "formatted_subtotal": item.formatted_subtotal,
        }
        for item in order.items.all()
    ]
    return {
        "id": str(order.id),
        "order_code": order.order_code,
        "user_email": order.user.email,
        "status": order.status,
        "status_display": order.get_status_display(),
        "packaging_type": order.packaging_type,
        "packaging_display": order.get_packaging_type_display(),
        "reusable_returned": order.reusable_returned,
        "reusable_containers": order.reusable_containers,
        "delivery_address": order.delivery_address,
        "delivery_notes": order.delivery_notes,
        "delivery_eta_minutes": order.delivery_eta_minutes,
        "subtotal": order.subtotal,
        "packaging_fee": order.packaging_fee,
        "delivery_fee": order.delivery_fee,
        "total_price": order.total_price,
        "formatted_total_price": order.formatted_total_price,
        "eco_points": order.eco_points,
        "total_items_count": order.total_items_count,
        "can_cancel": order.can_cancel,
        "can_edit_note": order.can_edit_note,
        "created_at": order.created_at.strftime("%d %b %Y, %H:%M"),
        "created_at_iso": order.created_at.isoformat(),
        "items": items_data,
    }


# ==========================================
# 1. CART VIEWS (HTML + AJAX)
# ==========================================


def cart_view(request: HttpRequest) -> HttpResponse:
    """Menampilkan halaman keranjang belanja (Your cart) sesuai desain Figma."""
    cart = get_or_create_cart(request)
    items = get_cart_items(cart)
    for item in items:
        item.tenant_area = tenant_area(item.menu_item.tenantId)
    subtotal = sum(item.subtotal for item in items)
    context = {
        "cart": cart,
        "items": items,
        "total_items": sum(item.quantity for item in items),
        "tenant_count": len(get_cart_tenants(items)),
        "formatted_subtotal": format_rupiah(subtotal),
        "max_eco_points": Order.PACKAGING_ECO_POINTS[Order.PackagingType.REUSABLE],
    }
    return render(request, "orders/cart.html", context)


@require_POST
def add_to_cart_view(request: HttpRequest, menu_item_id) -> HttpResponse:
    """Menambahkan item ke dalam keranjang."""
    menu_item = get_object_or_404(MenuItem, id=menu_item_id)
    cart = get_or_create_cart(request)

    quantity = _parse_int(_request_data(request).get("quantity", 1)) or 1
    add_item_to_cart(cart, menu_item, quantity)

    message = f"{menu_item.name} added to your cart."
    if _is_ajax(request):
        return JsonResponse(
            {"success": True, "message": message, "cart": _cart_to_dict(cart)}
        )
    messages.success(request, message)
    return redirect("orders:cart")


@require_POST
def update_cart_item_view(request: HttpRequest, item_id) -> HttpResponse:
    """Mengubah kuantitas item keranjang via stepper (+) atau (-)."""
    cart = get_or_create_cart(request)
    cart_item = cart.items.filter(id=item_id).first()
    data = _request_data(request)
    action = data.get("action")

    quantity = None
    if cart_item is not None:
        if action == "increase":
            quantity = cart_item.quantity + 1
        elif action == "decrease":
            # Sesuai desain, tombol (-) berhenti di 1; hapus item lewat Remove.
            quantity = max(1, cart_item.quantity - 1)
        elif "quantity" in data:
            quantity = _parse_int(data["quantity"])

    if quantity is None:
        if _is_ajax(request):
            return JsonResponse(
                {"success": False, "error": "Invalid quantity."}, status=400
            )
        return redirect("orders:cart")

    updated_item = update_cart_item_quantity(cart, item_id, quantity)

    if _is_ajax(request):
        return JsonResponse(
            {
                "success": True,
                "item_deleted": updated_item is None,
                "item": (
                    {
                        "id": str(updated_item.id),
                        "quantity": updated_item.quantity,
                        "subtotal": updated_item.subtotal,
                        "formatted_subtotal": updated_item.formatted_subtotal,
                    }
                    if updated_item
                    else None
                ),
                "cart": _cart_to_dict(cart),
            }
        )
    return redirect("orders:cart")


@require_POST
def remove_cart_item_view(request: HttpRequest, item_id) -> HttpResponse:
    """Menghapus satu item dari keranjang."""
    cart = get_or_create_cart(request)
    deleted = remove_cart_item(cart, item_id)
    message = "Item removed from your cart." if deleted else "Item not found."

    if _is_ajax(request):
        return JsonResponse(
            {"success": deleted, "message": message, "cart": _cart_to_dict(cart)},
            status=200 if deleted else 404,
        )
    if deleted:
        messages.success(request, message)
    return redirect("orders:cart")


# ==========================================
# 2. CHECKOUT VIEW (CREATE ORDER)
# ==========================================


def _packaging_options(stocks) -> list:
    sold_out = [stock.tenant.name for stock in stocks if stock.quantity < 1]
    options = []
    for value, label in Order.PackagingType.choices:
        disabled = value == Order.PackagingType.REUSABLE and bool(sold_out)
        options.append(
            {
                "value": value,
                "label": label,
                "description": (
                    f"Sold out at {', '.join(sold_out)} today."
                    if disabled
                    else PACKAGING_DESCRIPTIONS[value]
                ),
                "fee": Order.PACKAGING_FEES[value],
                "formatted_fee": format_rupiah(Order.PACKAGING_FEES[value]),
                "eco_points": Order.PACKAGING_ECO_POINTS[value],
                "disabled": disabled,
            }
        )
    return options


@login_required
def checkout_view(request: HttpRequest) -> HttpResponse:
    """Halaman checkout: alamat tersimpan, kemasan ramah lingkungan, dan catatan."""
    cart = get_or_create_cart(request)
    items = get_cart_items(cart)

    if not items:
        if _is_ajax(request):
            return JsonResponse(
                {"success": False, "error": "Your cart is empty."}, status=400
            )
        messages.warning(request, "Your cart is empty.")
        return redirect("orders:cart")

    tenants = get_cart_tenants(items)
    addresses = list(DeliveryAddress.objects.filter(owner=request.user))
    for address in addresses:
        address.quote = quote_delivery(address, tenants)
    stocks = get_reusable_stocks(tenants)
    packaging_options = _packaging_options(stocks)

    if request.method == "POST":
        form = CheckoutForm(_request_data(request), user=request.user)
        if form.is_valid():
            try:
                order = create_order_from_cart(
                    user=request.user,
                    cart=cart,
                    packaging_type=form.cleaned_data["packaging_type"],
                    address=form.cleaned_data["address"],
                    delivery_notes=form.cleaned_data["delivery_notes"],
                )
            except ValueError as err:
                form.add_error(None, str(err))
            else:
                placed_url = reverse("orders:order_placed", args=[order.id])
                if _is_ajax(request):
                    return JsonResponse(
                        {
                            "success": True,
                            "message": f"Order {order.order_code} placed.",
                            "order": _order_to_dict(order),
                            "redirect_url": placed_url,
                        }
                    )
                return redirect(placed_url)
        if _is_ajax(request):
            return JsonResponse({"success": False, "errors": form.errors}, status=400)
    else:
        # ?address= dan ?packaging= dipakai setelah alamat baru dibuat di checkout.
        default_address = next(
            (
                address
                for address in addresses
                if str(address.pk) == request.GET.get("address")
            ),
            None,
        ) or next(
            (address for address in addresses if address.is_default),
            addresses[0] if addresses else None,
        )
        available = [
            option["value"] for option in packaging_options if not option["disabled"]
        ]
        packaging = request.GET.get("packaging")
        form = CheckoutForm(
            user=request.user,
            initial={
                "address": default_address.pk if default_address else None,
                "packaging_type": packaging if packaging in available else available[0],
            },
        )

    selected_address_id = str(form["address"].value() or "")
    selected_address = next(
        (address for address in addresses if str(address.pk) == selected_address_id),
        None,
    )
    selected_packaging = next(
        (
            option
            for option in packaging_options
            if option["value"] == form["packaging_type"].value()
        ),
        packaging_options[0],
    )
    subtotal = sum(item.subtotal for item in items)
    delivery_fee = selected_address.quote.fee if selected_address else 0

    tenant_pins = []
    for tenant in tenants:
        location = getattr(tenant, "location", None)
        if location is not None:
            tenant_pins.append(
                {
                    "name": tenant.name,
                    "lat": float(location.latitude),
                    "lng": float(location.longitude),
                }
            )

    context = {
        "items": items,
        "form": form,
        "addresses": addresses,
        "selected_address_id": selected_address_id,
        "packaging_options": packaging_options,
        "selected_packaging": selected_packaging,
        "low_stocks": [
            stock
            for stock in stocks
            if 0 < stock.quantity <= ReusableContainerStock.LOW_STOCK_THRESHOLD
        ],
        "subtotal": subtotal,
        "formatted_subtotal": format_rupiah(subtotal),
        "formatted_delivery_fee": (
            format_rupiah(delivery_fee) if selected_address else "—"
        ),
        "formatted_total": format_rupiah(
            subtotal + selected_packaging["fee"] + delivery_fee
        ),
        "tenant_pins": tenant_pins,
        "map_center": {"latitude": DEFAULT_CENTER[0], "longitude": DEFAULT_CENTER[1]},
        "new_address_defaults": {
            "recipient_name": request.user.get_full_name() or request.user.display_name,
            "phone_number": getattr(
                UserProfile.objects.filter(user=request.user).first(),
                "phone_number",
                "",
            ),
        },
    }
    return render(request, "orders/checkout.html", context)


@login_required
def order_placed_view(request: HttpRequest, order_id) -> HttpResponse:
    """Langkah 3 stepper: konfirmasi pesanan yang baru dibuat."""
    order = get_object_or_404(
        Order.objects.prefetch_related("items"), id=order_id, user=request.user
    )
    return render(request, "orders/order_placed.html", {"order": order})


# ==========================================
# 3. ORDER HISTORY & FILTER VIEWS (MY ORDERS)
# ==========================================


def _status_counts(user) -> dict:
    rows = (
        Order.objects.filter(user=user)
        .values("status")
        .annotate(total=Count("id"))
        .order_by()
    )
    counts = {status.value: 0 for status in Order.Status}
    for row in rows:
        counts[row["status"]] = row["total"]
    counts["all"] = sum(counts.values())
    return counts


def _filter_orders(request: HttpRequest) -> dict:
    """Filter riwayat pesanan berdasarkan status dan rentang tanggal (?status=,
    ?date_range=today|7_days|30_days|custom&start_date=&end_date=)."""
    orders = Order.objects.filter(user=request.user).prefetch_related(
        "items__menu_item"
    )

    active_status = request.GET.get("status", "all").strip().lower()
    if active_status in Order.Status.values:
        orders = orders.filter(status=active_status)
    else:
        active_status = "all"

    date_range = request.GET.get("date_range", "all").strip().lower()
    now = timezone.now()
    if date_range == "today":
        orders = orders.filter(created_at__date=timezone.localdate())
    elif date_range == "7_days":
        orders = orders.filter(created_at__gte=now - timedelta(days=7))
    elif date_range == "30_days":
        orders = orders.filter(created_at__gte=now - timedelta(days=30))
    elif date_range == "custom":
        start_date = parse_date(request.GET.get("start_date", ""))
        end_date = parse_date(request.GET.get("end_date", ""))
        if start_date:
            orders = orders.filter(created_at__date__gte=start_date)
        if end_date:
            orders = orders.filter(created_at__date__lte=end_date)
    else:
        date_range = "all"

    return {
        "orders": orders,
        "status_counts": _status_counts(request.user),
        "active_status": active_status,
        "date_range": date_range,
        "unreturned_containers": get_user_unreturned_containers_count(request.user),
    }


def _orders_json(result: dict) -> JsonResponse:
    return JsonResponse(
        {
            "success": True,
            "status_counts": result["status_counts"],
            "active_status": result["active_status"],
            "date_range": result["date_range"],
            "unreturned_containers": result["unreturned_containers"],
            "orders": [_order_to_dict(order) for order in result["orders"]],
        }
    )


def _review_url(order: Order) -> str:
    """Halaman review menu pertama di pesanan; modul reviews belum tentu terpasang."""
    item = next((item for item in order.items.all() if item.menu_item_id), None)
    if item is None:
        return reverse("catalog:show_catalog")
    try:
        return reverse("reviews:menu", args=[str(item.menu_item_id)])
    except NoReverseMatch:
        if item.tenant_id:
            return reverse("catalog:show_catalog_tenant", args=[item.tenant_id])
        return reverse("catalog:show_catalog")


def _order_card_html(request: HttpRequest, order: Order) -> str:
    order.review_url = _review_url(order)
    return render_to_string(
        "orders/partials/order_card.html", {"order": order}, request=request
    )


@login_required
def order_list_view(request: HttpRequest) -> HttpResponse:
    """Halaman riwayat pesanan (My orders) sesuai desain Figma."""
    result = _filter_orders(request)
    if _is_ajax(request):
        return _orders_json(result)

    page_obj = Paginator(result["orders"], ORDERS_PER_PAGE).get_page(
        request.GET.get("page")
    )
    orders = list(page_obj)
    for order in orders:
        order.review_url = _review_url(order)
    status_counts = result["status_counts"]
    context = {
        **result,
        "orders": orders,
        "page_obj": page_obj,
        "status_filters": [("all", "All", status_counts["all"])]
        + [
            (status.value, status.label, status_counts[status.value])
            for status in Order.Status
        ],
        "date_ranges": DATE_RANGES,
        "container_return_points": CONTAINER_RETURN_POINTS,
    }
    return render(request, "orders/orders.html", context)


@login_required
@require_POST
def cancel_order_view(request: HttpRequest, order_id) -> HttpResponse:
    """Membatalkan pesanan yang masih berstatus Pending (Delete / Cancel)."""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    try:
        order = cancel_order(order)
    except ValueError as err:
        if _is_ajax(request):
            return JsonResponse({"success": False, "error": str(err)}, status=400)
        messages.error(request, str(err))
        return redirect("orders:order_list")

    message = f"Order {order.order_code} cancelled."
    if _is_ajax(request):
        return JsonResponse(
            {
                "success": True,
                "message": message,
                "order": _order_to_dict(order),
                "card_html": _order_card_html(request, order),
                "status_counts": _status_counts(request.user),
            }
        )
    messages.success(request, message)
    return redirect("orders:order_list")


@login_required
@require_POST
def update_order_note_view(request: HttpRequest, order_id) -> HttpResponse:
    """Mengubah catatan pengiriman pada pesanan berstatus Pending (Update)."""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    form = OrderNoteForm(_request_data(request))
    error = None
    if not order.can_edit_note:
        error = "The tenant is already preparing this order, so the note is locked."
    elif not form.is_valid():
        error = form.errors["delivery_notes"][0]

    if error:
        if _is_ajax(request):
            return JsonResponse({"success": False, "error": error}, status=400)
        messages.error(request, error)
        return redirect("orders:order_list")

    order.delivery_notes = form.cleaned_data["delivery_notes"].strip()
    order.save(update_fields=["delivery_notes", "updated_at"])

    message = "Delivery note updated."
    if _is_ajax(request):
        return JsonResponse(
            {
                "success": True,
                "message": message,
                "delivery_notes": order.delivery_notes,
                "order": _order_to_dict(order),
                "card_html": _order_card_html(request, order),
            }
        )
    messages.success(request, message)
    return redirect("orders:order_list")


@login_required
@require_POST
def reorder_view(request: HttpRequest, order_id) -> HttpResponse:
    """Memasukkan kembali seluruh menu dari pesanan sebelumnya ke dalam keranjang."""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    cart = get_or_create_cart(request)
    added_count = reorder_items_to_cart(order, cart)

    message = f"{added_count} item{'s' if added_count != 1 else ''} from {order.order_code} added to your cart."
    if _is_ajax(request):
        return JsonResponse(
            {
                "success": True,
                "message": message,
                "added_count": added_count,
                "cart": _cart_to_dict(cart),
            }
        )
    messages.success(request, message)
    return redirect("orders:cart")


# ==========================================
# 4. REST JSON API ENDPOINTS (MOBILE / FLUTTER)
# ==========================================


@require_GET
def api_cart(request: HttpRequest) -> JsonResponse:
    """Endpoint REST JSON untuk melihat keranjang aktif."""
    cart = get_or_create_cart(request)
    return JsonResponse({"success": True, "cart": _cart_to_dict(cart)})


@login_required
@require_GET
def api_orders_list(request: HttpRequest) -> JsonResponse:
    """Endpoint REST JSON untuk riwayat pesanan (mendukung query param status &
    date_range)."""
    return _orders_json(_filter_orders(request))
