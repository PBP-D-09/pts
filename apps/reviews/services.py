from django.db import transaction

from .integration import resolve_menu, resolve_packaging
from .models import Review


@transaction.atomic
def create_review(
    *,
    menu_uuid,
    author,
    food_rating,
    packaging_rating,
    text,
    photo=None,
    order_id=None,
):
    menu = resolve_menu(str(menu_uuid))
    packaging_type = resolve_packaging(
        menu.key,
        author,
        order_id=str(order_id) if order_id is not None else None,
    )
    return Review.objects.create(
        menu_key=menu.key,
        author=author,
        food_rating=food_rating,
        packaging_rating=packaging_rating,
        packaging_type=packaging_type,
        text=text,
        photo=photo,
    )


@transaction.atomic
def update_review(*, review, validated_data):
    validated_data = dict(validated_data)
    old_photo = review.photo
    photo = validated_data.pop("photo", None)
    remove_photo = validated_data.pop("remove_photo", False)
    for field, value in validated_data.items():
        setattr(review, field, value)
    if photo is not None:
        review.photo = photo
    elif remove_photo:
        review.photo = ""
    review.save()
    if old_photo and old_photo.name != review.photo.name:
        transaction.on_commit(lambda: old_photo.delete(save=False), robust=True)
    return review


@transaction.atomic
def delete_review(*, review):
    photo = review.photo
    review.delete()
    if photo:
        transaction.on_commit(lambda: photo.delete(save=False), robust=True)
