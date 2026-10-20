import json

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import DataError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    EmailAuthenticationForm,
    PhotoUploadForm,
    ProfileForm,
    RegistrationForm,
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
)
from .services import (
    add_allergy,
    delete_allergy,
    register_user,
    reset_eco_points,
    toggle_diet,
    update_profile,
    update_profile_photo,
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
    return render(request, "accounts/accounts.html", _account_context(request.user))


@login_required
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


@login_required
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


@login_required
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


@login_required
@require_POST
def upload_photo(request):
    form = PhotoUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        error = form.errors.get("photo", ["Foto tidak valid."])[0]
        return JsonResponse({"error": error}, status=400)
    profile = get_profile_for_user(request.user)
    update_profile_photo(profile=profile, photo=form.cleaned_data["photo"])
    return JsonResponse({"photo_url": profile.photo.url})


@login_required
@require_POST
def reset_eco_points_view(request):
    if request.POST.get("confirm") != "on":
        messages.error(request, "Konfirmasi diperlukan untuk mereset Eco Points.")
    else:
        reset_eco_points(profile=get_profile_for_user(request.user))
        messages.success(request, "Statistik Eco Points berhasil direset.")
    return redirect("accounts:accounts")


@login_required
@require_GET
def get_recommendations_api(request):
    menus = get_recommendations(get_profile_for_user(request.user))
    data = [
        {
            "id": menu.pk,
            "name": menu.name,
            "description": menu.description,
            "eco_points": menu.eco_points,
            "image_url": menu.image.url if getattr(menu, "image", None) else "",
        }
        for menu in menus
    ]
    return JsonResponse({"recommendations": data})


@require_GET
def admin_insights_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Autentikasi diperlukan."}, status=401)
    if not request.user.is_staff:
        return JsonResponse({"detail": "Akses staf diperlukan."}, status=403)
    return JsonResponse(get_admin_insights_data())
