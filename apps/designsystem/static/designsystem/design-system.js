document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.querySelector("[data-sidebar]");
  const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  const sidebarOverlay = document.querySelector("[data-sidebar-overlay]");
  const sidebarOpenIcon = document.querySelector("[data-sidebar-open-icon]");
  const sidebarCloseIcon = document.querySelector("[data-sidebar-close-icon]");
  const desktopMedia = window.matchMedia("(min-width: 768px)");
  let sidebarOpen = false;

  const syncSidebar = () => {
    if (!sidebar || !sidebarToggle || !sidebarOverlay) return;

    const isDesktop = desktopMedia.matches;
    const isVisible = isDesktop || sidebarOpen;
    sidebar.classList.toggle("-translate-x-full", !isVisible);
    sidebar.classList.toggle("translate-x-0", isVisible);
    sidebar.setAttribute("aria-hidden", String(!isVisible));
    sidebar.inert = !isVisible;
    sidebarToggle.setAttribute("aria-expanded", String(sidebarOpen));
    sidebarToggle.setAttribute(
      "aria-label",
      sidebarOpen ? "Tutup navigasi design system" : "Buka navigasi design system",
    );
    sidebarOverlay.hidden = isDesktop || !sidebarOpen;
    if (sidebarOpenIcon) sidebarOpenIcon.hidden = sidebarOpen;
    if (sidebarCloseIcon) sidebarCloseIcon.hidden = !sidebarOpen;
    document.body.classList.toggle("overflow-hidden", sidebarOpen && !isDesktop);
  };

  const closeSidebar = (restoreFocus = false) => {
    if (!sidebarOpen) return;
    sidebarOpen = false;
    syncSidebar();
    if (restoreFocus) sidebarToggle?.focus();
  };

  sidebarToggle?.addEventListener("click", () => {
    sidebarOpen = !sidebarOpen;
    syncSidebar();
    if (sidebarOpen) sidebar?.querySelector("[data-sidebar-search]")?.focus();
  });
  sidebarOverlay?.addEventListener("click", () => closeSidebar(true));
  desktopMedia.addEventListener("change", () => {
    sidebarOpen = false;
    syncSidebar();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebarOpen) closeSidebar(true);
  });
  syncSidebar();

  const search = document.querySelector("[data-sidebar-search]");
  const navItems = [...document.querySelectorAll("[data-nav-item]")];
  const navGroups = [...document.querySelectorAll("[data-nav-group]")];
  const emptySearch = document.querySelector("[data-search-empty]");

  search?.addEventListener("input", () => {
    const query = search.value.trim().toLocaleLowerCase("id");
    navItems.forEach((item) => {
      item.hidden = !item.dataset.searchText.includes(query);
    });
    navGroups.forEach((group) => {
      group.hidden = !group.querySelector("[data-nav-item]:not([hidden])");
    });
    if (emptySearch) {
      emptySearch.hidden = navItems.some((item) => !item.hidden);
    }
  });

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  sidebar?.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      const target = document.querySelector(link.getAttribute("href"));
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth" });
      window.history.replaceState(null, "", link.getAttribute("href"));
      closeSidebar();
    });
  });

  const copyText = async (value) => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return;
    }

    const textArea = document.createElement("textarea");
    textArea.value = value;
    textArea.style.position = "fixed";
    textArea.style.opacity = "0";
    document.body.append(textArea);
    textArea.select();
    document.execCommand("copy");
    textArea.remove();
  };

  document.querySelectorAll("[data-code-block]").forEach((block) => {
    const button = block.querySelector("[data-copy-code]");
    const code = block.querySelector("code");
    const status = block.querySelector("[data-copy-status]");
    const copyIcon = block.querySelector("[data-copy-icon]");
    const successIcon = block.querySelector("[data-copy-success-icon]");
    let resetTimer;

    button?.addEventListener("click", async () => {
      try {
        await copyText(code?.textContent || "");
        if (status) status.textContent = "Kode disalin.";
        if (copyIcon) copyIcon.hidden = true;
        if (successIcon) successIcon.hidden = false;
        window.clearTimeout(resetTimer);
        resetTimer = window.setTimeout(() => {
          if (copyIcon) copyIcon.hidden = false;
          if (successIcon) successIcon.hidden = true;
          if (status) status.textContent = "";
        }, 2000);
      } catch {
        if (status) status.textContent = "Kode tidak dapat disalin.";
        window.showToast?.("Kode tidak dapat disalin.", "error");
      }
    });
  });

  document.querySelectorAll("[data-demo-toast]").forEach((button) => {
    button.addEventListener("click", () => {
      window.showToast?.(button.dataset.toastMessage, button.dataset.toastLevel);
    });
  });

  document.querySelectorAll("[data-dialog-open]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById(button.dataset.dialogOpen)?.showModal();
    });
  });
  document.querySelectorAll("[data-dialog]").forEach((dialog) => {
    dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
      button.addEventListener("click", () => dialog.close());
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  });

});
