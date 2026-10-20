from django.db import transaction
from django.utils import timezone

from .models import CustomUser, DietActivity, EcoPointActivity, UserAllergy


@transaction.atomic
def register_user(*, full_name, email, password):
    return CustomUser.objects.create_user(
        email=email.lower(),
        password=password,
        first_name=full_name.strip(),
    )


@transaction.atomic
def update_profile(*, profile, full_name, email, birth_date, phone_number):
    user = profile.user
    user.first_name = full_name.strip()
    user.email = email.lower()
    user.save(update_fields=["first_name", "email"])

    profile.birth_date = birth_date
    profile.phone_number = phone_number
    profile.save(update_fields=["birth_date", "phone_number"])
    DietActivity.objects.create(
        profile=profile,
        activity_date=timezone.localdate(),
        source=DietActivity.Source.PROFILE,
        summary="Data profil diperbarui.",
    )
    return profile


@transaction.atomic
def toggle_diet(*, profile, diet):
    if profile.diets.filter(pk=diet.pk).exists():
        profile.diets.remove(diet)
        is_selected = False
        summary = f"Preferensi {diet.label} dihapus."
    else:
        profile.diets.add(diet)
        is_selected = True
        summary = f"Preferensi {diet.label} ditambahkan."
    DietActivity.objects.create(
        profile=profile,
        activity_date=timezone.localdate(),
        source=DietActivity.Source.PROFILE,
        summary=summary,
    )
    return is_selected


@transaction.atomic
def add_allergy(*, profile, name):
    normalized_name = name.strip()[:50]
    if not normalized_name:
        return None
    existing = profile.allergies.filter(name__iexact=normalized_name).first()
    if existing:
        return existing
    allergy = UserAllergy.objects.create(profile=profile, name=normalized_name)
    DietActivity.objects.create(
        profile=profile,
        activity_date=timezone.localdate(),
        source=DietActivity.Source.PROFILE,
        summary=f"Alergi {allergy.name} ditambahkan.",
    )
    return allergy


@transaction.atomic
def delete_allergy(*, profile, allergy_id):
    allergy = UserAllergy.objects.get(pk=allergy_id, profile=profile)
    name = allergy.name
    allergy.delete()
    DietActivity.objects.create(
        profile=profile,
        activity_date=timezone.localdate(),
        source=DietActivity.Source.PROFILE,
        summary=f"Alergi {name} dihapus.",
    )


@transaction.atomic
def update_profile_photo(*, profile, photo):
    old_name = profile.photo.name if profile.photo else ""
    profile.photo = photo
    profile.save(update_fields=["photo"])
    if old_name and old_name != profile.photo.name:
        transaction.on_commit(lambda: profile.photo.storage.delete(old_name))
    return profile


@transaction.atomic
def record_eco_points(*, profile, points, activity_type, description, co2_saved=0):
    return EcoPointActivity.objects.create(
        profile=profile,
        points=points,
        activity_type=activity_type,
        description=description,
        co2_saved=co2_saved,
    )


@transaction.atomic
def reset_eco_points(*, profile):
    profile.point_activities.all().delete()
