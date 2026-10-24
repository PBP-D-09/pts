from django.contrib import admin

from .models import DeliveryAddress, TenantLocation


@admin.register(TenantLocation)
class TenantLocationAdmin(admin.ModelAdmin):
    list_display = ("tenant", "city", "district", "category", "updated_at")
    list_filter = ("city", "category")
    search_fields = ("tenant__name", "address", "district")


@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ("label", "owner", "recipient_name", "is_default", "updated_at")
    list_filter = ("is_default",)
    search_fields = ("label", "owner__email", "recipient_name", "address")
