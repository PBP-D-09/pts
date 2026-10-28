from django.apps import apps
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Trim
from django.utils import timezone

from .models import CustomUser, DietPreference, EcoPointActivity, Tenant, UserProfile

UNKNOWN_ALLERGEN_INFO = "no allergen information listed"


def get_profile_for_user(user):
    return UserProfile.objects.select_related("user").get(user=user)


def get_tenant_for_user(user):
    return Tenant.objects.select_related("owner").get(owner=user)


def get_diet_preference(code):
    return DietPreference.objects.get(code=code)


def get_diet_preferences():
    return DietPreference.objects.all()


def get_selected_diet_codes(profile):
    return set(profile.diets.values_list("code", flat=True))


def get_account_dashboard(profile):
    month_start = timezone.localdate().replace(day=1)
    monthly_points = (
        profile.active_point_activities()
        .filter(created_at__date__gte=month_start)
        .aggregate(total=Sum("points"))["total"]
        or 0
    )
    return {
        "profile": profile,
        "diet_preferences": get_diet_preferences(),
        "selected_diet_codes": get_selected_diet_codes(profile),
        "recommendations": get_recommendations(profile),
        "unsupported_diets": get_unsupported_recommendation_diets(profile),
        "monthly_points": monthly_points,
    }


def get_unsupported_recommendation_diets(profile):
    return list(
        profile.diets.exclude(code=DietPreference.Code.VEGETARIAN).values_list(
            "label", flat=True
        )
    )


def get_recommendations(profile):
    try:
        menu_model = apps.get_model("catalog", "MenuItem")
    except LookupError:
        return []

    if get_unsupported_recommendation_diets(profile):
        return menu_model.objects.none()

    queryset = menu_model.objects.filter(tenantId__isnull=False).select_related(
        "tenantId", "category"
    )
    if profile.diets.filter(code=DietPreference.Code.VEGETARIAN).exists():
        queryset = queryset.filter(vegetarian=True)

    allergy_names = [
        name.strip()
        for name in profile.allergies.values_list("name", flat=True)
        if name.strip()
    ]
    if allergy_names:
        queryset = queryset.annotate(
            normalized_allergen_info=Trim("allergen_info")
        ).exclude(
            Q(allergen_info__isnull=True)
            | Q(normalized_allergen_info="")
            | Q(allergen_info__iexact=UNKNOWN_ALLERGEN_INFO)
        )
        for allergy_name in allergy_names:
            queryset = queryset.exclude(allergen_info__icontains=allergy_name)
    return queryset.order_by("tenantId__name", "name")[:3]


def get_admin_insights_data():
    recent_users = CustomUser.objects.order_by("-date_joined")[:8]
    diet_distribution = DietPreference.objects.annotate(
        user_count=Count("profiles")
    ).order_by("-user_count", "label")
    active_activities = EcoPointActivity.objects.filter(
        Q(profile__eco_points_reset_at__isnull=True)
        | Q(created_at__gte=F("profile__eco_points_reset_at"))
    )
    return {
        "summary": {
            "total_users": CustomUser.objects.count(),
            "total_eco_points": active_activities.aggregate(total=Sum("points"))[
                "total"
            ]
            or 0,
        },
        "diet_distribution": [
            {"code": diet.code, "label": diet.label, "user_count": diet.user_count}
            for diet in diet_distribution
        ],
        "recent_users": [
            {
                "id": user.pk,
                "name": user.first_name or user.email,
                "email": user.email,
                "date_joined": user.date_joined.isoformat(),
            }
            for user in recent_users
        ],
    }
