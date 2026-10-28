import random
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def format_rupiah(amount: int) -> str:
    """Helper untuk format mata uang Rupiah seperti 'Rp 170.000'."""
    return f"Rp {amount:,.0f}".replace(",", ".")


def generate_order_code() -> str:
    """Format kode pesanan: #SB-YYMMDD-XXXX (contoh: #SB-260928-0193)."""
    date_str = timezone.now().strftime("%y%m%d")
    while True:
        code = f"#SB-{date_str}-{random.randint(0, 9999):04d}"
        if not Order.objects.filter(order_code=code).exists():
            return code


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="carts",
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        owner = self.user.email if self.user else f"Guest ({self.session_key})"
        return f"Cart ({owner}) - {self.total_items} items"

    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items.all())

    @property
    def subtotal(self) -> int:
        return sum(item.subtotal for item in self.items.all())

    @property
    def formatted_subtotal(self) -> str:
        return format_rupiah(self.subtotal)


class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at"]
        unique_together = ("cart", "menu_item")

    def __str__(self):
        return f"{self.quantity}x {self.menu_item.name}"

    @property
    def subtotal(self) -> int:
        return self.menu_item.price * self.quantity

    @property
    def formatted_subtotal(self) -> str:
        return format_rupiah(self.subtotal)

    @property
    def formatted_price(self) -> str:
        return format_rupiah(self.menu_item.price)


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        ON_THE_WAY = "on_the_way", "On the way"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class PackagingType(models.TextChoices):
        REUSABLE = "reusable", "Reusable container"
        COMPOSTABLE = "compostable", "Compostable box"

    # Biaya dan Eco Points per pilihan kemasan, sesuai desain checkout.
    PACKAGING_FEES = {PackagingType.REUSABLE: 5000, PackagingType.COMPOSTABLE: 2000}
    PACKAGING_ECO_POINTS = {PackagingType.REUSABLE: 20, PackagingType.COMPOSTABLE: 10}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_code = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        default=generate_order_code,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    packaging_type = models.CharField(
        max_length=20,
        choices=PackagingType.choices,
        default=PackagingType.REUSABLE,
    )
    reusable_returned = models.BooleanField(
        default=False,
        help_text="Apakah wadah reusable untuk pesanan ini sudah dikembalikan.",
    )
    delivery_address = models.TextField(help_text="Alamat lengkap tujuan pengiriman.")
    delivery_notes = models.TextField(
        blank=True,
        default="",
        help_text="Catatan pengiriman sebelum pesanan diproses.",
    )
    delivery_eta_minutes = models.PositiveSmallIntegerField(default=0)
    subtotal = models.IntegerField(default=0, help_text="Total harga menu.")
    packaging_fee = models.IntegerField(default=0)
    delivery_fee = models.IntegerField(default=0)
    total_price = models.IntegerField(
        default=0, help_text="subtotal + packaging_fee + delivery_fee"
    )
    eco_points = models.PositiveIntegerField(default=0)
    reusable_containers = models.PositiveSmallIntegerField(
        default=0,
        help_text="Jumlah wadah reusable yang dipinjam (satu per tenant).",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_code} ({self.get_status_display()}) - {self.user.email}"

    @property
    def formatted_subtotal(self) -> str:
        return format_rupiah(self.subtotal)

    @property
    def formatted_packaging_fee(self) -> str:
        return format_rupiah(self.packaging_fee)

    @property
    def formatted_delivery_fee(self) -> str:
        return format_rupiah(self.delivery_fee)

    @property
    def formatted_total_price(self) -> str:
        return format_rupiah(self.total_price)

    @property
    def can_cancel(self) -> bool:
        """Hanya pesanan yang masih berstatus Pending yang dapat dibatalkan oleh pengguna."""
        return self.status == self.Status.PENDING

    @property
    def can_edit_note(self) -> bool:
        """Catatan pengiriman hanya dapat diubah selama pesanan masih Pending."""
        return self.status == self.Status.PENDING

    @property
    def total_items_count(self) -> int:
        return sum(item.quantity for item in self.items.all())


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    tenant = models.ForeignKey(
        "accounts.Tenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    item_name = models.CharField(max_length=255)
    tenant_name = models.CharField(max_length=255, blank=True, default="")
    price = models.IntegerField(help_text="Snapshot harga satuan menu saat dipesan.")
    quantity = models.PositiveIntegerField(default=1)
    subtotal = models.IntegerField(help_text="price * quantity")

    class Meta:
        # id berupa UUID acak, jadi urutkan dari item termahal seperti di desain.
        ordering = ["-subtotal", "item_name"]

    def __str__(self):
        return f"{self.quantity}x {self.item_name} ({self.order.order_code})"

    @property
    def formatted_price(self) -> str:
        return format_rupiah(self.price)

    @property
    def formatted_subtotal(self) -> str:
        return format_rupiah(self.subtotal)


class ReusableContainerStock(models.Model):
    """Sisa wadah reusable milik tenant. Tenant tanpa baris stok dianggap tidak
    dibatasi."""

    LOW_STOCK_THRESHOLD = 10

    tenant = models.OneToOneField(
        "accounts.Tenant",
        on_delete=models.CASCADE,
        related_name="reusable_stock",
    )
    quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tenant__name"]

    def __str__(self):
        return f"{self.tenant.name}: {self.quantity} wadah"

    @property
    def is_low(self) -> bool:
        return self.quantity <= self.LOW_STOCK_THRESHOLD
