from rest_framework import serializers

from .models import Review
from .selectors import sentiment


MAX_PHOTO_SIZE = 5 * 1024 * 1024
ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png"}


class ReviewWriteSerializer(serializers.Serializer):
    food_rating = serializers.IntegerField(min_value=1, max_value=5)
    packaging_rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(max_length=500, trim_whitespace=True)
    photo = serializers.ImageField(required=False, allow_null=False)
    remove_photo = serializers.BooleanField(required=False, write_only=True)
    order_id = serializers.UUIDField(required=False, write_only=True)

    def validate_text(self, value):
        if not value:
            raise serializers.ValidationError("Review text cannot be blank.")
        return value

    def validate_photo(self, value):
        extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if extension not in ALLOWED_PHOTO_EXTENSIONS:
            raise serializers.ValidationError("Upload a JPG or PNG image.")
        if value.size > MAX_PHOTO_SIZE:
            raise serializers.ValidationError("Photo must be 5 MiB or smaller.")
        if getattr(value, "image", None) is None or value.image.format not in {
            "JPEG",
            "PNG",
        }:
            raise serializers.ValidationError("Upload a valid JPG or PNG image.")
        return value

    def validate(self, attrs):
        if not self.partial and attrs.get("remove_photo"):
            raise serializers.ValidationError(
                {"remove_photo": "Photo removal is only available when editing."}
            )
        if self.partial and "order_id" in attrs:
            raise serializers.ValidationError(
                {"order_id": "An order can only be selected when creating a review."}
            )
        if self.partial and not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class ReviewSerializer(serializers.ModelSerializer):
    menu_uuid = serializers.CharField(source="menu_key", read_only=True)
    author = serializers.SerializerMethodField()
    packaging_type_display = serializers.CharField(
        source="get_packaging_type_display", read_only=True
    )
    sentiment = serializers.SerializerMethodField()
    helpful_count = serializers.SerializerMethodField()
    has_voted_helpful = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "menu_uuid",
            "author",
            "food_rating",
            "packaging_rating",
            "packaging_type",
            "packaging_type_display",
            "text",
            "photo_url",
            "sentiment",
            "helpful_count",
            "has_voted_helpful",
            "is_mine",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_sentiment(self, review):
        return sentiment(review.text)

    def get_author(self, review):
        return {
            "id": review.author_id,
            "display_name": review.author.display_name,
            "initials": review.initials,
        }

    def get_helpful_count(self, review):
        count = getattr(review, "helpful_count", None)
        return count if count is not None else review.helpful_votes.count()

    def get_has_voted_helpful(self, review):
        return bool(getattr(review, "voted", False))

    def get_is_mine(self, review):
        request = self.context.get("request")
        return bool(
            request
            and request.user.is_authenticated
            and request.user.pk == review.author_id
        )

    def get_photo_url(self, review):
        if not review.photo:
            return None
        url = review.photo.url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url
