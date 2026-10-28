from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import Model, Sum
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email wajib diisi.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser harus memiliki is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser harus memiliki is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    class AccountType(models.TextChoices):
        CUSTOMER = "customer", "Pelanggan"
        TENANT = "tenant", "Tenant"

    username = None
    email = models.EmailField("email address", unique=True)
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.CUSTOMER,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    @property
    def is_customer(self):
        return self.account_type == self.AccountType.CUSTOMER

    @property
    def is_tenant(self):
        return self.account_type == self.AccountType.TENANT

    @property
    def display_name(self):
        if self.is_tenant:
            try:
                return self.tenant.name or self.first_name or self.email
            except Tenant.DoesNotExist:
                pass
        return self.first_name or self.email

    def __str__(self):
        return self.email


class DietPreference(Model):
    class Code(models.TextChoices):
        VEGAN = "vegan", "Vegan"
        VEGETARIAN = "vegetarian", "Vegetarian"
        LOW_CARB = "low-carb", "Low Carb"
        KETO = "keto", "Keto"

    code = models.CharField(max_length=20, choices=Code.choices, unique=True)
    label = models.CharField(max_length=30)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return self.label


class UserProfile(Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    birth_date = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    photo = models.ImageField(upload_to="profiles/", blank=True)
    diets = models.ManyToManyField(DietPreference, blank=True, related_name="profiles")
    eco_points_reset_at = models.DateTimeField(null=True, blank=True)

    def active_point_activities(self):
        activities = self.point_activities.all()
        if self.eco_points_reset_at:
            activities = activities.filter(created_at__gte=self.eco_points_reset_at)
        return activities

    @property
    def eco_points(self):
        return (
            self.active_point_activities().aggregate(total=Sum("points"))["total"] or 0
        )

    @property
    def co2_saved(self):
        return self.active_point_activities().aggregate(total=Sum("co2_saved"))[
            "total"
        ] or Decimal(0)

    def __str__(self):
        return f"Profil {self.user.email}"


class Tenant(Model):
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tenant",
    )
    name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=30)
    photo = models.ImageField(upload_to="tenants/", blank=True)
    cuisines = models.ManyToManyField("catalog.tenantCuisine", related_name="tenants")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserAllergy(Model):
    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="allergies"
    )
    name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "name"], name="unique_profile_allergy"
            )
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class EcoPointActivity(Model):
    class ActivityType(models.TextChoices):
        ORDER = "order", "Pesanan"
        PACKAGING = "packaging", "Kemasan ramah lingkungan"
        ADJUSTMENT = "adjustment", "Penyesuaian"

    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="point_activities"
    )
    points = models.IntegerField()
    activity_type = models.CharField(max_length=20, choices=ActivityType.choices)
    description = models.CharField(max_length=160)
    co2_saved = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class DietActivity(Model):
    class Source(models.TextChoices):
        PROFILE = "profile", "Profil"
        ORDER = "order", "Pesanan"
        MANUAL = "manual", "Catatan"

    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="diet_activities"
    )
    activity_date = models.DateField()
    source = models.CharField(max_length=20, choices=Source.choices)
    summary = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-activity_date", "-created_at"]


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created and instance.is_customer:
        UserProfile.objects.create(user=instance)
