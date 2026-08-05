(function () {
  "use strict";

  const THEME_KEY = "lar-console-theme";
  const pageDescriptions = {
    "/": "녹화 상태, 저장소와 시스템 상태를 한눈에 확인합니다.",
    "/recording": "현재 녹화 상태와 시스템 사용량을 확인하고 채널별 녹화를 제어합니다.",
    "/config": "자동 녹화, 후처리, 파일명과 알림 설정을 관리합니다.",
    "/channels": "녹화 대상, 저장 경로, 화질과 파일 형식을 관리합니다.",
    "/cookies": "치지직과 유튜브 인증에 필요한 쿠키 정보를 관리합니다.",
    "/files": "녹화 파일을 찾고 이동하거나 이름을 변경하고 삭제합니다.",
    "/register": "콘솔을 사용할 관리자 계정을 생성합니다."
  };

  const nativeFetch = window.fetch.bind(window);
  let dirtyOwner = null;
  let dirtyBar = null;

  function currentPath() {
    const value = location.pathname.replace(/\/$/, "");
    return value || "/";
  }

  function forceLightTheme() {
    document.documentElement.dataset.theme = "light";
    document.documentElement.style.colorScheme = "light";
    try { localStorage.setItem(THEME_KEY, "light"); } catch (_) {}
  }

  function stripVersionFromTitle() {
    document.title = document.title
      .replace(/\s+v\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.-]+)?\s*$/i, "")
      .trim() || "Live Auto Recorder";
  }

  function addPageIntro() {
    const heading = document.querySelector("#content > h1, #content > h2");
    const copy = pageDescriptions[currentPath()];
    if (!heading || !copy || heading.nextElementSibling?.classList.contains("lar-page-intro")) return;
    const intro = document.createElement("p");
    intro.className = "lar-page-intro";
    intro.textContent = copy;
    heading.insertAdjacentElement("afterend", intro);
  }

  function ensureBackdrop() {
    let backdrop = document.querySelector(".lar-backdrop");
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.className = "lar-backdrop";
      document.body.appendChild(backdrop);
    }
    return backdrop;
  }

  function setNavOpen(open) {
    const nav = document.getElementById("mySidenav");
    const menu = document.querySelector(".menu-icon");
    document.body.classList.toggle("lar-nav-open", open);
    nav?.classList.toggle("lar-open", open);
    menu?.setAttribute("aria-expanded", String(open));
  }

  function bindNav() {
    const menu = document.querySelector(".menu-icon");
    if (menu && menu.dataset.larBound !== "1") {
      menu.dataset.larBound = "1";
      menu.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        setNavOpen(!document.body.classList.contains("lar-nav-open"));
      }, true);
    }

    const close = document.querySelector("#mySidenav .closebtn");
    if (close && close.dataset.larBound !== "1") {
      close.dataset.larBound = "1";
      close.addEventListener("click", function (event) {
        event.preventDefault();
        setNavOpen(false);
      }, true);
    }

    ensureBackdrop().addEventListener("click", function () { setNavOpen(false); });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") setNavOpen(false);
    });
  }

  function toastRegion() {
    let region = document.querySelector(".lar-toast-region");
    if (!region) {
      region = document.createElement("div");
      region.className = "lar-toast-region";
      region.setAttribute("role", "status");
      region.setAttribute("aria-live", "polite");
      document.body.appendChild(region);
    }
    return region;
  }

  function toast(message, tone, action) {
    const item = document.createElement("div");
    item.className = "lar-toast";
    item.dataset.tone = tone || "info";

    const copy = document.createElement("span");
    copy.className = "lar-toast-message";
    copy.textContent = message;
    item.appendChild(copy);

    if (action && typeof action.run === "function") {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "lar-toast-action";
      button.textContent = action.label || "다시 시도";
      button.addEventListener("click", function () {
        item.remove();
        action.run();
      });
      item.appendChild(button);
    }

    toastRegion().appendChild(item);
    window.setTimeout(function () { item.remove(); }, action ? 7000 : 3600);
    return item;
  }

  function feedbackMessage(url) {
    const value = String(url || "");
    if (/channels/i.test(value)) return "채널 정보가 저장되었습니다.";
    if (/config/i.test(value)) return "설정이 저장되었습니다.";
    if (/cookie/i.test(value)) return "쿠키 정보가 저장되었습니다.";
    if (/record/i.test(value)) return "녹화 요청이 처리되었습니다.";
    if (/file|move|rename|mkdir/i.test(value)) return "파일 작업이 처리되었습니다.";
    return "요청이 처리되었습니다.";
  }

  function installFetchFeedback() {
    window.fetch = function (input, init) {
      const request = input instanceof Request ? input : null;
      const method = String(init?.method || request?.method || "GET").toUpperCase();
      const url = String(request?.url || input || "");
      const silent = /\/api\/sys_metrics|\/ws\/sys_metrics|recording_history/i.test(url);

      return nativeFetch(input, init).then(function (response) {
        if (!silent && method !== "GET") {
          if (response.ok) toast(feedbackMessage(url), "success");
          else toast("요청 처리에 실패했습니다. (" + response.status + ")", "error");
        } else if (!silent && method === "GET" && response.status >= 500) {
          toast("데이터를 불러오지 못했습니다.", "error", {
            label: "새로고침",
            run: function () { location.reload(); }
          });
        }
        return response;
      }).catch(function (error) {
        if (!silent) {
          toast("서버에 연결할 수 없습니다.", "error", {
            label: "다시 시도",
            run: function () { location.reload(); }
          });
        }
        throw error;
      });
    };
  }

  function confirmDialog() {
    let dialog = document.querySelector("dialog.lar-confirm");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "lar-confirm";
    dialog.innerHTML = '<form method="dialog" class="lar-confirm-body"><h2 class="lar-confirm-title">작업을 진행할까요?</h2><p class="lar-confirm-copy"></p><div class="lar-confirm-actions"><button value="cancel" class="lar-confirm-cancel">취소</button><button value="confirm" class="lar-confirm-danger">진행</button></div></form>';
    document.body.appendChild(dialog);
    return dialog;
  }

  function askConfirmation(message) {
    const dialog = confirmDialog();
    dialog.querySelector(".lar-confirm-copy").textContent = message;
    return new Promise(function (resolve) {
      const done = function () {
        dialog.removeEventListener("close", done);
        resolve(dialog.returnValue === "confirm");
      };
      dialog.addEventListener("close", done);
      if (typeof dialog.showModal === "function") dialog.showModal();
      else resolve(window.confirm(message));
    });
  }

  function bindConfirmations() {
    document.addEventListener("click", function (event) {
      const target = event.target.closest("#stop-all-recording,.delete-channel,.delete-file,[data-action='delete']");
      if (!target) return;
      if (target.dataset.larConfirmed === "1") {
        delete target.dataset.larConfirmed;
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();
      const message = target.id === "stop-all-recording"
        ? "진행 중인 모든 녹화를 중지합니다. 현재 파일이 마무리될 때까지 잠시 걸릴 수 있습니다."
        : "삭제한 항목은 복구하기 어려울 수 있습니다. 계속 진행하시겠습니까?";

      askConfirmation(message).then(function (confirmed) {
        if (!confirmed) return;
        target.dataset.larConfirmed = "1";
        target.click();
      });
    }, true);
  }

  function dirtyBarElement() {
    if (dirtyBar) return dirtyBar;
    dirtyBar = document.createElement("div");
    dirtyBar.className = "lar-dirty-bar";
    dirtyBar.hidden = true;
    dirtyBar.innerHTML = '<strong>저장되지 않은 변경사항이 있습니다.</strong><button type="button">변경사항 저장</button>';
    dirtyBar.querySelector("button").addEventListener("click", function () {
      if (!dirtyOwner) return;
      const form = dirtyOwner.matches("form") ? dirtyOwner : dirtyOwner.closest("form");
      if (form?.requestSubmit) form.requestSubmit();
      else dirtyOwner.querySelector(".edit-channel,button[type='submit'],input[type='submit']")?.click();
    });
    document.body.appendChild(dirtyBar);
    return dirtyBar;
  }

  function markDirty(owner) {
    dirtyOwner = owner;
    owner.classList.add("lar-dirty");
    dirtyBarElement().hidden = false;
  }

  function clearDirty(owner) {
    owner?.classList.remove("lar-dirty");
    if (!owner || dirtyOwner === owner) {
      dirtyOwner = null;
      dirtyBarElement().hidden = true;
    }
  }

  function bindDirtyTracking(root) {
    const host = root?.querySelectorAll ? root : document;
    host.querySelectorAll("#configForm,#updateCookiesForm,.channel-edit-form").forEach(function (owner) {
      if (owner.dataset.larDirtyBound === "1") return;
      owner.dataset.larDirtyBound = "1";
      ["input", "change"].forEach(function (type) {
        owner.addEventListener(type, function (event) {
          if (event.target.matches("input,select,textarea")) markDirty(owner);
        });
      });
      owner.addEventListener("submit", function () { clearDirty(owner); });
      owner.querySelectorAll(".edit-channel").forEach(function (button) {
        button.addEventListener("click", function () { clearDirty(owner); });
      });
    });
  }

  function bindSubmitState(root) {
    const host = root?.querySelectorAll ? root : document;
    host.querySelectorAll("form").forEach(function (form) {
      if (form.dataset.larSubmitBound === "1") return;
      form.dataset.larSubmitBound = "1";
      form.addEventListener("submit", function () {
        const button = form.querySelector("button[type='submit'],input[type='submit']");
        if (!button || button.disabled) return;
        const original = button.value || button.textContent;
        requestAnimationFrame(function () {
          if (form.checkValidity && !form.checkValidity()) return;
          button.disabled = true;
          if (button.tagName === "INPUT") button.value = "저장 중...";
          else button.textContent = "저장 중...";
          window.setTimeout(function () {
            if (!document.body.contains(button)) return;
            button.disabled = false;
            if (button.tagName === "INPUT") button.value = original;
            else button.textContent = original;
          }, 8000);
        });
      });
    });
  }

  function enhanceA11y(root) {
    const host = root?.querySelectorAll ? root : document;
    host.querySelectorAll(".error-message,.alert-error").forEach(function (node) {
      node.setAttribute("role", "alert");
      node.setAttribute("aria-live", "assertive");
    });
    host.querySelectorAll("[id*=status],[id*=message],.description").forEach(function (node) {
      if (!node.hasAttribute("aria-live")) node.setAttribute("aria-live", "polite");
    });
    host.querySelectorAll("table").forEach(function (table) {
      if (table.hasAttribute("aria-label")) return;
      const section = table.closest("section,.card,.config-section");
      const title = section?.querySelector("h1,h2,h3,.eyebrow");
      table.setAttribute("aria-label", title ? title.textContent.trim() : "데이터 표");
    });
    host.querySelectorAll("img:not([alt])").forEach(function (image) { image.alt = ""; });
  }

  function enhanceLongText(root) {
    const host = root?.querySelectorAll ? root : document;
    host.querySelectorAll(".channel-output,.channel-quality,[id^='filename-'],.td-file,.file-name,.file-path,.path-cell,[data-path]").forEach(function (node) {
      if (node.dataset.larEllipsis === "1") return;
      node.dataset.larEllipsis = "1";
      node.classList.add("lar-ellipsis");
      node.title = node.textContent.trim();
      node.tabIndex = 0;
      const toggle = function () { node.classList.toggle("lar-expanded-text"); };
      node.addEventListener("click", toggle);
      node.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggle();
        }
      });
    });
  }

  function installSkeletons() {
    const metrics = document.querySelectorAll("#cpu-percent,#mem-percent,#net-rate,.tile-value");
    metrics.forEach(function (node) { node.classList.add("lar-skeleton"); });
    window.addEventListener("lar:sys-metrics", function () {
      metrics.forEach(function (node) { node.classList.remove("lar-skeleton"); });
    }, { once: true });
    window.setTimeout(function () {
      metrics.forEach(function (node) { node.classList.remove("lar-skeleton"); });
    }, 5000);
  }

  function mountOf(disk) {
    return String(disk?.mountpoint || disk?.mount || disk?.label || disk?.device || "");
  }

  function compactMetrics(payload) {
    const cpuName = document.getElementById("cpu-name");
    if (cpuName) {
      const actual = payload?.cpu?.name || payload?.cpu_name || cpuName.textContent;
      if (actual && actual !== "사용률") cpuName.title = actual;
      cpuName.textContent = "사용률";
    }
    const networkBrief = document.getElementById("net-brief");
    if (networkBrief) networkBrief.textContent = "실시간 송수신";

    const disks = Array.isArray(payload?.disks) ? payload.disks : [];
    const chosen = disks.filter(function (disk) {
      const mount = mountOf(disk);
      return Number(disk?.total) > 0 && !/^\/(etc|proc|sys|dev)(\/|$)/.test(mount);
    }).sort(function (a, b) {
      function score(disk) {
        const mount = mountOf(disk).toLowerCase();
        let value = Number(disk?.total) || 0;
        if (mount === "/app/chzzk") value += 1e18;
        else if (/chzzk|record/.test(mount)) value += 5e17;
        return value;
      }
      return score(b) - score(a);
    })[0];

    const chosenMount = mountOf(chosen);
    let primary = null;
    document.querySelectorAll("#disk-row-1 .tile.disk,#disk-row-2 .tile.disk").forEach(function (node) {
      const key = node.dataset.larDiskKey || node.querySelector(".tile-title")?.textContent.trim() || "";
      const selected = !!chosen && key === chosenMount;
      node.classList.toggle("lar-primary-storage", selected);
      node.hidden = !selected;
      if (selected) primary = node;
    });

    const row1 = document.getElementById("disk-row-1");
    const row2 = document.getElementById("disk-row-2");
    if (primary && row1) {
      row1.prepend(primary);
      const title = primary.querySelector(".tile-title");
      const sub = primary.querySelector(".tile-sub");
      if (title) title.textContent = "녹화 저장소";
      if (sub) sub.textContent = chosenMount || "/app/chzzk";
      row1.hidden = false;
    }
    if (row2) row2.hidden = true;
  }

  function observeDynamicContent() {
    const pending = new Set();
    let scheduled = false;
    const observer = new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(function (node) {
          if (node.nodeType === Node.ELEMENT_NODE) pending.add(node);
        });
      });
      if (!pending.size || scheduled) return;
      scheduled = true;
      requestAnimationFrame(function () {
        pending.forEach(function (node) {
          enhanceA11y(node);
          enhanceLongText(node);
          bindSubmitState(node);
          bindDirtyTracking(node);
        });
        pending.clear();
        scheduled = false;
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function boot() {
    forceLightTheme();
    stripVersionFromTitle();
    document.body.classList.add("lar-ui-v3");
    addPageIntro();
    bindNav();
    installFetchFeedback();
    bindConfirmations();
    bindSubmitState(document);
    bindDirtyTracking(document);
    enhanceA11y(document);
    enhanceLongText(document);
    installSkeletons();
    observeDynamicContent();

    window.addEventListener("offline", function () { toast("네트워크 연결이 끊어졌습니다.", "error"); });
    window.addEventListener("online", function () { toast("네트워크가 다시 연결되었습니다.", "success"); });
    window.addEventListener("beforeunload", function (event) {
      if (!dirtyOwner) return;
      event.preventDefault();
      event.returnValue = "";
    });
    window.addEventListener("lar:sys-metrics", function (event) {
      requestAnimationFrame(function () { compactMetrics(event.detail || {}); });
    });

    window.LiveAutoRecorderUI = { toast: toast, setTheme: forceLightTheme };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
