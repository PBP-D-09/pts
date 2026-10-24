from django import forms

from .models import DeliveryAddress, TenantLocation

COORDINATE_WIDGET_ATTRS = {"step": "0.000001", "data-coordinate": "true"}


class StyledFormMixin:
    def _style_fields(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            field.widget.attrs.setdefault("class", "ui-input")


class DeliveryAddressForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = DeliveryAddress
        fields = (
            "label",
            "recipient_name",
            "phone_number",
            "address",
            "landmark",
            "courier_note",
            "latitude",
            "longitude",
            "is_default",
        )
        widgets = {
            "label": forms.TextInput(attrs={"placeholder": "Rumah, Kantor, Kos"}),
            "address": forms.TextInput(
                attrs={"placeholder": "Klik peta atau cari alamat untuk mengisi"}
            ),
            "landmark": forms.TextInput(
                attrs={"placeholder": "Dekat masjid, pagar hijau"}
            ),
            "courier_note": forms.TextInput(
                attrs={"placeholder": "Titip di satpam, telepon dulu"}
            ),
            "latitude": forms.NumberInput(
                attrs={**COORDINATE_WIDGET_ATTRS, "data-lat-input": "true"}
            ),
            "longitude": forms.NumberInput(
                attrs={**COORDINATE_WIDGET_ATTRS, "data-lng-input": "true"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["address"].widget.attrs["data-address-input"] = "true"
        self._style_fields()


class TenantLocationForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = TenantLocation
        fields = (
            "address",
            "district",
            "city",
            "category",
            "opening_time",
            "closing_time",
            "delivery_radius_km",
            "latitude",
            "longitude",
        )
        widgets = {
            "opening_time": forms.TimeInput(attrs={"type": "time"}),
            "closing_time": forms.TimeInput(attrs={"type": "time"}),
            "latitude": forms.NumberInput(
                attrs={**COORDINATE_WIDGET_ATTRS, "data-lat-input": "true"}
            ),
            "longitude": forms.NumberInput(
                attrs={**COORDINATE_WIDGET_ATTRS, "data-lng-input": "true"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["address"].widget.attrs["data-address-input"] = "true"
        self._style_fields()


class TenantFilterForm(forms.Form):
    """Filter peta tenan. Semua field opsional dan nilai salah diabaikan."""

    RADIUS_CHOICES = [
        ("", "Semua jarak"),
        ("1", "1 km"),
        ("3", "3 km"),
        ("5", "5 km"),
        ("10", "10 km"),
    ]

    q = forms.CharField(required=False, max_length=100)
    city = forms.CharField(required=False, max_length=100)
    category = forms.ChoiceField(
        required=False,
        choices=[("", "Semua kategori"), *TenantLocation.Category.choices],
    )
    open_now = forms.BooleanField(required=False)
    radius = forms.ChoiceField(required=False, choices=RADIUS_CHOICES)
    lat = forms.FloatField(required=False, min_value=-90, max_value=90)
    lng = forms.FloatField(required=False, min_value=-180, max_value=180)
