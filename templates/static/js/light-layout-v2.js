(function () {
  "use strict";

  const THEME_KEY = "lar-console-theme";

  function forceLightTheme() {
    if (document.documentElement.dataset.theme !== "light") {
      document.documentElement.dataset.theme = "light";
    }
    try {
      localStorage.setItem(THEME_KEY, "light");
    } catch (_) {}

    if (
      window.LiveAutoRecorderUI &&
      typeof window.LiveAutoRecorderUI.setTheme === "function"
    ) {
      window.LiveAutoRecorderUI.setTheme("light");
    }

    const themeButton = document.querySelector("[data-lar-theme-toggle]");
    if (themeButton) {
      themeButton.hidden = true;
      themeButton.setAttribute("aria-hidden", "true");
      themeButton.tabIndex = -1;
    }
  }

  function boot() {
    forceLightTheme();

    const observer = new MutationObserver(function () {
      if (document.documentElement.dataset.theme !== "light") {
        forceLightTheme();
      }
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
