from django import forms


class ShowcaseForm(forms.Form):
    full_name = forms.CharField(
        label="Nama lengkap",
        widget=forms.TextInput(
            attrs={"class": "ui-input", "placeholder": "Nama lengkap"}
        ),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={"class": "ui-input", "placeholder": "nama@example.com"}
        ),
    )
    phone_number = forms.CharField(
        label="Nomor telepon",
        required=False,
        widget=forms.TextInput(
            attrs={"class": "ui-input", "placeholder": "0812 3456 7890"}
        ),
    )
