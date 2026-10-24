from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    remove_photo = forms.BooleanField(required=False)

    class Meta:
        model = Review
        fields = ["food_rating", "packaging_rating", "text", "photo"]
        error_messages = {
            "text": {"required": "Please write your review."},
            "food_rating": {"required": "Please select a food rating."},
            "packaging_rating": {"required": "Please select a packaging rating."},
        }
        widgets = {
            "food_rating": forms.RadioSelect(
                choices=[(i, f"{i} stars") for i in range(1, 6)]
            ),
            "packaging_rating": forms.RadioSelect(
                choices=[(i, f"{i} stars") for i in range(1, 6)]
            ),
            "text": forms.Textarea(
                attrs={
                    "rows": 4,
                    "maxlength": 500,
                    "placeholder": "Tell us about the food and packaging...",
                    "class": "ui-input",
                }
            ),
            "photo": forms.FileInput(attrs={"accept": "image/jpeg,image/png"}),
        }

    def clean_text(self):
        value = self.cleaned_data["text"].strip()
        if not value:
            raise forms.ValidationError("Please write your review.")
        return value

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "content_type"):
            if photo.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Photo must be 5 MB or smaller.")
            if photo.image.format not in {"JPEG", "PNG"} or photo.name.rsplit(".", 1)[
                -1
            ].lower() not in {"jpg", "jpeg", "png"}:
                raise forms.ValidationError("Please upload a JPG or PNG image.")
        return photo


class ReviewFilterForm(forms.Form):
    rating = forms.ChoiceField(
        required=False,
        choices=[("", "All Ratings")]
        + [(str(i), f"{i} {'Star' if i == 1 else 'Stars'}") for i in range(5, 0, -1)],
    )
    sentiment = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All sentiments"),
            ("positive", "Positive"),
            ("neutral", "Neutral"),
            ("negative", "Negative"),
        ],
    )
    packaging = forms.ChoiceField(
        label="Packaging satisfaction",
        required=False,
        choices=[
            ("", "All satisfaction levels"),
            ("very_satisfied", "Very Satisfied"),
            ("satisfied", "Satisfied"),
            ("neutral", "Neutral"),
            ("unsatisfied", "Unsatisfied"),
        ],
    )
    sort = forms.ChoiceField(
        label="Sort by",
        required=False,
        choices=[
            ("newest", "Newest"),
            ("oldest", "Oldest"),
            ("helpful", "Most Helpful"),
            ("highest", "Highest Rating"),
        ],
    )
