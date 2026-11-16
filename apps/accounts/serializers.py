from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.catalog.models import TenantCuisine

from .models import (
    CustomUser,
    DietActivity,
    DietPreference,
    EcoPointActivity,
    Tenant,
    UserAllergy,
    UserProfile,
)


class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["id", "email", "account_type", "first_name", "last_name"]


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)

    def validate_email(self, value):
        email = value.strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Email ini sudah digunakan.")
        return email

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password2": "Password tidak cocok."})
        return attrs

    def create(self, validated_data):
        from .services import register_user

        return register_user(
            full_name=validated_data["full_name"],
            email=validated_data["email"],
            password=validated_data["password"],
        )


class TenantRegisterSerializer(serializers.Serializer):
    tenant_name = serializers.CharField(max_length=150)
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=30)
    password = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)

    def validate_email(self, value):
        email = value.strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Email ini sudah digunakan.")
        return email

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password2": "Password tidak cocok."})
        return attrs

    def create(self, validated_data):
        from .services import register_tenant

        return register_tenant(
            tenant_name=validated_data["tenant_name"],
            full_name=validated_data["full_name"],
            email=validated_data["email"],
            phone_number=validated_data["phone_number"],
            password=validated_data["password"],
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        password = attrs["password"]
        user = authenticate(
            self.context.get("request"), username=email, password=password
        )
        if user is None:
            raise serializers.ValidationError("Email atau password tidak tepat.")
        if not user.is_active:
            raise serializers.ValidationError("Akun ini tidak aktif.")
        attrs["user"] = user
        return attrs


class DietPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DietPreference
        fields = ["code", "label"]


class UserAllergySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAllergy
        fields = ["id", "name", "created_at"]
        read_only_fields = ["id", "created_at"]


class EcoPointActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = EcoPointActivity
        fields = [
            "id",
            "points",
            "activity_type",
            "description",
            "co2_saved",
            "created_at",
        ]
        read_only_fields = fields


class DietActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DietActivity
        fields = ["id", "activity_date", "source", "summary", "created_at"]
        read_only_fields = fields


class UserProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.first_name", read_only=True)
    account_type = serializers.CharField(source="user.account_type", read_only=True)
    photo = serializers.SerializerMethodField()
    diets = DietPreferenceSerializer(many=True, read_only=True)
    allergies = UserAllergySerializer(many=True, read_only=True)
    eco_points = serializers.IntegerField(read_only=True)
    co2_saved = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "email",
            "full_name",
            "account_type",
            "birth_date",
            "phone_number",
            "photo",
            "diets",
            "allergies",
            "eco_points",
            "co2_saved",
        ]

    def get_photo(self, obj):
        return obj.photo.url if obj.photo else None


class ProfileUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    birth_date = serializers.DateField(required=False, allow_null=True)
    phone_number = serializers.CharField(
        max_length=30, required=False, allow_blank=True
    )

    def validate_email(self, value):
        email = value.strip().lower()
        user = self.context["request"].user
        if CustomUser.objects.exclude(pk=user.pk).filter(email__iexact=email).exists():
            raise serializers.ValidationError("Email ini sudah digunakan.")
        return email


class TenantSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="owner.first_name", read_only=True)
    email = serializers.EmailField(source="owner.email", read_only=True)
    photo = serializers.SerializerMethodField()
    cuisines = serializers.SlugRelatedField(
        slug_field="name", many=True, read_only=True
    )

    class Meta:
        model = Tenant
        fields = ["full_name", "email", "name", "phone_number", "photo", "cuisines"]

    def get_photo(self, obj):
        return obj.photo.url if obj.photo else None


class TenantUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=30)
    cuisines = serializers.SlugRelatedField(
        slug_field="name",
        many=True,
        queryset=TenantCuisine.objects.all(),
        required=False,
    )

    def validate_email(self, value):
        email = value.strip().lower()
        user = self.context["request"].user
        if CustomUser.objects.exclude(pk=user.pk).filter(email__iexact=email).exists():
            raise serializers.ValidationError("Email ini sudah digunakan.")
        return email


class MenuItemRecommendationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField()
    price = serializers.IntegerField()
    photo_url = serializers.SerializerMethodField()
    vegetarian = serializers.BooleanField()
    allergen_info = serializers.CharField()
    tenant_id = serializers.IntegerField(source="tenantId_id")
    tenant_name = serializers.CharField(source="tenantId.name")

    def get_photo_url(self, obj):
        return obj.photo.url if obj.photo else ""
