from django.contrib import admin

from .models import HelpfulVote, Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        "menu_key",
        "author",
        "food_rating",
        "packaging_rating",
        "created_at",
    ]
    list_filter = ["food_rating", "packaging_rating"]
    search_fields = ["menu_key", "text", "author__email"]
    readonly_fields = ["created_at", "updated_at"]


admin.site.register(HelpfulVote)
