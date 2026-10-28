"""Trusted Catalog and Orders adapters for Reviews."""

from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.urls import reverse
from django.utils.module_loading import import_string

from apps.catalog.models import MenuItem
from apps.orders.models import Order


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


def delivered_orders(menu_key, user):
    """Match the real customer/menu relation, never names or tenant ownership."""
    if not user.is_authenticated or not user.is_customer:
        return Order.objects.none()
    try:
        menu_id = UUID(menu_key)
    except ValueError, TypeError, AttributeError:
        return Order.objects.none()
    if str(menu_id) != menu_key:
        return Order.objects.none()
    return Order.objects.filter(
        user=user,
        status=Order.Status.DELIVERED,
        items__menu_item_id=menu_id,
    )


def resolve_review_order(menu_key, user, order_id):
    """An explicit order must be owned, delivered, and contain this live menu."""
    try:
        order_uuid = UUID(order_id)
    except ValueError, TypeError, AttributeError:
        raise Http404("Review order not found.") from None
    order = delivered_orders(menu_key, user).filter(pk=order_uuid).first()
    if order is None:
        raise Http404("Review order not found.")
    return order


def order_packaging(menu_key, user, *, order_id=None):
    """Snapshot a selected order, or an unambiguous delivered packaging history.

    Reviews do not require a purchase. Without an explicit order, differing
    packaging types are ambiguous; do not guess from dates, names, or prices.
    """
    if order_id is not None:
        return resolve_review_order(menu_key, user, order_id).packaging_type
    types = list(
        delivered_orders(menu_key, user)
        .order_by()
        .values_list("packaging_type", flat=True)
        .distinct()[:2]
    )
    return types[0] if len(types) == 1 else ""


def resolve_packaging(menu_key, user, *, order_id=None):
    """The browser cannot claim packaging; only the configured backend can."""
    resolver = getattr(settings, "REVIEWS_PACKAGING_RESOLVER", None)
    if not resolver:
        return ""
    adapter = import_string(resolver)
    value = (
        adapter(menu_key, user)
        if order_id is None
        else adapter(menu_key, user, order_id=order_id)
    )
    if value not in {"", "reusable", "compostable"}:
        raise ImproperlyConfigured(
            "Reviews packaging resolver returned an unsupported value."
        )
    return value
