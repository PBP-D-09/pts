import json

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import DataError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .decorators import customer_required, tenant_required
from .forms import (
    EmailAuthenticationForm,
    PhotoUploadForm,
    ProfileForm,
    RegistrationForm,
    TenantProfileForm,
    TenantRegistrationForm,
)
from .models import DietPreference, UserAllergy
from .selectors import (
    get_account_dashboard,
    get_admin_insights_data,
    get_diet_preference,
    get_diet_preferences,
    get_profile_for_user,
    get_recommendations,
    get_selected_diet_codes,
    get_tenant_for_user,
    get_unsupported_recommendation_diets,
)
from .services import (
    add_allergy,
    delete_allergy,
    register_tenant,
    register_user,
    reset_eco_points,
    toggle_diet,
    update_profile,
    update_profile_photo,
    update_tenant,
    update_tenant_photo,
)


def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None


def _account_context(user, profile_form=None):
    profile = get_profile_for_user(user)
    context = get_account_dashboard(profile)
    context["profile_form"] = profile_form or ProfileForm(instance=profile, user=user)
    return context


def _tenant_context(user, tenant_form=None):
    tenant = get_tenant_for_user(user)
    return {
        "tenant": tenant,
        "tenant_form": tenant_form or TenantProfileForm(instance=tenant, user=user),
    }


def _with_toast(response, message, level):
    response["HX-Trigger"] = json.dumps(
        {"showToast": {"message": message, "level": level}}
    )
    return response


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:accounts")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = register_user(
            full_name=form.cleaned_data["full_name"],
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password1"],
        )
        login(request, user)
        messages.success(
            request,
            "Akun berhasil dibuat. Lengkapi profilmu untuk mulai menerima rekomendasi.",
        )
        return redirect("accounts:accounts")
    return render(request, "accounts/register.html", {"form": form})


def register_tenant_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:accounts")
    form = TenantRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = register_tenant(
            tenant_name=form.cleaned_data["tenant_name"],
            full_name=form.cleaned_data["full_name"],
            email=form.cleaned_data["email"],
            phone_number=form.cleaned_data["phone_number"],
            password=form.cleaned_data["password1"],
        )
        login(request, user)
        messages.success(request, "Akun tenan berhasil dibuat.")
        return redirect("accounts:accounts")
    return render(request, "accounts/register_tenant.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:accounts")
    form = EmailAuthenticationForm(request, request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(_safe_next_url(request) or "accounts:accounts")
    if request.method == "POST":
        for error in form.non_field_errors():
            messages.error(request, error)
    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": _safe_next_url(request) or ""},
    )


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Kamu telah keluar dari akun.")
    return redirect("landing:landing")


@login_required
def accounts(request):
    if request.user.is_tenant:
        return render(
            request,
            "accounts/tenant_account.html",
            _tenant_context(request.user),
        )
    return render(request, "accounts/accounts.html", _account_context(request.user))


@customer_required
@require_POST
def update_profile_view(request):
    profile = get_profile_for_user(request.user)
    form = ProfileForm(request.POST, instance=profile, user=request.user)
    if not form.is_valid():
        if request.htmx:
            return _with_toast(
                render(
                    request,
                    "accounts/partials/profile_form.html",
                    {"profile_form": form},
                ),
                "Periksa kembali data yang kamu masukkan.",
                "error",
            )
        messages.error(request, "Periksa kembali data yang kamu masukkan.")
        return render(
            request,
            "accounts/accounts.html",
            _account_context(request.user, profile_form=form),
            status=400,
        )

    update_profile(profile=profile, **form.cleaned_data)
    if request.htmx:
        updated_user = profile.user
        return _with_toast(
            render(
                request,
                "accounts/partials/profile_update_response.html",
                {
                    "profile_form": ProfileForm(instance=profile, user=updated_user),
                    "display_name": updated_user.first_name or updated_user.email,
                },
            ),
            "Perubahan tersimpan.",
            "success",
        )
    messages.success(request, "Perubahan tersimpan.")
    return redirect("accounts:accounts")


@tenant_required
@require_POST
def update_tenant_view(request):
    tenant = get_tenant_for_user(request.user)
    form = TenantProfileForm(
        request.POST,
        instance=tenant,
        user=request.user,
    )
    if not form.is_valid():
        if request.htmx:
            return _with_toast(
                render(
                    request,
                    "accounts/partials/tenant_form.html",
                    {"tenant_form": form},
                ),
                "Periksa kembali data yang kamu masukkan.",
                "error",
            )
        messages.error(request, "Periksa kembali data yang kamu masukkan.")
        return render(
            request,
            "accounts/tenant_account.html",
            _tenant_context(request.user, tenant_form=form),
            status=400,
        )

    update_tenant(tenant=tenant, **form.cleaned_data)
    if request.htmx:
        return _with_toast(
            render(
                request,
                "accounts/partials/tenant_update_response.html",
                {
                    "tenant_form": TenantProfileForm(
                        instance=tenant,
                        user=tenant.owner,
                    ),
                    "display_name": tenant.owner.display_name,
                },
            ),
            "Perubahan tersimpan.",
            "success",
        )
    messages.success(request, "Perubahan tersimpan.")
    return redirect("accounts:accounts")


@customer_required
@require_POST
def toggle_diet_view(request):
    try:
        diet = get_diet_preference(request.POST.get("diet"))
    except DietPreference.DoesNotExist:
        raise Http404("Preferensi diet tidak ditemukan.")

    profile = get_profile_for_user(request.user)
    toggle_diet(profile=profile, diet=diet)
    return render(
        request,
        "accounts/partials/diet_preferences.html",
        {
            "diet_preferences": get_diet_preferences(),
            "selected_diet_codes": get_selected_diet_codes(profile),
        },
    )


@customer_required
@require_POST
def manage_allergy(request):
    profile = get_profile_for_user(request.user)
    allergy_id = request.POST.get("delete")
    try:
        if allergy_id:
            delete_allergy(profile=profile, allergy_id=allergy_id)
        else:
            add_allergy(profile=profile, name=request.POST.get("name", ""))
    except (
        UserAllergy.DoesNotExist,
        DataError,
        OverflowError,
        TypeError,
        ValueError,
    ):
        raise Http404("Alergi tidak ditemukan.")
    return render(request, "accounts/partials/allergies.html", {"profile": profile})


@customer_required
@require_POST
def upload_photo(request):
    form = PhotoUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        error = form.errors.get("photo", ["Foto tidak valid."])[0]
        return JsonResponse({"error": error}, status=400)
    profile = get_profile_for_user(request.user)
    update_profile_photo(profile=profile, photo=form.cleaned_data["photo"])
    return JsonResponse({"photo_url": profile.photo.url})


@tenant_required
@require_POST
def upload_tenant_photo(request):
    form = PhotoUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        error = form.errors.get("photo", ["Foto tidak valid."])[0]
        return JsonResponse({"error": error}, status=400)
    tenant = get_tenant_for_user(request.user)
    update_tenant_photo(tenant=tenant, photo=form.cleaned_data["photo"])
    return JsonResponse({"photo_url": tenant.photo.url})


@customer_required
@require_POST
def reset_eco_points_view(request):
    if request.POST.get("confirm") != "on":
        messages.error(request, "Konfirmasi diperlukan untuk mereset Eco Points.")
    else:
        reset_eco_points(profile=get_profile_for_user(request.user))
        messages.success(request, "Statistik Eco Points berhasil direset.")
    return redirect("accounts:accounts")


@customer_required
@require_GET
def get_recommendations_api(request):
    profile = get_profile_for_user(request.user)
    menus = get_recommendations(profile)
    data = [
        {
            "id": str(menu.pk),
            "name": menu.name,
            "description": menu.description,
            "price": menu.price,
            "photo_url": menu.photo.url if menu.photo else "",
            "vegetarian": menu.vegetarian,
            "allergen_info": menu.allergen_info,
            "tenant_id": menu.tenantId_id,
            "tenant_name": menu.tenantId.name,
            "tenant_url": reverse(
                "catalog:show_catalog_tenant", args=[menu.tenantId_id]
            ),
        }
        for menu in menus
    ]
    return JsonResponse(
        {
            "recommendations": data,
            "unsupported_diets": get_unsupported_recommendation_diets(profile),
        }
    )


@require_GET
def admin_insights_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Autentikasi diperlukan."}, status=401)
    if not request.user.is_staff:
        return JsonResponse({"detail": "Akses staf diperlukan."}, status=403)
    return JsonResponse(get_admin_insights_data())
