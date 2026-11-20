"""Tes endpoint Django REST Framework modul map (/api/v1/map/...)."""

from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import DeliveryAddress, TenantLocation
from .services import GeocodingError
from .tests import address_payload, make_address, make_tenant, make_user


class MapApiTestCase(APITestCase):
    def setUp(self):
        cache.clear()

    def login(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")


class TenantLocationsApiTests(MapApiTestCase):
    url = reverse("map_api:tenants")

    def setUp(self):
        super().setUp()
        make_tenant("Green Bowl", "green@example.com")
        make_tenant(
            "Salad Depok",
            "salad@example.com",
            city="Depok",
            district="Beji",
            category=TenantLocation.Category.SALAD,
            latitude=Decimal("-6.368200"),
            longitude=Decimal("106.832000"),
        )

    def test_public_list_hides_contact(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertIn("center", payload)
        self.assertNotIn("phone_number", payload["results"][0])
        self.assertIsInstance(payload["results"][0]["latitude"], float)

    def test_logged_in_list_shows_contact(self):
        self.login(make_user())
        payload = self.client.get(self.url).json()
        self.assertEqual(payload["results"][0]["phone_number"], "081234567890")

    def test_filters_by_city_category_and_query(self):
        payload = self.client.get(self.url, {"city": "depok"}).json()
        self.assertEqual([t["name"] for t in payload["results"]], ["Salad Depok"])
        payload = self.client.get(self.url, {"category": "salad"}).json()
        self.assertEqual(payload["count"], 1)
        payload = self.client.get(self.url, {"q": "menteng"}).json()
        self.assertEqual([t["name"] for t in payload["results"]], ["Green Bowl"])

    def test_radius_uses_given_center_and_sorts_by_distance(self):
        params = {"lat": "-6.368200", "lng": "106.832000"}
        payload = self.client.get(self.url, params).json()
        self.assertEqual(payload["results"][0]["name"], "Salad Depok")
        payload = self.client.get(self.url, {**params, "radius": "5"}).json()
        self.assertEqual(payload["count"], 1)

    def test_invalid_filters_return_400(self):
        for params in (
            {"category": "pizza"},
            {"radius": "7"},
            {"lat": "100", "lng": "106"},
            {"lat": "-6.2"},
        ):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_options(self):
        payload = self.client.get(reverse("map_api:tenant-filters")).json()
        self.assertEqual(payload["cities"], ["Depok", "Jakarta Pusat"])
        self.assertIn(
            {"value": "salad", "label": "Salad & wraps"}, payload["categories"]
        )
        self.assertEqual(payload["radius_km"], [1, 3, 5, 10])


class GeocodingApiTests(MapApiTestCase):
    def setUp(self):
        super().setUp()
        self.login(make_user())

    def test_requires_token(self):
        self.client.credentials()
        for name in ("map_api:search", "map_api:reverse"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("apps.map.api_views.services.search_places")
    def test_search(self, search_places):
        search_places.return_value = [{"name": "Margonda", "latitude": -6.3}]
        response = self.client.get(reverse("map_api:search"), {"q": "  margonda "})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["query"], "margonda")
        search_places.assert_called_once_with("margonda")

    def test_search_too_short(self):
        response = self.client.get(reverse("map_api:search"), {"q": "ab"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("minimal 3", response.json()["q"][0])

    @patch("apps.map.api_views.services.search_places")
    def test_search_upstream_failure(self, search_places):
        search_places.side_effect = GeocodingError("Layanan tidak tersedia.")
        response = self.client.get(reverse("map_api:search"), {"q": "margonda"})
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    @patch("apps.map.api_views.services.reverse_geocode")
    def test_reverse(self, reverse_geocode):
        reverse_geocode.return_value = {"name": "Monas"}
        url = reverse("map_api:reverse")
        response = self.client.get(url, {"lat": "-6.17", "lng": "106.82"})
        self.assertEqual(response.json(), {"result": {"name": "Monas"}})

        reverse_geocode.return_value = None
        response = self.client.get(url, {"lat": "-6.17", "lng": "106.82"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.get(url, {"lat": "abc", "lng": "106.82"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DeliveryAddressApiTests(MapApiTestCase):
    list_url = reverse("map_api:addresses")

    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.other = make_user("other@example.com")
        self.login(self.user)

    def detail_url(self, address):
        return reverse("map_api:address-detail", args=[address.pk])

    def test_requires_token(self):
        self.client.credentials()
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_only_own_addresses(self):
        make_address(self.user, label="Rumah")
        make_address(self.other, label="Punya orang")
        payload = self.client.get(self.list_url).json()
        self.assertEqual([a["label"] for a in payload], ["Rumah"])

    def test_create_first_address_becomes_default(self):
        response = self.client.post(self.list_url, address_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertTrue(data["is_default"])
        self.assertEqual(data["latitude"], -6.2088)
        address = DeliveryAddress.objects.get(pk=data["id"])
        self.assertEqual(address.owner, self.user)

    def test_create_rounds_long_gps_coordinates(self):
        payload = address_payload(latitude=-6.20881234567, longitude=106.84561234567)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        address = DeliveryAddress.objects.get(pk=response.json()["id"])
        self.assertEqual(address.latitude, Decimal("-6.208812"))

    def test_create_new_default_releases_old_default(self):
        old = make_address(self.user, is_default=True)
        payload = address_payload(is_default=True)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        old.refresh_from_db()
        self.assertFalse(old.is_default)

    def test_create_validation_errors(self):
        payload = address_payload(label="   ", latitude="95")
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("label", response.json())
        self.assertIn("latitude", response.json())

    def test_owner_cannot_be_set_from_payload(self):
        payload = address_payload(owner=self.other.pk)
        response = self.client.post(self.list_url, payload, format="json")
        address = DeliveryAddress.objects.get(pk=response.json()["id"])
        self.assertEqual(address.owner, self.user)

    def test_retrieve_update_and_delete_own_address(self):
        address = make_address(self.user, is_default=True)
        url = self.detail_url(address)

        self.assertEqual(self.client.get(url).json()["label"], "Rumah")

        response = self.client.patch(url, {"courier_note": "Telepon dulu"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["courier_note"], "Telepon dulu")
        self.assertEqual(response.json()["label"], "Rumah")

        response = self.client.put(url, address_payload(), format="json")
        self.assertEqual(response.json()["label"], "Kantor")

        response = self.client.put(url, {"label": "Kos"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DeliveryAddress.objects.filter(pk=address.pk).exists())

    def test_delete_default_promotes_another_address(self):
        default = make_address(self.user, is_default=True)
        other = make_address(self.user, label="Kampus")
        self.client.delete(self.detail_url(default))
        other.refresh_from_db()
        self.assertTrue(other.is_default)

    def test_other_users_address_is_not_found(self):
        address = make_address(self.other)
        url = self.detail_url(address)
        default_url = reverse("map_api:address-set-default", args=[address.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"label": "x"}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(self.client.post(default_url).status_code, 404)
        self.assertTrue(DeliveryAddress.objects.filter(pk=address.pk).exists())

    def test_set_default(self):
        home = make_address(self.user, is_default=True)
        campus = make_address(self.user, label="Kampus")
        url = reverse("map_api:address-set-default", args=[campus.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["is_default"])
        home.refresh_from_db()
        self.assertFalse(home.is_default)


class TenantLocationApiTests(MapApiTestCase):
    url = reverse("map_api:tenant-location")

    def location_payload(self, **overrides):
        data = {
            "address": "Jl. Kenari No. 5",
            "district": "Salemba",
            "city": "Jakarta Pusat",
            "category": "plant-based",
            "opening_time": "09:00",
            "closing_time": "20:00",
            "delivery_radius_km": "4.5",
            "latitude": -6.195,
            "longitude": 106.85,
        }
        data.update(overrides)
        return data

    def test_customer_is_forbidden(self):
        self.login(make_user())
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_create_with_put_then_patch_and_delete(self):
        tenant_user = make_tenant(skip=True)
        self.login(tenant_user)

        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(
            self.client.patch(self.url, {"city": "Depok"}).status_code, 404
        )

        response = self.client.put(self.url, self.location_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["opening_time"], "09:00")
        self.assertEqual(response.json()["tenant_id"], tenant_user.tenant.pk)

        response = self.client.patch(self.url, {"city": "Depok"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["city"], "Depok")
        self.assertEqual(response.json()["address"], "Jl. Kenari No. 5")

        self.assertEqual(self.client.get(self.url).json()["city"], "Depok")

        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertFalse(TenantLocation.objects.exists())
        self.assertEqual(self.client.delete(self.url).status_code, 404)

    def test_invalid_location(self):
        self.login(make_tenant(skip=True))
        payload = self.location_payload(category="pizza", delivery_radius_km="0.1")
        response = self.client.put(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.json())
        self.assertIn("delivery_radius_km", response.json())
