"""Catalog boundary. No Catalog schema or sample menu is invented here."""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.utils.module_loading import import_string


@dataclass(frozen=True)
class MenuContext:
    key: str
    name: str
    tenant: str = ""
    description: str = ""
    image_url: str = ""
    detail_url: str = ""
    packaging_label: str = ""


def resolve_menu(key):
    if len(key) > 100:
        raise Http404("Menu not found.")
    resolver = getattr(settings, "REVIEWS_MENU_RESOLVER", None)
    if resolver:
        menu = import_string(resolver)(key)
        if menu is None or menu.key != key:
            raise Http404("Menu not found.")
        return menu
    # An identifier-only workspace is usable until Catalog supplies its resolver.
    # All metadata stays empty rather than presenting fictional food or tenant data.
    return MenuContext(key=key, name=f"Menu {key}")


def resolve_packaging(menu_key, user):
    """Optional trusted Orders adapter; the browser cannot claim an order's packaging."""
    resolver = getattr(settings, "REVIEWS_PACKAGING_RESOLVER", None)
    if not resolver:
        return ""
    value = import_string(resolver)(menu_key, user)
    if value not in {"", "reusable", "compostable"}:
        raise ImproperlyConfigured(
            "Reviews packaging resolver returned an unsupported value."
        )
    return value
