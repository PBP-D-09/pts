import hashlib
import logging

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from .models import DeliveryAddress

logger = logging.getLogger(__name__)

NOMINATIM_TIMEOUT_SECONDS = 6
NOMINATIM_CACHE_SECONDS = 60 * 60 * 24


class GeocodingError(Exception):
    """Nominatim tidak bisa dihubungi atau membalas dengan respons tidak valid."""


@transaction.atomic
def save_delivery_address(form, *, owner):
    address = form.save(commit=False)
    address.owner = owner
    if address.is_default:
        DeliveryAddress.objects.filter(owner=owner, is_default=True).exclude(
            pk=address.pk
        ).update(is_default=False)
    elif (
        not DeliveryAddress.objects.filter(owner=owner).exclude(pk=address.pk).exists()
    ):
        # Alamat pertama otomatis menjadi alamat utama.
        address.is_default = True
    address.save()
    return address


@transaction.atomic
def delete_delivery_address(address):
    owner = address.owner
    was_default = address.is_default
    address.delete()
    if was_default:
        replacement = DeliveryAddress.objects.filter(owner=owner).first()
        if replacement:
            replacement.is_default = True
            replacement.save(update_fields=["is_default"])


@transaction.atomic
def set_default_address(address):
    DeliveryAddress.objects.filter(owner=address.owner, is_default=True).exclude(
        pk=address.pk
    ).update(is_default=False)
    address.is_default = True
    address.save(update_fields=["is_default", "updated_at"])
    return address


def save_tenant_location(form, *, tenant):
    location = form.save(commit=False)
    location.tenant = tenant
    location.save()
    return location


def _nominatim_get(path, params):
    cache_key = (
        "nominatim:"
        + hashlib.sha256(f"{path}?{sorted(params.items())}".encode()).hexdigest()
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            f"{settings.NOMINATIM_BASE_URL}/{path}",
            params={**params, "format": "jsonv2"},
            headers={
                "User-Agent": settings.NOMINATIM_USER_AGENT,
                "Accept-Language": "id,en",
            },
            timeout=NOMINATIM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning("Nominatim request failed: %s", error)
        raise GeocodingError(
            "Layanan pencarian alamat sedang tidak tersedia."
        ) from error

    cache.set(cache_key, payload, NOMINATIM_CACHE_SECONDS)
    return payload


def _place_from_payload(item):
    return {
        "display_name": item.get("display_name", ""),
        "name": item.get("name") or item.get("display_name", "").split(",")[0],
        "latitude": float(item["lat"]),
        "longitude": float(item["lon"]),
        "type": item.get("type", ""),
    }


def search_places(query, *, limit=5):
    payload = _nominatim_get(
        "search",
        {"q": query, "countrycodes": "id", "limit": limit, "addressdetails": 0},
    )
    if not isinstance(payload, list):
        raise GeocodingError("Respons layanan pencarian alamat tidak valid.")
    places = []
    for item in payload:
        try:
            places.append(_place_from_payload(item))
        except KeyError, TypeError, ValueError:
            continue
    return places


def reverse_geocode(latitude, longitude):
    payload = _nominatim_get(
        "reverse", {"lat": f"{latitude:.6f}", "lon": f"{longitude:.6f}", "zoom": 18}
    )
    if not isinstance(payload, dict) or "lat" not in payload:
        return None
    try:
        return _place_from_payload(payload)
    except KeyError, TypeError, ValueError:
        return None
