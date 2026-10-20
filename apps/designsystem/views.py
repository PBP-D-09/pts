from django.shortcuts import render
from django.views.decorators.http import require_GET

from .catalog import COLOR_GROUPS, NAVIGATION, SNIPPETS, TYPOGRAPHY_GROUPS
from .forms import ShowcaseForm


@require_GET
def index(request):
    form = ShowcaseForm()
    invalid_form = ShowcaseForm(
        {"full_name": "Pengguna SustainaBowl", "email": "", "phone_number": ""}
    )
    invalid_form.is_valid()

    context = {
        "navigation": NAVIGATION,
        "color_groups": COLOR_GROUPS,
        "typography_groups": TYPOGRAPHY_GROUPS,
        "snippets": SNIPPETS,
        "form": form,
        "invalid_form": invalid_form,
        "dropdown_items": [
            {"label": "Makanan utama", "url": "#panels-dialog"},
            {"label": "Minuman", "url": "#panels-dialog"},
            {"label": "Camilan sehat", "url": "#panels-dialog"},
        ],
    }
    return render(request, "designsystem/index.html", context)
