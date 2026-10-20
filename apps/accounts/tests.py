import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import (
    CustomUser,
    DietPreference,
    EcoPointActivity,
    UserAllergy,
)
from .selectors import get_admin_insights_data
from .services import record_eco_points


class AccountViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for code, label in [("vegan", "Vegan"), ("keto", "Keto")]:
            DietPreference.objects.get_or_create(code=code, defaults={"label": label})

    def create_user(self, email="user@example.com"):
        return CustomUser.objects.create_user(
            email=email, password="strong-password-123"
        )

    def test_registration_creates_profile_and_logs_in(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "User Test",
                "email": "test@example.com",
                "password1": "strong-password-123",
                "password2": "strong-password-123",
            },
        )
        user = CustomUser.objects.get(email="test@example.com")
        self.assertRedirects(response, reverse("accounts:accounts"))
        self.assertEqual(user.first_name, "User Test")
        self.assertTrue(hasattr(user, "userprofile"))

    def test_account_requires_authentication(self):
        response = self.client.get(reverse("accounts:accounts"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:accounts')}",
        )

    def test_account_page_renders_for_authenticated_user(self):
        self.client.force_login(self.create_user())
        response = self.client.get(reverse("accounts:accounts"))
        self.assertContains(response, "Preferensi Diet")

    def test_logout_requires_post_and_ends_session(self):
        user = self.create_user()
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("landing:landing"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_invalid_profile_update_keeps_field_errors(self):
        user = self.create_user()
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:update_profile"),
            {
                "full_name": "User Test",
                "email": "",
                "birth_date": "",
                "phone_number": "",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "This field is required.", status_code=400)

    def test_profile_update_uses_partial_response_for_htmx(self):
        user = self.create_user()
        user.first_name = "Nama Lama"
        user.save(update_fields=["first_name"])
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:update_profile"),
            {
                "full_name": "Nama Baru",
                "email": "new@example.com",
                "birth_date": "2004-05-19",
                "phone_number": "081212345678",
            },
            HTTP_HX_REQUEST="true",
        )
        user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.headers["HX-Trigger"]),
            {"showToast": {"message": "Perubahan tersimpan.", "level": "success"}},
        )
        self.assertEqual(user.first_name, "Nama Baru")
        self.assertEqual(user.email, "new@example.com")
        self.assertContains(response, 'value="Nama Baru"')
        self.assertContains(response, 'value="new@example.com"')
        self.assertNotContains(response, 'value="Nama Lama"')
        self.assertContains(
            response, 'id="account-profile-name" hx-swap-oob="innerHTML"'
        )
        self.assertContains(
            response, 'id="header-profile-name-desktop" hx-swap-oob="innerHTML"'
        )
        self.assertContains(
            response, 'id="header-profile-name-mobile" hx-swap-oob="innerHTML"'
        )

    def test_invalid_htmx_profile_update_preserves_input_without_name_swaps(self):
        user = self.create_user()
        user.first_name = "Nama Lama"
        user.save(update_fields=["first_name"])
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:update_profile"),
            {
                "full_name": "Nama Belum Valid",
                "email": "",
                "birth_date": "",
                "phone_number": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Nama Belum Valid"')
        self.assertContains(response, "This field is required.")
        self.assertNotContains(response, "hx-swap-oob")

    def test_user_can_toggle_only_own_diet(self):
        user = self.create_user()
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:toggle_diet"), {"diet": "vegan"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(user.userprofile.diets.filter(code="vegan").exists())
        self.client.post(
            reverse("accounts:toggle_diet"), {"diet": "vegan"}, HTTP_HX_REQUEST="true"
        )
        self.assertFalse(user.userprofile.diets.filter(code="vegan").exists())

    def test_user_can_add_and_delete_own_allergy_with_activity_history(self):
        user = self.create_user()
        self.client.force_login(user)
        self.client.post(
            reverse("accounts:manage_allergy"),
            {"name": "Kacang"},
            HTTP_HX_REQUEST="true",
        )
        allergy = UserAllergy.objects.get(profile=user.userprofile, name="Kacang")
        response = self.client.post(
            reverse("accounts:manage_allergy"),
            {"delete": allergy.pk},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserAllergy.objects.filter(pk=allergy.pk).exists())
        self.assertEqual(user.userprofile.diet_activities.count(), 2)

    def test_reset_only_removes_current_users_points(self):
        user = self.create_user()
        other = self.create_user("other@example.com")
        EcoPointActivity.objects.create(
            profile=user.userprofile,
            points=50,
            activity_type="order",
            description="Test",
        )
        EcoPointActivity.objects.create(
            profile=other.userprofile,
            points=25,
            activity_type="order",
            description="Other",
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:reset_eco_points"), {"confirm": "on"}
        )
        self.assertRedirects(response, reverse("accounts:accounts"))
        self.assertEqual(user.userprofile.point_activities.count(), 0)
        self.assertEqual(other.userprofile.point_activities.count(), 1)

    def test_record_eco_points_updates_profile_aggregates(self):
        user = self.create_user()
        record_eco_points(
            profile=user.userprofile,
            points=30,
            activity_type=EcoPointActivity.ActivityType.PACKAGING,
            description="Memilih kemasan reusable.",
            co2_saved="1.25",
        )
        self.assertEqual(user.userprofile.eco_points, 30)
        self.assertEqual(str(user.userprofile.co2_saved), "1.25")

    def test_recommendations_api_requires_authentication(self):
        response = self.client.get(reverse("accounts:recommendations_api"))
        self.assertEqual(response.status_code, 302)

    def test_recommendations_api_returns_safe_empty_state_without_catalog(self):
        self.client.force_login(self.create_user())
        response = self.client.get(reverse("accounts:recommendations_api"))
        self.assertJSONEqual(response.content, {"recommendations": []})

    def test_login_rejects_external_next_url(self):
        user = self.create_user()
        response = self.client.post(
            reverse("accounts:login"),
            {
                "email": user.email,
                "password": "strong-password-123",
                "next": "https://example.invalid/",
            },
        )
        self.assertRedirects(response, reverse("accounts:accounts"))

    def test_upload_photo_rejects_non_image_file(self):
        self.client.force_login(self.create_user())
        response = self.client.post(
            reverse("accounts:upload_photo"),
            {
                "photo": SimpleUploadedFile(
                    "not-an-image.jpg", b"not an image", content_type="image/jpeg"
                ),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_admin_insights_api_requires_authentication(self):
        response = self.client.get(reverse("accounts:admin_insights_api"))
        self.assertEqual(response.status_code, 401)

    def test_admin_insights_api_rejects_regular_user(self):
        self.client.force_login(self.create_user())
        response = self.client.get(reverse("accounts:admin_insights_api"))
        self.assertEqual(response.status_code, 403)

    def test_admin_insights_api_returns_expected_payload_for_staff(self):
        staff = CustomUser.objects.create_superuser(
            email="staff@example.com", password="strong-password-123"
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("accounts:admin_insights_api"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["total_users"], 1)
        self.assertEqual(response.json()["recent_users"][0]["email"], staff.email)

    def test_admin_insights_selector_returns_diet_distribution(self):
        user = self.create_user()
        user.userprofile.diets.add(DietPreference.objects.get(code="vegan"))
        payload = get_admin_insights_data()
        vegan = next(
            item for item in payload["diet_distribution"] if item["code"] == "vegan"
        )
        self.assertEqual(vegan["user_count"], 1)
