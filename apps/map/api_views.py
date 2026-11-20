from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Tenant
from apps.accounts.permissions import IsTenant
from apps.accounts.selectors import get_tenant_for_user

from . import selectors, services
from .forms import TenantFilterForm
from .models import DeliveryAddress, TenantLocation
from .serializers import (
    DeliveryAddressSerializer,
    PlaceSearchSerializer,
    ReverseGeocodeSerializer,
    TenantFilterSerializer,
    TenantLocationSerializer,
)

NOT_FOUND_ADDRESS = {"detail": "Alamat tidak ditemukan."}
NOT_FOUND_TENANT = {"detail": "Profil tenan tidak ditemukan."}


def _own_address_or_none(user, pk):
    try:
        return selectors.get_address_for_user(user, pk)
    except DeliveryAddress.DoesNotExist:
        return None


# --- Peta publik lokasi tenan --------------------------------------------


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([AllowAny])
def tenant_locations_api(request):
    serializer = TenantFilterSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    results, center = selectors.filter_tenant_locations(serializer.validated_data)
    # Kontak tenan hanya untuk pengguna yang sudah login (sama seperti web).
    include_contact = request.user.is_authenticated
    tenants = [
        selectors.serialize_tenant_location(
            location, distance, include_contact=include_contact
        )
        for location, distance in results
    ]
    return Response(
        {
            "count": len(tenants),
            "center": {"latitude": center[0], "longitude": center[1]},
            "results": tenants,
        }
    )


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([AllowAny])
def tenant_filters_api(request):
    """Pilihan filter untuk dropdown di aplikasi mobile."""
    return Response(
        {
            "cities": selectors.get_cities(),
            "categories": [
                {"value": value, "label": label}
                for value, label in TenantLocation.Category.choices
            ],
            "radius_km": [
                int(value) for value, _label in TenantFilterForm.RADIUS_CHOICES if value
            ],
        }
    )


# --- Nominatim (pencarian & reverse geocoding) ----------------------------


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def search_api(request):
    serializer = PlaceSearchSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    query = serializer.validated_data["q"]
    try:
        places = services.search_places(query)
    except services.GeocodingError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    return Response({"query": query, "results": places})


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def reverse_api(request):
    serializer = ReverseGeocodeSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    try:
        place = services.reverse_geocode(
            serializer.validated_data["lat"], serializer.validated_data["lng"]
        )
    except services.GeocodingError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    if place is None:
        return Response(
            {"detail": "Alamat tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND
        )
    return Response({"result": place})


# --- CRUD alamat pengiriman (hanya pemilik akun) ---------------------------


@api_view(["GET", "POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def addresses_api(request):
    if request.method == "GET":
        addresses = selectors.get_addresses_for_user(request.user)
        return Response(DeliveryAddressSerializer(addresses, many=True).data)

    serializer = DeliveryAddressSerializer(
        data=request.data, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)
    address = serializer.save()
    return Response(
        DeliveryAddressSerializer(address).data, status=status.HTTP_201_CREATED
    )


@api_view(["GET", "PATCH", "PUT", "DELETE"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def address_detail_api(request, pk):
    # Alamat milik orang lain dibalas 404, bukan 403, supaya tidak bocor.
    address = _own_address_or_none(request.user, pk)
    if address is None:
        return Response(NOT_FOUND_ADDRESS, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(DeliveryAddressSerializer(address).data)

    if request.method == "DELETE":
        services.delete_delivery_address(address)
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = DeliveryAddressSerializer(
        address,
        data=request.data,
        context={"request": request},
        partial=(request.method == "PATCH"),
    )
    serializer.is_valid(raise_exception=True)
    address = serializer.save()
    return Response(DeliveryAddressSerializer(address).data)


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def address_set_default_api(request, pk):
    address = _own_address_or_none(request.user, pk)
    if address is None:
        return Response(NOT_FOUND_ADDRESS, status=status.HTTP_404_NOT_FOUND)
    address = services.set_default_address(address)
    return Response(DeliveryAddressSerializer(address).data)


# --- Lokasi tenan (hanya akun tenan pemilik) ---------------------------------


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsTenant])
def tenant_location_api(request):
    try:
        tenant = get_tenant_for_user(request.user)
    except Tenant.DoesNotExist:
        return Response(NOT_FOUND_TENANT, status=status.HTTP_404_NOT_FOUND)
    location = TenantLocation.objects.filter(tenant=tenant).first()

    if request.method == "GET":
        if location is None:
            return Response(
                {"detail": "Lokasi tenan belum diatur."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            selectors.serialize_tenant_location(location, 0, include_contact=True)
        )

    if request.method == "DELETE":
        if not services.delete_tenant_location(tenant):
            return Response(
                {"detail": "Lokasi tenan belum diatur."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PUT membuat atau mengganti lokasi; PATCH hanya untuk lokasi yang sudah ada.
    if request.method == "PATCH" and location is None:
        return Response(
            {"detail": "Lokasi tenan belum diatur. Gunakan PUT untuk membuatnya."},
            status=status.HTTP_404_NOT_FOUND,
        )
    serializer = TenantLocationSerializer(
        location,
        data=request.data,
        context={"request": request, "tenant": tenant},
        partial=(request.method == "PATCH"),
    )
    serializer.is_valid(raise_exception=True)
    created = location is None
    location = serializer.save()
    return Response(
        selectors.serialize_tenant_location(location, 0, include_contact=True),
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )
