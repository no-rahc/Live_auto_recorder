(function () {
  "use strict";

  const path = location.pathname.replace(/\/$/, "") || "/";
  const mobile = window.matchMedia("(max-width: 700px)");

  function makeButton(label, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    return button;
  }

  function enhanceRecording() {
    if (path !== "/recording" && !document.body.classList.contains("page-recording")) return;

    const content = document.getElementById("content");
    const system = document.getElementById("sys-dashboard");
    const channels = document.getElementById("channel-list");
    const filters = document.querySelector(".filter-container");
    if (!content || !system || !channels) return;

    const systemAnchor = document.createComment("lar-system-dashboard-origin");
    system.parentNode.insertBefore(systemAnchor, system);

    let filterToggle = document.querySelector(".lar-recording-filter-toggle");
    if (filters && !filterToggle) {
      filterToggle = makeButton("검색·필터 열기", "lar-recording-filter-toggle");
      filterToggle.setAttribute("aria-expanded", "false");
      filters.insertAdjacentElement("beforebegin", filterToggle);
      filterToggle.addEventListener("click", function () {
        const collapsed = filters.classList.toggle("lar-mobile-collapsed");
        filterToggle.setAttribute("aria-expanded", String(!collapsed));
        filterToggle.textContent = collapsed ? "검색·필터 열기" : "검색·필터 닫기";
      });
    }

    let systemHead = document.querySelector(".lar-recording-section-head");
    if (!systemHead) {
      systemHead = document.createElement("div");
      systemHead.className = "lar-recording-section-head";
      systemHead.innerHTML = "<strong>시스템 상태</strong><span>CPU · 메모리 · 네트워크 · 저장소</span>";
      system.insertAdjacentElement("beforebegin", systemHead);
    }

    function applyLayout() {
      if (mobile.matches) {
        filters?.classList.add("lar-mobile-collapsed");
        if (filterToggle) {
          filterToggle.setAttribute("aria-expanded", "false");
          filterToggle.textContent = "검색·필터 열기";
        }
        channels.insertAdjacentElement("afterend", systemHead);
        systemHead.insertAdjacentElement("afterend", system);
      } else {
        filters?.classList.remove("lar-mobile-collapsed");
        systemAnchor.parentNode.insertBefore(system, systemAnchor.nextSibling);
        system.insertAdjacentElement("beforebegin", systemHead);
      }
    }

    applyLayout();
    mobile.addEventListener?.("change", applyLayout);
  }

  function enhanceConfigSaveBar() {
    if (path !== "/config" && !document.body.classList.contains("page-config")) return;

    const bar = document.querySelector(".lar-config-savebar");
    if (bar) {
      const title = bar.querySelector("strong");
      const syncTitle = function () {
        if (bar.classList.contains("is-dirty") && title && title.textContent !== "변경사항 저장") {
          title.textContent = "변경사항 저장";
        }
      };
      const observer = new MutationObserver(syncTitle);
      observer.observe(bar, { attributes: true, attributeFilter: ["class"] });
      syncTitle();
    }

    const viewport = window.visualViewport;
    if (!viewport) return;
    const updateKeyboard = function () {
      const keyboardOpen = viewport.height < window.innerHeight * 0.72;
      document.body.classList.toggle("lar-virtual-keyboard", keyboardOpen);
    };
    viewport.addEventListener("resize", updateKeyboard);
    updateKeyboard();
  }

  function enhanceChannelRegistration() {
    if (path !== "/channels" && !document.body.classList.contains("page-channels")) return;
    const form = document.getElementById("addChannelForm");
    if (!form || form.dataset.larAdvancedReady === "1") return;

    const fields = Array.from(form.querySelectorAll(":scope > .lar-field"));
    if (fields.length <= 3) return;
    form.dataset.larAdvancedReady = "1";

    const advanced = document.createElement("div");
    advanced.className = "lar-channel-advanced-fields";
    advanced.hidden = mobile.matches;
    fields.slice(3).forEach((field) => advanced.appendChild(field));

    const toggle = makeButton("고급 설정 열기", "lar-channel-advanced-toggle");
    toggle.setAttribute("aria-expanded", String(!advanced.hidden));
    toggle.addEventListener("click", function () {
      advanced.hidden = !advanced.hidden;
      toggle.setAttribute("aria-expanded", String(!advanced.hidden));
      toggle.textContent = advanced.hidden ? "고급 설정 열기" : "고급 설정 닫기";
    });

    const submit = form.querySelector(":scope > button[type='submit'], :scope > input[type='submit']");
    if (submit) {
      form.insertBefore(toggle, submit);
      form.insertBefore(advanced, submit);
    } else {
      form.append(toggle, advanced);
    }

    function syncForViewport() {
      if (!mobile.matches) {
        advanced.hidden = false;
        toggle.hidden = true;
      } else {
        toggle.hidden = false;
        advanced.hidden = toggle.getAttribute("aria-expanded") !== "true";
      }
    }

    syncForViewport();
    mobile.addEventListener?.("change", syncForViewport);
  }

  function setFileButtonClass(button, kind) {
    if (!button) return;
    button.classList.remove("lar-file-action-primary", "lar-file-action-secondary", "lar-file-action-danger");
    button.classList.add(`lar-file-action-${kind}`);
  }

  function enhanceFiles() {
    if (path !== "/files" && !document.body.classList.contains("page-files")) return;

    ["btnUp", "btnRefresh", "btnStreamCopy", "mobMove", "mobRename", "mobDetail", "mobSelect", "mobCancel"].forEach((id) => {
      setFileButtonClass(document.getElementById(id), "secondary");
    });
    ["btnMkdir"].forEach((id) => setFileButtonClass(document.getElementById(id), "primary"));
    ["btnDelete", "mobDelete"].forEach((id) => setFileButtonClass(document.getElementById(id), "danger"));

    const actionBar = document.querySelector(".mobile-actionbar");
    if (!actionBar) return;

    function updateSelection() {
      const selected = Array.from(document.querySelectorAll(".file-browser input[type='checkbox']:checked"))
        .some((input) => !input.closest("thead"));
      actionBar.classList.toggle("lar-has-selection", selected);
      actionBar.setAttribute("aria-hidden", selected ? "false" : "true");
    }

    document.addEventListener("change", function (event) {
      if (event.target.matches?.(".file-browser input[type='checkbox']")) updateSelection();
    });
    const observer = new MutationObserver(updateSelection);
    const browser = document.querySelector(".file-browser");
    if (browser) observer.observe(browser, { subtree: true, childList: true, attributes: true, attributeFilter: ["checked", "class"] });
    updateSelection();
  }

  function enhanceOperationsTabs() {
    if (path !== "/operations" && !document.body.classList.contains("page-operations")) return;
    const tabs = document.querySelector(".ops-tabs");
    if (!tabs) return;

    function updateScrollState() {
      tabs.classList.toggle("lar-can-scroll", tabs.scrollWidth > tabs.clientWidth + 4);
    }

    tabs.addEventListener("click", function (event) {
      const button = event.target.closest("button");
      if (!button) return;
      button.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    });
    window.addEventListener("resize", updateScrollState);
    updateScrollState();
  }

  function boot() {
    document.body.classList.add("lar-ui-refinement-v1");
    enhanceRecording();
    enhanceConfigSaveBar();
    enhanceChannelRegistration();
    enhanceFiles();
    enhanceOperationsTabs();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
