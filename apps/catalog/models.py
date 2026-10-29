# Create your models here.
import uuid
from django.db import models

class TenantCuisine(models.Model):
	name = models.CharField(primary_key=True, max_length=255)

	def __str__(self):
		return self.name

class AllergenIngredient(models.Model):
	name = models.CharField(primary_key=True, max_length=255)

class MenuCategory(models.Model):
	tenantId = models.ForeignKey("accounts.Tenant", on_delete=models.CASCADE, related_name="menu_categories", blank=True, null=True)
	name = models.CharField(max_length=255)

	def __str__(self):
		return self.name
	
class MenuItem(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	tenantId = models.ForeignKey("accounts.Tenant", on_delete=models.CASCADE, related_name="menus", blank=True, null=True)
	name = models.CharField(max_length=255)
	description = models.TextField()
	photo = models.ImageField(upload_to="menu_items/", blank=True)
	category = models.ForeignKey(MenuCategory, on_delete=models.SET_NULL, related_name="menu_items", blank=True, null=True)
	allergen_info = models.TextField(default="no allergen information listed")  
	vegetarian = models.BooleanField(default=False)
	price = models.IntegerField()

	def __str__(self):
		return self.name