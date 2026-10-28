from io import BytesIO
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import Tenant
from apps.catalog.models import MenuCategory, MenuItem
from apps.orders.models import Order, OrderItem

from .forms import ReviewForm
from .integration import MenuContext, resolve_menu, resolve_packaging
from .models import HelpfulVote, Review
from .selectors import rating_summary, sentiment


def photo(name="meal.png", format="PNG"):
    stream = BytesIO()
    Image.new("RGB", (16, 16), "green").save(stream, format=format)
    return SimpleUploadedFile(
        name, stream.getvalue(), content_type=f"image/{format.lower()}"
    )


def packaging_resolver(menu_key, user):
    return "reusable" if user.is_customer else ""


def menu_resolver(key):
    if key == "available":
        return MenuContext(key=key, name="Actual catalog menu", tenant="Catalog tenant")


class ReviewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.author = User.objects.create_user(
            email="author@example.com",
            password="test-password",
            first_name="Review Author",
        )
        cls.other = User.objects.create_user(
            email="other@example.com", password="test-password"
        )
        cls.tenant = User.objects.create_user(
            email="tenant@example.com", password="test-password", account_type="tenant"
        )
        cls.restaurant = Tenant.objects.create(
            owner=cls.tenant, name="Green Kitchen", phone_number="021123456"
        )
        cls.category = MenuCategory.objects.create(
            tenantId=cls.restaurant, name="Bowls"
        )
        cls.menu = MenuItem.objects.create(
            tenantId=cls.restaurant,
            category=cls.category,
            name="Tempeh Bowl",
            description="Fresh tempeh and vegetables",
            price=30000,
            photo="menu_items/tempeh.png",
        )
        cls.menu_b = MenuItem.objects.create(
            tenantId=cls.restaurant, name="Rice Bowl", description="Rice", price=20000
        )
        cls.empty_menu = MenuItem.objects.create(
            name="Empty Bowl", description="No reviews yet", price=10000
        )
        cls.menu_key = str(cls.menu.pk)
        cls.other_key = str(cls.menu_b.pk)
        cls.review = Review.objects.create(
            menu_key=cls.menu_key,
            author=cls.author,
            food_rating=5,
            packaging_rating=4,
            text="Fresh and delicious",
        )
        cls.other_review = Review.objects.create(
            menu_key=cls.other_key,
            author=cls.other,
            food_rating=1,
            packaging_rating=1,
            text="Bad and cold",
        )

    def setUp(self):
        self.media = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.settings_override.disable)
        self.url = reverse("reviews:menu", args=[self.menu_key])
        self.create_url = reverse("reviews:create", args=[self.menu_key])
        self.payload = {"food_rating": 4, "packaging_rating": 5, "text": "A good meal"}
        self.ajax = {"HTTP_X_REVIEWS_REQUEST": "true"}

    def test_public_page_and_empty_state(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fresh and delicious")
        self.assertNotContains(response, "Bad and cold")
        self.assertContains(response, "Log in to write")
        response = self.client.get(
            reverse("reviews:menu", args=[str(self.empty_menu.pk)])
        )
        self.assertContains(response, "No reviews yet")
        self.assertNotContains(response, 'aria-label="Rating summary"')

    def test_guest_mutations_denied(self):
        for url in [
            self.create_url,
            reverse("reviews:edit", args=[self.review.pk]),
            reverse("reviews:delete", args=[self.review.pk]),
            reverse("reviews:helpful", args=[self.review.pk]),
        ]:
            self.assertEqual(self.client.post(url, self.payload).status_code, 302)
            self.assertEqual(
                self.client.post(url, self.payload, **self.ajax).status_code, 401
            )
        self.assertEqual(Review.objects.count(), 2)

    def test_customer_create_and_ajax_response(self):
        self.client.force_login(self.author)
        response = self.client.post(
            self.create_url, {**self.payload, "photo": photo()}, **self.ajax
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("published", response.json()["message"])
        review = Review.objects.latest("pk")
        self.assertEqual(review.author, self.author)
        self.assertEqual(review.menu_key, self.menu_key)
        self.assertTrue(review.photo.storage.exists(review.photo.name))
        response = self.client.get(self.url)
        self.assertContains(response, "You • Review Author")
        self.assertContains(response, "A good meal")

    def test_tenant_cannot_create(self):
        self.client.force_login(self.tenant)
        self.assertEqual(
            self.client.post(self.create_url, self.payload).status_code, 403
        )
        self.assertNotContains(self.client.get(self.url), 'id="write-review"')

    def test_owner_edit_delete_and_other_user_cannot(self):
        self.client.force_login(self.other)
        for action in ["edit", "delete"]:
            url = reverse(f"reviews:{action}", args=[self.review.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, self.payload).status_code, 404)
        self.client.force_login(self.author)
        edit = reverse("reviews:edit", args=[self.review.pk])
        self.assertContains(self.client.get(edit, **self.ajax), "Fresh and delicious")
        response = self.client.post(
            edit,
            {**self.payload, "author": self.other.pk, "menu_key": "forged"},
            **self.ajax,
        )
        self.assertEqual(response.status_code, 200)
        self.review.refresh_from_db()
        self.assertEqual(self.review.food_rating, 4)
        self.assertEqual(self.review.menu_key, self.menu_key)
        self.assertEqual(self.review.author, self.author)
        delete = reverse("reviews:delete", args=[self.review.pk])
        self.assertEqual(self.client.get(delete).status_code, 200)
        self.assertTrue(Review.objects.filter(pk=self.review.pk).exists())
        HelpfulVote.objects.create(review=self.review, user=self.other)
        self.assertEqual(self.client.post(delete, **self.ajax).status_code, 200)
        self.assertFalse(Review.objects.filter(pk=self.review.pk).exists())
        self.assertEqual(HelpfulVote.objects.count(), 0)

    def test_photo_replace_and_remove_cleanup(self):
        self.client.force_login(self.author)
        url = reverse("reviews:edit", args=[self.review.pk])
        self.client.post(url, {**self.payload, "photo": photo()})
        self.review.refresh_from_db()
        old = self.review.photo
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {**self.payload, "photo": photo("replacement.png")})
        self.review.refresh_from_db()
        self.assertNotEqual(old.name, self.review.photo.name)
        self.assertFalse(old.storage.exists(old.name))
        old = self.review.photo
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {**self.payload, "remove_photo": "true"})
        self.review.refresh_from_db()
        self.assertFalse(self.review.photo)
        self.assertFalse(old.storage.exists(old.name))

    def test_delete_cleans_photo(self):
        self.client.force_login(self.author)
        self.client.post(
            reverse("reviews:edit", args=[self.review.pk]),
            {**self.payload, "photo": photo()},
        )
        self.review.refresh_from_db()
        old = self.review.photo
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("reviews:delete", args=[self.review.pk]))
        self.assertFalse(old.storage.exists(old.name))

    def test_forms_reject_invalid_ratings_text_and_uploads(self):
        for change in [
            {"food_rating": 0},
            {"food_rating": 6},
            {"food_rating": "oops"},
            {"packaging_rating": -1},
            {"packaging_rating": 6},
            {"text": " "},
            {"text": "x" * 501},
        ]:
            self.assertFalse(ReviewForm({**self.payload, **change}).is_valid(), change)
        for upload in [
            SimpleUploadedFile("fake.png", b"not an image", content_type="image/png"),
            photo("bad.gif", "GIF"),
        ]:
            self.assertFalse(ReviewForm(self.payload, {"photo": upload}).is_valid())
        large = photo()
        large.size = 5 * 1024 * 1024 + 1
        self.assertFalse(ReviewForm(self.payload, {"photo": large}).is_valid())
        self.assertTrue(
            ReviewForm(self.payload, {"photo": photo("meal.jpg", "JPEG")}).is_valid()
        )
        self.client.force_login(self.author)
        response = self.client.post(
            self.create_url, {**self.payload, "text": " "}, **self.ajax
        )
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Please write your review", status_code=422)

    def test_helpful_toggle_and_http_methods(self):
        self.client.force_login(self.other)
        url = reverse("reviews:helpful", args=[self.review.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(
            self.client.post(url, **self.ajax).json(), {"selected": True, "count": 1}
        )
        self.assertContains(self.client.get(self.url), 'aria-pressed="true"')
        self.assertEqual(
            self.client.post(url, **self.ajax).json(), {"selected": False, "count": 0}
        )

    def test_db_constraints(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.create(
                menu_key="x",
                author=self.author,
                food_rating=7,
                packaging_rating=5,
                text="bad",
            )
        HelpfulVote.objects.create(review=self.review, user=self.other)
        with self.assertRaises(IntegrityError), transaction.atomic():
            HelpfulVote.objects.create(review=self.review, user=self.other)

    def test_filter_sort_pagination_and_summary(self):
        for i in range(6):
            Review.objects.create(
                menu_key=self.menu_key,
                author=self.other,
                food_rating=2,
                packaging_rating=1,
                text=f"Bad meal {i}",
            )
        summary = rating_summary(self.menu_key)
        self.assertEqual(summary["total"], 7)
        self.assertEqual(summary["distribution"][0][1], 1)
        self.assertAlmostEqual(summary["food"], 17 / 7)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["page"]), 4)
        self.assertTrue(response.context["page"].has_next())
        response = self.client.get(self.url, {"page": 2}, **self.ajax)
        self.assertEqual(len(response.context["page"]), 3)
        self.assertNotContains(response, "<!DOCTYPE")
        response = self.client.get(
            self.url, {"rating": "5", "sentiment": "positive", "packaging": "satisfied"}
        )
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertContains(response, "Clear Filters")
        response = self.client.get(self.url, {"rating": "1"})
        self.assertContains(response, "No reviews match your filters")
        for sort in ["oldest", "highest", "helpful"]:
            HelpfulVote.objects.get_or_create(review=self.review, user=self.other)
            response = self.client.get(self.url, {"sort": sort})
            self.assertEqual(response.context["page"][0].pk, self.review.pk)
        self.assertNotEqual(
            self.client.get(self.url).context["page"][0].pk, self.review.pk
        )
        for params in [
            {"rating": "injection"},
            {"packaging": "unknown"},
            {"sort": "text"},
        ]:
            self.assertEqual(self.client.get(self.url, params).status_code, 400)
        self.assertEqual(
            self.client.get(self.url, {"page": "nonsense"}).status_code, 200
        )
        self.assertEqual(self.client.get(self.url, {"page": "-1"}).status_code, 200)

    def test_sentiment_is_text_based(self):
        self.assertEqual(sentiment("Fresh enak delicious"), "positive")
        self.assertEqual(sentiment("Bad, cold, bocor"), "negative")
        self.assertEqual(sentiment("not good"), "negative")
        self.assertEqual(sentiment("tidak buruk"), "positive")
        self.assertEqual(sentiment("A bowl of rice"), "neutral")

    @override_settings(REVIEWS_MENU_RESOLVER="apps.reviews.tests.menu_resolver")
    def test_catalog_resolver_contract(self):
        self.assertEqual(resolve_menu("available").name, "Actual catalog menu")
        response = self.client.get(reverse("reviews:menu", args=["available"]))
        self.assertContains(response, "Catalog tenant")
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.author)
        self.assertEqual(
            self.client.post(self.create_url, self.payload).status_code, 404
        )

    def test_csrf_and_escaping(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.author)
        self.assertEqual(client.post(self.create_url, self.payload).status_code, 403)
        Review.objects.filter(pk=self.review.pk).update(
            text='<script>alert("xss")</script>'
        )
        response = self.client.get(self.url)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("xss")</script>')

    def test_empty_post_has_validation_errors(self):
        self.client.force_login(self.author)
        response = self.client.post(self.create_url, {}, **self.ajax)
        self.assertContains(response, "Please select a food rating.", status_code=422)
        self.assertContains(
            response, "Please select a packaging rating.", status_code=422
        )
        self.assertContains(response, "Please write your review.", status_code=422)
        self.assertEqual(Review.objects.count(), 2)

    @override_settings(
        REVIEWS_PACKAGING_RESOLVER="apps.reviews.tests.packaging_resolver"
    )
    def test_packaging_badge_comes_from_trusted_adapter(self):
        self.client.force_login(self.author)
        self.client.post(
            self.create_url, {**self.payload, "packaging_type": "compostable"}
        )
        review = Review.objects.latest("pk")
        self.assertEqual(review.packaging_type, "reusable")
        self.assertContains(self.client.get(self.url), "Reusable container")
        self.client.post(
            reverse("reviews:edit", args=[review.pk]),
            {**self.payload, "packaging_type": "compostable"},
        )
        review.refresh_from_db()
        self.assertEqual(review.packaging_type, "reusable")

    def test_real_catalog_metadata_and_navigation(self):
        with self.assertNumQueries(1):
            menu = resolve_menu(self.menu_key)
            self.assertEqual(menu.tenant, self.restaurant.name)
        self.assertEqual(menu.key, self.menu_key)
        self.assertEqual(menu.name, self.menu.name)
        self.assertEqual(menu.description, self.menu.description)
        self.assertEqual(menu.image_url, self.menu.photo.url)
        tenant_url = reverse("catalog:show_catalog_tenant", args=[self.restaurant.pk])
        self.assertEqual(menu.detail_url, tenant_url)
        response = self.client.get(self.url)
        for value in [
            menu.name,
            menu.tenant,
            menu.description,
            menu.image_url,
            tenant_url,
        ]:
            self.assertContains(response, value)
        response = self.client.get(tenant_url)
        self.assertContains(response, f'href="{self.url}"', count=2)
        self.assertContains(response, reverse("reviews:menu", args=[self.other_key]))
        menu = resolve_menu(str(self.empty_menu.pk))
        self.assertEqual(menu.tenant, "")
        self.assertEqual(menu.image_url, "")
        self.assertEqual(menu.detail_url, reverse("catalog:show_catalog"))

    def test_missing_invalid_and_noncanonical_menu_rejected(self):
        self.client.force_login(self.author)
        for key in [
            str(uuid4()),
            "contoh-menu",
            "x" * 101,
            self.menu_key.upper(),
            self.menu.pk.hex,
        ]:
            for action in ["menu", "create"]:
                url = reverse(f"reviews:{action}", args=[key])
                self.assertEqual(self.client.get(url).status_code, 404)
                if action == "create":
                    self.assertEqual(
                        self.client.post(url, self.payload).status_code, 404
                    )
        self.assertEqual(Review.objects.count(), 2)

    def test_catalog_rename_and_deleted_menu_preserve_reviews(self):
        self.menu.name = "Updated bowl name"
        self.menu.save(update_fields=["name"])
        self.assertContains(self.client.get(self.url), "Updated bowl name")
        self.menu.delete()
        self.assertTrue(Review.objects.filter(pk=self.review.pk).exists())
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(
            self.client.post(self.create_url, self.payload).status_code, 404
        )
        self.assertEqual(
            self.client.post(
                reverse("reviews:edit", args=[self.review.pk]), self.payload
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("reviews:helpful", args=[self.review.pk])
            ).status_code,
            404,
        )
        delete = reverse("reviews:delete", args=[self.review.pk])
        self.assertContains(self.client.get(delete), reverse("catalog:show_catalog"))
        self.assertRedirects(self.client.post(delete), reverse("catalog:show_catalog"))

    def test_legacy_reviews_are_preserved_and_not_exposed_as_catalog(self):
        legacy = Review.objects.create(
            menu_key="contoh-menu",
            author=self.author,
            food_rating=4,
            packaging_rating=5,
            text="Legacy",
        )
        self.assertEqual(
            self.client.get(
                reverse("reviews:menu", args=[legacy.menu_key])
            ).status_code,
            404,
        )
        self.assertEqual(self.client.get(self.url).context["summary"]["total"], 1)
        legacy.refresh_from_db()
        self.assertEqual(legacy.text, "Legacy")
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.post(reverse("reviews:delete", args=[legacy.pk])).status_code,
            404,
        )
        self.assertTrue(Review.objects.filter(pk=legacy.pk).exists())

    @override_settings(REVIEWS_MENU_RESOLVER=None)
    def test_unconfigured_catalog_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_menu(self.menu_key)

    @override_settings(REVIEWS_PACKAGING_RESOLVER=None)
    def test_without_orders_rating_still_saved_and_no_purchase_claim(self):
        self.client.force_login(self.author)
        self.client.post(
            self.create_url, {**self.payload, "packaging_type": "reusable"}
        )
        review = Review.objects.latest("pk")
        self.assertEqual(review.packaging_rating, 5)
        self.assertEqual(review.packaging_type, "")
        response = self.client.get(self.url)
        self.assertNotContains(response, "Reusable container")
        self.assertNotContains(response, "Verified purchase")
        self.assertAlmostEqual(response.context["summary"]["overall"], 4.5)
        self.assertEqual(response.context["summary"]["total"], 2)

    def test_tenant_can_read_and_vote_but_not_edit_customer_review(self):
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse("reviews:edit", args=[self.review.pk]), self.payload
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("reviews:delete", args=[self.review.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("reviews:helpful", args=[self.review.pk]), **self.ajax
            ).json(),
            {"selected": True, "count": 1},
        )

    def test_login_returns_to_reviews(self):
        response = self.client.get(self.create_url)
        self.assertIn("next=", response.url)
        response = self.client.post(
            reverse("accounts:login"),
            {
                "email": self.author.email,
                "password": "test-password",
                "next": self.url,
            },
        )
        self.assertRedirects(response, self.url)

    def test_review_list_does_not_query_per_author_or_vote(self):
        from django.contrib.auth.models import AnonymousUser

        from .selectors import review_queryset

        for i in range(8):
            Review.objects.create(
                menu_key=self.menu_key,
                author=self.other,
                food_rating=3,
                packaging_rating=3,
                text=f"Meal {i}",
            )
        with self.assertNumQueries(1):
            for review in review_queryset(self.menu_key, AnonymousUser(), {}):
                self.assertTrue(review.author.display_name)
                self.assertTrue(review.initials)
                self.assertEqual(review.helpful_count, 0)
                self.assertFalse(review.voted)

    def test_model_validation_rejects_invalid_menu_for_admin(self):
        self.review.full_clean()
        self.review.menu_key = "invented-menu"
        with self.assertRaises(ValidationError) as error:
            self.review.full_clean()
        self.assertIn("menu_key", error.exception.message_dict)

    def test_packaging_contract_accepts_compostable_and_rejects_unknown(self):
        from unittest.mock import patch

        from .integration import resolve_packaging

        with override_settings(REVIEWS_PACKAGING_RESOLVER="orders.adapter"):
            with patch(
                "apps.reviews.integration.import_string",
                return_value=lambda key, user: "compostable",
            ):
                self.assertEqual(
                    resolve_packaging(self.menu_key, self.author), "compostable"
                )
            with (
                patch(
                    "apps.reviews.integration.import_string",
                    return_value=lambda key, user: "plastic",
                ),
                self.assertRaises(ImproperlyConfigured),
            ):
                resolve_packaging(self.menu_key, self.author)

    def test_filters_keep_summary_and_cover_all_satisfaction_levels(self):
        for rating in range(1, 6):
            Review.objects.create(
                menu_key=self.menu_key,
                author=self.other,
                food_rating=rating,
                packaging_rating=rating,
                text="Bad" if rating < 3 else "Rice" if rating == 3 else "Good",
            )
        expected = {"very_satisfied": 1, "satisfied": 2, "neutral": 1, "unsatisfied": 2}
        for packaging, count in expected.items():
            response = self.client.get(self.url, {"packaging": packaging})
            self.assertEqual(response.context["page"].paginator.count, count)
            self.assertEqual(response.context["summary"]["total"], 6)
        for value, count in {"negative": 2, "neutral": 1, "positive": 3}.items():
            response = self.client.get(self.url, {"sentiment": value})
            self.assertEqual(response.context["page"].paginator.count, count)
        response = self.client.get(
            self.url,
            {"rating": "5", "sentiment": "negative", "packaging": "unsatisfied"},
        )
        self.assertEqual(response.context["page"].paginator.count, 0)
        self.assertEqual(response.context["summary"]["total"], 6)

    def test_csrf_rejects_all_mutations_without_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.author)
        for url in [self.create_url] + [
            reverse(f"reviews:{action}", args=[self.review.pk])
            for action in ["edit", "delete", "helpful"]
        ]:
            self.assertEqual(
                client.post(url, self.payload, **self.ajax).status_code, 403
            )
        self.assertEqual(Review.objects.count(), 2)
        self.assertEqual(HelpfulVote.objects.count(), 0)


class OrdersReviewsIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.customer = User.objects.create_user(email="buyer@example.com")
        cls.other = User.objects.create_user(email="foreign@example.com")
        cls.tenant_user = User.objects.create_user(
            email="seller@example.com", account_type="tenant"
        )
        cls.tenant = Tenant.objects.create(
            owner=cls.tenant_user, name="Kitchen", phone_number="021"
        )
        cls.menu = MenuItem.objects.create(
            name="Bowl", description="Vegetables", price=30000, tenantId=cls.tenant
        )
        # Same name and price are deliberately insufficient to identify a menu.
        cls.other_menu = MenuItem.objects.create(
            name="Bowl", description="Other bowl", price=30000
        )

    def setUp(self):
        self.key = str(self.menu.pk)
        self.create_url = reverse("reviews:create", args=[self.key])
        self.payload = {"food_rating": 4, "packaging_rating": 5, "text": "Fresh"}
        self.ajax = {"HTTP_X_REVIEWS_REQUEST": "true"}
        self.client.force_login(self.customer)

    def make_order(self, *, menu=None, user=None, **fields):
        order = Order.objects.create(
            user=user or self.customer,
            status=fields.pop("status", Order.Status.DELIVERED),
            packaging_type=fields.pop("packaging_type", Order.PackagingType.REUSABLE),
            delivery_address="Private delivery address",
            **fields,
        )
        self.add_item(order, menu or self.menu)
        return order

    def add_item(self, order, menu):
        return OrderItem.objects.create(
            order=order,
            menu_item=menu,
            tenant=menu.tenantId,
            item_name=menu.name,
            price=menu.price,
            quantity=1,
            subtotal=menu.price,
        )

    def selected_url(self, order, menu=None):
        return (
            reverse("reviews:create", args=[str((menu or self.menu).pk)])
            + f"?order={order.pk}"
        )

    def history_review_url(self, order, menu=None):
        from django.utils.html import escape

        return escape(
            reverse("reviews:menu", args=[str((menu or self.menu).pk)])
            + f"?order={order.pk}&write=1"
        )

    def test_order_entry_opens_existing_menu_modal_with_exact_create_url(self):
        order = self.make_order()
        url = reverse("reviews:menu", args=[self.key]) + f"?order={order.pk}&write=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["order"], order)
        self.assertContains(response, 'data-open-create="true"')
        self.assertContains(response, f'data-create-url="{self.selected_url(order)}"')
        self.assertContains(response, 'id="reviews-dialog"')
        self.assertNotContains(response, order.delivery_address)

    def test_order_entry_cannot_expose_foreign_or_ineligible_order(self):
        for order in [
            self.make_order(user=self.other),
            self.make_order(status="cancelled"),
        ]:
            url = (
                reverse("reviews:menu", args=[self.key]) + f"?order={order.pk}&write=1"
            )
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.get(url, **self.ajax).status_code, 404)
        order = self.make_order()
        url = reverse("reviews:menu", args=[self.key]) + f"?order={order.pk}&write=1"
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.tenant_user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_filtering_and_pagination_preserve_order_without_reopening_modal(self):
        order = self.make_order()
        for i in range(6):
            Review.objects.create(
                author=self.customer,
                menu_key=self.key,
                text=f"Meal {i}",
                food_rating=4,
                packaging_rating=5,
            )
        url = reverse("reviews:menu", args=[self.key])
        response = self.client.get(
            url, {"order": str(order.pk), "write": "1", "rating": "4"}
        )
        self.assertIn(f"order={order.pk}", response.context["next_url"])
        self.assertNotIn("write=", response.context["next_url"])
        self.assertEqual(response.context["clear_filters_url"], f"?order={order.pk}")
        self.assertContains(response, f'name="order" value="{order.pk}"')
        for _, clear_url in response.context["active_filters"]:
            self.assertIn(f"order={order.pk}", clear_url)
            self.assertNotIn("write=", clear_url)
        response = self.client.get(url + response.context["next_url"], **self.ajax)
        self.assertEqual(response.context["page"].number, 2)
        self.assertFalse(response.context["open_create"])

    def test_checkout_order_item_relations_supply_packaging_after_delivery(self):
        from apps.map.models import DeliveryAddress
        from apps.orders.models import Cart
        from apps.orders.services import add_item_to_cart, create_order_from_cart

        address = DeliveryAddress.objects.create(
            owner=self.customer,
            label="Home",
            recipient_name="Customer",
            phone_number="0812",
            address="QA address",
            latitude="-6.390000",
            longitude="106.830000",
        )
        cart = Cart.objects.create(user=self.customer)
        add_item_to_cart(cart, self.menu, 2)
        order = create_order_from_cart(self.customer, cart, "compostable", address)
        self.assertEqual(resolve_packaging(self.key, self.customer), "")
        order.status = Order.Status.DELIVERED
        order.save(update_fields=["status"])
        self.assertEqual(
            self.client.post(self.selected_url(order), self.payload).status_code, 302
        )
        self.assertEqual(Review.objects.get().packaging_type, "compostable")

    def test_real_order_packaging_is_saved_for_both_choices(self):
        for packaging in Order.PackagingType.values:
            with self.subTest(packaging=packaging):
                order = self.make_order(packaging_type=packaging)
                response = self.client.post(
                    self.selected_url(order),
                    {
                        **self.payload,
                        "author": self.other.pk,
                        "menu_key": str(self.other_menu.pk),
                        "packaging_type": "plastic",
                    },
                    **self.ajax,
                )
                self.assertEqual(response.status_code, 200)
                review = Review.objects.latest("pk")
                self.assertEqual(review.author, self.customer)
                self.assertEqual(review.menu_key, self.key)
                self.assertEqual(review.packaging_type, packaging)
                self.assertEqual(
                    response.json()["url"], reverse("reviews:menu", args=[self.key])
                )

    def test_all_order_statuses_follow_delivered_history_actions(self):
        for status in Order.Status.values:
            with self.subTest(status=status):
                order = self.make_order(status=status)
                expected = 200 if status == Order.Status.DELIVERED else 404
                url = self.selected_url(order)
                self.assertEqual(self.client.get(url).status_code, expected)
                response = self.client.post(url, self.payload, **self.ajax)
                self.assertEqual(response.status_code, expected)
                history = self.client.get(
                    reverse("orders:order_list"), {"status": status}
                )
                if status == Order.Status.DELIVERED:
                    self.assertContains(history, self.history_review_url(order))
                else:
                    self.assertNotContains(history, "Write a review")
        self.assertEqual(Review.objects.count(), 1)

    def test_no_purchase_remains_allowed_without_packaging_claim(self):
        response = self.client.post(self.create_url, self.payload)
        self.assertRedirects(response, reverse("reviews:menu", args=[self.key]))
        self.assertEqual(Review.objects.get().packaging_type, "")

    def test_unselected_packaging_ignores_non_delivered_orders(self):
        for status in Order.Status.values:
            if status != Order.Status.DELIVERED:
                self.make_order(status=status, packaging_type="compostable")
        self.assertEqual(resolve_packaging(self.key, self.customer), "")
        self.make_order()
        self.assertEqual(resolve_packaging(self.key, self.customer), "reusable")

    def test_another_customer_and_another_menu_never_supply_packaging(self):
        self.make_order(user=self.other)
        self.make_order(menu=self.other_menu)
        self.assertEqual(resolve_packaging(self.key, self.customer), "")
        self.client.post(self.create_url, self.payload, **self.ajax)
        self.assertEqual(Review.objects.get().packaging_type, "")

    def test_foreign_order_rejected_without_disclosing_order_details(self):
        order = self.make_order(user=self.other)
        for method in [self.client.get, self.client.post]:
            data = {} if method == self.client.get else self.payload
            response = method(
                self.selected_url(order),
                **({"data": data} if data else {}),
                **self.ajax,
            )
            self.assertEqual(response.status_code, 404)
            self.assertNotContains(response, order.delivery_address, status_code=404)
            self.assertNotContains(response, order.order_code, status_code=404)
        self.assertFalse(Review.objects.exists())

    def test_order_for_same_named_different_menu_rejected(self):
        order = self.make_order(menu=self.other_menu)
        self.assertEqual(self.client.get(self.selected_url(order)).status_code, 404)
        self.assertEqual(
            self.client.post(self.selected_url(order), self.payload).status_code, 404
        )
        self.assertFalse(Review.objects.exists())

    def test_invalid_or_missing_explicit_order_never_falls_back(self):
        self.make_order()
        for order_id in ["", "bad-id", str(uuid4()), "1", "x" * 101]:
            with self.subTest(order_id=order_id):
                url = f"{self.create_url}?order={order_id}"
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, self.payload).status_code, 404)
        self.assertFalse(Review.objects.exists())

    def test_multiple_delivered_orders_with_same_packaging_are_unambiguous(self):
        order = self.make_order()
        self.make_order()
        # Duplicate lines must not change attribution or DISTINCT semantics.
        self.add_item(order, self.menu)
        with self.assertNumQueries(1):
            self.assertEqual(resolve_packaging(self.key, self.customer), "reusable")

    def test_differing_packaging_requires_explicit_order_without_guessing_latest(self):
        older = self.make_order()
        newer = self.make_order(packaging_type="compostable")
        self.assertEqual(resolve_packaging(self.key, self.customer), "")
        self.client.post(self.create_url, self.payload)
        self.assertEqual(Review.objects.latest("pk").packaging_type, "")
        # Either order can be selected, even when it is not the newest purchase.
        for order in [newer, older]:
            self.client.post(self.selected_url(order), self.payload)
            self.assertEqual(
                Review.objects.latest("pk").packaging_type, order.packaging_type
            )

    def test_multi_menu_order_has_a_link_for_each_exact_menu(self):
        order = self.make_order()
        self.add_item(order, self.other_menu)
        history = self.client.get(reverse("orders:order_list"))
        self.assertContains(history, "Write a review</a>", count=2)
        for menu in [self.menu, self.other_menu]:
            url = self.selected_url(order, menu)
            self.assertContains(
                history, f'href="{self.history_review_url(order, menu)}"', count=1
            )
            form = self.client.get(url)
            self.assertEqual(form.context["menu"].key, str(menu.pk))
            self.assertContains(form, order.order_code)
            self.assertNotContains(form, order.delivery_address)
            self.assertEqual(self.client.post(url, self.payload).status_code, 302)
            self.assertEqual(Review.objects.latest("pk").menu_key, str(menu.pk))

    def test_form_error_and_ajax_keep_order_and_menu_context(self):
        order = self.make_order(packaging_type="compostable")
        url = self.selected_url(order)
        response = self.client.get(url, **self.ajax)
        self.assertEqual(response.context["order"], order)
        self.assertContains(response, "Compostable box")
        response = self.client.post(url, {**self.payload, "text": " "}, **self.ajax)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.context["order"], order)
        self.assertFalse(Review.objects.exists())
        self.assertEqual(
            self.client.post(url, self.payload, **self.ajax).status_code, 200
        )
        self.assertEqual(Review.objects.get().packaging_type, "compostable")

    def test_recheck_order_at_submit_after_status_or_ownership_changes(self):
        order = self.make_order()
        url = self.selected_url(order)
        self.assertEqual(self.client.get(url).status_code, 200)
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status"])
        self.assertEqual(self.client.post(url, self.payload).status_code, 404)
        order.status, order.user = Order.Status.DELIVERED, self.other
        order.save(update_fields=["status", "user"])
        self.assertEqual(self.client.post(url, self.payload).status_code, 404)
        self.assertFalse(Review.objects.exists())

    def test_posted_order_id_cannot_override_url_order(self):
        owned = self.make_order()
        foreign = self.make_order(user=self.other, packaging_type="compostable")
        self.client.post(
            self.selected_url(owned),
            {**self.payload, "order": foreign.pk, "order_id": foreign.pk},
        )
        self.assertEqual(Review.objects.get().packaging_type, "reusable")

    def test_snapshot_survives_order_changes_deletion_and_review_edit(self):
        order = self.make_order()
        self.client.post(self.selected_url(order), self.payload)
        review = Review.objects.get()
        self.make_order(packaging_type="compostable")
        order.delete()
        response = self.client.post(
            reverse("reviews:edit", args=[review.pk]),
            {**self.payload, "packaging_type": "compostable", "text": "Updated"},
        )
        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.assertEqual(review.packaging_type, "reusable")
        self.assertEqual(review.text, "Updated")

    def test_deleted_menu_is_not_replaced_by_same_named_menu(self):
        order = self.make_order()
        url = self.selected_url(order)
        self.client.post(url, self.payload)
        review = Review.objects.get()
        self.menu.delete()
        self.assertIsNone(order.items.get().menu_item_id)
        self.assertNotContains(
            self.client.get(reverse("orders:order_list")), "Write a review"
        )
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.payload).status_code, 404)
        self.assertEqual(resolve_packaging(str(self.other_menu.pk), self.customer), "")
        self.assertTrue(Review.objects.filter(pk=review.pk).exists())
        self.assertEqual(
            self.client.post(reverse("reviews:delete", args=[review.pk])).status_code,
            302,
        )

    def test_partly_deleted_order_only_links_remaining_menu(self):
        order = self.make_order()
        self.add_item(order, self.other_menu)
        self.menu.delete()
        history = self.client.get(reverse("orders:order_list"))
        self.assertContains(history, "Write a review</a>", count=1)
        self.assertContains(history, self.history_review_url(order, self.other_menu))

    def test_guest_and_tenant_cannot_claim_packaging_or_write_from_order(self):
        from django.contrib.auth.models import AnonymousUser

        order = self.make_order()
        for user in [AnonymousUser(), self.tenant_user]:
            with self.assertNumQueries(0):
                self.assertEqual(resolve_packaging(self.key, user), "")
        self.client.logout()
        response = self.client.get(self.selected_url(order))
        self.assertEqual(response.status_code, 302)
        self.assertIn("order%3D", response.url)
        self.assertEqual(
            self.client.post(
                self.selected_url(order), self.payload, **self.ajax
            ).status_code,
            401,
        )
        self.client.force_login(self.tenant_user)
        self.assertEqual(self.client.get(self.selected_url(order)).status_code, 403)
        self.assertEqual(
            self.client.post(self.selected_url(order), self.payload).status_code, 403
        )
        self.assertFalse(Review.objects.exists())

    def test_adapter_rejects_invalid_packaging_in_order_data(self):
        order = self.make_order(packaging_type="plastic")
        with self.assertRaises(ImproperlyConfigured):
            resolve_packaging(self.key, self.customer, order_id=str(order.pk))
        self.assertFalse(Review.objects.exists())

    def test_container_return_does_not_change_original_packaging(self):
        order = self.make_order(reusable_returned=True)
        self.assertEqual(
            resolve_packaging(self.key, self.customer, order_id=str(order.pk)),
            "reusable",
        )

    def test_history_and_ajax_cards_never_show_another_customers_links(self):
        from django.test import RequestFactory

        from apps.orders.views import _order_card_html

        owned = self.make_order()
        foreign = self.make_order(user=self.other)
        history = self.client.get(reverse("orders:order_list"))
        self.assertContains(history, self.history_review_url(owned))
        self.assertNotContains(history, str(foreign.pk))
        request = RequestFactory().get("/orders/")
        request.user = self.customer
        request.session = {}
        html = _order_card_html(request, owned)
        self.assertIn(self.history_review_url(owned), html)
        owned.status = Order.Status.CANCELLED
        self.assertNotIn("Write a review", _order_card_html(request, owned))
