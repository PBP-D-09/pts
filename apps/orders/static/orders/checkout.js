// Ringkasan biaya checkout, preview peta, dan tambah alamat baru tanpa keluar checkout.
// Angka di sini hanya tampilan; server menghitung ulang semuanya saat order dibuat.
(() => {
  const form = document.querySelector("[data-checkout-form]");
  if (!form) return;

  // Catatan kurir dan toast dibawa melewati reload setelah alamat baru disimpan.
  const NOTE_KEY = "orders:checkout-note";
  const SAVED_KEY = "orders:address-saved";

  const subtotal = Number(form.dataset.subtotal);
  const rupiah = (amount) => `Rp ${amount.toLocaleString("id-ID")}`;
  const checked = (name) => form.querySelector(`input[name="${name}"]:checked`);
  const setText = (selector, text) => {
    form.querySelector(selector).textContent = text;
  };

  const updateSummary = () => {
    const address = checked("address");
    const packaging = checked("packaging_type");
    const packagingFee = packaging ? Number(packaging.dataset.fee) : 0;
    const deliveryFee = address ? Number(address.dataset.fee) : 0;
    setText("[data-summary-packaging]", rupiah(packagingFee));
    setText("[data-summary-delivery]", address ? rupiah(deliveryFee) : "—");
    setText("[data-summary-total]", rupiah(subtotal + packagingFee + deliveryFee));
    setText("[data-summary-points]", packaging ? packaging.dataset.points : "0");
  };

  const noteInput = form.elements.delivery_notes;
  try {
    const savedNote = sessionStorage.getItem(NOTE_KEY);
    if (savedNote && !noteInput.value) noteInput.value = savedNote;
    if (sessionStorage.getItem(SAVED_KEY)) {
      window.showToast?.("Address saved and selected for this order.", "success");
    }
    sessionStorage.removeItem(NOTE_KEY);
    sessionStorage.removeItem(SAVED_KEY);
  } catch {
    // sessionStorage bisa diblokir browser; catatan cukup tidak dipulihkan.
  }

  // Preview peta memakai Leaflet + gaya pin dari modul map. Peta kecil tidak bisa
  // digeser (agar tidak menangkap scroll halaman); klik untuk memperbesar.
  const mapElement = document.getElementById("checkout-map");
  let showSelectedAddress = () => {};
  if (mapElement && typeof L !== "undefined") {
    const tenants = JSON.parse(document.getElementById("checkout-tenants").textContent);
    const center = JSON.parse(document.getElementById("checkout-map-center").textContent);
    const handlers = [
      "dragging",
      "touchZoom",
      "doubleClickZoom",
      "scrollWheelZoom",
      "boxZoom",
      "keyboard",
    ];
    const map = L.map(mapElement, {
      attributionControl: false,
      zoomControl: false,
      ...Object.fromEntries(handlers.map((handler) => [handler, false])),
    });
    const zoomControl = L.control.zoom({ position: "topleft" });
    L.control
      .attribution({ position: "bottomleft", prefix: false })
      .addAttribution(
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      )
      .addTo(map);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      referrerPolicy: "strict-origin-when-cross-origin",
    }).addTo(map);

    const pinIcon = (variant) =>
      L.divIcon({
        className: "",
        html: `<span class="sb-pin sb-pin--${variant}"></span>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      });
    tenants.forEach((tenant) => {
      L.marker([tenant.lat, tenant.lng], { icon: pinIcon("tenant"), title: tenant.name }).addTo(
        map,
      );
    });

    let addressMarker = null;
    let draftMarker = null;
    showSelectedAddress = () => {
      const points = tenants.map((tenant) => [tenant.lat, tenant.lng]);
      const address = checked("address");
      if (address) {
        const point = [Number(address.dataset.lat), Number(address.dataset.lng)];
        if (addressMarker) {
          addressMarker.setLatLng(point);
        } else {
          addressMarker = L.marker(point, { icon: pinIcon("address") }).addTo(map);
        }
        points.unshift(point);
      }
      if (points.length) {
        map.fitBounds(points, { padding: [40, 14], maxZoom: 16 });
      } else {
        map.setView([center.latitude, center.longitude], 13);
      }
    };
    // Leaflet perlu ukuran kontainer final; panggil ulang setelah layout/animasi.
    const refit = () => {
      map.invalidateSize();
      if (!draftMarker) showSelectedAddress();
    };
    showSelectedAddress();
    window.setTimeout(refit, 150);

    const preview = mapElement.closest("[data-map-preview]");
    const overlay = preview.querySelector("[data-map-overlay]");
    const expandButton = preview.querySelector("[data-map-expand]");
    const collapseButton = preview.querySelector("[data-map-collapse]");
    const hint = preview.querySelector("[data-map-hint]");
    let expanded = false;

    const setExpanded = (value, { focus = true } = {}) => {
      expanded = value;
      preview.toggleAttribute("data-expanded", value);
      overlay.hidden = value;
      expandButton.hidden = value;
      collapseButton.hidden = !value;
      handlers.forEach((handler) => map[handler][value ? "enable" : "disable"]());
      if (value) {
        zoomControl.addTo(map);
      } else {
        zoomControl.remove();
      }
      if (focus) (value ? collapseButton : expandButton).focus();
      // Durasi transisi tinggi di template: duration-300.
      window.setTimeout(refit, 320);
    };

    // Tambah alamat baru: pin di peta, isian di panel, simpan lewat API modul map.
    const panel = document.querySelector("[data-new-address]");
    const addressForm = document.getElementById("new-address-form");
    const fields = addressForm.elements;
    const errorBox = panel.querySelector("[data-new-address-error]");
    let autofilledAddress = "";

    const showError = (message) => {
      errorBox.textContent = message;
      errorBox.hidden = !message;
    };

    const fillAddressFromPin = async (lat, lng) => {
      try {
        const response = await fetch(`${addressForm.dataset.reverseUrl}?lat=${lat}&lng=${lng}`);
        if (!response.ok) return;
        const { result } = await response.json();
        // Jangan timpa alamat yang sudah diketik sendiri oleh pengguna.
        if (result && (!fields.address.value || fields.address.value === autofilledAddress)) {
          fields.address.value = result.display_name;
          autofilledAddress = result.display_name;
        }
      } catch {
        // Alamat tetap bisa diketik manual.
      }
    };

    const setDraftPoint = ({ lat, lng }) => {
      fields.latitude.value = lat.toFixed(6);
      fields.longitude.value = lng.toFixed(6);
      hint.hidden = true;
      showError("");
      fillAddressFromPin(fields.latitude.value, fields.longitude.value);
    };

    const placeDraft = (event) => {
      if (draftMarker) {
        draftMarker.setLatLng(event.latlng);
      } else {
        draftMarker = L.marker(event.latlng, { draggable: true, icon: pinIcon("draft") }).addTo(map);
        draftMarker.on("dragend", () => setDraftPoint(draftMarker.getLatLng()));
      }
      setDraftPoint(event.latlng);
    };

    const startAdding = () => {
      if (!expanded) setExpanded(true, { focus: false });
      panel.hidden = false;
      hint.hidden = Boolean(draftMarker);
      mapElement.classList.add("leaflet-crosshair");
      map.off("click", placeDraft).on("click", placeDraft);
      panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
      fields.label.focus({ preventScroll: true });
    };

    const stopAdding = () => {
      panel.hidden = true;
      hint.hidden = true;
      showError("");
      mapElement.classList.remove("leaflet-crosshair");
      map.off("click", placeDraft);
      draftMarker?.remove();
      draftMarker = null;
      autofilledAddress = "";
      addressForm.reset();
    };

    overlay.addEventListener("click", () => setExpanded(true));
    expandButton.addEventListener("click", () => setExpanded(true));
    collapseButton.addEventListener("click", () => {
      stopAdding();
      setExpanded(false);
    });
    document.querySelectorAll("[data-add-address]").forEach((button) => {
      button.addEventListener("click", startAdding);
    });
    panel.querySelector("[data-new-address-cancel]").addEventListener("click", stopAdding);
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (!panel.hidden) {
        stopAdding();
      } else if (expanded) {
        setExpanded(false);
      }
    });

    addressForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!fields.latitude.value) {
        showError("Click the map to place a pin for this address first.");
        return;
      }
      const submit = panel.querySelector('[type="submit"]');
      submit.disabled = true;
      try {
        const response = await fetch(addressForm.getAttribute("action"), {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            "X-CSRFToken": fields.csrfmiddlewaretoken.value,
          },
          body: JSON.stringify(Object.fromEntries(new FormData(addressForm))),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          const [field, messages] = Object.entries(data.errors || {})[0] || [];
          const label = fields[field]?.closest("label")?.querySelector(".ui-field__label");
          showError(
            messages
              ? `${label ? `${label.firstChild.textContent.trim()}: ` : ""}${messages[0]}`
              : data.error || "Couldn't save the address. Please try again.",
          );
          return;
        }
        const params = new URLSearchParams({ address: data.address.id });
        const packaging = checked("packaging_type");
        if (packaging) params.set("packaging", packaging.value);
        try {
          if (noteInput.value) sessionStorage.setItem(NOTE_KEY, noteInput.value);
          sessionStorage.setItem(SAVED_KEY, "1");
        } catch {
          // Lanjut tanpa memulihkan catatan.
        }
        window.location.assign(`${window.location.pathname}?${params}`);
      } catch {
        showError("Couldn't reach the server. Check your connection and try again.");
      } finally {
        submit.disabled = false;
      }
    });
  }

  form.addEventListener("change", (event) => {
    if (event.target.name === "address") showSelectedAddress();
    if (event.target.name === "address" || event.target.name === "packaging_type") {
      updateSummary();
    }
  });
})();
