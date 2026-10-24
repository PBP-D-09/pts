from django.forms import ModelForm, TextInput, Textarea, Select, CheckboxInput, NumberInput
from .models import MenuItem, MenuCategory

class MenuItemForm(ModelForm):
    class Meta:
        model = MenuItem
        fields = [
            "name",
            "description",
            "category",
            "allergen_info",
            "vegetarian",
            "price",
        ]

        labels = {
            "name": "Menu name",
            "description": "Description",
            "category": "Menu category",
            "allergen_info": "Allergen information",
            "vegetarian": "Vegetarian",
            "price": "Price",
        }

        widgets = {
            "name": TextInput(attrs={
                "class": "w-full rounded-lg border border-gray-300 px-3 py-2",
                "placeholder": "Enter menu name",
            }),
            "description": Textarea(attrs={
                "class": "w-full rounded-lg border border-gray-300 px-3 py-2",
                "placeholder": "Describe the menu",
                "rows": 4,
            }),
            "category": Select(attrs={
                "class": "w-full rounded-lg border border-gray-300 px-3 py-2",
            }),
            "allergen_info": Textarea(attrs={
                "class": "w-full rounded-lg border border-gray-300 px-3 py-2",
                "placeholder": "List allergens, if any",
                "rows": 3,
            }),
            "vegetarian": CheckboxInput(attrs={
                "class": "h-4 w-4 rounded border-gray-300",
            }),
            "price": NumberInput(attrs={
                "class": "w-full rounded-lg border border-gray-300 px-3 py-2",
                "placeholder": "Enter price",
                "min": 0,
            }),
        }
    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)

        if tenant is not None:
            self.fields["category"].queryset = (
                MenuCategory.objects.filter(tenantId=tenant)
            )