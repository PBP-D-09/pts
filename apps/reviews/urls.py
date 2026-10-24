from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("menu/<slug:menu_key>/", views.reviews, name="menu"),
    path("menu/<slug:menu_key>/create/", views.create_review, name="create"),
    path("<int:pk>/edit/", views.edit_review, name="edit"),
    path("<int:pk>/delete/", views.delete_review, name="delete"),
    path("<int:pk>/helpful/", views.helpful, name="helpful"),
]
