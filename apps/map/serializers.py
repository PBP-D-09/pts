from decimal import ROUND_HALF_UP, Decimal

from rest_framework import serializers

from . import services
from .forms import TenantFilterForm
from .models import DeliveryAddress, TenantLocation

MIN_SEARCH_LENGTH = 3
MAX_SEARCH_LENGTH = 150


class CoordinateField(serializers.DecimalField):
    """Koordinat sebagai angka JSON (bukan string).

    GPS di ponsel biasanya memberi lebih dari 6 angka di belakang koma, jadi
    nilainya dibulatkan ke 6 desimal (sekitar 0,1 m) alih-alih ditolak.
    """

    def __init__(self, limit, **kwargs):
        super().__init__(
            max_digits=9,
            decimal_places=6,
            min_value=Decimal(-limit),
            max_value=Decimal(limit),
            rounding=ROUND_HALF_UP,
            coerce_to_string=False,
            **kwargs,
        )

    def validate_precision(self, value):
        return super().validate_precision(self.quantize(value))


class DeliveryAddressSerializer(serializers.ModelSerializer):
    latitude = CoordinateField(90)
    longitude = CoordinateField(180)

    class Meta:
        model = DeliveryAddress
        fields = [
            "id",
            "label",
            "recipient_name",
            "phone_number",
            "address",
            "landmark",
            "courier_note",
            "latitude",
            "longitude",
            "is_default",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]
        # Aturan satu alamat utama per pengguna dijaga oleh service
        # (alamat utama lama otomatis dilepas), bukan ditolak di sini.
        validators = []

    def create(self, validated_data):
        address = DeliveryAddress(**validated_data)
        return services.persist_delivery_address(
            address, owner=self.context["request"].user
        )

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        return services.persist_delivery_address(instance, owner=instance.owner)


class TenantLocationSerializer(serializers.ModelSerializer):
    latitude = CoordinateField(90)
    longitude = CoordinateField(180)
    opening_time = serializers.TimeField(format="%H:%M")
    closing_time = serializers.TimeField(format="%H:%M")
    delivery_radius_km = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=Decimal("0.5"),
        max_value=Decimal(50),
        required=False,
        coerce_to_string=False,
    )

    class Meta:
        model = TenantLocation
        fields = [
            "address",
            "district",
            "city",
            "category",
            "opening_time",
            "closing_time",
            "delivery_radius_km",
            "latitude",
            "longitude",
        ]

    def create(self, validated_data):
        location = TenantLocation(**validated_data)
        return services.persist_tenant_location(location, tenant=self.context["tenant"])

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        return services.persist_tenant_location(instance, tenant=instance.tenant)


class TenantFilterSerializer(serializers.Serializer):
    """Query parameter filter peta tenan (sama dengan TenantFilterForm di web)."""

    q = serializers.CharField(required=False, allow_blank=True, max_length=100)
    city = serializers.CharField(required=False, allow_blank=True, max_length=100)
    category = serializers.ChoiceField(
        required=False,
        allow_blank=True,
        choices=TenantLocation.Category.choices,
    )
    open_now = serializers.BooleanField(required=False, default=False)
    radius = serializers.ChoiceField(
        required=False,
        allow_blank=True,
        choices=[value for value, _label in TenantFilterForm.RADIUS_CHOICES if value],
    )
    lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    lng = serializers.FloatField(required=False, min_value=-180, max_value=180)

    def validate(self, attrs):
        if ("lat" in attrs) != ("lng" in attrs):
            raise serializers.ValidationError(
                "Parameter lat dan lng harus dikirim bersamaan."
            )
        return attrs


class PlaceSearchSerializer(serializers.Serializer):
    q = serializers.CharField(
        min_length=MIN_SEARCH_LENGTH,
        max_length=MAX_SEARCH_LENGTH,
        error_messages={
            "min_length": f"Masukkan minimal {MIN_SEARCH_LENGTH} karakter.",
            "blank": f"Masukkan minimal {MIN_SEARCH_LENGTH} karakter.",
        },
    )


class ReverseGeocodeSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
