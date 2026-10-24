import json
from datetime import UTC, datetime, time
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.services import register_tenant

from .forms import DeliveryAddressForm
from .models import DeliveryAddress, TenantLocation, distance_km
from .seed_data import TENANT_LOCATIONS
from .services import (
    GeocodingError,
    delete_delivery_address,
    reverse_geocode,
    save_delivery_address,
    search_places,
)

PASSWORD = "strong-password-123"


def make_user(email="user@example.com"):
    return CustomUser.objects.create_user(email=email, password=PASSWORD)


def make_tenant(name="Green Bowl", email="tenant@example.com", **location):
    user = register_tenant(
        tenant_name=name,
        full_name="Pengelola",
        email=email,
        phone_number="081234567890",
        password=PASSWORD,
    )
    if not location.pop("skip", False):
        defaults = {
            "address": "Jl. HOS Cokroaminoto No. 24",
            "district": "Menteng",
            "city": "Jakarta Pusat",
            "category": TenantLocation.Category.HEALTHY_BOWL,
            "latitude": Decimal("-6.196800"),
            "longitude": Decimal("106.831900"),
            "opening_time": time(0, 0),
            "closing_time": time(23, 59),
        }
        defaults.update(location)
        TenantLocation.objects.create(tenant=user.tenant, **defaults)
    return user


def make_address(owner, **fields):
    data = {
        "label": "Rumah",
        "recipient_name": "Penerima",
        "phone_number": "0811111111",
        "address": "Jl. Margonda Raya No. 100",
        "latitude": Decimal("-6.368200"),
        "longitude": Decimal("106.832000"),
    }
    data.update(fields)
    return DeliveryAddress.objects.create(owner=owner, **data)


def address_payload(**overrides):
    data = {
        "label": "Kantor",
        "recipient_name": "Awiddy",
        "phone_number": "081234567890",
        "address": "Jl. Sudirman No. 1",
        "landmark": "Gedung kaca",
        "courier_note": "Titip resepsionis",
        "latitude": "-6.208800",
        "longitude": "106.845600",
    }
    data.update(overrides)
    return data


def nominatim_response(payload, status=200):
    response = Mock()
    response.json.return_value = payload
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(str(status))
    else:
        response.raise_for_status.return_value = None
    return response


class ModelTests(TestCase):
    def test_distance_km_between_known_points(self):
        # Monas ke Bundaran HI kira-kira 2 km.
        distance = distance_km(-6.175392, 106.827153, -6.195000, 106.823000)
        self.assertAlmostEqual(distance, 2.2, delta=0.3)
        self.assertEqual(distance_km(1, 1, 1, 1), 0)

    def test_tenant_location_open_hours(self):
        user = make_tenant(opening_time=time(8, 0), closing_time=time(21, 0))
        location = user.tenant.location
        self.assertTrue(location.is_open_at(datetime(2026, 1, 1, 12, 0, tzinfo=UTC)))
        self.assertFalse(location.is_open_at(datetime(2026, 1, 1, 21, 0, tzinfo=UTC)))
        self.assertFalse(location.is_open_at(datetime(2026, 1, 1, 7, 59, tzinfo=UTC)))
        self.assertEqual(str(location), "Lokasi Green Bowl")

    def test_tenant_location_open_hours_past_midnight(self):
        user = make_tenant(opening_time=time(18, 0), closing_time=time(2, 0))
        location = user.tenant.location
        self.assertTrue(location.is_open_at(datetime(2026, 1, 1, 23, 0, tzinfo=UTC)))
        self.assertTrue(location.is_open_at(datetime(2026, 1, 1, 1, 0, tzinfo=UTC)))
        self.assertFalse(location.is_open_at(datetime(2026, 1, 1, 12, 0, tzinfo=UTC)))

    def test_coordinates_are_validated(self):
        address = DeliveryAddress(
            owner=make_user(),
            label="Salah",
            recipient_name="A",
            phone_number="1",
            address="x",
            latitude=Decimal(91),
            longitude=Decimal(200),
        )
        with self.assertRaises(ValidationError) as ctx:
            address.full_clean()
        self.assertIn("latitude", ctx.exception.message_dict)
        self.assertIn("longitude", ctx.exception.message_dict)

    def test_only_one_default_address_per_user(self):
        user = make_user()
        make_address(user, is_default=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_address(user, label="Kantor", is_default=True)
        # Pengguna lain tetap boleh punya alamat utama sendiri.
        make_address(make_user("other@example.com"), is_default=True)

    def test_address_to_dict(self):
        address = make_address(make_user(), landmark="Dekat masjid")
        data = address.to_dict()
        self.assertEqual(data["label"], "Rumah")
        self.assertEqual(data["landmark"], "Dekat masjid")
        self.assertAlmostEqual(data["latitude"], -6.3682)
        self.assertIn("Rumah", str(address))


class AddressServiceTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def _save(self, **overrides):
        form = DeliveryAddressForm(address_payload(**overrides))
        self.assertTrue(form.is_valid(), form.errors)
        return save_delivery_address(form, owner=self.user)

    def test_first_address_becomes_default(self):
        first = self._save()
        second = self._save(label="Kos")
        self.assertTrue(first.is_default)
        second.refresh_from_db()
        self.assertFalse(second.is_default)

    def test_new_default_replaces_old_default(self):
        first = self._save()
        second = self._save(label="Kos", is_default="on")
        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_deleting_default_promotes_another_address(self):
        first = self._save()
        second = self._save(label="Kos")
        delete_delivery_address(first)
        second.refresh_from_db()
        self.assertTrue(second.is_default)

    def test_deleting_last_address(self):
        delete_delivery_address(self._save())
        self.assertFalse(DeliveryAddress.objects.exists())


class NominatimServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("apps.map.services.requests.get")
    def test_search_places_parses_and_caches(self, mock_get):
        mock_get.return_value = nominatim_response(
            [
                {
                    "display_name": "Menteng, Jakarta Pusat, Indonesia",
                    "name": "Menteng",
                    "lat": "-6.1963",
                    "lon": "106.8302",
                    "type": "suburb",
                },
                {"display_name": "data rusak"},
            ]
        )
        places = search_places("Menteng")
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["name"], "Menteng")
        self.assertAlmostEqual(places[0]["latitude"], -6.1963)

        # Panggilan kedua diambil dari cache, tidak memanggil Nominatim lagi.
        search_places("Menteng")
        self.assertEqual(mock_get.call_count, 1)
        _, kwargs = mock_get.call_args
        self.assertIn("User-Agent", kwargs["headers"])
        self.assertEqual(kwargs["params"]["countrycodes"], "id")

    @patch("apps.map.services.requests.get")
    def test_search_places_network_error(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("down")
        with self.assertRaises(GeocodingError):
            search_places("Depok")

    @patch("apps.map.services.requests.get")
    def test_search_places_http_error_and_invalid_payload(self, mock_get):
        mock_get.return_value = nominatim_response({}, status=503)
        with self.assertRaises(GeocodingError):
            search_places("Bogor")
        mock_get.return_value = nominatim_response({"not": "a list"})
        with self.assertRaises(GeocodingError):
            search_places("Bekasi")

    @patch("apps.map.services.requests.get")
    def test_reverse_geocode(self, mock_get):
        mock_get.return_value = nominatim_response(
            {"display_name": "Jl. Margonda", "lat": "-6.36", "lon": "106.83"}
        )
        place = reverse_geocode(-6.36, 106.83)
        self.assertEqual(place["display_name"], "Jl. Margonda")
        self.assertEqual(place["name"], "Jl. Margonda")

    @patch("apps.map.services.requests.get")
    def test_reverse_geocode_not_found(self, mock_get):
        mock_get.return_value = nominatim_response({"error": "Unable to geocode"})
        self.assertIsNone(reverse_geocode(0, 0))
        mock_get.return_value = nominatim_response({"lat": "x", "lon": "y"})
        self.assertIsNone(reverse_geocode(1, 1))


class TenantMapViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_tenant("Green Bowl", "green@example.com")
        make_tenant(
            "Kebun Salad",
            "salad@example.com",
            category=TenantLocation.Category.SALAD,
            latitude=Decimal("-6.186400"),
            longitude=Decimal("106.826700"),
        )
        make_tenant(
            "Kampus Sehat",
            "depok@example.com",
            city="Depok",
            district="Beji",
            latitude=Decimal("-6.368300"),
            longitude=Decimal("106.832600"),
            opening_time=time(3, 0),
            closing_time=time(3, 1),
        )
        # Tenan tanpa lokasi tidak tampil di peta.
        make_tenant("Tanpa Lokasi", "nolocation@example.com", skip=True)

    def api(self, **params):
        response = self.client.get(reverse("map:tenant_locations_api"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def names(self, **params):
        return [item["name"] for item in self.api(**params)["results"]]

    def test_map_page_is_public(self):
        response = self.client.get(reverse("map:map"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "map/map.html")
        self.assertContains(response, "Temukan tenant di sekitarmu")
        self.assertContains(response, "leaflet.js")
        self.assertContains(response, 'id="tenant-data"')

    def test_htmx_request_returns_partial(self):
        response = self.client.get(
            reverse("map:map"), {"category": "salad"}, HTTP_HX_REQUEST="true"
        )
        self.assertTemplateUsed(response, "map/partials/tenant_results.html")
        self.assertTemplateNotUsed(response, "map/map.html")
        self.assertContains(response, "Kebun Salad")
        self.assertNotContains(response, "Green Bowl")

    def test_results_sorted_by_distance_from_default_center(self):
        self.assertEqual(self.names(), ["Kebun Salad", "Green Bowl", "Kampus Sehat"])

    def test_filters(self):
        self.assertEqual(self.names(q="kebun"), ["Kebun Salad"])
        self.assertEqual(self.names(q="beji"), ["Kampus Sehat"])
        self.assertEqual(self.names(city="depok"), ["Kampus Sehat"])
        self.assertEqual(self.names(category="salad"), ["Kebun Salad"])
        self.assertNotIn("Kampus Sehat", self.names(open_now="on"))

    def test_radius_filter_uses_chosen_center(self):
        depok = {"lat": "-6.3646", "lng": "106.8287"}
        self.assertEqual(self.names(radius="3", **depok), ["Kampus Sehat"])
        self.assertEqual(len(self.names(radius="10")), 2)

    def test_invalid_filters_are_ignored(self):
        self.assertEqual(len(self.names(radius="999", lat="abc")), 3)

    def test_contact_only_visible_to_logged_in_users(self):
        guest = self.api()["results"][0]
        self.assertNotIn("phone_number", guest)
        response = self.client.get(reverse("map:map"))
        self.assertContains(response, "Login untuk lihat kontak")
        self.assertNotContains(response, "081234567890")

        make_user()
        self.client.login(email="user@example.com", password=PASSWORD)
        member = self.api()["results"][0]
        self.assertEqual(member["phone_number"], "081234567890")

    def test_api_shape(self):
        data = self.api()
        self.assertEqual(data["count"], 3)
        first = data["results"][0]
        for key in ("latitude", "longitude", "distance_km", "is_open_now"):
            self.assertIn(key, first)


class SearchApiTests(TestCase):
    url = reverse("map:search_api")

    @patch("apps.map.views.search_places")
    def test_json_search(self, mock_search):
        mock_search.return_value = [
            {
                "display_name": "Depok",
                "name": "Depok",
                "latitude": -6.4,
                "longitude": 106.8,
            }
        ]
        response = self.client.get(self.url, {"q": "Depok"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["name"], "Depok")
        mock_search.assert_called_once_with("Depok")

    @patch("apps.map.views.search_places")
    def test_htmx_search_renders_clickable_results(self, mock_search):
        mock_search.return_value = [
            {
                "display_name": "Depok, Jawa Barat",
                "name": "Depok",
                "latitude": -6.4,
                "longitude": 106.8,
            }
        ]
        response = self.client.get(self.url, {"q": "Depok"}, HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(response, "map/partials/search_results.html")
        self.assertContains(response, 'data-place-lat="-6.4"')
        self.assertContains(response, "Depok, Jawa Barat")

    @patch("apps.map.views.search_places")
    def test_short_query_is_not_sent(self, mock_search):
        response = self.client.get(self.url, {"q": "de"})
        self.assertEqual(response.status_code, 400)
        response = self.client.get(self.url, {"q": "de"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "minimal 3 huruf")
        mock_search.assert_not_called()

    @patch("apps.map.views.search_places", side_effect=GeocodingError("Mati"))
    def test_search_error(self, _mock_search):
        response = self.client.get(self.url, {"q": "Depok"})
        self.assertEqual(response.status_code, 502)
        response = self.client.get(self.url, {"q": "Depok"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Mati")

    @patch("apps.map.views.search_places", return_value=[])
    def test_htmx_empty_results(self, _mock_search):
        response = self.client.get(self.url, {"q": "zzzz"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Tidak ada hasil")


class ReverseApiTests(TestCase):
    url = reverse("map:reverse_api")

    @patch("apps.map.views.reverse_geocode")
    def test_reverse(self, mock_reverse):
        mock_reverse.return_value = {"display_name": "Jl. Margonda"}
        response = self.client.get(self.url, {"lat": "-6.36", "lng": "106.83"})
        self.assertEqual(response.json()["result"]["display_name"], "Jl. Margonda")

    def test_invalid_coordinates(self):
        self.assertEqual(self.client.get(self.url, {"lat": "x"}).status_code, 400)
        response = self.client.get(self.url, {"lat": "100", "lng": "0"})
        self.assertEqual(response.status_code, 400)

    @patch("apps.map.views.reverse_geocode", return_value=None)
    def test_not_found(self, _mock_reverse):
        response = self.client.get(self.url, {"lat": "0", "lng": "0"})
        self.assertEqual(response.status_code, 404)

    @patch("apps.map.views.reverse_geocode", side_effect=GeocodingError("Mati"))
    def test_service_error(self, _mock_reverse):
        response = self.client.get(self.url, {"lat": "0", "lng": "0"})
        self.assertEqual(response.status_code, 502)


class AddressViewTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user("other@example.com")
        self.client.login(email="user@example.com", password=PASSWORD)

    def test_pages_require_login(self):
        self.client.logout()
        response = self.client.get(reverse("map:addresses"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('map:addresses')}",
            fetch_redirect_response=False,
        )
        response = self.client.post(reverse("map:address_create"), address_payload())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(DeliveryAddress.objects.exists())

    def test_api_returns_401_for_guests(self):
        self.client.logout()
        response = self.client.get(
            reverse("map:address_list_api"), HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 401)

    def test_list_page_shows_only_own_addresses(self):
        make_address(self.user, label="Rumah Saya")
        make_address(self.other, label="Rumah Orang Lain")
        make_tenant()
        response = self.client.get(reverse("map:addresses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rumah Saya")
        self.assertNotContains(response, "Rumah Orang Lain")
        self.assertContains(response, "Green Bowl")  # lokasi tenan di peta

        data = self.client.get(reverse("map:address_list_api")).json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["label"], "Rumah Saya")

    def test_detail_api(self):
        address = make_address(self.user)
        response = self.client.get(reverse("map:address_detail_api", args=[address.pk]))
        self.assertEqual(response.json()["address"]["id"], address.pk)

    def test_create_with_regular_post(self):
        response = self.client.post(reverse("map:address_create"), address_payload())
        self.assertRedirects(response, reverse("map:addresses"))
        address = DeliveryAddress.objects.get()
        self.assertEqual(address.owner, self.user)
        self.assertEqual(address.courier_note, "Titip resepsionis")
        self.assertTrue(address.is_default)

    def test_create_with_htmx_returns_panel_and_toast(self):
        response = self.client.post(
            reverse("map:address_create"), address_payload(), HTTP_HX_REQUEST="true"
        )
        self.assertTemplateUsed(response, "map/partials/address_panel.html")
        self.assertContains(response, "Kantor")
        self.assertContains(response, 'id="address-data"')
        trigger = json.loads(response["HX-Trigger"])
        self.assertEqual(trigger["showToast"]["level"], "success")

    def test_create_with_json_body(self):
        response = self.client.post(
            reverse("map:address_create"),
            data=json.dumps(
                {**address_payload(), "is_default": True, "landmark": None}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["address"]["is_default"])

    def test_create_invalid(self):
        bad = address_payload(latitude="200", label="")
        response = self.client.post(
            reverse("map:address_create"), bad, HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("latitude", response.json()["errors"])

        response = self.client.post(
            reverse("map:address_create"), bad, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(
            json.loads(response["HX-Trigger"])["showToast"]["level"], "error"
        )
        self.assertContains(response, "ui-field--error")

        response = self.client.post(reverse("map:address_create"), bad)
        self.assertRedirects(response, reverse("map:addresses"))

        response = self.client.post(
            reverse("map:address_create"),
            data="{not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DeliveryAddress.objects.exists())

    def test_edit_form(self):
        address = make_address(self.user, label="Rumah Lama")
        url = reverse("map:address_edit", args=[address.pk])
        response = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(response, "map/partials/address_form.html")
        self.assertContains(response, 'Ubah alamat "Rumah Lama"')
        self.assertContains(response, reverse("map:address_update", args=[address.pk]))
        response = self.client.get(url)
        self.assertTemplateUsed(response, "map/addresses.html")

    def test_update(self):
        address = make_address(self.user)
        url = reverse("map:address_update", args=[address.pk])
        payload = address_payload(label="Rumah Baru", courier_note="Bel dua kali")

        response = self.client.post(url, payload, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Rumah Baru")
        address.refresh_from_db()
        self.assertEqual(address.courier_note, "Bel dua kali")

        response = self.client.post(url, payload, HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["address"]["label"], "Rumah Baru")
        response = self.client.post(url, payload)
        self.assertRedirects(response, reverse("map:addresses"))

    def test_update_invalid(self):
        address = make_address(self.user)
        url = reverse("map:address_update", args=[address.pk])
        bad = address_payload(longitude="")
        response = self.client.post(url, bad, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Ubah alamat")
        response = self.client.post(url, bad, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post(url, bad)
        self.assertRedirects(response, reverse("map:address_edit", args=[address.pk]))
        address.refresh_from_db()
        self.assertEqual(address.label, "Rumah")

    def test_delete(self):
        address = make_address(self.user)
        url = reverse("map:address_delete", args=[address.pk])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Belum ada alamat tersimpan")
        self.assertFalse(DeliveryAddress.objects.exists())

        for headers, status in (({"HTTP_ACCEPT": "application/json"}, 200), ({}, 302)):
            address = make_address(self.user)
            response = self.client.post(
                reverse("map:address_delete", args=[address.pk]), **headers
            )
            self.assertEqual(response.status_code, status)
            self.assertFalse(DeliveryAddress.objects.filter(pk=address.pk).exists())

    def test_set_default(self):
        first = make_address(self.user, is_default=True)
        second = make_address(self.user, label="Kantor")
        response = self.client.post(
            reverse("map:address_set_default", args=[second.pk]), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(second.is_default)
        self.assertFalse(first.is_default)

        response = self.client.post(
            reverse("map:address_set_default", args=[first.pk]),
            HTTP_ACCEPT="application/json",
        )
        self.assertTrue(response.json()["address"]["is_default"])
        response = self.client.post(
            reverse("map:address_set_default", args=[second.pk])
        )
        self.assertRedirects(response, reverse("map:addresses"))

    def test_cannot_touch_other_users_address(self):
        foreign = make_address(self.other, label="Milik Orang")
        for name in ("address_update", "address_delete", "address_set_default"):
            response = self.client.post(
                reverse(f"map:{name}", args=[foreign.pk]), address_payload()
            )
            self.assertEqual(response.status_code, 404, name)
        for name in ("address_edit", "address_detail_api"):
            response = self.client.get(reverse(f"map:{name}", args=[foreign.pk]))
            self.assertEqual(response.status_code, 404, name)
        foreign.refresh_from_db()
        self.assertEqual(foreign.label, "Milik Orang")

    def test_mutations_require_post(self):
        address = make_address(self.user)
        response = self.client.get(reverse("map:address_delete", args=[address.pk]))
        self.assertEqual(response.status_code, 405)


class TenantLocationViewTests(TestCase):
    url = reverse("map:tenant_location")

    def location_payload(self, **overrides):
        data = {
            "address": "Jl. Cikini Raya No. 58",
            "district": "Cikini",
            "city": "Jakarta Pusat",
            "category": "plant-based",
            "opening_time": "08:00",
            "closing_time": "20:00",
            "delivery_radius_km": "4.5",
            "latitude": "-6.192300",
            "longitude": "106.840400",
        }
        data.update(overrides)
        return data

    def setUp(self):
        self.tenant_user = make_tenant("Mangkuk Lestari", skip=True)
        self.client.login(email="tenant@example.com", password=PASSWORD)

    def test_only_tenants_can_manage_location(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        make_user()
        self.client.login(email="user@example.com", password=PASSWORD)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("map:tenant_location_delete")).status_code, 403
        )

    def test_create_update_and_delete_location(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Tambahkan lokasi")

        response = self.client.post(self.url, self.location_payload())
        self.assertRedirects(response, self.url)
        location = TenantLocation.objects.get(tenant=self.tenant_user.tenant)
        self.assertEqual(location.delivery_radius_km, Decimal("4.5"))
        self.assertContains(self.client.get(self.url), "Ubah lokasi")

        response = self.client.post(
            self.url,
            self.location_payload(city="Depok"),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.json()["location"]["city"], "Depok")
        self.assertEqual(TenantLocation.objects.count(), 1)

        response = self.client.post(reverse("map:tenant_location_delete"))
        self.assertRedirects(response, self.url)
        self.assertFalse(TenantLocation.objects.exists())

        response = self.client.post(
            reverse("map:tenant_location_delete"), HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.json(), {"deleted": False})

    def test_invalid_location(self):
        bad = self.location_payload(latitude="-100", delivery_radius_km="0")
        response = self.client.post(self.url, bad)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "ui-field--error", status_code=400)
        response = self.client.post(self.url, bad, HTTP_ACCEPT="application/json")
        self.assertIn("latitude", response.json()["errors"])
        self.assertFalse(TenantLocation.objects.exists())

    def test_tenant_without_profile_gets_404(self):
        user = CustomUser.objects.create_user(
            email="broken@example.com",
            password=PASSWORD,
            account_type=CustomUser.AccountType.TENANT,
        )
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 404)


class SeedCommandTests(TestCase):
    def test_seed_is_idempotent(self):
        out = StringIO()
        call_command("seed_map", stdout=out)
        call_command("seed_map", stdout=out)
        self.assertEqual(TenantLocation.objects.count(), len(TENANT_LOCATIONS))
        self.assertIn("0 baru", out.getvalue())
        user = CustomUser.objects.get(email="tenant01@seed.sustainabowl.id")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.is_tenant)
