from django.forms import (
    CheckboxInput,
    FileInput,
    ModelForm,
    NumberInput,
    Select,
    Textarea,
    TextInput,
)

from .models import MenuCategory, MenuItem


class MenuItemForm(ModelForm):
    class Meta:
        model = MenuItem
        fields = [
            "photo",
            "name",
            "description",
            "category",
            "allergen_info",
            "vegetarian",
            "price",
        ]

        labels = {
            "photo": "Photo",
            "name": "Menu name",
            "description": "Description",
            "category": "Menu category",
            "allergen_info": "Allergen information",
            "vegetarian": "Vegetarian",
            "price": "Price",
        }

        widgets = {
            "photo": FileInput(
                attrs={
                    "accept": "image/*",
                    "class": (
                        "block w-full cursor-pointer rounded-xl "
                        "border border-gray-200 bg-gray-50 "
                        "text-sm text-gray-500 shadow-sm "
                        "transition duration-200 "
                        "hover:border-orange-300 hover:bg-orange-50/40 "
                        "focus:outline-none focus:ring-4 focus:ring-orange-100 "
                        "file:mr-4 file:cursor-pointer file:border-0 "
                        "file:border-r file:border-gray-200 "
                        "file:bg-orange-50 file:px-5 file:py-3 "
                        "file:text-sm file:font-semibold file:text-orange-700 "
                        "hover:file:bg-orange-100 "
                        "file:transition-colors file:duration-200"
                    ),
                }
            ),
            "name": TextInput(
                attrs={
                    "class": (
                        "w-full rounded-xl border border-gray-200 "
                        "bg-white px-4 py-3 text-sm text-gray-800 "
                        "shadow-sm placeholder:text-gray-400 "
                        "transition duration-200 "
                        "hover:border-gray-300 "
                        "focus:border-orange-400 focus:outline-none "
                        "focus:ring-4 focus:ring-orange-100"
                    ),
                    "placeholder": "e.g. Grilled Chicken Rice",
                }
            ),
            "description": Textarea(
                attrs={
                    "class": (
                        "w-full rounded-xl border border-gray-200 "
                        "bg-white px-4 py-3 text-sm leading-6 text-gray-800 "
                        "shadow-sm placeholder:text-gray-400 "
                        "transition duration-200 "
                        "hover:border-gray-300 "
                        "focus:border-orange-400 focus:outline-none "
                        "focus:ring-4 focus:ring-orange-100"
                    ),
                    "placeholder": "Describe the ingredients, flavor, and portion...",
                    "rows": 4,
                }
            ),
            "category": Select(
                attrs={
                    "class": (
                        "w-full cursor-pointer appearance-none rounded-xl "
                        "border border-gray-200 bg-white px-4 py-3 "
                        "text-sm text-gray-800 shadow-sm "
                        "transition duration-200 "
                        "hover:border-gray-300 "
                        "focus:border-orange-400 focus:outline-none "
                        "focus:ring-4 focus:ring-orange-100"
                    ),
                }
            ),
            "allergen_info": Textarea(
                attrs={
                    "class": (
                        "w-full rounded-xl border border-gray-200 "
                        "bg-white px-4 py-3 text-sm leading-6 text-gray-800 "
                        "shadow-sm placeholder:text-gray-400 "
                        "transition duration-200 "
                        "hover:border-gray-300 "
                        "focus:border-orange-400 focus:outline-none "
                        "focus:ring-4 focus:ring-orange-100"
                    ),
                    "placeholder": "e.g. Contains peanuts, milk, or eggs. Leave blank if unknown.",
                    "rows": 3,
                }
            ),
            "vegetarian": CheckboxInput(
                attrs={
                    "class": (
                        "h-5 w-5 cursor-pointer rounded-md "
                        "border-gray-300 text-orange-600 "
                        "shadow-sm transition duration-200 "
                        "focus:outline-none focus:ring-4 focus:ring-orange-100 "
                        "focus:ring-offset-1"
                    ),
                }
            ),
            "price": NumberInput(
                attrs={
                    "class": (
                        "w-full rounded-xl border border-gray-200 "
                        "bg-white px-4 py-3 text-sm text-gray-800 "
                        "shadow-sm placeholder:text-gray-400 "
                        "transition duration-200 "
                        "hover:border-gray-300 "
                        "focus:border-orange-400 focus:outline-none "
                        "focus:ring-4 focus:ring-orange-100"
                    ),
                    "placeholder": "e.g. 25000",
                    "min": 0,
                    "step": 1,
                    "inputmode": "numeric",
                }
            ),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)

        if tenant is not None:
            self.fields["category"].queryset = MenuCategory.objects.filter(
                tenantId=tenant
            )


class MenuCategoryForm(ModelForm):
    class Meta:
        model = MenuCategory
        fields = ["name"]

        labels = {
            "name": "Category Name",
        }

        widgets = {
            "name": TextInput(
                attrs={
                    "placeholder": "e.g. Main Course",
                    "class": (
                        "w-full rounded-xl border border-gray-300 px-4 py-3 "
                        "text-gray-900 outline-none transition "
                        "focus:border-orange-500 focus:ring-2 focus:ring-orange-100"
                    ),
                }
            ),
        }
