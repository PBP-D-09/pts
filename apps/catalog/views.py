# Create your views here.
from django.contrib import messages
from django.core import serializers
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import tenant_required
from apps.accounts.models import Tenant

from .forms import MenuItemForm


def show_catalog(request):
    return render(request, "catalog/catalog.html")


def show_catalog_tenant(request, tenant_id):
    tenant = get_object_or_404(Tenant, pk=tenant_id)

    context = {
        "tenant": tenant,
    }
    return render(request, "catalog/catalog_tenant.html", context)


@tenant_required
def show_menuItem_form(request):
    form = MenuItemForm(request.POST or None)
    context = {"form": form}
    return render(request, "catalog/menuItem_form.html", context)


def get_tenants_json(request):
    title_query = request.GET.get("title", "").strip()
    tenants = Tenant.objects.all()

    if title_query:
        tenants = Tenant.filter(title__icontains=title_query)

    tenants_json = serializers.serialize("json", tenants)
    return HttpResponse(tenants_json, content_type="application/json")


@tenant_required
@require_POST
def save_menuItem(request):
    form = MenuItemForm(request.POST or None)

    if form.is_valid:
        form.save()
        messages.success(request, "menu berhasil dibuat!")
        redirect("catalog:show_menuItem_form")
