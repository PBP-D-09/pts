# Create your tests here.
import base64
import tempfile

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings

from .forms import MenuCategoryForm, MenuItemForm
from .models import AllergenIngredient, MenuCategory, MenuItem, TenantCuisine


# A valid, tiny PNG used to exercise ImageField without requiring a fixture file.
TINY_GIF = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


class CatalogTestDataMixin:
    """Shared setup for catalog tests."""

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        username_field = user_model.USERNAME_FIELD

        cls.owner_user = user_model.objects.create_user(
            **{username_field: "owner@example.com" if username_field == "email" else "owner"},
            password="test-password-123",
        )
        cls.other_user = user_model.objects.create_user(
            **{username_field: "other@example.com" if username_field == "email" else "other"},
            password="test-password-123",
        )

        # Tenant is in the accounts app and has owner, name, and phone_number fields.
        from django.apps import apps

        tenant_model = apps.get_model("accounts", "Tenant")
        cls.tenant = tenant_model.objects.create(
            owner=cls.owner_user,
            name="Test Restaurant",
            phone_number="081234567890",
        )
        cls.other_tenant = tenant_model.objects.create(
            owner=cls.other_user,
            name="Other Restaurant",
            phone_number="081234567891",
        )

        cls.category = MenuCategory.objects.create(
            tenantId=cls.tenant,
            name="Main Course",
        )
        cls.other_category = MenuCategory.objects.create(
            tenantId=cls.other_tenant,
            name="Desserts",
        )


class TenantCuisineModelTests(TestCase):
    def test_name_is_primary_key(self):
        field = TenantCuisine._meta.get_field("name")
        self.assertTrue(field.primary_key)

    def test_string_representation_is_name(self):
        cuisine = TenantCuisine.objects.create(name="Indonesian")
        self.assertEqual(str(cuisine), "Indonesian")

    def test_name_must_be_unique(self):
        TenantCuisine.objects.create(name="Indonesian")
        with self.assertRaises(IntegrityError):
            TenantCuisine.objects.create(name="Indonesian")


class AllergenIngredientModelTests(TestCase):
    def test_name_is_primary_key(self):
        field = AllergenIngredient._meta.get_field("name")
        self.assertTrue(field.primary_key)

    def test_name_must_be_unique(self):
        AllergenIngredient.objects.create(name="Peanuts")
        with self.assertRaises(IntegrityError):
            AllergenIngredient.objects.create(name="Peanuts")


class MenuCategoryModelTests(CatalogTestDataMixin, TestCase):
    def test_category_is_associated_with_tenant(self):
        self.assertEqual(self.category.tenantId, self.tenant)
        self.assertIn(self.category, self.tenant.menu_categories.all())

    def test_category_string_representation_is_name(self):
        self.assertEqual(str(self.category), "Main Course")

    def test_category_can_have_no_tenant(self):
        category = MenuCategory.objects.create(name="Unassigned")
        self.assertIsNone(category.tenantId)

    def test_deleting_tenant_deletes_its_categories(self):
        category_pk = self.category.pk
        self.tenant.delete()
        self.assertFalse(MenuCategory.objects.filter(pk=category_pk).exists())


class MenuItemModelTests(CatalogTestDataMixin, TestCase):
    def test_item_uses_uuid_primary_key(self):
        item = MenuItem.objects.create(
            tenantId=self.tenant,
            name="Chicken Rice",
            description="Grilled chicken with rice",
            category=self.category,
            price=25000,
        )
        self.assertEqual(item.pk.version, 4)
        self.assertEqual(MenuItem._meta.pk.get_internal_type(), "UUIDField")

    def test_string_representation_is_name(self):
        item = MenuItem.objects.create(
            tenantId=self.tenant,
            name="Chicken Rice",
            description="Grilled chicken with rice",
            price=25000,
        )
        self.assertEqual(str(item), "Chicken Rice")

    def test_allergen_info_default(self):
        item = MenuItem.objects.create(
            name="Plain Rice",
            description="Steamed rice",
            price=5000,
        )
        self.assertEqual(item.allergen_info, "no allergen information listed")

    def test_vegetarian_defaults_to_false(self):
        item = MenuItem.objects.create(
            name="Chicken Rice",
            description="Rice with chicken",
            price=25000,
        )
        self.assertFalse(item.vegetarian)

    def test_item_is_related_to_tenant(self):
        item = MenuItem.objects.create(
            tenantId=self.tenant,
            name="Chicken Rice",
            description="Rice with chicken",
            price=25000,
        )
        self.assertIn(item, self.tenant.menus.all())

    def test_deleting_category_sets_item_category_to_null(self):
        item = MenuItem.objects.create(
            tenantId=self.tenant,
            name="Chicken Rice",
            description="Rice with chicken",
            category=self.category,
            price=25000,
        )
        self.category.delete()
        item.refresh_from_db()
        self.assertIsNone(item.category)

    def test_deleting_tenant_deletes_its_items(self):
        item = MenuItem.objects.create(
            tenantId=self.tenant,
            name="Chicken Rice",
            description="Rice with chicken",
            price=25000,
        )
        item_pk = item.pk
        self.tenant.delete()
        self.assertFalse(MenuItem.objects.filter(pk=item_pk).exists())

    def test_photo_upload_path(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                item = MenuItem.objects.create(
                    name="Test Photo",
                    description="Photo upload test",
                    price=10000,
                    photo=SimpleUploadedFile(
                        "dish.gif", TINY_GIF, content_type="image/gif"
                    ),
                )
                self.assertTrue(item.photo.name.startswith("menu_items/"))
                item.photo.delete(save=False)


class MenuCategoryFormTests(CatalogTestDataMixin, TestCase):
    def test_valid_category_form(self):
        form = MenuCategoryForm(data={"name": "Drinks"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_category_name_is_required(self):
        form = MenuCategoryForm(data={"name": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_category_form_saves_name(self):
        form = MenuCategoryForm(data={"name": "Drinks"})
        self.assertTrue(form.is_valid(), form.errors)
        category = form.save()
        self.assertEqual(category.name, "Drinks")


class MenuItemFormTests(CatalogTestDataMixin, TestCase):
    def valid_data(self, **overrides):
        data = {
            "name": "Chicken Rice",
            "description": "Grilled chicken served with rice",
            "category": str(self.category.pk),
            "allergen_info": "Contains soy",
            "price": "25000",
            # Unchecked HTML checkboxes are omitted from POST data.
        }
        data.update(overrides)
        return data

    def test_valid_item_form_for_tenant_category(self):
        form = MenuItemForm(data=self.valid_data(), tenant=self.tenant)
        self.assertTrue(form.is_valid(), form.errors)

    def test_category_queryset_is_limited_to_given_tenant(self):
        form = MenuItemForm(tenant=self.tenant)
        allowed_ids = set(
            form.fields["category"].queryset.values_list("pk", flat=True)
        )
        self.assertIn(self.category.pk, allowed_ids)
        self.assertNotIn(self.other_category.pk, allowed_ids)

    def test_rejects_category_owned_by_another_tenant(self):
        form = MenuItemForm(
            data=self.valid_data(category=str(self.other_category.pk)),
            tenant=self.tenant,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_name_is_required(self):
        form = MenuItemForm(
            data=self.valid_data(name=""),
            tenant=self.tenant,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_description_is_required(self):
        form = MenuItemForm(
            data=self.valid_data(description=""),
            tenant=self.tenant,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)

    def test_price_is_required(self):
        form = MenuItemForm(
            data=self.valid_data(price=""),
            tenant=self.tenant,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("price", form.errors)

    def test_price_must_be_an_integer(self):
        form = MenuItemForm(
            data=self.valid_data(price="not-a-number"),
            tenant=self.tenant,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("price", form.errors)

    def test_item_form_saves_item(self):
        form = MenuItemForm(data=self.valid_data(), tenant=self.tenant)
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save(commit=False)
        item.tenantId = self.tenant
        item.save()
        self.assertEqual(item.name, "Chicken Rice")
        self.assertEqual(item.category, self.category)
        self.assertEqual(item.price, 25000)
        self.assertFalse(item.vegetarian)

    def test_form_accepts_uploaded_image(self):
        upload = SimpleUploadedFile(
            "dish.gif", TINY_GIF, content_type="image/gif"
        )
        form = MenuItemForm(
            data=self.valid_data(),
            files={"photo": upload},
            tenant=self.tenant,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_widgets_have_expected_input_types(self):
        form = MenuItemForm(tenant=self.tenant)
        self.assertEqual(form.fields["photo"].widget.input_type, "file")
        self.assertEqual(form.fields["name"].widget.input_type, "text")
        self.assertEqual(form.fields["price"].widget.input_type, "number")
        self.assertEqual(form.fields["vegetarian"].widget.input_type, "checkbox")


class CatalogAdminRegistrationTests(TestCase):
    def test_catalog_models_are_registered_in_admin(self):
        self.assertIn(TenantCuisine, admin.site._registry)
        self.assertIn(AllergenIngredient, admin.site._registry)
        self.assertIn(MenuCategory, admin.site._registry)
        self.assertIn(MenuItem, admin.site._registry)
