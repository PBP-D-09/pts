import re

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser, Tenant
from apps.catalog.models import MenuCategory, MenuItem


class LandingPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = CustomUser.objects.create_user(
            email="tenant@example.com",
            password="test-password",
            account_type=CustomUser.AccountType.TENANT,
        )
        cls.tenant = Tenant.objects.create(
            owner=owner,
            name="Dapur Hijau",
            phone_number="08123456789",
        )
        cls.category = MenuCategory.objects.create(
            tenantId=cls.tenant,
            name="Makanan Utama",
        )

    def create_menu_item(self, name, **overrides):
        values = {
            "tenantId": self.tenant,
            "name": name,
            "description": f"Deskripsi {name}",
            "category": self.category,
            "price": 12_500,
        }
        values.update(overrides)
        return MenuItem.objects.create(**values)

    def test_page_uses_real_application_links(self):
        response = self.client.get(reverse("landing:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "landing/landing.html")
        self.assertContains(response, f'href="{reverse("catalog:show_catalog")}"')
        self.assertRegex(
            response.content.decode(),
            rf'<a href="{re.escape(reverse("catalog:show_catalog"))}"\s+'
            'id="landing-cta"',
        )
        self.assertContains(response, f'href="{reverse("map:map")}"')
        self.assertNotContains(response, 'href="#"')
        self.assertNotContains(response, ">Tenants</a>")

    def test_footer_contact_links_are_accessible_and_safe(self):
        response = self.client.get(reverse("landing:landing"))

        self.assertContains(response, 'href="mailto:hello@sustainabowl.com"')
        self.assertContains(response, 'aria-label="Kirim email ke SustainaBowl"')
        self.assertContains(response, 'href="https://instagram.com"')
        self.assertContains(response, 'aria-label="Instagram SustainaBowl"')
        self.assertContains(response, 'href="https://github.com/PBP-D-09/pts"')
        self.assertContains(response, 'aria-label="GitHub SustainaBowl"')
        self.assertContains(response, 'rel="noopener noreferrer"', count=2)

    def test_hero_communicates_the_main_value_and_actions(self):
        response = self.client.get(reverse("landing:landing"))

        self.assertContains(response, "Sustaina")
        self.assertContains(response, "Try Now")
        self.assertContains(response, "Temukan tenan")
        self.assertContains(response, "Preferensi diet")
        self.assertContains(response, "Informasi alergen")
        self.assertContains(response, "Eco Points")
        self.assertContains(response, "sustainabowl-hero.png")

    def test_page_loads_scroll_animation_assets_and_hooks(self):
        response = self.client.get(reverse("landing:landing"))

        self.assertContains(response, 'href="/static/landing/landing.css"')
        self.assertContains(response, 'src="/static/landing/landing.js"')
        self.assertContains(response, "data-landing-page")
        self.assertContains(response, "data-scroll-progress-fill")
        self.assertContains(response, "data-scroll-section", count=7)
        self.assertContains(response, "data-reveal-item")
        self.assertContains(response, "landing-steps-section", count=1)
        self.assertContains(response, "landing-step-card", count=4)
        self.assertContains(response, "data-faq-accordion", count=3)
        self.assertRegex(
            response.content.decode(),
            r"<details[^>]*\bopen\b[^>]*data-faq-accordion",
        )
        self.assertNotContains(response, "pt-3 text-primary-10")

    def test_menu_preview_is_limited_ordered_and_uses_real_tenant_links(self):
        self.create_menu_item(
            "Alpha Bowl",
            vegetarian=True,
            allergen_info="Mengandung kacang",
        )
        self.create_menu_item("Gamma Bowl")
        self.create_menu_item("Beta Bowl", price=25_000, allergen_info="")
        self.create_menu_item("Zeta Bowl")

        response = self.client.get(reverse("landing:landing"))
        html = response.content.decode()

        self.assertContains(response, "Alpha Bowl")
        self.assertContains(response, "Beta Bowl")
        self.assertContains(response, "Gamma Bowl")
        self.assertNotContains(response, "Zeta Bowl")
        self.assertLess(html.index("Alpha Bowl"), html.index("Beta Bowl"))
        self.assertLess(html.index("Beta Bowl"), html.index("Gamma Bowl"))
        self.assertContains(response, "Vegetarian")
        self.assertContains(response, "Mengandung kacang")
        self.assertContains(response, "Info alergen belum tersedia", count=2)
        self.assertContains(response, "Rp25.000")
        self.assertContains(
            response,
            f'href="{reverse("catalog:show_catalog_tenant", args=[self.tenant.pk])}"',
            count=3,
        )

    def test_menu_preview_has_an_empty_state(self):
        response = self.client.get(reverse("landing:landing"))

        self.assertContains(response, "Menu sedang disiapkan")
        self.assertContains(
            response, "Tenan kami sedang menambahkan pilihan sehat baru"
        )

    def test_discovery_section_links_to_map_and_tenant_registration(self):
        response = self.client.get(reverse("landing:landing"))

        self.assertContains(response, f'href="{reverse("map:map")}"')
        self.assertContains(
            response,
            f'href="{reverse("accounts:register_tenant")}"',
        )
        self.assertContains(response, "Buka peta")
        self.assertContains(response, "Daftar sebagai tenan")

    def test_header_uses_logo_instead_of_separate_home_links(self):
        response = self.client.get(reverse("landing:landing"))
        html = response.content.decode()

        for label in ("Navigasi utama", "Navigasi mobile"):
            navigation = re.search(
                rf'<nav[^>]*aria-label="{label}"[^>]*>(.*?)</nav>',
                html,
                re.DOTALL,
            )
            self.assertIsNotNone(navigation)
            self.assertNotIn("Home</a>", navigation.group(1))

        footer = re.search(
            r'<nav[^>]*aria-label="Navigasi footer"[^>]*>(.*?)</nav>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(footer)
        self.assertIn("Home</a>", footer.group(1))
