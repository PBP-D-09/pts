import json
from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.catalog.models import MenuItem

from .models import (
    CustomUser,
    DietPreference,
    EcoPointActivity,
    Tenant,
    UserAllergy,
)
from .selectors import get_admin_insights_data
from .services import record_eco_points, register_tenant


class AccountViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for code, label in DietPreference.Code.choices:
            DietPreference.objects.get_or_create(code=code, defaults={"label": label})

    def create_user(self, email="user@example.com"):
        return CustomUser.objects.create_user(
            email=email, password="strong-password-123"
        )

    def create_tenant(self, email="tenant@example.com"):
        return register_tenant(
            tenant_name="Dapur Hijau",
            full_name="Pengelola Tenan",
            email=email,
            phone_number="081234567890",
            password="strong-password-123",
        )

    def create_menu(
        self,
        *,
        tenant=None,
        name="Nasi Sayur",
        allergen_info="Tidak mengandung kacang",
        vegetarian=False,
        price=25_000,
    ):
        tenant = tenant or self.create_tenant().tenant
        return MenuItem.objects.create(
            tenantId=tenant,
            name=name,
            description=f"Deskripsi {name}",
            allergen_info=allergen_info,
            vegetarian=vegetarian,
            price=price,
        )

    def test_user_manager_rejects_invalid_user_and_superuser_data(self):
        with self.assertRaisesMessage(ValueError, "Email wajib diisi."):
            CustomUser.objects.create_user(email="", password="password")
        with self.assertRaisesMessage(
            ValueError, "Superuser harus memiliki is_staff=True."
        ):
            CustomUser.objects.create_superuser(
                email="staff-false@example.com",
                password="password",
                is_staff=False,
            )
        with self.assertRaisesMessage(
            ValueError, "Superuser harus memiliki is_superuser=True."
        ):
            CustomUser.objects.create_superuser(
                email="superuser-false@example.com",
                password="password",
                is_superuser=False,
            )

    def test_tenant_display_name_falls_back_without_tenant_profile(self):
        user = CustomUser.objects.create_user(
            email="orphan-tenant@example.com",
            password="password",
            first_name="Nama Pengelola",
            account_type=CustomUser.AccountType.TENANT,
        )

        self.assertEqual(user.display_name, "Nama Pengelola")

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
        self.assertEqual(user.account_type, CustomUser.AccountType.CUSTOMER)
        self.assertTrue(hasattr(user, "userprofile"))
        self.assertFalse(hasattr(user, "tenant"))

    def test_tenant_registration_creates_tenant_and_logs_in(self):
        response = self.client.post(
            reverse("accounts:register_tenant"),
            {
                "tenant_name": "Warung Lestari",
                "full_name": "Pemilik Warung",
                "email": "owner@example.com",
                "phone_number": "081298765432",
                "password1": "strong-password-123",
                "password2": "strong-password-123",
            },
        )

        user = CustomUser.objects.get(email="owner@example.com")
        self.assertRedirects(response, reverse("accounts:accounts"))
        self.assertEqual(user.account_type, CustomUser.AccountType.TENANT)
        self.assertEqual(user.first_name, "Pemilik Warung")
        self.assertEqual(user.tenant.name, "Warung Lestari")
        self.assertEqual(user.tenant.phone_number, "081298765432")
        self.assertFalse(hasattr(user, "userprofile"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_tenant_registration_rejects_existing_email_without_partial_data(self):
        self.create_user("used@example.com")

        response = self.client.post(
            reverse("accounts:register_tenant"),
            {
                "tenant_name": "Warung Lestari",
                "full_name": "Pemilik Warung",
                "email": "USED@EXAMPLE.COM",
                "phone_number": "081298765432",
                "password1": "strong-password-123",
                "password2": "strong-password-123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email ini sudah digunakan.")
        self.assertEqual(CustomUser.objects.count(), 1)
        self.assertEqual(Tenant.objects.count(), 0)

    def test_customer_registration_rejects_existing_email(self):
        self.create_user("used-customer@example.com")

        response = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "User Test",
                "email": "USED-CUSTOMER@EXAMPLE.COM",
                "password1": "strong-password-123",
                "password2": "strong-password-123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email ini sudah digunakan.")
        self.assertEqual(CustomUser.objects.count(), 1)

    def test_authenticated_user_is_redirected_from_registration_pages(self):
        self.client.force_login(self.create_user())

        for url_name in ("accounts:register", "accounts:register_tenant"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(response, reverse("accounts:accounts"))

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
        self.assertContains(response, "Eco Points")
        self.assertNotContains(response, "Aktivitas Diet")
        self.assertNotContains(response, "Riwayat Eco Points")
        self.assertNotContains(response, "JSON API")
        self.assertNotContains(response, 'id="reset-points"')
        self.assertNotContains(response, ">Reset<")

    def test_removed_eco_point_history_endpoint_returns_not_found(self):
        self.client.force_login(self.create_user())

        response = self.client.get("/accounts/eco-points/history/")

        self.assertEqual(response.status_code, 404)

    def test_account_page_adapts_for_tenant(self):
        user = self.create_tenant()
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:accounts"))

        self.assertContains(response, "Akun Tenan")
        self.assertContains(response, "Dapur Hijau")
        self.assertContains(response, 'value="Pengelola Tenan"')
        self.assertContains(response, 'id="tenant-photo-icon"')
        self.assertNotContains(response, "Preferensi Diet")
        self.assertNotContains(response, "Eco Points")

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

    def test_tenant_profile_update_uses_partial_response_for_htmx(self):
        user = self.create_tenant()
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:update_tenant"),
            {
                "name": "Dapur Bumi",
                "full_name": "Pengelola Baru",
                "email": "new-tenant@example.com",
                "phone_number": "089876543210",
            },
            HTTP_HX_REQUEST="true",
        )

        user.refresh_from_db()
        user.tenant.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.first_name, "Pengelola Baru")
        self.assertEqual(user.email, "new-tenant@example.com")
        self.assertEqual(user.tenant.name, "Dapur Bumi")
        self.assertEqual(user.tenant.phone_number, "089876543210")
        self.assertEqual(
            json.loads(response.headers["HX-Trigger"]),
            {"showToast": {"message": "Perubahan tersimpan.", "level": "success"}},
        )
        self.assertContains(response, 'value="Dapur Bumi"')
        self.assertContains(
            response, 'id="tenant-account-name" hx-swap-oob="innerHTML"'
        )
        self.assertContains(
            response, 'id="header-profile-name-desktop" hx-swap-oob="innerHTML"'
        )

    def test_invalid_tenant_update_preserves_input(self):
        user = self.create_tenant()
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:update_tenant"),
            {
                "name": "Nama Belum Valid",
                "full_name": "Pengelola",
                "email": "",
                "phone_number": "081234567890",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Nama Belum Valid"')
        self.assertContains(response, "This field is required.")
        self.assertNotContains(response, "hx-swap-oob")

    def test_account_type_guards_customer_and_tenant_endpoints(self):
        tenant_user = self.create_tenant()
        self.client.force_login(tenant_user)
        customer_endpoints = (
            ("post", "accounts:update_profile"),
            ("post", "accounts:upload_photo"),
            ("post", "accounts:toggle_diet"),
            ("post", "accounts:manage_allergy"),
            ("post", "accounts:reset_eco_points"),
            ("get", "accounts:recommendations_api"),
        )
        for method, url_name in customer_endpoints:
            with self.subTest(url_name=url_name):
                response = getattr(self.client, method)(reverse(url_name))
                self.assertEqual(response.status_code, 403)

        customer_user = self.create_user("customer@example.com")
        self.client.force_login(customer_user)
        for url_name in ("accounts:update_tenant", "accounts:upload_tenant_photo"):
            with self.subTest(url_name=url_name):
                tenant_response = self.client.post(reverse(url_name))
                self.assertEqual(tenant_response.status_code, 403)

    def test_deleting_tenant_owner_cascades_tenant(self):
        user = self.create_tenant()
        tenant_id = user.tenant.pk

        user.delete()

        self.assertFalse(Tenant.objects.filter(pk=tenant_id).exists())

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

    def test_unknown_diet_returns_not_found(self):
        self.client.force_login(self.create_user())

        response = self.client.post(
            reverse("accounts:toggle_diet"),
            {"diet": "not-a-diet"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 404)

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

    def test_empty_and_duplicate_allergy_do_not_create_extra_records(self):
        user = self.create_user()
        self.client.force_login(user)

        for name in ("Kacang", " kacang ", "   "):
            self.client.post(
                reverse("accounts:manage_allergy"),
                {"name": name},
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(user.userprofile.allergies.count(), 1)
        self.assertEqual(user.userprofile.diet_activities.count(), 1)

    def test_allergy_delete_rejects_malformed_and_out_of_range_ids(self):
        self.client.force_login(self.create_user())

        for allergy_id in ("not-a-number", str(2**100)):
            with self.subTest(allergy_id=allergy_id):
                response = self.client.post(
                    reverse("accounts:manage_allergy"),
                    {"delete": allergy_id},
                    HTTP_HX_REQUEST="true",
                )

                self.assertEqual(response.status_code, 404)

    def test_user_cannot_delete_another_users_allergy(self):
        user = self.create_user()
        other = self.create_user("other@example.com")
        allergy = UserAllergy.objects.create(
            profile=other.userprofile,
            name="Susu",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:manage_allergy"),
            {"delete": allergy.pk},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(UserAllergy.objects.filter(pk=allergy.pk).exists())

    def test_reset_starts_new_statistics_without_deleting_history(self):
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
        user.userprofile.refresh_from_db()
        self.assertEqual(user.userprofile.point_activities.count(), 2)
        self.assertEqual(user.userprofile.eco_points, 0)
        self.assertEqual(user.userprofile.co2_saved, 0)
        self.assertTrue(
            user.userprofile.point_activities.filter(
                activity_type=EcoPointActivity.ActivityType.ADJUSTMENT,
                description="Statistik Eco Points direset.",
                points=0,
            ).exists()
        )
        self.assertEqual(other.userprofile.point_activities.count(), 1)

        record_eco_points(
            profile=user.userprofile,
            points=10,
            activity_type=EcoPointActivity.ActivityType.PACKAGING,
            description="Aktivitas baru",
            co2_saved="0.50",
        )
        self.assertEqual(user.userprofile.eco_points, 10)
        self.assertEqual(str(user.userprofile.co2_saved), "0.5")

    def test_reset_requires_confirmation(self):
        user = self.create_user()
        record_eco_points(
            profile=user.userprofile,
            points=20,
            activity_type=EcoPointActivity.ActivityType.ORDER,
            description="Pesanan",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("accounts:reset_eco_points"))

        self.assertRedirects(response, reverse("accounts:accounts"))
        user.userprofile.refresh_from_db()
        self.assertIsNone(user.userprofile.eco_points_reset_at)
        self.assertEqual(user.userprofile.eco_points, 20)

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

    def test_recommendations_api_returns_safe_empty_state_without_menu(self):
        self.client.force_login(self.create_user())
        response = self.client.get(reverse("accounts:recommendations_api"))
        self.assertJSONEqual(
            response.content, {"recommendations": [], "unsupported_diets": []}
        )

    def test_recommendations_use_real_catalog_fields_and_tenant_link(self):
        user = self.create_user()
        menu = self.create_menu(vegetarian=True, allergen_info="Susu")
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:recommendations_api"))

        recommendation = response.json()["recommendations"][0]
        self.assertEqual(recommendation["id"], str(menu.pk))
        self.assertEqual(recommendation["name"], menu.name)
        self.assertEqual(recommendation["price"], 25_000)
        self.assertTrue(recommendation["vegetarian"])
        self.assertEqual(recommendation["allergen_info"], "Susu")
        self.assertEqual(recommendation["tenant_name"], "Dapur Hijau")
        self.assertEqual(
            recommendation["tenant_url"],
            reverse("catalog:show_catalog_tenant", args=[menu.tenantId_id]),
        )
        self.assertNotIn("eco_points", recommendation)

    def test_vegetarian_recommendation_excludes_non_vegetarian_menu(self):
        user = self.create_user()
        user.userprofile.diets.add(
            DietPreference.objects.get(code=DietPreference.Code.VEGETARIAN)
        )
        vegetarian = self.create_menu(name="Gado-gado", vegetarian=True)
        self.create_menu(
            tenant=vegetarian.tenantId,
            name="Ayam Bakar",
            vegetarian=False,
        )
        self.client.force_login(user)

        names = [
            item["name"]
            for item in self.client.get(reverse("accounts:recommendations_api")).json()[
                "recommendations"
            ]
        ]

        self.assertEqual(names, ["Gado-gado"])

    def test_unsupported_diet_returns_no_recommendations_instead_of_guessing(self):
        user = self.create_user()
        user.userprofile.diets.add(DietPreference.objects.get(code="vegan"))
        self.create_menu(vegetarian=True)
        self.client.force_login(user)

        payload = self.client.get(reverse("accounts:recommendations_api")).json()

        self.assertEqual(payload["recommendations"], [])
        self.assertEqual(payload["unsupported_diets"], ["Vegan"])

    def test_allergy_excludes_matching_and_unknown_allergen_information(self):
        user = self.create_user()
        UserAllergy.objects.create(profile=user.userprofile, name="KACANG")
        tenant = self.create_tenant().tenant
        self.create_menu(
            tenant=tenant,
            name="Mengandung alergen",
            allergen_info="Mengandung kacang tanah",
        )
        self.create_menu(
            tenant=tenant,
            name="Alergen tidak diketahui",
            allergen_info="no allergen information listed",
        )
        safe_menu = self.create_menu(
            tenant=tenant,
            name="Menu Aman",
            allergen_info="Mengandung susu",
        )
        self.client.force_login(user)

        payload = self.client.get(reverse("accounts:recommendations_api")).json()

        self.assertEqual(
            [item["id"] for item in payload["recommendations"]], [str(safe_menu.pk)]
        )

    def test_recommendations_are_deterministic_and_limited_to_three(self):
        user = self.create_user()
        tenant = self.create_tenant().tenant
        for name in ("D", "B", "A", "C"):
            self.create_menu(tenant=tenant, name=name)
        self.client.force_login(user)

        payload = self.client.get(reverse("accounts:recommendations_api")).json()

        self.assertEqual(
            [item["name"] for item in payload["recommendations"]], ["A", "B", "C"]
        )

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

    def test_login_rejects_invalid_credentials(self):
        self.create_user("login-error@example.com")

        response = self.client.post(
            reverse("accounts:login"),
            {
                "email": "login-error@example.com",
                "password": "incorrect-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email atau password tidak tepat.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_normalizes_email_case(self):
        self.create_user("mixed.case@example.com")

        response = self.client.post(
            reverse("accounts:login"),
            {
                "email": "MIXED.CASE@EXAMPLE.COM",
                "password": "strong-password-123",
            },
        )

        self.assertRedirects(response, reverse("accounts:accounts"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_tenant_can_login_with_normalized_email(self):
        user = self.create_tenant("restaurant@example.com")

        response = self.client.post(
            reverse("accounts:login"),
            {
                "email": "RESTAURANT@EXAMPLE.COM",
                "password": "strong-password-123",
            },
        )

        self.assertRedirects(response, reverse("accounts:accounts"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

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

    def test_uploaded_photo_is_publicly_served_when_debug_is_false(self):
        self.client.force_login(self.create_user())
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="green").save(image_buffer, format="PNG")
        image_bytes = image_buffer.getvalue()

        with (
            TemporaryDirectory() as media_root,
            self.settings(DEBUG=False, MEDIA_ROOT=media_root),
        ):
            upload_response = self.client.post(
                reverse("accounts:upload_photo"),
                {
                    "photo": SimpleUploadedFile(
                        "profile.png", image_bytes, content_type="image/png"
                    )
                },
            )
            self.assertEqual(upload_response.status_code, 200)

            self.client.logout()
            media_response = self.client.get(upload_response.json()["photo_url"])

            self.assertEqual(media_response.status_code, 200)
            self.assertEqual(b"".join(media_response.streaming_content), image_bytes)

    def test_tenant_photo_upload_requires_authentication(self):
        response = self.client.post(reverse("accounts:upload_tenant_photo"))

        self.assertEqual(response.status_code, 302)

    def test_tenant_photo_rejects_invalid_and_oversized_files(self):
        self.client.force_login(self.create_tenant())
        invalid_response = self.client.post(
            reverse("accounts:upload_tenant_photo"),
            {
                "photo": SimpleUploadedFile(
                    "not-an-image.jpg",
                    b"not an image",
                    content_type="image/jpeg",
                )
            },
        )
        self.assertEqual(invalid_response.status_code, 400)

        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="green").save(image_buffer, format="PNG")
        oversized_image = image_buffer.getvalue() + b"\0" * (5 * 1024 * 1024)
        oversized_response = self.client.post(
            reverse("accounts:upload_tenant_photo"),
            {
                "photo": SimpleUploadedFile(
                    "oversized.png",
                    oversized_image,
                    content_type="image/png",
                )
            },
        )
        self.assertEqual(oversized_response.status_code, 400)
        self.assertIn("Ukuran foto maksimal 5 MB.", oversized_response.json()["error"])

    def test_tenant_photo_replacement_deletes_old_file_after_commit(self):
        user = self.create_tenant()
        self.client.force_login(user)

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            first_buffer = BytesIO()
            Image.new("RGB", (2, 2), color="green").save(first_buffer, format="PNG")
            self.client.post(
                reverse("accounts:upload_tenant_photo"),
                {
                    "photo": SimpleUploadedFile(
                        "first.png",
                        first_buffer.getvalue(),
                        content_type="image/png",
                    )
                },
            )
            user.tenant.refresh_from_db()
            old_name = user.tenant.photo.name
            storage = user.tenant.photo.storage
            self.assertTrue(storage.exists(old_name))

            second_buffer = BytesIO()
            Image.new("RGB", (2, 2), color="blue").save(second_buffer, format="PNG")
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("accounts:upload_tenant_photo"),
                    {
                        "photo": SimpleUploadedFile(
                            "second.png",
                            second_buffer.getvalue(),
                            content_type="image/png",
                        )
                    },
                )

            user.tenant.refresh_from_db()
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(user.tenant.photo.name, old_name)
            self.assertFalse(storage.exists(old_name))

    def test_tenant_photo_is_rendered_and_publicly_served(self):
        user = self.create_tenant()
        self.client.force_login(user)
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="green").save(image_buffer, format="PNG")
        image_bytes = image_buffer.getvalue()

        with (
            TemporaryDirectory() as media_root,
            self.settings(DEBUG=False, MEDIA_ROOT=media_root),
        ):
            upload_response = self.client.post(
                reverse("accounts:upload_tenant_photo"),
                {
                    "photo": SimpleUploadedFile(
                        "tenant.png",
                        image_bytes,
                        content_type="image/png",
                    )
                },
            )
            photo_url = upload_response.json()["photo_url"]
            dashboard_response = self.client.get(reverse("accounts:accounts"))
            self.assertContains(dashboard_response, 'id="tenant-photo"')
            self.assertContains(dashboard_response, f'src="{photo_url}"')

            self.client.logout()
            media_response = self.client.get(photo_url)

            self.assertEqual(media_response.status_code, 200)
            self.assertEqual(b"".join(media_response.streaming_content), image_bytes)

    def test_public_media_route_rejects_path_traversal(self):
        response = self.client.get("/media/../config/settings.py")

        self.assertEqual(response.status_code, 404)

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
