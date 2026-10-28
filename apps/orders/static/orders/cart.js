// Stepper kuantitas dan tombol Remove di halaman keranjang via AJAX (tanpa reload).
// Tanpa JavaScript, form yang sama tetap berfungsi lewat POST biasa.
(() => {
  const page = document.querySelector("[data-cart-page]");
  if (!page) return;

  const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;
  const setText = (selector, text) =>
    document.querySelectorAll(selector).forEach((element) => {
      element.textContent = text;
    });

  const renderCart = (cart) => {
    const isEmpty = cart.items.length === 0;
    setText("[data-cart-total-items]", plural(cart.total_items, "item"));
    setText("[data-cart-tenant-count]", plural(cart.tenant_count, "tenant"));
    setText("[data-cart-subtotal]", cart.formatted_subtotal);
    document.querySelectorAll("[data-cart-count]").forEach((badge) => {
      badge.textContent = cart.total_items;
      badge.hidden = cart.total_items === 0;
    });
    document.querySelectorAll("[data-cart-content]").forEach((element) => {
      element.hidden = isEmpty;
    });
    page.querySelector("[data-cart-empty]").hidden = !isEmpty;
  };

  const post = async (form, body) => {
    // getAttribute: form.action tertimpa oleh tombol stepper bernama "action".
    const response = await fetch(form.getAttribute("action"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.success) {
      throw new Error(data.error || data.message || "Something went wrong. Please try again.");
    }
    return data;
  };

  const updateQuantity = async (form, action) => {
    const row = form.closest("[data-cart-item]");
    const buttons = form.querySelectorAll("button");
    buttons.forEach((button) => {
      button.disabled = true;
    });
    let quantity = Number(row.querySelector("[data-item-quantity]").textContent);
    try {
      const data = await post(form, { action });
      quantity = data.item.quantity;
      row.querySelector("[data-item-quantity]").textContent = quantity;
      row.querySelector("[data-item-subtotal]").textContent = data.item.formatted_subtotal;
      renderCart(data.cart);
    } catch (error) {
      window.showToast?.(error.message, "error");
    } finally {
      buttons.forEach((button) => {
        button.disabled = button.matches("[data-stepper-decrease]") && quantity <= 1;
      });
    }
  };

  const removeItem = async (form) => {
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const data = await post(form, {});
      form.closest("[data-cart-item]").remove();
      renderCart(data.cart);
      window.showToast?.(data.message, "success");
    } catch (error) {
      button.disabled = false;
      window.showToast?.(error.message, "error");
    }
  };

  page.addEventListener("submit", (event) => {
    const form = event.target;
    if (form.matches("[data-cart-stepper]")) {
      event.preventDefault();
      updateQuantity(form, event.submitter?.value);
    } else if (form.matches("[data-cart-remove]")) {
      event.preventDefault();
      removeItem(form);
    }
  });
})();
