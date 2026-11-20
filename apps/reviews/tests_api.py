from io import BytesIO
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from PIL import Image
from rest_framework.authtoken.models import Token

from apps.accounts.models import Tenant
from apps.catalog.models import MenuItem
from apps.orders.models import Order, OrderItem

from .models import HelpfulVote, Review
from .serializers import MAX_PHOTO_SIZE


def image_upload(name="bowl.png", image_format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", (16, 16), "green").save(buffer, format=image_format)
    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        content_type=f"image/{image_format.lower()}",
    )


class ReviewsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.customer = User.objects.create_user(
            email="api-customer@example.com",
            password="test-password",
            first_name="API Customer",
        )
        cls.other_customer = User.objects.create_user(
            email="api-other@example.com",
            password="test-password",
            first_name="Other Customer",
        )
        cls.tenant_user = User.objects.create_user(
            email="api-tenant@example.com",
            password="test-password",
            account_type="tenant",
        )
        cls.tenant = Tenant.objects.create(
            owner=cls.tenant_user,
            name="API Kitchen",
            phone_number="021123456",
        )
        cls.menu = MenuItem.objects.create(
            tenantId=cls.tenant,
            name="Tempeh Bowl",
            description="Fresh tempeh and vegetables",
            price=30000,
        )
        cls.other_menu = MenuItem.objects.create(
            name="Rice Bowl",
            description="Rice and greens",
            price=20000,
        )
        cls.customer_token = Token.objects.create(user=cls.customer)
        cls.other_token = Token.objects.create(user=cls.other_customer)
        cls.tenant_token = Token.objects.create(user=cls.tenant_user)

    def setUp(self):
        self.media = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media.cleanup)

        self.client = APIClient()
        self.menu_uuid = str(self.menu.pk)
        self.list_url = reverse("reviews_api:menu-reviews", args=[self.menu_uuid])
        self.payload = {
            "food_rating": 4,
            "packaging_rating": 5,
            "text": "Fresh and delicious",
        }

    def authenticate(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def create_review(self, **changes):
        response = self.client.post(self.list_url, {**self.payload, **changes})
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def make_order(self, *, user=None, menu=None, status=Order.Status.DELIVERED, packaging="compostable"):
        order = Order.objects.create(
            user=user or self.customer,
            status=status,
            packaging_type=packaging,
            delivery_address="Private address",
        )
        menu = menu or self.menu
        OrderItem.objects.create(
            order=order,
            menu_item=menu,
            tenant=menu.tenantId,
            item_name=menu.name,
            price=menu.price,
            quantity=1,
            subtotal=menu.price,
        )
        return order

    def test_guest_can_read_list_and_detail_but_mutations_require_token(self):
        review = Review.objects.create(
            menu_key=self.menu_uuid,
            author=self.customer,
            food_rating=5,
            packaging_rating=4,
            text="Fresh",
        )
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pagination"]["count"], 1)
        self.assertEqual(response.data["results"][0]["author"]["display_name"], "API Customer")
        self.assertNotIn("email", response.data["results"][0]["author"])
        self.assertEqual(
            self.client.get(reverse("reviews_api:review-detail", args=[review.pk])).status_code,
            200,
        )
        self.assertEqual(self.client.post(self.list_url, self.payload).status_code, 401)
        self.assertEqual(
            self.client.post(
                reverse("reviews_api:review-helpful", args=[review.pk])
            ).status_code,
            401,
        )

    def test_token_authentication_and_customer_tenant_permissions(self):
        self.authenticate(self.tenant_token)
        self.assertEqual(self.client.post(self.list_url, self.payload).status_code, 403)

        self.authenticate(self.customer_token)
        created = self.create_review()
        detail_url = reverse("reviews_api:review-detail", args=[created["id"]])
        self.authenticate(self.tenant_token)
        self.assertEqual(
            self.client.patch(detail_url, {"text": "Tenant edit"}).status_code,
            403,
        )
        self.assertEqual(self.client.get(detail_url).status_code, 200)

        self.client.credentials(HTTP_AUTHORIZATION="Token invalid-token")
        self.assertEqual(self.client.get(self.list_url).status_code, 401)

    def test_create_detail_patch_and_delete_enforce_ownership(self):
        self.authenticate(self.customer_token)
        created = self.create_review(
            author=self.other_customer.pk,
            menu_key=str(self.other_menu.pk),
            packaging_type="reusable",
        )
        self.assertEqual(created["menu_uuid"], self.menu_uuid)
        self.assertEqual(created["author"]["id"], self.customer.pk)
        self.assertEqual(created["packaging_type"], "")

        detail_url = reverse("reviews_api:review-detail", args=[created["id"]])
        self.authenticate(self.other_token)
        self.assertEqual(
            self.client.patch(detail_url, {"text": "Changed by another user"}).status_code,
            404,
        )
        self.assertEqual(self.client.delete(detail_url).status_code, 404)

        self.authenticate(self.customer_token)
        updated = self.client.patch(
            detail_url,
            {"food_rating": 3, "text": "Updated by owner"},
            format="multipart",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["food_rating"], 3)
        self.assertEqual(updated.data["text"], "Updated by owner")
        self.assertEqual(updated.data["menu_uuid"], self.menu_uuid)
        self.assertEqual(self.client.delete(detail_url).status_code, 204)
        self.assertFalse(Review.objects.filter(pk=created["id"]).exists())

    def test_owner_can_delete_orphaned_review_but_other_users_cannot(self):
        self.authenticate(self.customer_token)
        created = self.create_review()
        review = Review.objects.get(pk=created["id"])
        detail_url = reverse("reviews_api:review-detail", args=[review.pk])
        helpful_url = reverse("reviews_api:review-helpful", args=[review.pk])

        self.menu.delete()

        self.assertEqual(self.client.get(detail_url).status_code, 404)
        self.assertEqual(
            self.client.patch(detail_url, {"text": "Update orphan"}).status_code,
            404,
        )
        self.assertEqual(self.client.post(helpful_url).status_code, 404)

        self.authenticate(self.other_token)
        self.assertEqual(self.client.delete(detail_url).status_code, 404)
        self.assertTrue(Review.objects.filter(pk=review.pk).exists())

        self.authenticate(self.customer_token)
        self.assertEqual(self.client.delete(detail_url).status_code, 204)
        self.assertFalse(Review.objects.filter(pk=review.pk).exists())

    def test_invalid_identifiers_and_missing_resources_return_json_404(self):
        responses = [
            self.client.get("/api/v1/reviews/menus/not-a-uuid/"),
            self.client.get(f"/api/v1/reviews/menus/{uuid4()}/"),
            self.client.get("/api/v1/reviews/not-an-id/"),
            self.client.get("/api/v1/reviews/999999999/"),
        ]
        for response in responses:
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response["Content-Type"], "application/json")

        self.authenticate(self.customer_token)
        helpful_response = self.client.post(
            "/api/v1/reviews/not-an-id/helpful/"
        )
        self.assertEqual(helpful_response.status_code, 404)
        self.assertEqual(helpful_response["Content-Type"], "application/json")

    def test_rating_text_and_patch_validation(self):
        self.authenticate(self.customer_token)
        invalid_payloads = [
            {"food_rating": 0},
            {"food_rating": 6},
            {"food_rating": "invalid"},
            {"packaging_rating": 0},
            {"packaging_rating": 6},
            {"text": " "},
            {"text": "x" * 501},
        ]
        for changes in invalid_payloads:
            with self.subTest(changes=changes):
                response = self.client.post(self.list_url, {**self.payload, **changes})
                self.assertEqual(response.status_code, 400)
        created = self.create_review()
        detail_url = reverse("reviews_api:review-detail", args=[created["id"]])
        self.assertEqual(
            self.client.patch(detail_url, {"order_id": "00000000-0000-0000-0000-000000000000"}).status_code,
            400,
        )
        self.assertEqual(self.client.patch(detail_url, {}).status_code, 400)

    def test_multipart_photo_validation_and_photo_removal(self):
        self.authenticate(self.customer_token)
        valid = self.client.post(
            self.list_url,
            {**self.payload, "photo": image_upload()},
            format="multipart",
        )
        self.assertEqual(valid.status_code, 201, valid.data)
        self.assertTrue(valid.data["photo_url"].endswith(".png"))

        jpeg = self.client.post(
            self.list_url,
            {**self.payload, "photo": image_upload("bowl.jpg", "JPEG")},
            format="multipart",
        )
        self.assertEqual(jpeg.status_code, 201, jpeg.data)
        self.assertTrue(jpeg.data["photo_url"].endswith(".jpg"))
        detail_url = reverse("reviews_api:review-detail", args=[valid.data["id"]])

        invalid_fake = SimpleUploadedFile(
            "fake.png", b"not an image", content_type="image/png"
        )
        self.assertEqual(
            self.client.post(
                self.list_url,
                {**self.payload, "photo": invalid_fake},
                format="multipart",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.list_url,
                {**self.payload, "photo": image_upload("animated.gif", "GIF")},
                format="multipart",
            ).status_code,
            400,
        )
        large_buffer = BytesIO()
        Image.new("RGB", (1400, 1400), "green").save(
            large_buffer,
            format="PNG",
            compress_level=0,
        )
        large = SimpleUploadedFile(
            "large.png",
            large_buffer.getvalue(),
            content_type="image/png",
        )
        self.assertGreater(large.size, MAX_PHOTO_SIZE)
        self.assertEqual(
            self.client.post(
                self.list_url,
                {**self.payload, "photo": large},
                format="multipart",
            ).status_code,
            400,
        )

        with self.captureOnCommitCallbacks(execute=True):
            removed = self.client.patch(
                detail_url,
                {"remove_photo": "true"},
                format="multipart",
            )
        self.assertEqual(removed.status_code, 200, removed.data)
        self.assertIsNone(removed.data["photo_url"])

    def test_filter_sort_summary_and_four_item_pagination(self):
        first = Review.objects.create(
            menu_key=self.menu_uuid,
            author=self.customer,
            food_rating=5,
            packaging_rating=4,
            text="Fresh and delicious",
        )
        HelpfulVote.objects.create(review=first, user=self.other_customer)
        for index in range(6):
            Review.objects.create(
                menu_key=self.menu_uuid,
                author=self.other_customer,
                food_rating=2 if index else 5,
                packaging_rating=1 if index else 4,
                text="Bad and cold" if index else "Great and fresh",
            )

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 4)
        self.assertEqual(response.data["pagination"]["count"], 7)
        self.assertEqual(response.data["pagination"]["next"], 2)
        self.assertEqual(response.data["summary"]["total"], 7)
        self.assertEqual(
            self.client.get(self.list_url, {"page": 2}).data["pagination"]["page"],
            2,
        )
        filtered = self.client.get(
            self.list_url,
            {"rating": "5", "sentiment": "positive", "packaging": "satisfied"},
        )
        self.assertEqual(filtered.data["pagination"]["count"], 2)
        self.assertEqual(
            self.client.get(self.list_url, {"sort": "oldest"}).data["results"][0]["id"],
            first.pk,
        )
        self.assertEqual(
            self.client.get(self.list_url, {"sort": "highest"}).data["results"][0]["food_rating"],
            5,
        )
        self.assertEqual(
            self.client.get(self.list_url, {"sort": "helpful"}).data["results"][0]["id"],
            first.pk,
        )
        self.assertEqual(
            self.client.get(self.list_url, {"sentiment": "unknown"}).status_code,
            400,
        )

    def test_helpful_vote_toggles_for_authenticated_users(self):
        review = Review.objects.create(
            menu_key=self.menu_uuid,
            author=self.customer,
            food_rating=5,
            packaging_rating=4,
            text="Fresh",
        )
        helpful_url = reverse("reviews_api:review-helpful", args=[review.pk])
        self.authenticate(self.other_token)
        first = self.client.post(helpful_url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data, {"review_id": review.pk, "selected": True, "helpful_count": 1})
        second = self.client.post(helpful_url)
        self.assertEqual(second.data["selected"], False)
        self.assertEqual(second.data["helpful_count"], 0)
        self.assertFalse(HelpfulVote.objects.exists())

    def test_order_resolver_sets_immutable_packaging_snapshot(self):
        order = self.make_order(packaging="compostable")
        self.authenticate(self.customer_token)
        created = self.create_review(order_id=str(order.pk))
        self.assertEqual(created["packaging_type"], "compostable")

        order.packaging_type = Order.PackagingType.REUSABLE
        order.save(update_fields=["packaging_type"])
        detail_url = reverse("reviews_api:review-detail", args=[created["id"]])
        updated = self.client.patch(detail_url, {"text": "Packaging snapshot stays"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["packaging_type"], "compostable")

    def test_explicit_order_must_be_delivered_owned_and_contain_menu(self):
        foreign = self.make_order(user=self.other_customer)
        pending = self.make_order(status=Order.Status.PENDING)
        other_menu_order = self.make_order(menu=self.other_menu)
        self.authenticate(self.customer_token)
        for order in (foreign, pending, other_menu_order):
            with self.subTest(order=order.pk):
                response = self.client.post(
                    self.list_url,
                    {**self.payload, "order_id": str(order.pk)},
                )
                self.assertEqual(response.status_code, 404)
        self.assertFalse(Review.objects.exists())
