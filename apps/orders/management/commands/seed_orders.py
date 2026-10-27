import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.catalog.models import MenuCategory, MenuItem
from apps.map.models import DeliveryAddress, TenantLocation
from apps.orders.models import Cart, CartItem, Order, OrderItem, ReusableContainerStock
from apps.orders.services import format_address, quote_delivery

User = get_user_model()

# (email, nama tenant, telepon, alamat, area, lat, lng, stok wadah reusable)
TENANTS = [
    (
        "greenhouse@kitchen.com",
        "Greenhouse Kitchen",
        "081234567890",
        "Jl. Haji Asmawi No. 8, Beji",
        "",
        "-6.355000",
        "106.832000",
        40,
    ),
    (
        "lautbiru@resto.com",
        "Laut Biru",
        "081298765432",
        "Jl. Margonda Raya No. 358",
        "Margonda",
        "-6.372000",
        "106.834500",
        6,
    ),
]

# (label, alamat, patokan, lat, lng, alamat utama)
ADDRESSES = [
    ("Home", "Jl. Margonda Raya No. 12, Depok", "", "-6.390000", "106.830000", True),
    (
        "Campus",
        "Fasilkom UI, Gedung A, Depok",
        "Lobi gedung A",
        "-6.364700",
        "106.828600",
        False,
    ),
]

# (nama, harga, indeks tenant, kategori, vegetarian, deskripsi)
MENU_ITEMS = [
    (
        "Grilled tempeh bowl",
        45000,
        0,
        "Healthy Bowls",
        True,
        "Tempe panggang bumbu rempah dengan nasi merah & sayuran organik",
    ),
    (
        "Keto salmon poke",
        58000,
        1,
        "Poke & Seafood",
        False,
        "Salmon segar nori dengan shirataki rice dan alpukat creamy",
    ),
    (
        "Kombucha, ginger",
        22000,
        0,
        "Cold Beverages",
        True,
        "Minuman fermentasi probiotik rasa jahe segar tanpa pemanis buatan",
    ),
    (
        "Vegan gado-gado bowl",
        38000,
        0,
        "Healthy Bowls",
        True,
        "Gado-gado tradisional dengan bumbu kacang mede sangrai",
    ),
    (
        "Low carb chicken bowl",
        42000,
        0,
        "Healthy Bowls",
        False,
        "Dada ayam panggang rosemary dengan kembang kol & brokoli",
    ),
    (
        "Chia pudding",
        25000,
        0,
        "Cold Beverages",
        True,
        "Puding biji chia dengan susu almond & buah beri segar",
    ),
    (
        "Tropical Spirulina Smoothie",
        30000,
        0,
        "Cold Beverages",
        True,
        "Smoothie spirulina dengan mangga dan nanas organik",
    ),
    (
        "Crispy Tofu Sesame Salad",
        32000,
        0,
        "Healthy Bowls",
        True,
        "Tahu krispi wijen dengan selada hijau hidroponik",
    ),
]

# Lima pesanan pada desain Figma "My orders".
FIGMA_ORDERS = [
    {
        "order_code": "#SB-260928-0193",
        "status": Order.Status.PENDING,
        "packaging": Order.PackagingType.REUSABLE,
        "age": timedelta(hours=1),
        "notes": "Titipkan di pos satpam lobi timur.",
        "items": [
            ("Grilled tempeh bowl", 2),
            ("Keto salmon poke", 1),
            ("Kombucha, ginger", 1),
        ],
    },
    {
        "order_code": "#SB-260928-0171",
        "status": Order.Status.ON_THE_WAY,
        "packaging": Order.PackagingType.COMPOSTABLE,
        "age": timedelta(hours=4),
        "notes": "",
        "items": [("Vegan gado-gado bowl", 1)],
    },
    {
        "order_code": "#SB-260924-0102",
        "status": Order.Status.DELIVERED,
        "packaging": Order.PackagingType.REUSABLE,
        "age": timedelta(days=4),
        "notes": "Tolong panggil jika sudah sampai.",
        "items": [("Low carb chicken bowl", 2)],
    },
    {
        "order_code": "#SB-260910-0033",
        "status": Order.Status.DELIVERED,
        "packaging": Order.PackagingType.REUSABLE,
        "age": timedelta(days=16),
        "notes": "",
        "items": [("Chia pudding", 2)],
    },
    {
        "order_code": "#SB-260902-0011",
        "status": Order.Status.CANCELLED,
        "packaging": Order.PackagingType.COMPOSTABLE,
        "age": timedelta(days=26),
        "notes": "",
        "items": [("Keto salmon poke", 1)],
    },
]

CART_ITEMS = [
    ("Grilled tempeh bowl", 2),
    ("Keto salmon poke", 1),
    ("Kombucha, ginger", 1),
]

MIN_TOTAL_ORDERS = 50


class Command(BaseCommand):
    help = "Seed data contoh modul orders sesuai desain Figma (aman dijalankan ulang)."

    def handle(self, *args, **options):
        customer = self._seed_customer()
        tenants = self._seed_tenants()
        addresses = self._seed_addresses(customer)
        menu = self._seed_menu(tenants)

        home = addresses[0]
        for spec in FIGMA_ORDERS:
            spec = dict(spec)
            items = [(menu[name], quantity) for name, quantity in spec.pop("items")]
            self._save_order(customer, home, items, **spec)

        statuses = list(Order.Status)
        packagings = list(Order.PackagingType)
        menu_items = list(menu.values())
        missing = max(0, MIN_TOTAL_ORDERS - Order.objects.count())
        for _ in range(missing):
            age = timedelta(days=random.randint(0, 45), hours=random.randint(1, 23))
            status = random.choice(statuses)
            packaging = random.choice(packagings)
            items = [
                (menu_item, random.randint(1, 3))
                for menu_item in random.sample(menu_items, k=random.randint(1, 3))
            ]
            self._save_order(
                customer,
                random.choice(addresses),
                items,
                order_code=f"#SB-{(timezone.now() - age):%y%m%d}-{random.randint(0, 9999):04d}",
                status=status,
                packaging=packaging,
                age=age,
                notes="Catatan pengiriman contoh." if random.random() > 0.5 else "",
                returned=status == Order.Status.DELIVERED and random.random() > 0.4,
            )

        cart, _ = Cart.objects.get_or_create(user=customer)
        cart.items.all().delete()
        for name, quantity in CART_ITEMS:
            CartItem.objects.create(cart=cart, menu_item=menu[name], quantity=quantity)

        self.stdout.write(
            self.style.SUCCESS(
                f"Selesai: {Order.objects.count()} orders, {OrderItem.objects.count()} "
                f"order items. Keranjang {customer.email}: {cart.total_items} items "
                f"({cart.formatted_subtotal}). Login: anantha@example.com / Password123!"
            )
        )

    def _seed_customer(self):
        customer, created = User.objects.get_or_create(
            email="anantha@example.com",
            defaults={
                "first_name": "Anantha",
                "last_name": "Kamal",
                "account_type": User.AccountType.CUSTOMER,
            },
        )
        if created:
            customer.set_password("Password123!")
            customer.save()
        return customer

    def _seed_tenants(self):
        tenants = []
        for email, name, phone, address, area, lat, lng, stock in TENANTS:
            owner, _ = User.objects.get_or_create(
                email=email,
                defaults={"first_name": name, "account_type": User.AccountType.TENANT},
            )
            tenant, _ = Tenant.objects.get_or_create(
                owner=owner, defaults={"name": name, "phone_number": phone}
            )
            TenantLocation.objects.update_or_create(
                tenant=tenant,
                defaults={
                    "address": address,
                    "district": area,
                    "city": "Depok",
                    "latitude": Decimal(lat),
                    "longitude": Decimal(lng),
                    "delivery_radius_km": Decimal("8.0"),
                },
            )
            ReusableContainerStock.objects.update_or_create(
                tenant=tenant, defaults={"quantity": stock}
            )
            tenants.append(tenant)
        return tenants

    def _seed_addresses(self, customer):
        addresses = []
        for label, address, landmark, lat, lng, is_default in ADDRESSES:
            delivery_address, _ = DeliveryAddress.objects.update_or_create(
                owner=customer,
                label=label,
                defaults={
                    "recipient_name": customer.get_full_name(),
                    "phone_number": "081311112222",
                    "address": address,
                    "landmark": landmark,
                    "latitude": Decimal(lat),
                    "longitude": Decimal(lng),
                    "is_default": is_default,
                },
            )
            addresses.append(delivery_address)
        return addresses

    def _seed_menu(self, tenants):
        menu = {}
        for (
            name,
            price,
            tenant_index,
            category_name,
            vegetarian,
            description,
        ) in MENU_ITEMS:
            tenant = tenants[tenant_index]
            category, _ = MenuCategory.objects.get_or_create(
                name=category_name, defaults={"tenantId": tenant}
            )
            menu[name], _ = MenuItem.objects.get_or_create(
                name=name,
                defaults={
                    "price": price,
                    "tenantId": tenant,
                    "category": category,
                    "vegetarian": vegetarian,
                    "description": description,
                },
            )
        return menu

    def _save_order(
        self,
        customer,
        address,
        items,
        *,
        order_code,
        status,
        packaging,
        age,
        notes,
        returned=False,
    ):
        """Membuat atau memperbarui pesanan berdasarkan order_code."""
        tenants = {menu_item.tenantId for menu_item, _ in items if menu_item.tenantId}
        quote = quote_delivery(address, tenants)
        subtotal = sum(menu_item.price * quantity for menu_item, quantity in items)
        packaging_fee = Order.PACKAGING_FEES[packaging]
        is_reusable = packaging == Order.PackagingType.REUSABLE
        order, _ = Order.objects.update_or_create(
            order_code=order_code,
            defaults={
                "user": customer,
                "status": status,
                "packaging_type": packaging,
                "reusable_returned": is_reusable and returned,
                "reusable_containers": max(1, len(tenants)) if is_reusable else 0,
                "delivery_address": format_address(address),
                "delivery_notes": notes,
                "delivery_eta_minutes": quote.eta_minutes,
                "subtotal": subtotal,
                "packaging_fee": packaging_fee,
                "delivery_fee": quote.fee,
                "total_price": subtotal + packaging_fee + quote.fee,
                "eco_points": Order.PACKAGING_ECO_POINTS[packaging],
            },
        )
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - age)
        order.items.all().delete()
        OrderItem.objects.bulk_create(
            OrderItem(
                order=order,
                menu_item=menu_item,
                tenant=menu_item.tenantId,
                item_name=menu_item.name,
                tenant_name=menu_item.tenantId.name if menu_item.tenantId else "",
                price=menu_item.price,
                quantity=quantity,
                subtotal=menu_item.price * quantity,
            )
            for menu_item, quantity in items
        )
