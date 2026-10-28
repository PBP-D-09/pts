# Register your models here.
from django.contrib import admin
from . import models

admin.site.register(models.TenantCuisine)
admin.site.register(models.AllergenIngredient)
admin.site.register(models.MenuCategory)
admin.site.register(models.MenuItem)