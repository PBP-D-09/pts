from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.show_catalog, name="show_catalog"),
    path(
        "tenants/<int:tenant_id>/",
        views.show_catalog_tenant,
        name="show_catalog_tenant",
    ),
    path("tenants/menu-item-form", views.show_menuItem_form, name="show_menuItem_form"),
    path("tenants/menu-item/save", views.save_menuItem, name="save_menuItem"),
    path("api/tenant/", views.get_tenants_json, name="get_tenants_json"),
]
