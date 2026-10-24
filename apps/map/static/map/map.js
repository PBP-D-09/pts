/* Modul map SustainaBowl: peta Leaflet + OpenStreetMap.
 *
 * Halaman memilih mode lewat atribut data-map-page pada <main>:
 *   - "tenants"   : peta publik lokasi tenan dengan filter HTMX
 *   - "addresses" : CRUD alamat pengiriman dengan pin interaktif
 *   - "tenant-location" : tenan mengatur titik lokasinya sendiri
 */
(() => {
  if (typeof L === "undefined") return;

  const NEAREST_TO_FIT = 8;
  const TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
  const TILE_ATTRIBUTION =
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

  const readJson = (id) => {
    const element = document.getElementById(id);
    if (!element) return null;
    try {
      return JSON.parse(element.textContent);
    } catch {
      return null;
    }
  };

  const pinIcon = (variant, label = "") =>
    L.divIcon({
      className: "",
      html: `<span class="sb-pin sb-pin--${variant}">${label}</span>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      popupAnchor: [0, -14],
    });

  const createMap = (element, center, zoom = 14) => {
    const map = L.map(element, { scrollWheelZoom: false }).setView(
      [center.latitude, center.longitude],
      zoom,
    );
    L.tileLayer(TILE_URL, { maxZoom: 19, attribution: TILE_ATTRIBUTION }).addTo(map);
    // Leaflet perlu ukuran kontainer yang final; panggil ulang setelah layout siap.
    window.setTimeout(() => map.invalidateSize(), 150);
    return map;
  };

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const osmLink = (lat, lng) =>
    `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=18/${lat}/${lng}`;

  const tenantPopup = (tenant) => {
    const root = el("div");
    root.append(el("p", "sb-popup__title", tenant.name));
    root.append(
      el("p", "sb-popup__meta", `${tenant.category_label} · ${tenant.distance_km} km`),
    );
    root.append(
      el("p", "sb-popup__row", [tenant.address, tenant.district, tenant.city].filter(Boolean).join(", ")),
    );
    const hours = el("p", "sb-popup__row");
    const status = el(
      "span",
      tenant.is_open_now ? "sb-popup__status--open" : "sb-popup__status--closed",
      tenant.is_open_now ? "Buka" : "Tutup",
    );
    hours.append(status, ` · ${tenant.opening_time}–${tenant.closing_time}`);
    root.append(hours);
    if (tenant.phone_number) {
      root.append(el("p", "sb-popup__row", `Telp: ${tenant.phone_number}`));
    }
    const link = el("a", "sb-popup__link", "Buka di OpenStreetMap");
    link.href = osmLink(tenant.latitude, tenant.longitude);
    link.target = "_blank";
    link.rel = "noopener";
    root.append(link);
    return root;
  };

  const addressPopup = (address) => {
    const root = el("div");
    root.append(el("p", "sb-popup__title", address.is_default ? `${address.label} (utama)` : address.label));
    root.append(el("p", "sb-popup__meta", `${address.recipient_name} · ${address.phone_number}`));
    root.append(el("p", "sb-popup__row", address.address));
    if (address.landmark) root.append(el("p", "sb-popup__row", `Patokan: ${address.landmark}`));
    if (address.courier_note) root.append(el("p", "sb-popup__row", `Catatan kurir: ${address.courier_note}`));
    return root;
  };

  const fitToMarkers = (map, markers, fallbackCenter) => {
    if (markers.length === 0) {
      if (fallbackCenter) map.setView([fallbackCenter.latitude, fallbackCenter.longitude], 13);
      return;
    }
    const group = L.featureGroup(markers);
    map.fitBounds(group.getBounds().pad(0.2), { maxZoom: 15 });
  };

  const reverseGeocode = async (url, lat, lng) => {
    try {
      const response = await fetch(`${url}?lat=${lat}&lng=${lng}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return null;
      const payload = await response.json();
      return payload.result || null;
    } catch {
      return null;
    }
  };

  /* ------------------------------------------------------------------ */
  /* Pin interaktif untuk memilih titik (alamat pengiriman/lokasi tenan) */
  /* ------------------------------------------------------------------ */
  const createPicker = (map, root) => {
    const reverseUrl = root.dataset.reverseUrl;
    let marker = null;

    const inputs = () => ({
      lat: document.querySelector("[data-lat-input]"),
      lng: document.querySelector("[data-lng-input]"),
      address: document.querySelector("[data-address-input]"),
    });

    const place = (lat, lng, { fill = true, label } = {}) => {
      const latFixed = Number(lat).toFixed(6);
      const lngFixed = Number(lng).toFixed(6);
      if (!marker) {
        marker = L.marker([lat, lng], { draggable: true, icon: pinIcon("draft") }).addTo(map);
        marker.on("dragend", () => {
          const position = marker.getLatLng();
          place(position.lat, position.lng);
        });
      } else {
        marker.setLatLng([lat, lng]);
      }
      const fields = inputs();
      if (fields.lat) fields.lat.value = latFixed;
      if (fields.lng) fields.lng.value = lngFixed;
      if (label && fields.address) {
        fields.address.value = label;
      } else if (fill && fields.address && reverseUrl) {
        reverseGeocode(reverseUrl, latFixed, lngFixed).then((result) => {
          if (result && fields.address) fields.address.value = result.display_name;
        });
      }
    };

    const syncFromInputs = () => {
      const fields = inputs();
      const lat = parseFloat(fields.lat?.value);
      const lng = parseFloat(fields.lng?.value);
      if (Number.isFinite(lat) && Number.isFinite(lng)) {
        place(lat, lng, { fill: false });
        map.setView([lat, lng], Math.max(map.getZoom(), 16));
      } else if (marker) {
        map.removeLayer(marker);
        marker = null;
      }
    };

    map.on("click", (event) => place(event.latlng.lat, event.latlng.lng));
    document.addEventListener("input", (event) => {
      if (event.target.matches("[data-lat-input], [data-lng-input]")) syncFromInputs();
    });

    return { place, syncFromInputs };
  };

  /* Hasil pencarian Nominatim (dirender HTMX) memindahkan pin di peta. */
  const bindSearchResults = (onPick) => {
    document.addEventListener("click", (event) => {
      const button = event.target.closest("[data-place-lat]");
      if (!button) return;
      event.preventDefault();
      const lat = parseFloat(button.dataset.placeLat);
      const lng = parseFloat(button.dataset.placeLng);
      onPick(lat, lng, button.dataset.placeName || "");
      const container = button.closest("[data-search-results]");
      if (container) container.innerHTML = "";
    });
  };

  /* --------------------------- Peta tenan --------------------------- */
  const initTenantsPage = (root) => {
    const mapElement = document.getElementById("tenant-map");
    const center = readJson("tenant-center") || { latitude: -6.175392, longitude: 106.827153 };
    const map = createMap(mapElement, center, 13);
    const layer = L.layerGroup().addTo(map);
    let markersById = new Map();
    let centerMarker = null;

    const form = document.getElementById("tenant-filter-form");
    const latInput = form?.querySelector("input[name=lat]");
    const lngInput = form?.querySelector("input[name=lng]");

    const render = () => {
      layer.clearLayers();
      markersById = new Map();
      const tenants = readJson("tenant-data") || [];
      const markers = tenants.map((tenant, index) => {
        const marker = L.marker([tenant.latitude, tenant.longitude], {
          icon: pinIcon("tenant", index + 1),
          title: tenant.name,
        }).bindPopup(tenantPopup(tenant));
        marker.addTo(layer);
        markersById.set(String(tenant.id), marker);
        return marker;
      });

      if (centerMarker) map.removeLayer(centerMarker);
      centerMarker = null;
      // Daftar sudah urut dari yang terdekat; fokuskan peta ke beberapa tenant terdekat.
      const nearest = markers.slice(0, NEAREST_TO_FIT);
      if (latInput?.value && lngInput?.value) {
        centerMarker = L.marker([latInput.value, lngInput.value], {
          icon: pinIcon("me"),
          title: "Titik pencarian",
          zIndexOffset: -100,
        }).addTo(map);
        nearest.push(centerMarker);
      }
      fitToMarkers(map, nearest, readJson("tenant-center"));
    };

    const submitFilters = () => {
      if (window.htmx && form) window.htmx.trigger(form, "submit");
      else form?.submit();
    };

    const setCenter = (lat, lng, label) => {
      if (!latInput || !lngInput) return;
      latInput.value = Number(lat).toFixed(6);
      lngInput.value = Number(lng).toFixed(6);
      const locationInput = document.getElementById("location-query");
      if (locationInput && label) locationInput.value = label.split(",")[0];
      submitFilters();
    };

    document.addEventListener("click", (event) => {
      const card = event.target.closest("[data-tenant-id]");
      if (!card || event.target.closest("a")) return;
      const marker = markersById.get(card.dataset.tenantId);
      if (!marker) return;
      map.setView(marker.getLatLng(), 16);
      marker.openPopup();
      document.querySelectorAll("[data-tenant-id]").forEach((item) =>
        item.classList.toggle("ring-2", item === card),
      );
      if (window.innerWidth < 1024) mapElement.scrollIntoView({ behavior: "smooth", block: "center" });
    });

    bindSearchResults((lat, lng, label) => setCenter(lat, lng, label));

    document.getElementById("use-my-location")?.addEventListener("click", () => {
      if (!navigator.geolocation) {
        window.showToast?.("Browser tidak mendukung lokasi.", "warning");
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (position) => setCenter(position.coords.latitude, position.coords.longitude, "Lokasiku"),
        () => window.showToast?.("Izin lokasi ditolak.", "warning"),
      );
    });

    document.getElementById("clear-location")?.addEventListener("click", () => {
      if (latInput) latInput.value = "";
      if (lngInput) lngInput.value = "";
      const locationInput = document.getElementById("location-query");
      if (locationInput) locationInput.value = "";
      submitFilters();
    });

    document.body.addEventListener("htmx:afterSwap", (event) => {
      if (event.detail.target.id === "tenant-results") render();
    });

    render();
  };

  /* ------------------------- Alamat pengiriman ------------------------- */
  const initAddressesPage = (root) => {
    const mapElement = document.getElementById("address-map");
    const center = readJson("address-center") || { latitude: -6.175392, longitude: 106.827153 };
    const map = createMap(mapElement, center, 13);
    const savedLayer = L.layerGroup().addTo(map);
    const tenantLayer = L.layerGroup().addTo(map);
    const picker = createPicker(map, root);

    (readJson("tenant-data") || []).forEach((tenant) => {
      L.marker([tenant.latitude, tenant.longitude], {
        icon: pinIcon("tenant", ""),
        title: tenant.name,
        opacity: 0.7,
      })
        .bindPopup(tenantPopup(tenant))
        .addTo(tenantLayer);
    });

    const renderSaved = ({ fit = true } = {}) => {
      savedLayer.clearLayers();
      const addresses = readJson("address-data") || [];
      const markers = addresses.map((address, index) =>
        L.marker([address.latitude, address.longitude], {
          icon: pinIcon(address.is_default ? "default" : "address", index + 1),
          title: address.label,
        })
          .bindPopup(addressPopup(address))
          .addTo(savedLayer),
      );
      if (fit) fitToMarkers(map, markers, null);
      picker.syncFromInputs();
    };

    document.addEventListener("click", (event) => {
      const focus = event.target.closest("[data-focus-address]");
      if (!focus) return;
      const lat = parseFloat(focus.dataset.lat);
      const lng = parseFloat(focus.dataset.lng);
      map.setView([lat, lng], 17);
      mapElement.scrollIntoView({ behavior: "smooth", block: "center" });
    });

    bindSearchResults((lat, lng, label) => {
      picker.place(lat, lng, { label });
      map.setView([lat, lng], 17);
    });

    document.body.addEventListener("htmx:afterSwap", (event) => {
      const id = event.detail.target.id;
      if (id === "address-panel") renderSaved();
      if (id === "address-form-slot") {
        picker.syncFromInputs();
        mapElement.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });

    renderSaved();
  };

  /* -------------------------- Lokasi tenan -------------------------- */
  const initTenantLocationPage = (root) => {
    const center = readJson("location-center") || { latitude: -6.175392, longitude: 106.827153 };
    const map = createMap(document.getElementById("location-map"), center, 15);
    const picker = createPicker(map, root);
    bindSearchResults((lat, lng, label) => {
      picker.place(lat, lng, { label });
      map.setView([lat, lng], 17);
    });
    picker.syncFromInputs();
  };

  const init = () => {
    const root = document.querySelector("[data-map-page]");
    if (!root) return;
    const pages = {
      tenants: initTenantsPage,
      addresses: initAddressesPage,
      "tenant-location": initTenantLocationPage,
    };
    pages[root.dataset.mapPage]?.(root);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
