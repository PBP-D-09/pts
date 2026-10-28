# Register your models here.
from django.contrib import admin

from . import models

admin.site.register(models.tenantCuisine)
admin.site.register(models.MenuCategory)
admin.site.register(models.MenuItem)
