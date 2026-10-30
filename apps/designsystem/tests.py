from django.test import SimpleTestCase
from django.urls import reverse

from .catalog import COLOR_GROUPS, NAVIGATION


class DesignSystemPageTests(SimpleTestCase):
    def test_page_is_public_and_uses_application_shell(self):
        response = self.client.get(reverse("designsystem:index"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "designsystem/index.html")
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, "Design System | SustainaBowl")
        self.assertContains(response, 'aria-label="Navigasi utama"')
        self.assertContains(response, 'aria-label="Navigasi footer"')

    def test_page_rejects_post_requests(self):
        response = self.client.post(reverse("designsystem:index"))

        self.assertEqual(response.status_code, 405)

    def test_page_renders_every_sidebar_target_once(self):
        response = self.client.get(reverse("designsystem:index"))
        section_ids = [item["id"] for group in NAVIGATION for item in group["items"]]

        self.assertEqual(len(section_ids), len(set(section_ids)))
        for section_id in section_ids:
            with self.subTest(section_id=section_id):
                self.assertContains(response, f'id="{section_id}"', count=1)
                self.assertContains(response, f'href="#{section_id}"')

    def test_page_renders_tokens_examples_and_interaction_hooks(self):
        response = self.client.get(reverse("designsystem:index"))

        self.assertContains(response, "primary-100")
        self.assertContains(response, "text-h1")
        self.assertContains(response, "data-sidebar-search")
        self.assertContains(response, "data-copy-code")
        self.assertContains(response, "data-demo-toast")
        self.assertContains(response, 'src="/static/designsystem/design-system.js"')
        for group in COLOR_GROUPS:
            for color in group["colors"]:
                with self.subTest(color_class=color["class_name"]):
                    self.assertContains(response, f'shadow-sm {color["class_name"]}"')
        for template_name in (
            "components/button.html",
            "components/choice.html",
            "components/toast.html",
            "components/form_field.html",
            "components/accordion.html",
            "components/dropdown.html",
        ):
            with self.subTest(template_name=template_name):
                self.assertTemplateUsed(response, template_name)
