from django.test import TestCase
from django.urls import reverse


class LandingViewTests(TestCase):
    def test_landing_page_renders_main_content(self):
        response = self.client.get(reverse("landing:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "landing/landing.html")
        self.assertContains(response, "SustainaBowl")
        self.assertContains(response, 'id="tentang"')
        self.assertContains(response, 'id="manfaat"')
        self.assertContains(response, 'id="bantuan"')
