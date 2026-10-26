"""Catalog metadata and optional, trusted Orders adapters for Reviews."""

from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.urls import reverse
from django.utils.module_loading import import_string

from apps.catalog.models import MenuItem


@dataclass(frozen=True)
class MenuContext:
    key: str
    name: str
    tenant: str = ""
    description: str = ""
    image_url: str = ""
    detail_url: str = ""
    packaging_label: str = ""


def catalog_menu(key):
    """Resolve only canonical UUIDs; legacy identifiers remain stored, never guessed."""
    try:
        menu_id = UUID(key)
    except ValueError, TypeError, AttributeError:
        return None
    if str(menu_id) != key:
        return None
    item = MenuItem.objects.select_related("tenantId").filter(pk=menu_id).first()
    if item is None:
        return None
    return MenuContext(
        key=str(item.pk),
        name=item.name,
        tenant=item.tenantId.name if item.tenantId_id else "",
        description=item.description,
        image_url=item.photo.url if item.photo else "",
        detail_url=(
            reverse("catalog:show_catalog_tenant", args=[item.tenantId_id])
            if item.tenantId_id
            else reverse("catalog:show_catalog")
        ),
    )


def resolve_menu(key):
    if not isinstance(key, str) or len(key) > 100:
        raise Http404("Menu not found.")
    resolver = getattr(settings, "REVIEWS_MENU_RESOLVER", None)
    if not resolver:
        raise ImproperlyConfigured("REVIEWS_MENU_RESOLVER must be configured.")
    menu = import_string(resolver)(key)
    if menu is None or menu.key != key:
        raise Http404("Menu not found.")
    return menu


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
