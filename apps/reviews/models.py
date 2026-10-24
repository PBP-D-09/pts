import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def review_photo_path(instance, filename):
    return f"reviews/{instance.author_id}/{uuid.uuid4().hex}.{filename.rsplit('.', 1)[-1].lower()}"


class Review(models.Model):
    # Opaque Catalog identifier; replace with a FK only after Catalog's contract exists.
    menu_key = models.SlugField(max_length=100, db_index=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    food_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    packaging_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    class PackagingType(models.TextChoices):
        REUSABLE = "reusable", "Reusable container"
        COMPOSTABLE = "compostable", "Compostable packaging"

    packaging_type = models.CharField(
        max_length=20, choices=PackagingType.choices, blank=True
    )
    text = models.CharField(max_length=500)
    photo = models.ImageField(upload_to=review_photo_path, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(food_rating__range=(1, 5)),
                name="reviews_food_rating_range",
            ),
            models.CheckConstraint(
                condition=models.Q(packaging_rating__range=(1, 5)),
                name="reviews_packaging_rating_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["menu_key", "-created_at"], name="reviews_menu_created_idx"
            )
        ]

    @property
    def initials(self):
        return "".join(part[0] for part in self.author.display_name.split()[:2]).upper()


class HelpfulVote(models.Model):
    review = models.ForeignKey(
        Review, on_delete=models.CASCADE, related_name="helpful_votes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_votes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["review", "user"], name="reviews_unique_helpful_vote"
            )
        ]
