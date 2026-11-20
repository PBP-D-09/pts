from django.urls import path

from . import api_views

app_name = "reviews_api"

urlpatterns = [
    path(
        "reviews/menus/<str:menu_uuid>/",
        api_views.menu_reviews_api,
        name="menu-reviews",
    ),
    path(
        "reviews/<str:pk>/",
        api_views.review_detail_api,
        name="review-detail",
    ),
    path(
        "reviews/<str:pk>/helpful/",
        api_views.helpful_api,
        name="review-helpful",
    ),
]
