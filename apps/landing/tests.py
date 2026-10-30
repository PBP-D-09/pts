from django.test import TestCase
from django.urls import reverse


class LandingPageTests(TestCase):
    def test_page_uses_real_application_links(self):
        response = self.client.get(reverse("landing:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "landing/landing.html")
        self.assertContains(response, f'href="{reverse("catalog:show_catalog")}"')
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
