from django import forms

from apps.map.models import DeliveryAddress

from .models import Order

NOTE_MAX_LENGTH = 500


class CheckoutForm(forms.Form):
    address = forms.ModelChoiceField(
        queryset=DeliveryAddress.objects.none(),
        error_messages={
            "required": "Choose a delivery address.",
            "invalid_choice": "Choose one of your saved addresses.",
        },
    )
    packaging_type = forms.ChoiceField(
        choices=Order.PackagingType.choices,
        initial=Order.PackagingType.REUSABLE,
        error_messages={"required": "Choose a packaging option."},
    )
    delivery_notes = forms.CharField(max_length=NOTE_MAX_LENGTH, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["address"].queryset = DeliveryAddress.objects.filter(owner=user)


class OrderNoteForm(forms.Form):
    delivery_notes = forms.CharField(max_length=NOTE_MAX_LENGTH, required=False)
