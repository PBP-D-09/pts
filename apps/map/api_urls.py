from django.urls import path

from . import api_views

app_name = "map_api"

urlpatterns = [
    path("tenants/", api_views.tenant_locations_api, name="tenants"),
    path("tenants/filters/", api_views.tenant_filters_api, name="tenant-filters"),
    path("search/", api_views.search_api, name="search"),
    path("reverse/", api_views.reverse_api, name="reverse"),
    path("addresses/", api_views.addresses_api, name="addresses"),
    path(
        "addresses/<int:pk>/",
        api_views.address_detail_api,
        name="address-detail",
    ),
    path(
        "addresses/<int:pk>/default/",
        api_views.address_set_default_api,
        name="address-set-default",
    ),
    path(
        "tenant/location/",
        api_views.tenant_location_api,
        name="tenant-location",
    ),
]
