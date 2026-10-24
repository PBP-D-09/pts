from django.db.models import Q
from django.utils import timezone

from .models import DeliveryAddress, TenantLocation

# Titik tengah default peta: Jakarta Pusat (Monas).
DEFAULT_CENTER = (-6.175392, 106.827153)


def get_addresses_for_user(user):
    return DeliveryAddress.objects.filter(owner=user)


def get_address_for_user(user, pk):
    """Raise DoesNotExist kalau alamat bukan milik user, supaya tidak bocor."""
    return DeliveryAddress.objects.get(owner=user, pk=pk)


def get_cities():
    return list(
        TenantLocation.objects.order_by("city")
        .values_list("city", flat=True)
        .distinct()
    )


def filter_tenant_locations(filters):
    """Mengembalikan daftar (lokasi, jarak_km) yang sudah difilter dan diurutkan.

    `filters` adalah cleaned_data dari TenantFilterForm.
    """
    queryset = TenantLocation.objects.select_related("tenant")

    query = (filters.get("q") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(tenant__name__icontains=query)
            | Q(address__icontains=query)
            | Q(district__icontains=query)
        )
    if filters.get("city"):
        queryset = queryset.filter(city__iexact=filters["city"])
    if filters.get("category"):
        queryset = queryset.filter(category=filters["category"])

    lat = filters.get("lat")
    lng = filters.get("lng")
    has_center = lat is not None and lng is not None
    center = (lat, lng) if has_center else DEFAULT_CENTER

    now = timezone.localtime()
    results = []
    for location in queryset:
        if filters.get("open_now") and not location.is_open_at(now):
            continue
        distance = location.distance_from(*center)
        results.append((location, distance))

    radius = filters.get("radius")
    if radius:
        results = [item for item in results if item[1] <= float(radius)]

    results.sort(key=lambda item: (item[1], item[0].tenant.name))
    return results, center


def serialize_tenant_location(location, distance, *, include_contact):
    data = {
        "id": location.pk,
        "tenant_id": location.tenant_id,
        "name": location.tenant.name,
        "address": location.address,
        "district": location.district,
        "city": location.city,
        "category": location.category,
        "category_label": location.get_category_display(),
        "latitude": float(location.latitude),
        "longitude": float(location.longitude),
        "opening_time": location.opening_time.strftime("%H:%M"),
        "closing_time": location.closing_time.strftime("%H:%M"),
        "is_open_now": location.is_open_now,
        "delivery_radius_km": float(location.delivery_radius_km),
        "distance_km": round(distance, 2),
        "photo_url": location.tenant.photo.url if location.tenant.photo else "",
    }
    # Kontak tenan hanya untuk pengguna yang sudah login (filter autentikasi).
    if include_contact:
        data["phone_number"] = location.tenant.phone_number
    return data
