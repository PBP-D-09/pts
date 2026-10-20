from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.accounts, name="accounts"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.update_profile_view, name="update_profile"),
    path("profile/photo/", views.upload_photo, name="upload_photo"),
    path("preferences/diets/", views.toggle_diet_view, name="toggle_diet"),
    path("preferences/allergies/", views.manage_allergy, name="manage_allergy"),
    path("eco-points/reset/", views.reset_eco_points_view, name="reset_eco_points"),
    path(
        "api/recommendations/",
        views.get_recommendations_api,
        name="recommendations_api",
    ),
    path("api/admin/insights/", views.admin_insights_api, name="admin_insights_api"),
]
