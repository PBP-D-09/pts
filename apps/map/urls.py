from django.urls import path

from . import views

app_name = "map"

urlpatterns = [
    path("", views.map_view, name="map"),
    path("api/tenants/", views.tenant_locations_api, name="tenant_locations_api"),
    path("api/search/", views.search_api, name="search_api"),
    path("api/reverse/", views.reverse_api, name="reverse_api"),
    path("addresses/", views.address_list, name="addresses"),
    path("addresses/create/", views.address_create, name="address_create"),
    path("addresses/<int:pk>/edit/", views.address_edit, name="address_edit"),
    path("addresses/<int:pk>/update/", views.address_update, name="address_update"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
    path(
        "addresses/<int:pk>/default/",
        views.address_set_default,
        name="address_set_default",
    ),
    path("api/addresses/", views.address_list_api, name="address_list_api"),
    path(
        "api/addresses/<int:pk>/",
        views.address_detail_api,
        name="address_detail_api",
    ),
    path("tenant/location/", views.tenant_location, name="tenant_location"),
    path(
        "tenant/location/delete/",
        views.tenant_location_delete,
        name="tenant_location_delete",
    ),
]
