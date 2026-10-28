// Halaman My orders: filter tanggal, Edit note, dan Cancel order via AJAX.
// Server mengirim ulang HTML kartu (card_html) agar markup hanya ada di template.
(() => {
  const page = document.querySelector("[data-orders-page]");
  if (!page) return;

  const activeStatus = page.dataset.activeStatus;
  const list = page.querySelector("[data-orders-list]");
  const noteDialog = document.getElementById("edit-note-dialog");
  const noteForm = noteDialog.querySelector("[data-edit-note-form]");
  const cancelDialog = document.getElementById("cancel-order-dialog");
  let noteUrl = null;
  let cancelForm = null;

  const post = async (url, csrfToken, body = {}) => {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.success) {
      throw new Error(data.error || "Something went wrong. Please try again.");
    }
    return data;
  };

  const csrfOf = (form) => form.querySelector("[name=csrfmiddlewaretoken]").value;

  const replaceCard = (element, data) => {
    const item = element.closest("[data-order-card]");
    // Kartu yang tidak lagi cocok dengan filter status aktif dikeluarkan dari daftar.
    if (activeStatus !== "all" && activeStatus !== data.order.status) {
      item.remove();
      const label = page.querySelector("[data-orders-count]");
      const total = Number(label.dataset.total) - 1;
      label.dataset.total = total;
      label.textContent = `${total} order${total === 1 ? "" : "s"}`;
      page.querySelector("[data-orders-empty]").hidden = list.children.length > 0;
      return;
    }
    item.innerHTML = data.card_html;
  };

  page.querySelector("[data-date-range]").addEventListener("change", (event) => {
    event.target.form.requestSubmit();
  });

  page.addEventListener("click", (event) => {
    const editButton = event.target.closest("[data-edit-note]");
    if (editButton) {
      noteUrl = editButton.dataset.url;
      noteDialog.querySelector("[data-dialog-order-code]").textContent =
        editButton.dataset.orderCode;
      noteForm.elements.delivery_notes.value = editButton.dataset.note;
      noteDialog.showModal();
      return;
    }
    const closeButton = event.target.closest("[data-dialog-close]");
    if (closeButton) closeButton.closest("dialog").close();
  });

  page.addEventListener("submit", async (event) => {
    const form = event.target;

    if (form.matches("[data-cancel-order]")) {
      event.preventDefault();
      cancelForm = form;
      cancelDialog.querySelector("[data-dialog-order-code]").textContent =
        form.dataset.orderCode;
      cancelDialog.showModal();
      return;
    }

    if (form.matches("[data-cancel-order-confirm]") && cancelForm) {
      try {
        const data = await post(cancelForm.getAttribute("action"), csrfOf(cancelForm));
        Object.entries(data.status_counts).forEach(([status, count]) => {
          const badge = page.querySelector(`[data-status-count="${status}"]`);
          if (badge) badge.textContent = count;
        });
        replaceCard(cancelForm, data);
        window.showToast?.(data.message, "success");
      } catch (error) {
        window.showToast?.(error.message, "error");
      }
      cancelForm = null;
      return;
    }

    if (form === noteForm) {
      event.preventDefault();
      const submit = form.querySelector("[type=submit]");
      submit.disabled = true;
      try {
        const data = await post(noteUrl, csrfOf(form), {
          delivery_notes: form.elements.delivery_notes.value,
        });
        const button = list.querySelector(`[data-edit-note][data-url="${noteUrl}"]`);
        if (button) replaceCard(button, data);
        noteDialog.close();
        window.showToast?.(data.message, "success");
      } catch (error) {
        window.showToast?.(error.message, "error");
      } finally {
        submit.disabled = false;
      }
    }
  });
})();
