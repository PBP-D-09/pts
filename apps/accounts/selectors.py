from django.apps import apps
from django.db.models import Count, Sum
from django.utils import timezone

from .models import CustomUser, DietPreference, EcoPointActivity, UserProfile


def get_profile_for_user(user):
    return UserProfile.objects.select_related("user").get(user=user)


def get_diet_preference(code):
    return DietPreference.objects.get(code=code)


def get_diet_preferences():
    return DietPreference.objects.all()


def get_selected_diet_codes(profile):
    return set(profile.diets.values_list("code", flat=True))


def get_account_dashboard(profile):
    month_start = timezone.localdate().replace(day=1)
    monthly_points = (
        profile.point_activities.filter(created_at__date__gte=month_start).aggregate(
            total=Sum("points")
        )["total"]
        or 0
    )
    return {
        "profile": profile,
        "diet_preferences": get_diet_preferences(),
        "selected_diet_codes": get_selected_diet_codes(profile),
        "recommendations": get_recommendations(profile),
        "point_activities": profile.point_activities.all()[:5],
        "diet_activities": profile.diet_activities.all()[:5],
        "monthly_points": monthly_points,
    }


def get_recommendations(profile):
    try:
        menu_model = apps.get_model("catalog", "MenuItem")
    except LookupError:
        return []

    field_names = {field.name for field in menu_model._meta.get_fields()}
    required = {"name", "description", "eco_points", "diet_tags", "allergen_tags"}
    if not required.issubset(field_names):
        return []

    diet_codes = list(profile.diets.values_list("code", flat=True))
    allergy_names = list(profile.allergies.values_list("name", flat=True))
    if not diet_codes:
        return []

    queryset = menu_model.objects.all()
    if "is_available" in field_names:
        queryset = queryset.filter(is_available=True)
    queryset = queryset.filter(diet_tags__code__in=diet_codes).distinct()
    if allergy_names:
        queryset = queryset.exclude(allergen_tags__name__in=allergy_names)
    return queryset[:3]


def get_admin_insights_data():
    recent_users = CustomUser.objects.order_by("-date_joined")[:8]
    diet_distribution = DietPreference.objects.annotate(
        user_count=Count("profiles")
    ).order_by("-user_count", "label")
    return {
        "summary": {
            "total_users": CustomUser.objects.count(),
            "total_eco_points": EcoPointActivity.objects.aggregate(total=Sum("points"))[
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
