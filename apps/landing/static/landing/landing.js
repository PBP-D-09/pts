document.addEventListener("DOMContentLoaded", () => {
  const page = document.querySelector("[data-landing-page]");
  const progressFill = document.querySelector("[data-scroll-progress-fill]");

  if (!page) return;

  const sections = [...page.querySelectorAll("[data-scroll-section]")];
  const faqAccordions = [...page.querySelectorAll("[data-faq-accordion]")];
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let revealObserver;
  let progressFrame;

  const updateProgress = () => {
    if (!progressFill) return;

    const pageTop = page.getBoundingClientRect().top + window.scrollY;
    const scrollDistance = Math.max(page.offsetHeight - window.innerHeight, 1);
    const currentDistance = window.scrollY - pageTop;
    const progress = Math.min(Math.max(currentDistance / scrollDistance, 0), 1);

    progressFill.style.transform = `scaleY(${progress})`;
    progressFrame = undefined;
  };

  const requestProgressUpdate = () => {
    if (!progressFill || progressFrame !== undefined) return;
    progressFrame = window.requestAnimationFrame(updateProgress);
  };

  const configureReveal = () => {
    revealObserver?.disconnect();

    if (reduceMotion.matches || !("IntersectionObserver" in window)) {
      page.classList.remove("landing-motion-ready");
      sections.forEach((section) => section.classList.add("is-visible"));
      return;
    }

    page.classList.add("landing-motion-ready");
    sections.forEach((section) => section.classList.remove("is-visible"));

    revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          entry.target.classList.toggle("is-visible", entry.isIntersecting);
        });
      },
      {
        rootMargin: "0px 0px -15% 0px",
        threshold: 0,
      },
    );

    sections.forEach((section) => revealObserver.observe(section));
  };

  configureReveal();
  reduceMotion.addEventListener?.("change", configureReveal);

  faqAccordions.forEach((details) => {
    const summary = details.querySelector("summary");
    const content = details.querySelector(".ui-accordion__content");

    if (!summary || !content) return;

    let heightAnimation;
    let contentAnimation;
    let targetOpen = details.open;

    const clearAnimation = () => {
      details.classList.remove("is-expanding", "is-closing");
      details.style.height = "";
      heightAnimation = undefined;
      contentAnimation = undefined;
      requestProgressUpdate();
    };

    const finishImmediately = (open) => {
      heightAnimation?.cancel();
      contentAnimation?.cancel();
      details.open = open;
      clearAnimation();
    };

    const setOpen = (open) => {
      targetOpen = open;

      if (reduceMotion.matches || typeof details.animate !== "function") {
        finishImmediately(open);
        return;
      }

      const wasOpen = details.open;
      const currentHeight = details.getBoundingClientRect().height;
      const currentOpacity = wasOpen ? getComputedStyle(content).opacity : "0";

      details.style.height = `${currentHeight}px`;
      heightAnimation?.cancel();
      contentAnimation?.cancel();

      if (open) details.open = true;

      let targetHeight;
      if (open) {
        details.style.height = "auto";
        targetHeight = details.getBoundingClientRect().height;
        details.style.height = `${currentHeight}px`;
      } else {
        targetHeight = summary.getBoundingClientRect().height;
      }

      details.classList.toggle("is-expanding", open);
      details.classList.toggle("is-closing", !open);

      heightAnimation = details.animate(
        { height: [`${currentHeight}px`, `${targetHeight}px`] },
        { duration: 280, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
      );
      contentAnimation = content.animate(
        { opacity: [currentOpacity, open ? "1" : "0"] },
        { duration: 200, easing: "ease-out" },
      );

      heightAnimation.onfinish = () => {
        if (targetOpen !== open) return;
        details.open = open;
        clearAnimation();
      };
    };

    summary.addEventListener("click", (event) => {
      event.preventDefault();
      setOpen(!targetOpen);
    });

    reduceMotion.addEventListener?.("change", () => {
      if (reduceMotion.matches && heightAnimation) finishImmediately(targetOpen);
    });
  });

  if (progressFill) {
    window.addEventListener("scroll", requestProgressUpdate, { passive: true });
    window.addEventListener("resize", requestProgressUpdate);
    window.addEventListener("pageshow", requestProgressUpdate);
    requestProgressUpdate();
  }
});
