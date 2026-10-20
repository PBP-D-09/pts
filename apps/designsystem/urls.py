from django.urls import path

from . import views

app_name = "designsystem"

urlpatterns = [
    path("", views.index, name="index"),
]
