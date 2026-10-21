from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm
from django.forms import ValidationError

from .models import CustomUser, Tenant, UserProfile


class RegistrationForm(UserCreationForm):
    full_name = forms.CharField(max_length=150, label="Nama lengkap")

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("full_name", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "ui-input"

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("Email ini sudah digunakan.")
        return email


class TenantRegistrationForm(UserCreationForm):
    tenant_name = forms.CharField(max_length=150, label="Nama tenan")
    full_name = forms.CharField(max_length=150, label="Nama penanggung jawab")
    phone_number = forms.CharField(max_length=30, label="Nomor telepon")

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = (
            "tenant_name",
            "full_name",
            "email",
            "phone_number",
            "password1",
            "password2",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(self.Meta.fields)
        for field in self.fields.values():
            field.widget.attrs["class"] = "ui-input"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("Email ini sudah digunakan.")
        return email


class EmailAuthenticationForm(forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Password", widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "ui-input"

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")
        if email and password:
            self.user_cache = authenticate(
                self.request, username=email, password=password
            )
            if self.user_cache is None:
                raise ValidationError("Email atau password tidak tepat.")
            if not self.user_cache.is_active:
                raise ValidationError("Akun ini tidak aktif.")
        return cleaned_data

    def get_user(self):
        return self.user_cache


class ProfileForm(forms.ModelForm):
    full_name = forms.CharField(max_length=150, label="Nama")
    email = forms.EmailField(label="Email")

    class Meta:
        model = UserProfile
        fields = ("birth_date", "phone_number")
        labels = {"birth_date": "Tanggal lahir", "phone_number": "No. Telp"}
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user, **kwargs):
        self.user = user
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("full_name", user.first_name)
        initial.setdefault("email", user.email)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "ui-input"

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if CustomUser.objects.exclude(pk=self.user.pk).filter(email=email).exists():
            raise ValidationError("Email ini sudah digunakan.")
        return email


class TenantProfileForm(forms.ModelForm):
    full_name = forms.CharField(max_length=150, label="Nama penanggung jawab")
    email = forms.EmailField(label="Email")

    class Meta:
        model = Tenant
        fields = ("name", "phone_number")
        labels = {"name": "Nama tenan", "phone_number": "Nomor telepon"}

    def __init__(self, *args, user, **kwargs):
        self.user = user
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("full_name", user.first_name)
        initial.setdefault("email", user.email)
        super().__init__(*args, **kwargs)
        self.order_fields(("name", "full_name", "email", "phone_number"))
        for field in self.fields.values():
            field.widget.attrs["class"] = "ui-input"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if (
            CustomUser.objects.exclude(pk=self.user.pk)
            .filter(email__iexact=email)
            .exists()
        ):
            raise ValidationError("Email ini sudah digunakan.")
        return email


class PhotoUploadForm(forms.Form):
    photo = forms.ImageField()

    def clean_photo(self):
        photo = self.cleaned_data["photo"]
        if photo.size > 5 * 1024 * 1024:
            raise ValidationError("Ukuran foto maksimal 5 MB.")
        if photo.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValidationError("Gunakan file JPEG, PNG, atau WebP.")
        return photo
