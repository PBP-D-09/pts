from rest_framework import serializers

from apps.catalog.models import MenuItem
from apps.map.models import DeliveryAddress

from . import services
from .forms import NOTE_MAX_LENGTH
from .models import CartItem, Order, OrderItem

# --- Output -------------------------------------------------------------


class CartItemSerializer(serializers.ModelSerializer):
    menu_item_id = serializers.UUIDField(source="menu_item.id", read_only=True)
    name = serializers.CharField(source="menu_item.name", read_only=True)
    tenant_name = serializers.SerializerMethodField()
    tenant_area = serializers.SerializerMethodField()
    price = serializers.IntegerField(source="menu_item.price", read_only=True)
    photo_url = serializers.SerializerMethodField()
    subtotal = serializers.IntegerField(read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "menu_item_id",
            "name",
            "tenant_name",
            "tenant_area",
            "price",
            "photo_url",
            "quantity",
            "subtotal",
        ]

    def get_tenant_name(self, item):
        tenant = item.menu_item.tenantId
        return tenant.name if tenant else ""

    def get_tenant_area(self, item):
        return services.tenant_area(item.menu_item.tenantId)

    def get_photo_url(self, item):
        photo = item.menu_item.photo
        if not photo:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(photo.url) if request else photo.url


class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "menu_item_id",
            "item_name",
            "tenant_name",
            "price",
            "quantity",
            "subtotal",
        ]


class OrderSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display")
    packaging_display = serializers.CharField(source="get_packaging_type_display")
    total_items_count = serializers.IntegerField()
    can_cancel = serializers.BooleanField()
    can_edit_note = serializers.BooleanField()
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_code",
            "status",
            "status_display",
            "packaging_type",
            "packaging_display",
            "reusable_returned",
            "reusable_containers",
            "delivery_address",
            "delivery_notes",
            "delivery_eta_minutes",
            "subtotal",
            "packaging_fee",
            "delivery_fee",
            "total_price",
            "eco_points",
            "total_items_count",
            "can_cancel",
            "can_edit_note",
            "created_at",
            "updated_at",
            "items",
        ]
        read_only_fields = fields


class CheckoutAddressSerializer(serializers.ModelSerializer):
    """Alamat tersimpan beserta ongkir dan estimasi waktu ke tenant di keranjang.
    Atribut `quote` diisi oleh view (lihat services.quote_delivery)."""

    delivery_fee = serializers.IntegerField(source="quote.fee")
    eta_minutes = serializers.IntegerField(source="quote.eta_minutes")

    class Meta:
        model = DeliveryAddress
        fields = [
            "id",
            "label",
            "recipient_name",
            "phone_number",
            "address",
            "landmark",
            "is_default",
            "delivery_fee",
            "eta_minutes",
        ]
        read_only_fields = fields


# --- Input --------------------------------------------------------------


class CartItemAddSerializer(serializers.Serializer):
    menu_item_id = serializers.PrimaryKeyRelatedField(
        queryset=MenuItem.objects.all(),
        error_messages={"does_not_exist": "Menu tidak ditemukan."},
    )
    quantity = serializers.IntegerField(min_value=1, default=1)


class CartItemUpdateSerializer(serializers.Serializer):
    # Kuantitas minimal 1; menghapus item dilakukan lewat DELETE.
    quantity = serializers.IntegerField(min_value=1)


class CheckoutSerializer(serializers.Serializer):
    address_id = serializers.PrimaryKeyRelatedField(
        queryset=DeliveryAddress.objects.none(),
        error_messages={
            "required": "Choose a delivery address.",
            "does_not_exist": "Choose one of your saved addresses.",
        },
    )
    packaging_type = serializers.ChoiceField(
        choices=Order.PackagingType.choices,
        error_messages={"required": "Choose a packaging option."},
    )
    delivery_notes = serializers.CharField(
        max_length=NOTE_MAX_LENGTH, allow_blank=True, default=""
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hanya alamat milik user sendiri yang boleh dipilih.
        user = self.context["request"].user
        self.fields["address_id"].queryset = DeliveryAddress.objects.filter(owner=user)


class OrderNoteSerializer(serializers.Serializer):
    delivery_notes = serializers.CharField(max_length=NOTE_MAX_LENGTH, allow_blank=True)
