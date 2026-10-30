# Create your views here.
from django.contrib import messages
from django.core import serializers
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import tenant_required
from apps.accounts.models import Tenant

from .forms import MenuCategoryForm, MenuItemForm
from .models import MenuCategory, MenuItem


def show_catalog(request):
    return render(request, "catalog/catalog.html")


def show_catalog_tenant(request, tenant_id):
    tenant = get_object_or_404(Tenant, pk=tenant_id)

    context = {"tenant": tenant}
    return render(request, "catalog/catalog_tenant.html", context)


def show_tenant_manage(request, tenant_id):
    tenant = get_object_or_404(Tenant, pk=tenant_id)
    menuItems = MenuItem.objects.filter(tenantId=tenant.pk)
    menuCategories = MenuCategory.objects.filter(tenantId=tenant.pk)

    context = {"tenant": tenant, "menu_items": menuItems, "categories": menuCategories}
    return render(request, "catalog/tenant_manage.html", context)


@tenant_required
def show_menuItem_form(request, item_id=None):
    if item_id is not None:
        menu = get_object_or_404(MenuItem, pk=item_id, tenantId=request.user.tenant)
        form = MenuItemForm(instance=menu)
    else:
        form = MenuItemForm()

    context = {"form": form, "category": "item", "item_id": item_id}
    return render(request, "catalog/menu_form.html", context)


@tenant_required
def show_menuCategory_form(request, category_id=None):
    if category_id is not None:
        category = get_object_or_404(
            MenuCategory, pk=category_id, tenantId=request.user.tenant
        )
        form = MenuCategoryForm(instance=category)
    else:
        form = MenuCategoryForm()

    context = {"form": form, "category": "category", "category_id": category_id}
    return render(request, "catalog/menu_form.html", context)


@require_POST
def save_menuItem(request, item_id=None):
    if item_id is not None:
        menu = get_object_or_404(MenuItem, pk=item_id, tenantId=request.user.tenant)
    else:
        menu = None

    form = MenuItemForm(request.POST, request.FILES, instance=menu)

    if form.is_valid():
        item = form.save(commit=False)

        if item_id is not None:
            messages.success(request, "a menu update has been made!")
        else:
            item.tenantId = request.user.tenant
            messages.success(request, "a menu has been made!")

        item.save()
    else:
        messages.error(
            request, "The form is invalid. Please check your input and try again."
        )

    return redirect("catalog:show_tenant_manage", tenant_id=request.user.tenant.pk)


@require_POST
def delete_menuItem(request, item_id):
    menu = get_object_or_404(MenuItem, pk=item_id)

    menu.delete()
    messages.success(request, "a menu has been deleted.")

    return redirect("catalog:show_tenant_manage", tenant_id=request.user.tenant.pk)


@require_POST
def save_menuCategory(request, category_id=None):
    if category_id is not None:
        category = get_object_or_404(
            MenuCategory, pk=category_id, tenantId=request.user.tenant
        )
    else:
        category = None

    form = MenuCategoryForm(request.POST, instance=category)

    if form.is_valid():
        category = form.save(commit=False)

        if category_id is not None:
            messages.success(request, "A category update has been made!")
        else:
            category.tenantId = request.user.tenant
            messages.success(request, "A category has been created!")

        category.save()
    else:
        messages.error(
            request, "The form is invalid. Please check your input and try again."
        )

    return redirect("catalog:show_tenant_manage", tenant_id=request.user.tenant.pk)


@require_POST
def delete_menuCategory(request, category_id):
    category = get_object_or_404(MenuCategory, pk=category_id)

    category.delete()
    messages.success(request, "a menu has been deleted.")

    return redirect("catalog:show_tenant_manage", tenant_id=request.user.tenant.pk)


def get_tenants_json(request):
    title_query = request.GET.get("title", "").strip()
    tenants = Tenant.objects.all()

    if title_query:
        tenants = Tenant.filter(title__icontains=title_query)

    tenants_json = serializers.serialize("json", tenants)
    return HttpResponse(tenants_json, content_type="application/json")
