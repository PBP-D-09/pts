import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import EcoPointActivity, Tenant, UserProfile
from apps.catalog.models import MenuCategory, MenuItem
from apps.map.models import DeliveryAddress, TenantLocation
from apps.orders.models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    ReusableContainerStock,
    format_rupiah,
)
from apps.orders.services import (
    DELIVERY_FALLBACK_FEE,
    ETA_FALLBACK_MINUTES,
    add_item_to_cart,
    cancel_order,
    create_order_from_cart,
    get_user_unreturned_containers_count,
    mark_containers_returned,
    quote_delivery,
    remove_cart_item,
    reorder_items_to_cart,
    update_cart_item_quantity,
)

User = get_user_model()
PASSWORD = "Password123!"


class OrdersTestMixin:
    """Data dasar: satu customer, dua tenant di Depok, menu, dan alamat Home."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="anantha@example.com",
            password=PASSWORD,
            first_name="Anantha",
            account_type=User.AccountType.CUSTOMER,
        )
        self.greenhouse = self._tenant("greenhouse@example.com", "Greenhouse Kitchen")
        self.laut_biru = self._tenant("lautbiru@example.com", "Laut Biru")
        TenantLocation.objects.create(
            tenant=self.greenhouse,
            address="Jl. Haji Asmawi No. 8",
            city="Depok",
            latitude=Decimal("-6.355000"),
            longitude=Decimal("106.832000"),
        )
        TenantLocation.objects.create(
            tenant=self.laut_biru,
            address="Jl. Margonda Raya No. 358",
            district="Margonda",
            city="Depok",
            latitude=Decimal("-6.372000"),
            longitude=Decimal("106.834500"),
        )
        self.category = MenuCategory.objects.create(
            name="Bowls", tenantId=self.greenhouse
        )
        self.tempeh = self._menu("Grilled tempeh bowl", 45000, self.greenhouse)
        self.kombucha = self._menu("Kombucha, ginger", 22000, self.greenhouse)
        self.poke = self._menu("Keto salmon poke", 58000, self.laut_biru)
        self.home = DeliveryAddress.objects.create(
            owner=self.user,
            label="Home",
            recipient_name="Anantha",
            phone_number="081311112222",
            address="Jl. Margonda Raya No. 12, Depok",
            latitude=Decimal("-6.390000"),
            longitude=Decimal("106.830000"),
            is_default=True,
        )
        self.campus = DeliveryAddress.objects.create(
            owner=self.user,
            label="Campus",
            recipient_name="Anantha",
            phone_number="081311112222",
            address="Fasilkom UI, Gedung A, Depok",
            latitude=Decimal("-6.364700"),
            longitude=Decimal("106.828600"),
        )

    def _tenant(self, email, name):
        owner = User.objects.create_user(
            email=email, password=PASSWORD, account_type=User.AccountType.TENANT
        )
        return Tenant.objects.create(owner=owner, name=name, phone_number="0812")

    def _menu(self, name, price, tenant):
        return MenuItem.objects.create(
            name=name,
            price=price,
            tenantId=tenant,
            category=self.category,
            description=name,
        )

    def _figma_cart(self):
        cart, _ = Cart.objects.get_or_create(user=self.user)
        add_item_to_cart(cart, self.tempeh, 2)
        add_item_to_cart(cart, self.poke, 1)
        add_item_to_cart(cart, self.kombucha, 1)
        return cart

    def _order(self, **fields):
        defaults = {
            "user": self.user,
            "status": Order.Status.PENDING,
            "packaging_type": Order.PackagingType.REUSABLE,
            "total_price": 45000,
            "delivery_address": "Jl. Margonda",
        }
        order = Order.objects.create(**{**defaults, **fields})
        OrderItem.objects.create(
            order=order,
            menu_item=self.tempeh,
            tenant=self.greenhouse,
            item_name=self.tempeh.name,
            tenant_name=self.greenhouse.name,
            price=45000,
            quantity=1,
            subtotal=45000,
        )
        return order

    def _points(self):
        return UserProfile.objects.get(user=self.user).eco_points


class OrdersModelTests(OrdersTestMixin, TestCase):
    def test_format_rupiah(self):
        self.assertEqual(format_rupiah(45000), "Rp 45.000")
        self.assertEqual(format_rupiah(170000), "Rp 170.000")
        self.assertEqual(format_rupiah(0), "Rp 0")

    def test_cart_and_cart_item_properties(self):
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, menu_item=self.tempeh, quantity=2)

        self.assertEqual(item.subtotal, 90000)
        self.assertEqual(item.formatted_subtotal, "Rp 90.000")
        self.assertEqual(item.formatted_price, "Rp 45.000")
        self.assertEqual(cart.total_items, 2)
        self.assertEqual(cart.formatted_subtotal, "Rp 90.000")

    def test_order_permissions_follow_status(self):
        order = self._order()
        self.assertEqual(order.total_items_count, 1)
        self.assertTrue(order.can_cancel)
        self.assertTrue(order.can_edit_note)

        order.status = Order.Status.PROCESSING
        self.assertFalse(order.can_cancel)
        self.assertFalse(order.can_edit_note)

    def test_generated_order_code_format(self):
        order = Order.objects.create(user=self.user, delivery_address="Jl. Margonda")
        self.assertRegex(order.order_code, r"^#SB-\d{6}-\d{4}$")

    def test_reusable_stock_is_low(self):
        stock = ReusableContainerStock(tenant=self.laut_biru, quantity=6)
        self.assertTrue(stock.is_low)
        stock.quantity = 40
        self.assertFalse(stock.is_low)


class OrdersServiceTests(OrdersTestMixin, TestCase):
    def test_add_update_and_remove_cart_item(self):
        cart = Cart.objects.create(user=self.user)
        item = add_item_to_cart(cart, self.poke, quantity=1)
        item = add_item_to_cart(cart, self.poke, quantity=2)
        self.assertEqual(item.quantity, 3)

        updated = update_cart_item_quantity(cart, item.id, quantity=5)
        self.assertEqual(updated.quantity, 5)
        self.assertIsNone(update_cart_item_quantity(cart, item.id, quantity=0))
        self.assertEqual(cart.total_items, 0)

        item = add_item_to_cart(cart, self.kombucha, 1)
        self.assertTrue(remove_cart_item(cart, item.id))
        self.assertFalse(remove_cart_item(cart, item.id))

    def test_quote_delivery_matches_design(self):
        tenants = [self.greenhouse, self.laut_biru]
        home = quote_delivery(self.home, tenants)
        campus = quote_delivery(self.campus, tenants)
        self.assertEqual((home.fee, home.eta_minutes), (8000, 25))
        self.assertEqual((campus.fee, campus.eta_minutes), (6000, 20))
        self.assertEqual(home.formatted_fee, "Rp 8.000")

    def test_quote_delivery_without_tenant_location_uses_fallback(self):
        TenantLocation.objects.filter(tenant=self.greenhouse).delete()
        tenant = Tenant.objects.get(pk=self.greenhouse.pk)
        quote = quote_delivery(self.home, [tenant])
        self.assertEqual(quote.fee, DELIVERY_FALLBACK_FEE)
        self.assertEqual(quote.eta_minutes, ETA_FALLBACK_MINUTES)

    def test_create_order_from_cart_calculates_fees_and_points(self):
        cart = self._figma_cart()
        stock = ReusableContainerStock.objects.create(tenant=self.laut_biru, quantity=6)

        order = create_order_from_cart(
            user=self.user,
            cart=cart,
            packaging_type=Order.PackagingType.REUSABLE,
            address=self.home,
            delivery_notes="  Jangan pakai kantong kresek.  ",
        )

        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.subtotal, 170000)
        self.assertEqual(order.packaging_fee, 5000)
        self.assertEqual(order.delivery_fee, 8000)
        self.assertEqual(order.total_price, 183000)
        self.assertEqual(order.delivery_eta_minutes, 25)
        self.assertEqual(order.eco_points, 20)
        self.assertEqual(order.reusable_containers, 2)
        self.assertEqual(order.delivery_notes, "Jangan pakai kantong kresek.")
        self.assertIn("Jl. Margonda Raya No. 12", order.delivery_address)
        self.assertEqual(order.items.count(), 3)
        self.assertEqual(
            set(order.items.values_list("tenant", flat=True)),
            {self.greenhouse.pk, self.laut_biru.pk},
        )
        self.assertEqual(cart.items.count(), 0)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 5)
        self.assertEqual(self._points(), 20)
        self.assertTrue(
            EcoPointActivity.objects.filter(
                activity_type=EcoPointActivity.ActivityType.PACKAGING,
                description__contains=order.order_code,
            ).exists()
        )

    def test_compostable_order_does_not_use_containers(self):
        cart = self._figma_cart()
        stock = ReusableContainerStock.objects.create(tenant=self.laut_biru, quantity=0)

        order = create_order_from_cart(
            user=self.user,
            cart=cart,
            packaging_type=Order.PackagingType.COMPOSTABLE,
            address=self.campus,
        )

        self.assertEqual(order.packaging_fee, 2000)
        self.assertEqual(order.delivery_fee, 6000)
        self.assertEqual(order.eco_points, 10)
        self.assertEqual(order.reusable_containers, 0)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 0)

    def test_reusable_sold_out_blocks_order(self):
        cart = self._figma_cart()
        ReusableContainerStock.objects.create(tenant=self.laut_biru, quantity=0)

        with self.assertRaisesMessage(ValueError, "sold out at Laut Biru"):
            create_order_from_cart(
                user=self.user,
                cart=cart,
                packaging_type=Order.PackagingType.REUSABLE,
                address=self.home,
            )
        self.assertFalse(Order.objects.exists())
        self.assertEqual(cart.items.count(), 3)

    def test_empty_cart_raises(self):
        cart = Cart.objects.create(user=self.user)
        with self.assertRaises(ValueError):
            create_order_from_cart(
                user=self.user,
                cart=cart,
                packaging_type=Order.PackagingType.REUSABLE,
                address=self.home,
            )

    def test_cancel_order_restores_stock_and_points(self):
        cart = self._figma_cart()
        stock = ReusableContainerStock.objects.create(tenant=self.laut_biru, quantity=6)
        order = create_order_from_cart(
            user=self.user,
            cart=cart,
            packaging_type=Order.PackagingType.REUSABLE,
            address=self.home,
        )

        cancel_order(order)

        order.refresh_from_db()
        stock.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(stock.quantity, 6)
        self.assertEqual(self._points(), 0)
        with self.assertRaises(ValueError):
            cancel_order(order)

    def test_mark_containers_returned(self):
        stock = ReusableContainerStock.objects.create(
            tenant=self.greenhouse, quantity=3
        )
        order = self._order(status=Order.Status.DELIVERED, reusable_containers=1)

        self.assertTrue(mark_containers_returned(order))
        self.assertFalse(mark_containers_returned(order))

        order.refresh_from_db()
        stock.refresh_from_db()
        self.assertTrue(order.reusable_returned)
        self.assertEqual(stock.quantity, 4)
        self.assertEqual(self._points(), 10)

    def test_reorder_items_to_cart(self):
        order = self._order(status=Order.Status.DELIVERED)
        cart = Cart.objects.create(user=self.user)
        self.assertEqual(reorder_items_to_cart(order, cart), 1)
        self.assertEqual(cart.total_items, 1)

    def test_get_user_unreturned_containers_count(self):
        self._order(status=Order.Status.DELIVERED, reusable_containers=2)
        self._order(
            status=Order.Status.DELIVERED,
            reusable_containers=1,
            reusable_returned=True,
        )
        self._order(
            status=Order.Status.DELIVERED,
            packaging_type=Order.PackagingType.COMPOSTABLE,
        )
        self._order(status=Order.Status.ON_THE_WAY, reusable_containers=1)
        self.assertEqual(get_user_unreturned_containers_count(self.user), 2)


class CartViewTests(OrdersTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(email=self.user.email, password=PASSWORD)

    def _ajax_post(self, url, body=None):
        return self.client.post(
            url,
            data=json.dumps(body or {}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_cart_view_shows_items_tenants_and_header_count(self):
        self._figma_cart()
        response = self.client.get(reverse("orders:cart"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "orders/cart.html")
        self.assertEqual(response.context["total_items"], 4)
        self.assertEqual(response.context["tenant_count"], 2)
        self.assertEqual(response.context["cart_item_count"], 4)
        self.assertContains(response, "Rp 170.000")
        self.assertContains(response, "Margonda")

    def test_add_to_cart_ajax(self):
        url = reverse("orders:add_to_cart", kwargs={"menu_item_id": self.tempeh.id})
        response = self._ajax_post(url, {"quantity": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cart"]["total_items"], 2)

    def test_stepper_increase_and_decrease_stops_at_one(self):
        cart = Cart.objects.create(user=self.user)
        item = add_item_to_cart(cart, self.tempeh, 1)
        url = reverse("orders:update_cart_item", kwargs={"item_id": item.id})

        response = self._ajax_post(url, {"action": "increase"})
        self.assertEqual(response.json()["item"]["quantity"], 2)
        self.assertEqual(response.json()["cart"]["formatted_subtotal"], "Rp 90.000")

        self._ajax_post(url, {"action": "decrease"})
        response = self._ajax_post(url, {"action": "decrease"})
        self.assertEqual(response.json()["item"]["quantity"], 1)
        self.assertTrue(CartItem.objects.filter(id=item.id).exists())

    def test_stepper_form_post_without_javascript(self):
        cart = Cart.objects.create(user=self.user)
        item = add_item_to_cart(cart, self.tempeh, 1)
        url = reverse("orders:update_cart_item", kwargs={"item_id": item.id})
        response = self.client.post(url, {"action": "increase"})
        self.assertRedirects(response, reverse("orders:cart"))
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_invalid_quantity_is_rejected(self):
        cart = Cart.objects.create(user=self.user)
        item = add_item_to_cart(cart, self.tempeh, 1)
        url = reverse("orders:update_cart_item", kwargs={"item_id": item.id})
        response = self._ajax_post(url, {"quantity": "abc"})
        self.assertEqual(response.status_code, 400)

    def test_remove_cart_item_ajax(self):
        cart = Cart.objects.create(user=self.user)
        item = add_item_to_cart(cart, self.tempeh, 1)
        url = reverse("orders:remove_cart_item", kwargs={"item_id": item.id})

        response = self._ajax_post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cart"]["total_items"], 0)
        self.assertEqual(self._ajax_post(url).status_code, 404)

    def test_guest_cart_is_merged_after_login(self):
        self.client.logout()
        add_url = reverse("orders:add_to_cart", kwargs={"menu_item_id": self.tempeh.id})
        self._ajax_post(add_url, {"quantity": 2})
        self.assertEqual(
            self.client.get(reverse("orders:cart")).context["total_items"], 2
        )

        # Django mengganti session key saat login; keranjang guest harus tetap ikut.
        self.client.login(email=self.user.email, password=PASSWORD)
        response = self.client.get(reverse("orders:cart"))
        self.assertEqual(response.context["total_items"], 2)
        self.assertFalse(Cart.objects.filter(user__isnull=True).exists())


class CheckoutViewTests(OrdersTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(email=self.user.email, password=PASSWORD)

    def test_checkout_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_empty_cart_redirects_to_cart(self):
        response = self.client.get(reverse("orders:checkout"))
        self.assertRedirects(response, reverse("orders:cart"))

    def test_checkout_page_shows_addresses_fees_and_low_stock(self):
        self._figma_cart()
        ReusableContainerStock.objects.create(tenant=self.laut_biru, quantity=6)

        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_address_id"], str(self.home.pk))
        self.assertEqual(response.context["formatted_total"], "Rp 183.000")
        self.assertContains(response, "Delivery Rp 8.000 · about 25 min")
        self.assertContains(response, "Delivery Rp 6.000 · about 20 min")
        self.assertContains(
            response, "Only 6 reusable containers left at Laut Biru today."
        )

    def test_sold_out_reusable_defaults_to_compostable(self):
        self._figma_cart()
        ReusableContainerStock.objects.create(tenant=self.laut_biru, quantity=0)
        response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(response.context["selected_packaging"]["value"], "compostable")
        self.assertContains(response, "Sold out at Laut Biru today.")

    def test_place_order_redirects_to_order_placed(self):
        self._figma_cart()
        response = self.client.post(
            reverse("orders:checkout"),
            {
                "address": self.campus.pk,
                "packaging_type": Order.PackagingType.COMPOSTABLE,
                "delivery_notes": "Tolong panggil saya.",
            },
        )

        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, reverse("orders:order_placed", args=[order.id]))
        self.assertEqual(order.total_price, 170000 + 2000 + 6000)
        placed = self.client.get(response.url)
        self.assertContains(placed, order.order_code)
        self.assertContains(placed, "Rp 178.000")

    def test_cannot_use_someone_elses_address(self):
        self._figma_cart()
        other = User.objects.create_user(email="other@example.com", password=PASSWORD)
        address = DeliveryAddress.objects.create(
            owner=other,
            label="Other",
            recipient_name="Other",
            phone_number="0812",
            address="Somewhere",
            latitude=Decimal("-6.36"),
            longitude=Decimal("106.83"),
        )
        response = self.client.post(
            reverse("orders:checkout"),
            {"address": address.pk, "packaging_type": Order.PackagingType.REUSABLE},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertFormError(
            response.context["form"], "address", "Choose one of your saved addresses."
        )

    def test_order_placed_page_is_private(self):
        other = User.objects.create_user(email="other@example.com", password=PASSWORD)
        order = self._order(user=other)
        response = self.client.get(reverse("orders:order_placed", args=[order.id]))
        self.assertEqual(response.status_code, 404)

    def test_initial_address_and_packaging_from_query(self):
        self._figma_cart()
        response = self.client.get(
            reverse("orders:checkout"),
            {"address": self.campus.pk, "packaging": "compostable"},
        )
        self.assertEqual(response.context["selected_address_id"], str(self.campus.pk))
        self.assertEqual(response.context["selected_packaging"]["value"], "compostable")
        self.assertEqual(response.context["formatted_total"], "Rp 178.000")

    def test_query_cannot_select_foreign_address_or_sold_out_packaging(self):
        self._figma_cart()
        ReusableContainerStock.objects.create(tenant=self.laut_biru, quantity=0)
        other = User.objects.create_user(email="other@example.com", password=PASSWORD)
        foreign = DeliveryAddress.objects.create(
            owner=other,
            label="Other",
            recipient_name="Other",
            phone_number="0812",
            address="Somewhere",
            latitude=Decimal("-6.36"),
            longitude=Decimal("106.83"),
        )
        response = self.client.get(
            reverse("orders:checkout"), {"address": foreign.pk, "packaging": "reusable"}
        )
        self.assertEqual(response.context["selected_address_id"], str(self.home.pk))
        self.assertEqual(response.context["selected_packaging"]["value"], "compostable")

    def test_new_address_panel_is_prefilled_from_profile(self):
        self._figma_cart()
        UserProfile.objects.filter(user=self.user).update(phone_number="081399990000")
        response = self.client.get(reverse("orders:checkout"))
        self.assertContains(response, 'value="Anantha"')
        self.assertContains(response, 'value="081399990000"')
        self.assertContains(response, 'id="new-address-form"')

    def test_checkout_without_addresses_still_offers_the_map(self):
        DeliveryAddress.objects.filter(owner=self.user).delete()
        self._figma_cart()
        response = self.client.get(reverse("orders:checkout"))
        self.assertContains(response, "No saved addresses yet")
        self.assertContains(response, 'id="checkout-map"')
        self.assertContains(response, "data-add-address")

    def test_address_created_from_checkout_is_selected_with_quote(self):
        # Kontrak yang dipakai checkout.js: API JSON modul map, lalu ?address=<id>.
        self._figma_cart()
        response = self.client.post(
            reverse("map:address_create"),
            data=json.dumps(
                {
                    "label": "Office",
                    "recipient_name": "Anantha",
                    "phone_number": "081311112222",
                    "address": "Jl. Juanda No. 1, Depok",
                    "landmark": "",
                    "latitude": "-6.364700",
                    "longitude": "106.828600",
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 201)
        address_id = response.json()["address"]["id"]

        response = self.client.get(reverse("orders:checkout"), {"address": address_id})
        self.assertEqual(response.context["selected_address_id"], str(address_id))
        self.assertContains(response, "Delivery Rp 6.000 · about 20 min", count=2)


class OrderHistoryViewTests(OrdersTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(email=self.user.email, password=PASSWORD)

    def test_order_list_filters_by_status(self):
        self._order(status=Order.Status.PENDING)
        self._order(status=Order.Status.DELIVERED, reusable_containers=1)

        response = self.client.get(reverse("orders:order_list"))
        self.assertEqual(len(response.context["orders"]), 2)
        self.assertContains(response, "Reusable containers to return")
        self.assertContains(response, "Write a review")

        response = self.client.get(reverse("orders:order_list") + "?status=pending")
        self.assertEqual(len(response.context["orders"]), 1)
        self.assertEqual(response.context["orders"][0].status, Order.Status.PENDING)

        response = self.client.get(
            reverse("orders:order_list"), HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        data = response.json()
        self.assertEqual(data["status_counts"]["pending"], 1)
        self.assertEqual(data["status_counts"]["delivered"], 1)
        self.assertEqual(data["status_counts"]["all"], 2)

    def test_order_list_is_paginated(self):
        for _ in range(12):
            self._order()

        response = self.client.get(reverse("orders:order_list"))
        self.assertEqual(len(response.context["orders"]), 10)
        self.assertContains(response, "12 orders")
        self.assertContains(response, "Page 1 of 2")

        response = self.client.get(reverse("orders:order_list") + "?page=2")
        self.assertEqual(len(response.context["orders"]), 2)

    def test_order_items_are_listed_most_expensive_first(self):
        order = self._order()
        OrderItem.objects.create(
            order=order,
            item_name="Keto salmon poke",
            price=58000,
            quantity=2,
            subtotal=116000,
        )
        names = [item.item_name for item in order.items.all()]
        self.assertEqual(names, ["Keto salmon poke", "Grilled tempeh bowl"])

    def test_order_list_filters_by_date_range(self):
        old = self._order()
        Order.objects.filter(pk=old.pk).update(created_at="2026-01-01T10:00:00Z")
        self._order()

        response = self.client.get(reverse("orders:order_list") + "?date_range=7_days")
        self.assertEqual(len(response.context["orders"]), 1)

        response = self.client.get(
            reverse("orders:api_orders_list"),
            {
                "date_range": "custom",
                "start_date": "2026-01-01",
                "end_date": "2026-01-01",
            },
        )
        self.assertEqual(len(response.json()["orders"]), 1)

    def test_order_history_is_private(self):
        other = User.objects.create_user(email="other@example.com", password=PASSWORD)
        order = self._order(user=other)
        response = self.client.post(
            reverse("orders:cancel_order", kwargs={"order_id": order.id}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("orders:order_list")).status_code, 302)

    def test_cancel_order_ajax_returns_card_and_counts(self):
        order = self._order()
        url = reverse("orders:cancel_order", kwargs={"order_id": order.id})

        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("Cancelled", data["card_html"])
        self.assertIn("Order again", data["card_html"])
        self.assertEqual(data["status_counts"]["cancelled"], 1)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 400)

    def test_update_order_note_ajax(self):
        order = self._order(delivery_notes="Catatan awal")
        url = reverse("orders:update_order_note", kwargs={"order_id": order.id})

        response = self.client.post(
            url,
            data=json.dumps({"delivery_notes": "Catatan baru"}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.json()["delivery_notes"], "Catatan baru")
        self.assertIn('data-note="Catatan baru"', response.json()["card_html"])
        order.refresh_from_db()
        self.assertEqual(order.delivery_notes, "Catatan baru")

    def test_note_is_locked_after_processing(self):
        order = self._order(status=Order.Status.PROCESSING)
        response = self.client.post(
            reverse("orders:update_order_note", kwargs={"order_id": order.id}),
            data=json.dumps({"delivery_notes": "Telat"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_reorder_adds_items_to_cart(self):
        order = self._order(status=Order.Status.DELIVERED)
        response = self.client.post(reverse("orders:reorder", args=[order.id]))
        self.assertRedirects(response, reverse("orders:cart"))
        self.assertEqual(Cart.objects.get(user=self.user).total_items, 1)

    def test_api_cart_and_api_orders(self):
        self.assertTrue(self.client.get(reverse("orders:api_cart")).json()["success"])
        response = self.client.get(reverse("orders:api_orders_list"))
        self.assertTrue(response.json()["success"])
