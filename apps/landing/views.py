from django.shortcuts import render

from apps.catalog.models import MenuItem

UNKNOWN_ALLERGEN_INFO = "no allergen information listed"


def _format_rupiah(value):
    return f"Rp{value:,}".replace(",", ".")


def _menu_preview(item):
    allergen_info = item.allergen_info.strip()
    has_allergen_info = bool(allergen_info) and (
        allergen_info.casefold() != UNKNOWN_ALLERGEN_INFO
    )

    return {
        "item": item,
        "formatted_price": _format_rupiah(item.price),
        "allergen_text": (
            allergen_info if has_allergen_info else "Info alergen belum tersedia"
        ),
        "has_allergen_info": has_allergen_info,
    }


def landing(request):
    menu_items = (
        MenuItem.objects.filter(tenantId__isnull=False)
        .select_related("tenantId", "category")
        .order_by("name", "id")[:3]
    )
    context = {"menu_previews": [_menu_preview(item) for item in menu_items]}
    return render(request, "landing/landing.html", context)
