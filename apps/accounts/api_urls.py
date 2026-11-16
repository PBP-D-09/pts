from django.urls import path

from . import api_views

app_name = "accounts_api"

urlpatterns = [
    path("register/", api_views.register_api, name="register"),
    path(
        "register/tenant/",
        api_views.register_tenant_api,
        name="register-tenant",
    ),
    path("login/", api_views.login_api, name="login"),
    path("logout/", api_views.logout_api, name="logout"),
    path("me/", api_views.me_api, name="me"),
    path("profile/", api_views.profile_api, name="profile"),
    path(
        "profile/photo/",
        api_views.profile_photo_api,
        name="profile-photo",
    ),
    path("diets/", api_views.diets_api, name="diets"),
    path(
        "diets/toggle/",
        api_views.diets_toggle_api,
        name="diets-toggle",
    ),
    path("allergies/", api_views.allergies_api, name="allergies"),
    path(
        "allergies/<int:pk>/",
        api_views.allergy_detail_api,
        name="allergy-detail",
    ),
    path("eco-points/", api_views.eco_points_api, name="eco-points"),
    path(
        "eco-points/history/",
        api_views.eco_points_history_api,
        name="eco-points-history",
    ),
    path(
        "eco-points/reset/",
        api_views.eco_points_reset_api,
        name="eco-points-reset",
    ),
    path(
        "diet-activities/",
        api_views.diet_activities_api,
        name="diet-activities",
    ),
    path(
        "recommendations/",
        api_views.recommendations_api,
        name="recommendations",
    ),
    path("tenant/", api_views.tenant_api, name="tenant"),
    path(
        "tenant/photo/",
        api_views.tenant_photo_api,
        name="tenant-photo",
    ),
    path(
        "admin/insights/",
        api_views.admin_insights_api,
        name="admin-insights",
    ),
]
