from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import CustomUser, Tenant
from apps.map.models import TenantLocation
from apps.map.seed_data import TENANT_LOCATIONS


class Command(BaseCommand):
    help = "Membuat tenan contoh beserta lokasinya untuk demo peta (aman dijalankan ulang)."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for index, row in enumerate(TENANT_LOCATIONS, start=1):
            name, address, district, city, category, lat, lng, opens, closes = row
            user, user_created = CustomUser.objects.get_or_create(
                email=f"tenant{index:02d}@seed.sustainabowl.id",
                defaults={
                    "first_name": f"Pengelola {name}",
                    "account_type": CustomUser.AccountType.TENANT,
                },
            )
            if user_created:
                # Akun contoh tidak bisa dipakai login.
                user.set_unusable_password()
                user.save(update_fields=["password"])
            tenant, _ = Tenant.objects.get_or_create(
                owner=user,
                defaults={
                    "name": name,
                    "phone_number": f"0812{index:08d}",
                },
            )
            _, was_created = TenantLocation.objects.update_or_create(
                tenant=tenant,
                defaults={
                    "address": address,
                    "district": district,
                    "city": city,
                    "category": category,
                    "latitude": lat,
                    "longitude": lng,
                    "opening_time": opens,
                    "closing_time": closes,
                },
            )
            created += int(was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(TENANT_LOCATIONS)} lokasi tenan siap ({created} baru)."
            )
        )
