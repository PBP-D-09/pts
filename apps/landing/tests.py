import re

from django.test import TestCase
from django.urls import reverse


class LandingPageTests(TestCase):
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

    def test_page_loads_scroll_animation_assets_and_hooks(self):
        response = self.client.get(reverse("landing:landing"))

        self.assertContains(response, 'href="/static/landing/landing.css"')
        self.assertContains(response, 'src="/static/landing/landing.js"')
        self.assertContains(response, "data-landing-page")
        self.assertContains(response, "data-scroll-progress-fill")
        self.assertContains(response, "data-scroll-section", count=4)
        self.assertContains(response, "data-reveal-item")
        self.assertContains(response, "data-faq-accordion", count=3)
        self.assertRegex(
            response.content.decode(),
            r"<details[^>]*\bopen\b[^>]*data-faq-accordion",
        )

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
