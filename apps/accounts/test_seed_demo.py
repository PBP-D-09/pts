from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.demo_seed_data import DEMO_EMAILS, DEMO_PASSWORD
from apps.accounts.models import (
    CustomUser,
    DietActivity,
    EcoPointActivity,
    Tenant,
    UserAllergy,
)
from apps.accounts.selectors import get_recommendations
from apps.catalog.models import MenuCategory, MenuItem
from apps.map.models import DeliveryAddress, TenantLocation
from apps.orders.models import Cart, Order, OrderItem, ReusableContainerStock
from apps.reviews.models import HelpfulVote, Review


class SeedDemoCommandTests(TestCase):
    def seed(self, **options):
        output = StringIO()
        call_command("seed_demo", stdout=output, **options)
        return output.getvalue()

    def demo_counts(self):
        tenants = Tenant.objects.filter(owner__email__in=DEMO_EMAILS)
        menus = MenuItem.objects.filter(tenantId__in=tenants)
        orders = Order.objects.filter(order_code__startswith="#DEMO-")
        reviews = Review.objects.filter(author__email__in=DEMO_EMAILS)
        return {
            "users": CustomUser.objects.filter(email__in=DEMO_EMAILS).count(),
            "tenants": tenants.count(),
            "locations": TenantLocation.objects.filter(tenant__in=tenants).count(),
            "stocks": ReusableContainerStock.objects.filter(tenant__in=tenants).count(),
            "categories": MenuCategory.objects.filter(tenantId__in=tenants).count(),
            "menus": menus.count(),
            "addresses": DeliveryAddress.objects.filter(
                owner__email="customer@demo.sustainabowl.test"
            ).count(),
            "orders": orders.count(),
            "order_items": OrderItem.objects.filter(order__in=orders).count(),
            "reviews": reviews.count(),
            "votes": HelpfulVote.objects.filter(review__in=reviews).count(),
        }

    def test_seed_is_idempotent_and_prints_credentials(self):
        first_output = self.seed()
        first_counts = self.demo_counts()
        second_output = self.seed()

        self.assertEqual(first_counts, self.demo_counts())
        self.assertEqual(
            first_counts,
            {
                "users": 12,
                "tenants": 5,
                "locations": 5,
                "stocks": 5,
                "categories": 10,
                "menus": 15,
                "addresses": 2,
                "orders": 12,
                "order_items": 13,
                "reviews": 8,
                "votes": 8,
            },
        )
        for output in (first_output, second_output):
            self.assertIn("Seed demo selesai", output)
            self.assertIn("customer@demo.sustainabowl.test", output)
            self.assertIn(DEMO_PASSWORD, output)

    def test_seed_covers_accounts_catalog_map_orders_and_reviews(self):
        self.seed()
        customer = CustomUser.objects.get(email="customer@demo.sustainabowl.test")
        tenant_owner = CustomUser.objects.get(email="tenant@demo.sustainabowl.test")
        admin = CustomUser.objects.get(email="admin@demo.sustainabowl.test")

        self.assertTrue(customer.check_password(DEMO_PASSWORD))
        self.assertTrue(customer.is_customer)
        self.assertTrue(tenant_owner.check_password(DEMO_PASSWORD))
        self.assertTrue(tenant_owner.is_tenant)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(customer.userprofile.diets.count(), 1)
        self.assertTrue(customer.userprofile.allergies.filter(name="Kacang").exists())
        self.assertGreater(customer.userprofile.eco_points, 0)
        self.assertEqual(
            EcoPointActivity.objects.filter(profile=customer.userprofile).count(), 4
        )
        self.assertEqual(
            DietActivity.objects.filter(profile=customer.userprofile).count(), 3
        )

        recommendations = list(get_recommendations(customer.userprofile))
        self.assertEqual(len(recommendations), 3)
        self.assertTrue(all(item.vegetarian for item in recommendations))
        self.assertTrue(
            all("kacang" not in item.allergen_info.lower() for item in recommendations)
        )
        self.assertTrue(all(item.allergen_info.strip() for item in recommendations))

        categories = set(TenantLocation.objects.values_list("category", flat=True))
        self.assertEqual(categories, set(TenantLocation.Category.values))
        self.assertEqual(
            set(Order.objects.values_list("status", flat=True)),
            set(Order.Status.values),
        )
        self.assertEqual(
            set(Order.objects.values_list("packaging_type", flat=True)),
            set(Order.PackagingType.values),
        )
        self.assertTrue(
            Order.objects.filter(
                status=Order.Status.DELIVERED,
                packaging_type=Order.PackagingType.REUSABLE,
                reusable_returned=False,
            ).exists()
        )
        cart = Cart.objects.get(user=customer)
        self.assertEqual(cart.items.count(), 3)
        self.assertEqual(cart.total_items, 4)

        featured = MenuItem.objects.get(name="Grilled Tempeh Bowl")
        self.assertEqual(Review.objects.filter(menu_key=str(featured.pk)).count(), 6)
        self.assertEqual(
            set(
                Review.objects.filter(menu_key=str(featured.pk)).values_list(
                    "food_rating", flat=True
                )
            ),
            {1, 2, 3, 4, 5},
        )
        self.assertFalse(customer.userprofile.photo)
        self.assertFalse(tenant_owner.tenant.photo)
        self.assertFalse(MenuItem.objects.exclude(photo="").exists())
        self.assertFalse(Review.objects.exclude(photo="").exists())

        self.client.force_login(customer)
        customer_urls = [
            reverse("accounts:accounts"),
            reverse("catalog:show_catalog"),
            reverse("catalog:show_catalog_tenant", args=[tenant_owner.tenant.pk]),
            reverse("map:map"),
            reverse("map:addresses"),
            reverse("orders:cart"),
            reverse("orders:checkout"),
            reverse("orders:order_list"),
            reverse("reviews:menu", args=[featured.pk]),
        ]
        for url in customer_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("reviews:menu", args=[featured.pk]), {"page": 2}
            ).status_code,
            200,
        )

        self.client.force_login(tenant_owner)
        for url in (
            reverse("accounts:accounts"),
            reverse("map:tenant_location"),
            reverse("catalog:show_tenant_manage", args=[tenant_owner.tenant.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_reset_demo_restores_seed_and_preserves_non_demo_user(self):
        non_demo = CustomUser.objects.create_user(
            email="real-user@example.com", password="real-password"
        )
        self.seed()
        customer = CustomUser.objects.get(email="customer@demo.sustainabowl.test")
        UserAllergy.objects.create(profile=customer.userprofile, name="Demo tambahan")
        customer.first_name = "Diubah"
        customer.save(update_fields=["first_name"])

        self.seed(reset_demo=True)

        self.assertTrue(CustomUser.objects.filter(pk=non_demo.pk).exists())
        customer = CustomUser.objects.get(email="customer@demo.sustainabowl.test")
        self.assertEqual(customer.first_name, "Alya")
        self.assertFalse(
            customer.userprofile.allergies.filter(name="Demo tambahan").exists()
        )
        self.assertEqual(self.demo_counts()["orders"], 12)

    @override_settings(PRODUCTION=True)
    def test_production_requires_explicit_flag(self):
        with self.assertRaisesMessage(CommandError, "--allow-production"):
            self.seed()

        self.seed(allow_production=True)
        self.assertEqual(self.demo_counts()["users"], 12)

    def test_seed_refuses_to_take_over_non_demo_order_code(self):
        user = CustomUser.objects.create_user(
            email="real-order@example.com", password="real-password"
        )
        Order.objects.create(
            user=user,
            order_code="#DEMO-0001",
            delivery_address="Alamat pengguna asli",
        )

        with self.assertRaisesMessage(CommandError, "user non-demo"):
            self.seed()

        self.assertFalse(CustomUser.objects.filter(email__in=DEMO_EMAILS).exists())
