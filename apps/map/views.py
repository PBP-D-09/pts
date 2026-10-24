import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse, QueryDict
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.decorators import tenant_required
from apps.accounts.models import Tenant

from .forms import DeliveryAddressForm, TenantFilterForm, TenantLocationForm
from .models import DeliveryAddress, TenantLocation
from .selectors import (
    DEFAULT_CENTER,
    filter_tenant_locations,
    get_address_for_user,
    get_addresses_for_user,
    get_cities,
    serialize_tenant_location,
)
from .services import (
    GeocodingError,
    delete_delivery_address,
    reverse_geocode,
    save_delivery_address,
    save_tenant_location,
    search_places,
    set_default_address,
)

MIN_SEARCH_LENGTH = 3


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _wants_json(request):
    if request.htmx:
        return False
    accept = request.headers.get("Accept", "")
    return (
        "application/json" in accept
        or request.content_type == "application/json"
        or request.GET.get("format") == "json"
    )


def _request_data(request):
    """Data form dari POST biasa atau body JSON (untuk klien seperti Flutter)."""
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            payload = {}
        data = QueryDict(mutable=True)
        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(value, bool):
                    if value:
                        data[key] = "on"
                elif value is not None:
                    data[key] = str(value)
        return data
    return request.POST


def _with_toast(response, message, level="success"):
    response["HX-Trigger"] = json.dumps(
        {"showToast": {"message": message, "level": level}}
    )
    return response


def login_required_json(view_func):
    """Seperti login_required, tetapi membalas 401 JSON untuk klien API."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if _wants_json(request):
                return JsonResponse(
                    {"error": "Silakan login terlebih dahulu."}, status=401
                )
            return login_required(view_func)(request, *args, **kwargs)
        return view_func(request, *args, **kwargs)

    return wrapped


def _get_own_address(request, pk):
    try:
        return get_address_for_user(request.user, pk)
    except DeliveryAddress.DoesNotExist:
        raise Http404("Alamat tidak ditemukan.") from None


# ---------------------------------------------------------------------------
# Peta publik lokasi tenan
# ---------------------------------------------------------------------------


def _tenant_filter_results(request):
    form = TenantFilterForm(request.GET or None)
    filters = form.cleaned_data if form.is_valid() else {}
    results, center = filter_tenant_locations(filters)
    include_contact = request.user.is_authenticated
    tenants = [
        serialize_tenant_location(location, distance, include_contact=include_contact)
        for location, distance in results
    ]
    return form, filters, tenants, center


@require_GET
def map_view(request):
    form, filters, tenants, center = _tenant_filter_results(request)
    context = {
        "filter_form": form,
        "filters": filters,
        "tenants": tenants,
        "center": {"latitude": center[0], "longitude": center[1]},
        "cities": get_cities(),
        "categories": TenantLocation.Category.choices,
        "radius_choices": TenantFilterForm.RADIUS_CHOICES[1:],
    }
    if request.htmx and not request.htmx.history_restore_request:
        return render(request, "map/partials/tenant_results.html", context)
    return render(request, "map/map.html", context)


@require_GET
def tenant_locations_api(request):
    _form, _filters, tenants, center = _tenant_filter_results(request)
    return JsonResponse(
        {
            "count": len(tenants),
            "center": {"latitude": center[0], "longitude": center[1]},
            "results": tenants,
        }
    )


# ---------------------------------------------------------------------------
# Integrasi Nominatim (pencarian & reverse geocoding)
# ---------------------------------------------------------------------------


@require_GET
def search_api(request):
    query = (request.GET.get("q") or "").strip()[:150]
    places, error = [], ""
    if len(query) >= MIN_SEARCH_LENGTH:
        try:
            places = search_places(query)
        except GeocodingError as exc:
            error = str(exc)

    if request.htmx:
        return render(
            request,
            "map/partials/search_results.html",
            {
                "query": query,
                "places": places,
                "error": error,
                "too_short": 0 < len(query) < MIN_SEARCH_LENGTH,
            },
        )
    if error:
        return JsonResponse({"error": error}, status=502)
    if len(query) < MIN_SEARCH_LENGTH:
        return JsonResponse(
            {"error": f"Masukkan minimal {MIN_SEARCH_LENGTH} karakter."}, status=400
        )
    return JsonResponse({"query": query, "results": places})


@require_GET
def reverse_api(request):
    try:
        latitude = float(request.GET["lat"])
        longitude = float(request.GET["lng"])
    except KeyError, ValueError:
        return JsonResponse({"error": "Koordinat tidak valid."}, status=400)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return JsonResponse({"error": "Koordinat tidak valid."}, status=400)
    try:
        place = reverse_geocode(latitude, longitude)
    except GeocodingError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    if place is None:
        return JsonResponse({"error": "Alamat tidak ditemukan."}, status=404)
    return JsonResponse({"result": place})


# ---------------------------------------------------------------------------
# CRUD alamat pengiriman (hanya pemilik akun)
# ---------------------------------------------------------------------------


def _address_panel_context(user, form=None, editing=None):
    addresses = list(get_addresses_for_user(user))
    return {
        "addresses": addresses,
        "addresses_data": [address.to_dict() for address in addresses],
        "address_form": form or DeliveryAddressForm(),
        "editing": editing,
    }


def _render_panel(request, message, level="success", **panel_kwargs):
    response = render(
        request,
        "map/partials/address_panel.html",
        _address_panel_context(request.user, **panel_kwargs),
    )
    return _with_toast(response, message, level)


@login_required
@require_GET
def address_list(request):
    context = _address_panel_context(request.user)
    context["center"] = {
        "latitude": DEFAULT_CENTER[0],
        "longitude": DEFAULT_CENTER[1],
    }
    context["tenants"] = [
        serialize_tenant_location(location, distance, include_contact=True)
        for location, distance in filter_tenant_locations({})[0]
    ]
    return render(request, "map/addresses.html", context)


@login_required_json
@require_GET
def address_list_api(request):
    addresses = get_addresses_for_user(request.user)
    return JsonResponse(
        {
            "count": len(addresses),
            "results": [address.to_dict() for address in addresses],
        }
    )


@login_required_json
@require_GET
def address_detail_api(request, pk):
    address = _get_own_address(request, pk)
    return JsonResponse({"address": address.to_dict()})


@login_required_json
@require_POST
def address_create(request):
    form = DeliveryAddressForm(_request_data(request))
    if not form.is_valid():
        if request.htmx:
            return _render_panel(
                request, "Periksa kembali data alamat.", "error", form=form
            )
        if _wants_json(request):
            return JsonResponse({"errors": form.errors}, status=400)
        messages.error(request, "Periksa kembali data alamat.")
        return redirect("map:addresses")

    address = save_delivery_address(form, owner=request.user)
    if request.htmx:
        return _render_panel(request, "Alamat baru tersimpan.")
    if _wants_json(request):
        return JsonResponse({"address": address.to_dict()}, status=201)
    messages.success(request, "Alamat baru tersimpan.")
    return redirect("map:addresses")


@login_required
@require_GET
def address_edit(request, pk):
    address = _get_own_address(request, pk)
    form = DeliveryAddressForm(instance=address)
    if request.htmx:
        return render(
            request,
            "map/partials/address_form.html",
            {"address_form": form, "editing": address},
        )
    context = _address_panel_context(request.user, form=form, editing=address)
    context["center"] = {
        "latitude": float(address.latitude),
        "longitude": float(address.longitude),
    }
    context["tenants"] = []
    return render(request, "map/addresses.html", context)


@login_required_json
@require_POST
def address_update(request, pk):
    address = _get_own_address(request, pk)
    form = DeliveryAddressForm(_request_data(request), instance=address)
    if not form.is_valid():
        if request.htmx:
            return _render_panel(
                request,
                "Periksa kembali data alamat.",
                "error",
                form=form,
                editing=address,
            )
        if _wants_json(request):
            return JsonResponse({"errors": form.errors}, status=400)
        messages.error(request, "Periksa kembali data alamat.")
        return redirect("map:address_edit", pk=pk)

    address = save_delivery_address(form, owner=request.user)
    if request.htmx:
        return _render_panel(request, "Alamat diperbarui.")
    if _wants_json(request):
        return JsonResponse({"address": address.to_dict()})
    messages.success(request, "Alamat diperbarui.")
    return redirect("map:addresses")


@login_required_json
@require_POST
def address_delete(request, pk):
    address = _get_own_address(request, pk)
    delete_delivery_address(address)
    if request.htmx:
        return _render_panel(request, "Alamat dihapus.")
    if _wants_json(request):
        return JsonResponse({"deleted": pk})
    messages.success(request, "Alamat dihapus.")
    return redirect("map:addresses")


@login_required_json
@require_POST
def address_set_default(request, pk):
    address = set_default_address(_get_own_address(request, pk))
    if request.htmx:
        return _render_panel(request, f"{address.label} jadi alamat utama.")
    if _wants_json(request):
        return JsonResponse({"address": address.to_dict()})
    messages.success(request, f"{address.label} jadi alamat utama.")
    return redirect("map:addresses")


# ---------------------------------------------------------------------------
# Pengelolaan lokasi tenan (hanya akun tenan pemilik)
# ---------------------------------------------------------------------------


def _get_own_tenant(user):
    try:
        return Tenant.objects.get(owner=user)
    except Tenant.DoesNotExist:
        raise Http404("Profil tenan tidak ditemukan.") from None


@tenant_required
@require_http_methods(["GET", "POST"])
def tenant_location(request):
    tenant = _get_own_tenant(request.user)
    location = TenantLocation.objects.filter(tenant=tenant).first()
    form = TenantLocationForm(
        _request_data(request) if request.method == "POST" else None,
        instance=location,
    )

    if request.method == "POST":
        if form.is_valid():
            location = save_tenant_location(form, tenant=tenant)
            if _wants_json(request):
                return JsonResponse(
                    {
                        "location": serialize_tenant_location(
                            location, 0, include_contact=True
                        )
                    }
                )
            messages.success(request, "Lokasi tenan tersimpan.")
            return redirect("map:tenant_location")
        if _wants_json(request):
            return JsonResponse({"errors": form.errors}, status=400)
        messages.error(request, "Periksa kembali data lokasi tenan.")

    if location:
        center = {
            "latitude": float(location.latitude),
            "longitude": float(location.longitude),
        }
    else:
        center = {"latitude": DEFAULT_CENTER[0], "longitude": DEFAULT_CENTER[1]}
    return render(
        request,
        "map/tenant_location.html",
        {
            "tenant": tenant,
            "location": location,
            "location_form": form,
            "center": center,
        },
        status=400 if request.method == "POST" else 200,
    )


@tenant_required
@require_POST
def tenant_location_delete(request):
    tenant = _get_own_tenant(request.user)
    deleted, _ = TenantLocation.objects.filter(tenant=tenant).delete()
    if _wants_json(request):
        return JsonResponse({"deleted": bool(deleted)})
    if deleted:
        messages.success(request, "Lokasi tenan dihapus dari peta.")
    return redirect("map:tenant_location")
