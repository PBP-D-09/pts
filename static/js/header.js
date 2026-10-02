document.addEventListener("DOMContentLoaded", () => {
  const mobileNav = document.querySelector("[data-mobile-nav]");

  if (!mobileNav || mobileNav.dataset.initialized === "true") return;

  const toggle = mobileNav.querySelector("[data-mobile-nav-toggle]");
  const menu = mobileNav.querySelector("[data-mobile-nav-menu]");
  const openIcon = mobileNav.querySelector("[data-mobile-nav-open-icon]");
  const closeIcon = mobileNav.querySelector("[data-mobile-nav-close-icon]");
  const animationClasses = [
    "pointer-events-none",
    "-translate-y-5",
    "opacity-0",
  ];
  let closeTimer;

  if (!toggle || !menu || !openIcon || !closeIcon) return;

  mobileNav.dataset.initialized = "true";

  const setIcons = (isOpen) => {
    openIcon.hidden = isOpen;
    closeIcon.hidden = !isOpen;
  };

  const openMenu = () => {
    window.clearTimeout(closeTimer);
    menu.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    toggle.setAttribute("aria-label", "Tutup menu navigasi");
    setIcons(true);

    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        menu.classList.remove(...animationClasses);
      });
    });
  };

  const closeMenu = (immediate = false) => {
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Buka menu navigasi");
    setIcons(false);
    menu.classList.add(...animationClasses);

    window.clearTimeout(closeTimer);
    if (immediate) {
      menu.hidden = true;
      return;
    }

    closeTimer = window.setTimeout(() => {
      menu.hidden = true;
    }, 200);
  };

  toggle.addEventListener("click", () => {
    if (toggle.getAttribute("aria-expanded") === "true") {
      closeMenu();
    } else {
      openMenu();
    }
  });

  menu.querySelectorAll("a[href]").forEach((link) => {
    link.addEventListener("click", () => closeMenu());
  });

  document.addEventListener("click", (event) => {
    if (!mobileNav.contains(event.target) && !menu.hidden) closeMenu();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) {
      closeMenu();
      toggle.focus();
    }
  });

  window.addEventListener("resize", () => {
    if (window.matchMedia("(min-width: 768px)").matches) closeMenu(true);
  });
});
