from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
	path("", views.show_catalog, name="show_catalog"),
	path("tenants/<int:tenant_id>/", views.show_catalog_tenant, name="show_catalog_tenant"),
	path("tenants/<int:tenant_id>/manage/", views.show_tenant_manage, name="show_tenant_manage"),
	path("tenants/menu-item/add/", views.show_menuItem_form, name="show_menuItem_form"),
	path("tenants/menu-item/<int:item_id>/edit/", views.show_menuItem_form, name="edit_menuItem_form"),
	path("tenants/menu-item/save/", views.save_menuItem, name="add_menuItem"),
	path("tenants/menu-item/<int:item_id>/save/", views.save_menuItem, name="update_menuItem"),
	path("tenants/menu-item/<int:item_id>/delete/", views.delete_menuItem, name="delete_menuItem"),
	path("tenants/menu-category/add/", views.show_menuCategory_form, name="show_menuCategory_form"),
	path("tenants/menu-category/<int:category_id>/edit/", views.show_menuCategory_form, name="edit_menuCategory_form"),
	path("tenants/menu-category/save/", views.save_menuCategory, name="add_menuCategory"),
	path("tenants/menu-category/<int:category_id>/save/", views.save_menuCategory, name="update_menuCategory"),
	path("tenants/menu-category/<int:category_id>/delete/", views.delete_menuCategory, name="delete_menuCategory"),
	path("api/tenant/", views.get_tenants_json, name="get_tenants_json"),
]