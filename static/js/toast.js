(() => {
  const defaultDuration = 3000;
  const validLevels = new Set(["success", "warning", "error"]);

  const getContainer = () => document.getElementById("toast-container");

  window.showToast = (message, level = "success", options = {}) => {
    const container = getContainer();
    const text = String(message || "").trim();
    if (!container || !text) return null;

    const toast = document.createElement("p");
    const toastLevel = validLevels.has(level) ? level : "success";
    const duration = Number.isFinite(options.duration)
      ? options.duration
      : defaultDuration;

    toast.className = `ui-toast ui-toast--${toastLevel} pointer-events-auto`;
    toast.role = toastLevel === "error" ? "alert" : "status";
    toast.textContent = text;
    container.append(toast);

    if (duration > 0) {
      window.setTimeout(() => toast.remove(), duration);
    }

    return toast;
  };

  document.querySelectorAll("#django-toast-messages [data-toast-level]").forEach(
    (message) => window.showToast(message.textContent, message.dataset.toastLevel),
  );

  document.body.addEventListener("showToast", (event) => {
    const { message, level, options } = event.detail?.value || event.detail || {};
    window.showToast(message, level, options);
  });
})();
