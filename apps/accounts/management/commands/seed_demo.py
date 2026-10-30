from datetime import date, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.demo_seed_data import (
    ADDRESSES,
    ADMIN,
    CUSTOMERS,
    DEMO_EMAILS,
    DEMO_ORDER_PREFIX,
    DEMO_PASSWORD,
    MENU_ITEMS,
    ORDER_SPECS,
    REVIEW_SPECS,
    TENANTS,
)
from apps.accounts.models import (
    CustomUser,
    DietActivity,
    DietPreference,
    EcoPointActivity,
    Tenant,
    UserAllergy,
    UserProfile,
)
from apps.catalog.models import (
    AllergenIngredient,
    MenuCategory,
    MenuItem,
    TenantCuisine,
)
from apps.map.models import DeliveryAddress, TenantLocation
from apps.orders.models import Cart, CartItem, Order, OrderItem, ReusableContainerStock
from apps.orders.services import format_address, quote_delivery
from apps.reviews.models import HelpfulVote, Review


class Command(BaseCommand):
    help = (
        "Membuat dataset demo lengkap SustainaBowl secara idempotent tanpa "
        "mengubah data non-demo."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-demo",
            action="store_true",
            help="Hapus akun demo beserta relasinya sebelum membuat ulang data.",
        )
        parser.add_argument(
            "--allow-production",
            action="store_true",
            help="Izinkan seed saat PRODUCTION=True.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.PRODUCTION and not options["allow_production"]:
            raise CommandError(
                "seed_demo dinonaktifkan di production. Gunakan --allow-production "
                "jika dataset demo memang ingin dibuat."
            )

        if options["reset_demo"]:
            deleted, _ = CustomUser.objects.filter(email__in=DEMO_EMAILS).delete()
            self.stdout.write(f"Menghapus {deleted} objek yang dimiliki data demo.")

        self._guard_order_codes()
        users = self._seed_users()
        references = self._seed_reference_data()
        tenants = self._seed_tenants(users, references["cuisines"])
        menus = self._seed_menus(tenants)
        self._seed_profiles(users, references["diets"])
        addresses = self._seed_addresses(users["customer"])
        self._seed_orders(users["customer"], addresses["Rumah"], menus)
        self._seed_cart(users["customer"], menus)
        self._seed_reviews(users, menus)
        self._print_summary()

    def _guard_order_codes(self):
        codes = [f"{DEMO_ORDER_PREFIX}{number}" for number, *_ in ORDER_SPECS]
        conflict = (
            Order.objects.filter(order_code__in=codes)
            .exclude(user__email__in=DEMO_EMAILS)
            .values_list("order_code", flat=True)
            .first()
        )
        if conflict:
            raise CommandError(
                f"Kode pesanan demo {conflict} sudah dimiliki user non-demo."
            )

    def _seed_users(self):
        admin = self._upsert_user(
            ADMIN,
            account_type=CustomUser.AccountType.CUSTOMER,
            is_staff=True,
            is_superuser=True,
        )
        customers = {
            spec["email"]: self._upsert_user(
                spec, account_type=CustomUser.AccountType.CUSTOMER
            )
            for spec in CUSTOMERS
        }
        tenant_owners = {
            spec["key"]: self._upsert_user(
                {
                    "email": spec["email"],
                    "first_name": spec["manager"],
                    "last_name": "",
                },
                account_type=CustomUser.AccountType.TENANT,
            )
            for spec in TENANTS
        }
        return {
            "admin": admin,
            "customer": customers[CUSTOMERS[0]["email"]],
            "customers": customers,
            "tenant_owners": tenant_owners,
        }

    def _upsert_user(
        self,
        spec,
        *,
        account_type,
        is_staff=False,
        is_superuser=False,
    ):
        user, _ = CustomUser.objects.update_or_create(
            email=spec["email"],
            defaults={
                "first_name": spec["first_name"],
                "last_name": spec.get("last_name", ""),
                "account_type": account_type,
                "is_active": True,
                "is_staff": is_staff,
                "is_superuser": is_superuser,
            },
        )
        user.set_password(DEMO_PASSWORD)
        user.save(update_fields=["password"])
        if account_type == CustomUser.AccountType.CUSTOMER:
            UserProfile.objects.get_or_create(user=user)
        else:
            UserProfile.objects.filter(user=user).delete()
        return user

    def _seed_reference_data(self):
        diet_labels = {
            DietPreference.Code.VEGAN: "Vegan",
            DietPreference.Code.VEGETARIAN: "Vegetarian",
            DietPreference.Code.LOW_CARB: "Low Carb",
            DietPreference.Code.KETO: "Keto",
        }
        diets = {
            code: DietPreference.objects.update_or_create(
                code=code, defaults={"label": label}
            )[0]
            for code, label in diet_labels.items()
        }
        cuisine_names = sorted(
            {name for tenant in TENANTS for name in tenant["cuisines"]}
        )
        cuisines = {
            name: TenantCuisine.objects.get_or_create(name=name)[0]
            for name in cuisine_names
        }
        for name in ("Gluten", "Kacang", "Kedelai", "Susu", "Telur"):
            AllergenIngredient.objects.get_or_create(name=name)
        return {"diets": diets, "cuisines": cuisines}

    def _seed_tenants(self, users, cuisines):
        tenants = {}
        for spec in TENANTS:
            tenant, _ = Tenant.objects.update_or_create(
                owner=users["tenant_owners"][spec["key"]],
                defaults={
                    "name": spec["name"],
                    "phone_number": spec["phone"],
                },
            )
            tenant.cuisines.set(cuisines[name] for name in spec["cuisines"])
            location = spec["location"]
            TenantLocation.objects.update_or_create(
                tenant=tenant,
                defaults={
                    "address": location["address"],
                    "district": location["district"],
                    "city": location["city"],
                    "category": location["category"],
                    "latitude": Decimal(location["latitude"]),
                    "longitude": Decimal(location["longitude"]),
                    "opening_time": time.fromisoformat(location["opening_time"]),
                    "closing_time": time.fromisoformat(location["closing_time"]),
                    "delivery_radius_km": Decimal(location["delivery_radius_km"]),
                },
            )
            ReusableContainerStock.objects.update_or_create(
                tenant=tenant, defaults={"quantity": spec["stock"]}
            )
            tenants[spec["key"]] = tenant
        return tenants

    def _seed_menus(self, tenants):
        menus = {}
        categories = {}
        for (
            tenant_key,
            category_name,
            name,
            price,
            vegetarian,
            allergen_info,
            description,
        ) in MENU_ITEMS:
            category_key = (tenant_key, category_name)
            if category_key not in categories:
                categories[category_key], _ = MenuCategory.objects.get_or_create(
                    tenantId=tenants[tenant_key], name=category_name
                )
            menu, _ = MenuItem.objects.update_or_create(
                tenantId=tenants[tenant_key],
                name=name,
                defaults={
                    "description": description,
                    "category": categories[category_key],
                    "allergen_info": allergen_info,
                    "vegetarian": vegetarian,
                    "price": price,
                },
            )
            menus[name] = menu
        return menus

    def _seed_profiles(self, users, diets):
        main_profile = users["customer"].userprofile
        main_profile.birth_date = date(1999, 5, 14)
        main_profile.phone_number = "081311112222"
        main_profile.eco_points_reset_at = None
        main_profile.save(
            update_fields=["birth_date", "phone_number", "eco_points_reset_at"]
        )
        main_profile.diets.set([diets[DietPreference.Code.VEGETARIAN]])
        UserAllergy.objects.get_or_create(profile=main_profile, name="Kacang")

        reviewer_profiles = []
        for index, spec in enumerate(CUSTOMERS[1:], start=1):
            profile = users["customers"][spec["email"]].userprofile
            profile.phone_number = f"0813222200{index:02d}"
            profile.save(update_fields=["phone_number"])
            profile.diets.set([diets[DietPreference.Code.VEGAN]] if index == 1 else [])
            reviewer_profiles.append(profile)

        activities = [
            (
                20,
                EcoPointActivity.ActivityType.PACKAGING,
                "Kemasan reusable pesanan demo",
                "0.35",
                2,
            ),
            (
                10,
                EcoPointActivity.ActivityType.PACKAGING,
                "Kemasan compostable pesanan demo",
                "0.20",
                8,
            ),
            (
                15,
                EcoPointActivity.ActivityType.ORDER,
                "Bonus pesanan sehat mingguan",
                "0.50",
                16,
            ),
            (
                20,
                EcoPointActivity.ActivityType.PACKAGING,
                "Pengembalian wadah reusable demo",
                "0.40",
                25,
            ),
        ]
        now = timezone.now()
        for points, activity_type, description, co2_saved, age in activities:
            activity, _ = EcoPointActivity.objects.update_or_create(
                profile=main_profile,
                description=description,
                defaults={
                    "points": points,
                    "activity_type": activity_type,
                    "co2_saved": Decimal(co2_saved),
                },
            )
            EcoPointActivity.objects.filter(pk=activity.pk).update(
                created_at=now - timedelta(days=age)
            )

        diet_activities = [
            (DietActivity.Source.PROFILE, "Preferensi Vegetarian dipilih.", 1),
            (DietActivity.Source.PROFILE, "Alergi Kacang ditambahkan.", 3),
            (DietActivity.Source.ORDER, "Memesan tiga menu vegetarian.", 6),
        ]
        for source, summary, age in diet_activities:
            DietActivity.objects.update_or_create(
                profile=main_profile,
                summary=summary,
                defaults={
                    "activity_date": timezone.localdate() - timedelta(days=age),
                    "source": source,
                },
            )

    def _seed_addresses(self, customer):
        DeliveryAddress.objects.filter(owner=customer).update(is_default=False)
        addresses = {}
        for spec in ADDRESSES:
            address, _ = DeliveryAddress.objects.update_or_create(
                owner=customer,
                label=spec["label"],
                defaults={
                    **spec,
                    "latitude": Decimal(spec["latitude"]),
                    "longitude": Decimal(spec["longitude"]),
                },
            )
            addresses[spec["label"]] = address
        return addresses

    def _seed_orders(self, customer, address, menus):
        now = timezone.now()
        for (
            number,
            status,
            packaging,
            days,
            hours,
            returned,
            item_specs,
        ) in ORDER_SPECS:
            items = [(menus[name], quantity) for name, quantity in item_specs]
            tenants = {item.tenantId for item, _ in items if item.tenantId is not None}
            quote = quote_delivery(address, tenants)
            subtotal = sum(item.price * quantity for item, quantity in items)
            packaging_fee = Order.PACKAGING_FEES[packaging]
            reusable = packaging == Order.PackagingType.REUSABLE
            order, _ = Order.objects.update_or_create(
                order_code=f"{DEMO_ORDER_PREFIX}{number}",
                defaults={
                    "user": customer,
                    "status": status,
                    "packaging_type": packaging,
                    "reusable_returned": reusable and returned,
                    "delivery_address": format_address(address),
                    "delivery_notes": (
                        "Data pesanan contoh untuk demonstrasi SustainaBowl."
                    ),
                    "delivery_eta_minutes": quote.eta_minutes,
                    "subtotal": subtotal,
                    "packaging_fee": packaging_fee,
                    "delivery_fee": quote.fee,
                    "total_price": subtotal + packaging_fee + quote.fee,
                    "eco_points": Order.PACKAGING_ECO_POINTS[packaging],
                    "reusable_containers": len(tenants) if reusable else 0,
                },
            )
            Order.objects.filter(pk=order.pk).update(
                created_at=now - timedelta(days=days, hours=hours)
            )
            order.items.all().delete()
            OrderItem.objects.bulk_create(
                OrderItem(
                    order=order,
                    menu_item=item,
                    tenant=item.tenantId,
                    item_name=item.name,
                    tenant_name=item.tenantId.name if item.tenantId else "",
                    price=item.price,
                    quantity=quantity,
                    subtotal=item.price * quantity,
                )
                for item, quantity in items
            )

    def _seed_cart(self, customer, menus):
        cart, _ = Cart.objects.get_or_create(user=customer)
        cart.items.all().delete()
        for name, quantity in (
            ("Grilled Tempeh Bowl", 2),
            ("Garden Quinoa Bowl", 1),
            ("Berry Chia Pudding", 1),
        ):
            CartItem.objects.create(cart=cart, menu_item=menus[name], quantity=quantity)

    def _seed_reviews(self, users, menus):
        reviews = {}
        now = timezone.now()
        for (
            email,
            menu_name,
            food_rating,
            packaging_rating,
            packaging_type,
            text,
            age,
        ) in REVIEW_SPECS:
            author = users["customers"][email]
            menu = menus[menu_name]
            review, _ = Review.objects.update_or_create(
                author=author,
                menu_key=str(menu.pk),
                defaults={
                    "food_rating": food_rating,
                    "packaging_rating": packaging_rating,
                    "packaging_type": packaging_type,
                    "text": text,
                },
            )
            Review.objects.filter(pk=review.pk).update(
                created_at=now - timedelta(days=age)
            )
            reviews[(email, menu_name)] = review

        featured = "Grilled Tempeh Bowl"
        vote_pairs = [
            (CUSTOMERS[0]["email"], CUSTOMERS[1]["email"]),
            (CUSTOMERS[0]["email"], CUSTOMERS[2]["email"]),
            (CUSTOMERS[0]["email"], CUSTOMERS[5]["email"]),
            (CUSTOMERS[1]["email"], CUSTOMERS[0]["email"]),
            (CUSTOMERS[2]["email"], CUSTOMERS[0]["email"]),
            (CUSTOMERS[3]["email"], CUSTOMERS[1]["email"]),
            (CUSTOMERS[4]["email"], CUSTOMERS[1]["email"]),
            (CUSTOMERS[5]["email"], CUSTOMERS[1]["email"]),
        ]
        for voter_email, author_email in vote_pairs:
            HelpfulVote.objects.get_or_create(
                review=reviews[(author_email, featured)],
                user=users["customers"][voter_email],
            )

    def _print_summary(self):
        demo_users = CustomUser.objects.filter(email__in=DEMO_EMAILS)
        demo_tenants = Tenant.objects.filter(owner__email__in=DEMO_EMAILS)
        demo_menus = MenuItem.objects.filter(tenantId__in=demo_tenants)
        demo_orders = Order.objects.filter(order_code__startswith=DEMO_ORDER_PREFIX)
        demo_reviews = Review.objects.filter(author__email__in=DEMO_EMAILS)
        self.stdout.write(
            self.style.SUCCESS(
                "Seed demo selesai: "
                f"{demo_users.count()} akun, {demo_tenants.count()} tenan, "
                f"{demo_menus.count()} menu, {demo_orders.count()} pesanan, "
                f"dan {demo_reviews.count()} review."
            )
        )
        self.stdout.write("Kredensial demo (password untuk semua akun: Demo123!):")
        self.stdout.write("  Customer: customer@demo.sustainabowl.test")
        self.stdout.write("  Tenant:   tenant@demo.sustainabowl.test")
        self.stdout.write("  Admin:    admin@demo.sustainabowl.test")
