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

from .forms import ReviewForm
from .integration import MenuContext, resolve_menu
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
