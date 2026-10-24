import math
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

LATITUDE_VALIDATORS = [
    MinValueValidator(Decimal(-90)),
    MaxValueValidator(Decimal(90)),
]
LONGITUDE_VALIDATORS = [
    MinValueValidator(Decimal(-180)),
    MaxValueValidator(Decimal(180)),
]

EARTH_RADIUS_KM = 6371.0


def distance_km(lat1, lon1, lat2, lon2):
    """Jarak garis lurus (haversine) antara dua titik, dalam kilometer."""
    lat1, lon1, lat2, lon2 = (math.radians(float(v)) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class TenantLocation(models.Model):
    class Category(models.TextChoices):
        HEALTHY_BOWL = "healthy-bowl", "Healthy bowl"
        SALAD = "salad", "Salad & wraps"
        PLANT_BASED = "plant-based", "Plant-based"
        SMOOTHIE = "smoothie", "Smoothie & jus"
        LOCAL = "local", "Masakan lokal"

    tenant = models.OneToOneField(
        "accounts.Tenant",
        on_delete=models.CASCADE,
        related_name="location",
    )
    address = models.CharField("Alamat", max_length=255)
    district = models.CharField("Kecamatan/area", max_length=100, blank=True)
    city = models.CharField("Kota", max_length=100)
    category = models.CharField(
        "Kategori makanan",
        max_length=20,
        choices=Category.choices,
        default=Category.HEALTHY_BOWL,
    )
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=LATITUDE_VALIDATORS
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=LONGITUDE_VALIDATORS
    )
    opening_time = models.TimeField("Jam buka", default="08:00")
    closing_time = models.TimeField("Jam tutup", default="21:00")
    delivery_radius_km = models.DecimalField(
        "Radius pengiriman (km)",
        max_digits=4,
        decimal_places=1,
        default=Decimal("3.0"),
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(50)],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tenant__name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name="tenant_location_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lte=180),
                name="tenant_location_longitude_range",
            ),
        ]

    def __str__(self):
        return f"Lokasi {self.tenant.name}"

    def is_open_at(self, moment):
        current = moment.time()
        if self.opening_time <= self.closing_time:
            return self.opening_time <= current < self.closing_time
        # Jam operasional melewati tengah malam, misalnya 18.00-02.00.
        return current >= self.opening_time or current < self.closing_time

    @property
    def is_open_now(self):
        return self.is_open_at(timezone.localtime())

    def distance_from(self, latitude, longitude):
        return distance_km(self.latitude, self.longitude, latitude, longitude)


class DeliveryAddress(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="delivery_addresses",
    )
    label = models.CharField("Label alamat", max_length=50)
    recipient_name = models.CharField("Nama penerima", max_length=100)
    phone_number = models.CharField("Nomor telepon penerima", max_length=30)
    address = models.CharField("Alamat lengkap", max_length=255)
    landmark = models.CharField("Patokan lokasi", max_length=150, blank=True)
    courier_note = models.CharField("Catatan untuk kurir", max_length=255, blank=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=LATITUDE_VALIDATORS
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=LONGITUDE_VALIDATORS
    )
    is_default = models.BooleanField("Jadikan alamat utama", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "-updated_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name="delivery_address_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lte=180),
                name="delivery_address_longitude_range",
            ),
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(is_default=True),
                name="unique_default_delivery_address",
            ),
        ]
        indexes = [models.Index(fields=["owner", "-updated_at"])]

    def __str__(self):
        return f"{self.label} - {self.owner}"

    def to_dict(self):
        return {
            "id": self.pk,
            "label": self.label,
            "recipient_name": self.recipient_name,
            "phone_number": self.phone_number,
            "address": self.address,
            "landmark": self.landmark,
            "courier_note": self.courier_note,
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
            "is_default": self.is_default,
            "updated_at": self.updated_at.isoformat(),
        }
