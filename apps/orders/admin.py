from django.contrib import admin, messages

from .models import Cart, CartItem, Order, OrderItem, ReusableContainerStock
from .services import mark_containers_returned


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("subtotal",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "session_key",
        "total_items",
        "formatted_subtotal",
        "updated_at",
    )
    search_fields = ("user__email", "session_key")
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("subtotal",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_code",
        "user",
        "status",
        "packaging_type",
        "formatted_total_price",
        "reusable_returned",
        "created_at",
    )
    list_filter = ("status", "packaging_type", "reusable_returned", "created_at")
    search_fields = ("order_code", "user__email", "delivery_address")
    readonly_fields = (
        "subtotal",
        "packaging_fee",
        "delivery_fee",
        "total_price",
        "eco_points",
        "reusable_containers",
    )
    inlines = [OrderItemInline]
    actions = ["mark_reusable_returned"]

    @admin.action(description="Mark reusable containers as returned")
    def mark_reusable_returned(self, request, queryset):
        returned = sum(mark_containers_returned(order) for order in queryset)
        self.message_user(
            request,
            f"{returned} order(s) marked as returned. "
            "Only delivered orders with reusable containers are updated.",
            messages.SUCCESS if returned else messages.WARNING,
        )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "item_name",
        "tenant_name",
        "price",
        "quantity",
        "subtotal",
    )
    search_fields = ("order__order_code", "item_name", "tenant_name")


@admin.register(ReusableContainerStock)
class ReusableContainerStockAdmin(admin.ModelAdmin):
    list_display = ("tenant", "quantity", "is_low", "updated_at")
    list_editable = ("quantity",)
    search_fields = ("tenant__name",)

    @admin.display(boolean=True, description="Low stock")
    def is_low(self, obj):
        return obj.is_low
