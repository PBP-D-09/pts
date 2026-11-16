from django.db import DataError
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from . import selectors, services
from .forms import PhotoUploadForm
from .models import DietPreference, UserAllergy
from .permissions import IsCustomer, IsTenant
from .serializers import (
    CustomUserSerializer,
    DietActivitySerializer,
    DietPreferenceSerializer,
    EcoPointActivitySerializer,
    LoginSerializer,
    MenuItemRecommendationSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    TenantRegisterSerializer,
    TenantSerializer,
    TenantUpdateSerializer,
    UserAllergySerializer,
    UserProfileSerializer,
)


def _issue_token(user):
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


# --- Auth ---------------------------------------------------------------


@api_view(["POST"])
@permission_classes([AllowAny])
def register_api(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response(
        {"token": _issue_token(user), "user": CustomUserSerializer(user).data},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def register_tenant_api(request):
    serializer = TenantRegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response(
        {"token": _issue_token(user), "user": CustomUserSerializer(user).data},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login_api(request):
    serializer = LoginSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data["user"]
    return Response(
        {"token": _issue_token(user), "user": CustomUserSerializer(user).data}
    )


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def logout_api(request):
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def me_api(request):
    return Response(CustomUserSerializer(request.user).data)


# --- Profil pelanggan -----------------------------------------------------


@api_view(["GET", "PATCH", "PUT"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def profile_api(request):
    profile = selectors.get_profile_for_user(request.user)

    if request.method == "GET":
        return Response(UserProfileSerializer(profile).data)

    serializer = ProfileUpdateSerializer(
        data=request.data,
        context={"request": request},
        partial=(request.method == "PATCH"),
    )
    serializer.is_valid(raise_exception=True)
    services.update_profile(profile=profile, **serializer.validated_data)
    profile.refresh_from_db()
    return Response(UserProfileSerializer(profile).data)


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def profile_photo_api(request):
    form = PhotoUploadForm(request.data, request.FILES)
    if not form.is_valid():
        error = form.errors.get("photo", ["Foto tidak valid."])[0]
        return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
    profile = selectors.get_profile_for_user(request.user)
    services.update_profile_photo(profile=profile, photo=form.cleaned_data["photo"])
    return Response({"photo_url": profile.photo.url})


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def diets_api(request):
    profile = selectors.get_profile_for_user(request.user)
    diets = selectors.get_diet_preferences()
    selected = selectors.get_selected_diet_codes(profile)
    data = DietPreferenceSerializer(diets, many=True).data
    for item in data:
        item["selected"] = item["code"] in selected
    return Response(data)


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def diets_toggle_api(request):
    try:
        diet = selectors.get_diet_preference(request.data.get("code"))
    except DietPreference.DoesNotExist:
        return Response(
            {"detail": "Preferensi diet tidak ditemukan."},
            status=status.HTTP_404_NOT_FOUND,
        )
    profile = selectors.get_profile_for_user(request.user)
    is_selected = services.toggle_diet(profile=profile, diet=diet)
    return Response({"code": diet.code, "selected": is_selected})


@api_view(["GET", "POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def allergies_api(request):
    profile = selectors.get_profile_for_user(request.user)

    if request.method == "GET":
        return Response(UserAllergySerializer(profile.allergies.all(), many=True).data)

    name = request.data.get("name", "")
    allergy = services.add_allergy(profile=profile, name=name)
    if allergy is None:
        return Response(
            {"detail": "Nama alergi tidak boleh kosong."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(UserAllergySerializer(allergy).data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def allergy_detail_api(request, pk):
    profile = selectors.get_profile_for_user(request.user)
    try:
        services.delete_allergy(profile=profile, allergy_id=pk)
    except UserAllergy.DoesNotExist, DataError, OverflowError, TypeError, ValueError:
        return Response(
            {"detail": "Alergi tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND
        )
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def eco_points_api(request):
    profile = selectors.get_profile_for_user(request.user)
    return Response({"eco_points": profile.eco_points, "co2_saved": profile.co2_saved})


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def eco_points_history_api(request):
    profile = selectors.get_profile_for_user(request.user)
    activities = profile.active_point_activities()
    return Response(EcoPointActivitySerializer(activities, many=True).data)


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def eco_points_reset_api(request):
    if not request.data.get("confirm"):
        return Response(
            {"detail": "Konfirmasi diperlukan untuk mereset Eco Points."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    profile = selectors.get_profile_for_user(request.user)
    services.reset_eco_points(profile=profile)
    return Response({"eco_points": profile.eco_points, "co2_saved": profile.co2_saved})


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def diet_activities_api(request):
    profile = selectors.get_profile_for_user(request.user)
    return Response(
        DietActivitySerializer(profile.diet_activities.all(), many=True).data
    )


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsCustomer])
def recommendations_api(request):
    profile = selectors.get_profile_for_user(request.user)
    menus = selectors.get_recommendations(profile)
    return Response(
        {
            "recommendations": MenuItemRecommendationSerializer(menus, many=True).data,
            "unsupported_diets": selectors.get_unsupported_recommendation_diets(
                profile
            ),
        }
    )


# --- Profil tenant ----------------------------------------------------


@api_view(["GET", "PATCH", "PUT"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsTenant])
def tenant_api(request):
    tenant = selectors.get_tenant_for_user(request.user)

    if request.method == "GET":
        return Response(TenantSerializer(tenant).data)

    serializer = TenantUpdateSerializer(
        data=request.data,
        context={"request": request},
        partial=(request.method == "PATCH"),
    )
    serializer.is_valid(raise_exception=True)
    validated = dict(serializer.validated_data)
    cuisines = validated.pop("cuisines", None)
    services.update_tenant(tenant=tenant, cuisines=cuisines, **validated)
    tenant.refresh_from_db()
    return Response(TenantSerializer(tenant).data)


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsTenant])
def tenant_photo_api(request):
    form = PhotoUploadForm(request.data, request.FILES)
    if not form.is_valid():
        error = form.errors.get("photo", ["Foto tidak valid."])[0]
        return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
    tenant = selectors.get_tenant_for_user(request.user)
    services.update_tenant_photo(tenant=tenant, photo=form.cleaned_data["photo"])
    return Response({"photo_url": tenant.photo.url})


# --- Admin --------------------------------------------------------------


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_insights_api(request):
    return Response(selectors.get_admin_insights_data())
