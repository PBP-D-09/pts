"""Tes endpoint Django REST Framework modul orders (/api/v1/orders/...)."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.map.models import DeliveryAddress

from .forms import NOTE_MAX_LENGTH
from .models import Cart, Order, ReusableContainerStock
from .services import add_item_to_cart
from .tests import PASSWORD, OrdersTestMixin, User


class OrdersApiTestCase(OrdersTestMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.login(self.user)

    def login(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def _cart(self):
        cart, _ = Cart.objects.get_or_create(user=self.user)
        return cart


class AuthTests(OrdersApiTestCase):
    def test_requires_token(self):
        self.client.credentials()
        for url in (
            reverse("orders_api:cart"),
            reverse("orders_api:orders"),
            reverse("orders_api:checkout"),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tenant_is_forbidden(self):
        self.login(self.greenhouse.owner)
        response = self.client.get(reverse("orders_api:cart"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CartApiTests(OrdersApiTestCase):
    def test_empty_cart(self):
        payload = self.client.get(reverse("orders_api:cart")).json()
        self.assertEqual(payload["total_items"], 0)
        self.assertEqual(payload["subtotal"], 0)
        self.assertEqual(payload["items"], [])

    def test_add_item_twice_merges_quantity(self):
        url = reverse("orders_api:cart-items")
        body = {"menu_item_id": str(self.tempeh.id), "quantity": 2}
        response = self.client.post(url, body, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.client.post(url, {"menu_item_id": str(self.tempeh.id)}, format="json")

        payload = self.client.get(reverse("orders_api:cart")).json()
        self.assertEqual(payload["total_items"], 3)
        self.assertEqual(payload["subtotal"], 135000)
        item = payload["items"][0]
        self.assertEqual(item["name"], "Grilled tempeh bowl")
        self.assertEqual(item["tenant_name"], "Greenhouse Kitchen")
        self.assertEqual(item["tenant_area"], "Depok")
        self.assertIsNone(item["photo_url"])

    def test_add_rejects_unknown_menu_and_bad_quantity(self):
        url = reverse("orders_api:cart-items")
        response = self.client.post(
            url,
            {"menu_item_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("menu_item_id", response.json())

        response = self.client.post(
            url, {"menu_item_id": str(self.tempeh.id), "quantity": 0}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", response.json())

    def test_update_and_delete_item(self):
        item = add_item_to_cart(self._cart(), self.poke, 1)
        url = reverse("orders_api:cart-item-detail", args=[item.id])

        response = self.client.patch(url, {"quantity": 4}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["items"][0]["quantity"], 4)
        self.assertEqual(response.json()["subtotal"], 232000)

        response = self.client.patch(url, {"quantity": 0}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["items"], [])

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_touch_another_users_cart_item(self):
        other = User.objects.create_user(
            email="other@example.com",
            password=PASSWORD,
            account_type=User.AccountType.CUSTOMER,
        )
        other_cart = Cart.objects.create(user=other)
        item = add_item_to_cart(other_cart, self.tempeh, 1)
        url = reverse("orders_api:cart-item-detail", args=[item.id])

        response = self.client.patch(url, {"quantity": 5}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)


class CheckoutApiTests(OrdersApiTestCase):
    url = reverse("orders_api:checkout")

    def test_empty_cart_is_rejected(self):
        self.assertEqual(
            self.client.get(self.url).status_code, status.HTTP_400_BAD_REQUEST
        )
        response = self.client.post(
            self.url,
            {"address_id": self.home.pk, "packaging_type": "reusable"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_preview_lists_addresses_with_quotes_and_packaging(self):
        self._figma_cart()
        payload = self.client.get(self.url).json()

        self.assertEqual(payload["cart"]["total_items"], 4)
        self.assertEqual(payload["default_address_id"], self.home.pk)
        labels = {address["label"] for address in payload["addresses"]}
        self.assertEqual(labels, {"Home", "Campus"})
        for address in payload["addresses"]:
            self.assertGreater(address["delivery_fee"], 0)
            self.assertGreater(address["eta_minutes"], 0)
        values = [option["value"] for option in payload["packaging_options"]]
        self.assertEqual(values, ["reusable", "compostable"])
        self.assertFalse(payload["packaging_options"][0]["disabled"])

    def test_preview_disables_reusable_when_sold_out(self):
        self._figma_cart()
        ReusableContainerStock.objects.create(tenant=self.laut_biru, quantity=0)
        payload = self.client.get(self.url).json()
        reusable = payload["packaging_options"][0]
        self.assertTrue(reusable["disabled"])
        self.assertIn("Laut Biru", reusable["description"])

    def test_place_order_empties_cart(self):
        self._figma_cart()
        response = self.client.post(
            self.url,
            {
                "address_id": self.campus.pk,
                "packaging_type": "compostable",
                "delivery_notes": "  Titip di satpam  ",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = response.json()
        self.assertEqual(order["status"], "pending")
        self.assertEqual(order["packaging_type"], "compostable")
        self.assertEqual(order["delivery_notes"], "Titip di satpam")
        self.assertEqual(order["subtotal"], 170000)
        self.assertEqual(
            order["total_price"],
            order["subtotal"] + order["packaging_fee"] + order["delivery_fee"],
        )
        self.assertEqual(order["total_items_count"], 4)
        self.assertTrue(order["can_cancel"])
        self.assertEqual(self._cart().items.count(), 0)

    def test_rejects_someone_elses_address_and_bad_packaging(self):
        self._figma_cart()
        other = User.objects.create_user(
            email="other@example.com",
            password=PASSWORD,
            account_type=User.AccountType.CUSTOMER,
        )
        foreign = DeliveryAddress.objects.create(
            owner=other,
            label="Kos",
            recipient_name="Other",
            phone_number="0812",
            address="Jl. Kober",
            latitude=self.home.latitude,
            longitude=self.home.longitude,
        )
        response = self.client.post(
            self.url,
            {"address_id": foreign.pk, "packaging_type": "plastic"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        errors = response.json()
        self.assertIn("address_id", errors)
        self.assertIn("packaging_type", errors)
        self.assertFalse(Order.objects.exists())

    def test_sold_out_reusable_returns_detail(self):
        self._figma_cart()
        ReusableContainerStock.objects.create(tenant=self.greenhouse, quantity=0)
        response = self.client.post(
            self.url,
            {"address_id": self.home.pk, "packaging_type": "reusable"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Greenhouse Kitchen", response.json()["detail"])
        self.assertEqual(self._cart().items.count(), 3)


class OrderHistoryApiTests(OrdersApiTestCase):
    def test_list_with_counts_and_status_filter(self):
        self._order()
        self._order(status=Order.Status.DELIVERED)
        url = reverse("orders_api:orders")

        payload = self.client.get(url).json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["status_counts"]["all"], 2)
        self.assertEqual(payload["status_counts"]["delivered"], 1)
        self.assertEqual(
            payload["results"][0]["items"][0]["item_name"], self.tempeh.name
        )

        payload = self.client.get(url, {"status": "delivered"}).json()
        self.assertEqual(payload["active_status"], "delivered")
        self.assertEqual(payload["count"], 1)

    def test_date_range_filter(self):
        old = self._order()
        Order.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        self._order()
        url = reverse("orders_api:orders")

        self.assertEqual(
            self.client.get(url, {"date_range": "7_days"}).json()["count"], 1
        )
        self.assertEqual(
            self.client.get(url, {"date_range": "30_days"}).json()["count"], 2
        )
        payload = self.client.get(
            url, {"date_range": "custom", "start_date": "2026-02-30"}
        ).json()
        self.assertEqual(payload["count"], 2)

    def test_other_users_orders_are_hidden(self):
        other = User.objects.create_user(
            email="other@example.com",
            password=PASSWORD,
            account_type=User.AccountType.CUSTOMER,
        )
        order = self._order(user=other)
        self.assertEqual(
            self.client.get(reverse("orders_api:orders")).json()["count"], 0
        )
        response = self.client.get(reverse("orders_api:order-detail", args=[order.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class OrderActionApiTests(OrdersApiTestCase):
    def test_cancel_pending_order(self):
        order = self._order()
        response = self.client.post(reverse("orders_api:order-cancel", args=[order.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "cancelled")
        self.assertFalse(response.json()["can_cancel"])

    def test_cannot_cancel_processing_order(self):
        order = self._order(status=Order.Status.PROCESSING)
        response = self.client.post(reverse("orders_api:order-cancel", args=[order.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.json())

    def test_update_note(self):
        order = self._order()
        url = reverse("orders_api:order-note", args=[order.id])
        response = self.client.patch(
            url, {"delivery_notes": "  Pagar hijau  "}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["delivery_notes"], "Pagar hijau")

        too_long = "x" * (NOTE_MAX_LENGTH + 1)
        response = self.client.patch(url, {"delivery_notes": too_long}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_note_locked_after_pending(self):
        order = self._order(status=Order.Status.ON_THE_WAY)
        response = self.client.patch(
            reverse("orders_api:order-note", args=[order.id]),
            {"delivery_notes": "Baru"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        order.refresh_from_db()
        self.assertEqual(order.delivery_notes, "")

    def test_reorder_adds_items_to_cart(self):
        order = self._order(status=Order.Status.DELIVERED)
        response = self.client.post(
            reverse("orders_api:order-reorder", args=[order.id])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["added_count"], 1)
        self.assertEqual(payload["cart"]["items"][0]["name"], self.tempeh.name)
