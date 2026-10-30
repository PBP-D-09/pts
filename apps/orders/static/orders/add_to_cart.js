// Dialog konfirmasi "Add to cart" di halaman menu: pilih jumlah, lihat subtotal,
// lalu tambahkan ke keranjang via AJAX tanpa meninggalkan halaman.
// Tanpa JavaScript, form di kartu menu tetap menambah 1 item lewat POST biasa.
(() => {
  const dialog = document.querySelector("[data-add-to-cart-dialog]");
  if (!dialog) return;

  const confirmForm = dialog.querySelector("[data-add-to-cart-confirm]");
  const input = dialog.querySelector("[data-quantity-input]");
  const photo = dialog.querySelector("[data-item-photo]");
  const submitButton = confirmForm.querySelector("[type=submit]");
  const minQuantity = Number(input.min);
  const maxQuantity = Number(input.max);
  let source = null;

  const formatRupiah = (amount) => `Rp ${amount.toLocaleString("id-ID")}`;
  const setText = (selector, text) => {
    dialog.querySelector(selector).textContent = text;
  };

  const setQuantity = (value) => {
    const quantity = Math.min(maxQuantity, Math.max(minQuantity, Math.trunc(Number(value)) || minQuantity));
    input.value = quantity;
    dialog.querySelector("[data-quantity-step='-1']").disabled = quantity <= minQuantity;
    dialog.querySelector("[data-quantity-step='1']").disabled = quantity >= maxQuantity;
    setText("[data-quantity-subtotal]", formatRupiah(Number(source.dataset.price) * quantity));
    return quantity;
  };

  const open = (form) => {
    source = form;
    const { name, tenant, price } = form.dataset;
    setText("[data-item-name]", name);
    setText("[data-item-tenant]", tenant);
    setText("[data-item-price]", formatRupiah(Number(price)));
    const hasPhoto = Boolean(form.dataset.photo);
    if (hasPhoto) photo.src = form.dataset.photo;
    else photo.removeAttribute("src");
    photo.hidden = !hasPhoto;
    dialog.querySelector("[data-item-photo-placeholder]").hidden = hasPhoto;
    setQuantity(1);
    submitButton.disabled = false;
    dialog.showModal();
  };

  const addToCart = async () => {
    const quantity = setQuantity(input.value);
    submitButton.disabled = true;
    try {
      const response = await fetch(source.getAttribute("action"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": source.querySelector("[name=csrfmiddlewaretoken]").value,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ quantity }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.success) {
        throw new Error(data.error || "Couldn't add this item. Please try again.");
      }
      document.querySelectorAll("[data-cart-count]").forEach((badge) => {
        badge.textContent = data.cart.total_items;
        badge.hidden = data.cart.total_items === 0;
      });
      dialog.close();
      window.showToast?.(data.message, "success");
    } catch (error) {
      submitButton.disabled = false;
      window.showToast?.(error.message, "error");
    }
  };

  document.addEventListener("submit", (event) => {
    if (!event.target.matches("[data-add-to-cart]")) return;
    event.preventDefault();
    open(event.target);
  });

  confirmForm.addEventListener("submit", (event) => {
    event.preventDefault();
    addToCart();
  });

  dialog.querySelectorAll("[data-quantity-step]").forEach((button) => {
    button.addEventListener("click", () => {
      setQuantity(Number(input.value) + Number(button.dataset.quantityStep));
    });
  });
  input.addEventListener("change", () => setQuantity(input.value));
  dialog.querySelector("[data-dialog-close]").addEventListener("click", () => dialog.close());
  // Klik di luar kotak dialog (backdrop) juga menutupnya.
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
})();
