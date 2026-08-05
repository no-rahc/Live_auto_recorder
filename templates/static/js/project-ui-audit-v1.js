(function () {
  "use strict";

  const path = location.pathname.replace(/\/$/, "") || "/";

  function makeButton(label, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    return button;
  }

  function addPasswordToggle(input) {
    if (!input || input.dataset.larPasswordToggle === "1") return;
    input.dataset.larPasswordToggle = "1";

    const wrapper = document.createElement("div");
    wrapper.className = "lar-password-field";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const toggle = makeButton("보기", "lar-password-toggle");
    toggle.setAttribute("aria-label", "비밀번호 표시");
    toggle.setAttribute("aria-pressed", "false");
    toggle.addEventListener("click", function () {
      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      toggle.textContent = reveal ? "숨기기" : "보기";
      toggle.setAttribute("aria-label", reveal ? "비밀번호 숨기기" : "비밀번호 표시");
      toggle.setAttribute("aria-pressed", String(reveal));
    });
    wrapper.appendChild(toggle);
  }

  function enhanceAuth() {
    const loginForm = document.getElementById("loginForm");
    if (loginForm) {
      document.body.classList.add("lar-auth-mode");
      const card = loginForm.parentElement;
      card?.classList.add("lar-auth-card");
      const heading = card?.querySelector(":scope > h2");
      if (heading && !heading.nextElementSibling?.classList.contains("lar-workspace-copy")) {
        const copy = document.createElement("p");
        copy.className = "lar-workspace-copy";
        copy.textContent = "관리자 계정으로 로그인해 녹화와 저장소 상태를 관리합니다.";
        heading.insertAdjacentElement("afterend", copy);
      }
      addPasswordToggle(loginForm.querySelector('input[name="password"]'));
      loginForm.querySelector('input[name="username"]')?.setAttribute("autocomplete", "username");
      loginForm.querySelector('input[name="password"]')?.setAttribute("autocomplete", "current-password");
    }

    if (document.body.classList.contains("page-register")) {
      document.body.classList.add("lar-auth-mode");
      const form = document.querySelector(".register-form");
      if (!form) return;
      form.querySelector('input[name="username"]')?.setAttribute("autocomplete", "username");
      const password = form.querySelector('input[name="password"]');
      const confirm = form.querySelector('input[name="password_confirm"]');
      password?.setAttribute("autocomplete", "new-password");
      confirm?.setAttribute("autocomplete", "new-password");
      addPasswordToggle(password);
      addPasswordToggle(confirm);

      if (confirm && !form.querySelector(".lar-password-match")) {
        const status = document.createElement("p");
        status.className = "lar-password-match";
        status.setAttribute("role", "status");
        status.setAttribute("aria-live", "polite");
        confirm.closest(".lar-password-field")?.insertAdjacentElement("afterend", status);
        const refresh = function () {
          if (!confirm.value) {
            status.textContent = "";
            status.dataset.state = "";
          } else if (password?.value === confirm.value) {
            status.textContent = "비밀번호가 일치합니다.";
            status.dataset.state = "ok";
          } else {
            status.textContent = "비밀번호가 일치하지 않습니다.";
            status.dataset.state = "error";
          }
        };
        password?.addEventListener("input", refresh);
        confirm.addEventListener("input", refresh);
      }
    }
  }

  function wrapFormFields(form) {
    if (!form || form.dataset.larFieldGrid === "1") return;
    form.dataset.larFieldGrid = "1";
    const children = Array.from(form.children);
    let field = null;

    children.forEach(function (node) {
      if (node.tagName === "LABEL") {
        field = document.createElement("div");
        field.className = "lar-field";
        form.insertBefore(field, node);
        field.appendChild(node);
        return;
      }
      if (node.matches?.('button[type="submit"],input[type="submit"]')) {
        field = null;
        return;
      }
      if (field) field.appendChild(node);
    });

    form.querySelectorAll(".lar-field").forEach(function (item) {
      const label = item.querySelector("label")?.textContent.trim() || "";
      if (/저장 경로|녹화 제외/.test(label)) item.classList.add("lar-field--full");
    });
  }

  function platformValue(card) {
    return card.querySelector(".edit-platform")?.value || "";
  }

  function openChannelEditor(card, open) {
    const form = card.querySelector(".channel-edit-form");
    const toggle = card.querySelector(".lar-channel-edit-toggle");
    if (!form || !toggle) return;
    form.hidden = !open;
    card.classList.toggle("lar-edit-open", open);
    toggle.textContent = open ? "설정 닫기" : "설정 열기";
    toggle.setAttribute("aria-expanded", String(open));
    if (open) form.querySelector("input,select,button")?.focus({ preventScroll: true });
  }

  function enhanceChannels() {
    if (path !== "/channels" && !document.body.classList.contains("page-channels")) return;
    wrapFormFields(document.getElementById("addChannelForm"));

    const list = document.querySelector(".channel-list");
    if (list && !list.querySelector(".channel-card")) {
      const empty = document.createElement("div");
      empty.className = "lar-empty-state";
      empty.textContent = "등록된 채널이 없습니다. 위 양식에서 첫 녹화 채널을 추가하세요.";
      list.appendChild(empty);
    }

    document.querySelectorAll(".channel-card").forEach(function (card, index) {
      if (card.dataset.larChannelAudit === "1") return;
      card.dataset.larChannelAudit = "1";

      const body = card.querySelector(".channel-card-body");
      const form = card.querySelector(".channel-edit-form");
      if (!body || !form) return;
      form.style.removeProperty("display");
      form.hidden = true;
      form.id = form.id || `lar-channel-editor-${index + 1}`;

      const actions = document.createElement("div");
      actions.className = "lar-channel-summary-actions";
      const badge = document.createElement("span");
      badge.className = "lar-platform-badge";
      badge.dataset.platform = platformValue(card);
      badge.textContent = badge.dataset.platform === "youtube" ? "YouTube" : "CHZZK";
      const toggle = makeButton("설정 열기", "lar-channel-edit-toggle");
      toggle.setAttribute("aria-controls", form.id);
      toggle.setAttribute("aria-expanded", "false");
      actions.append(badge, toggle);
      body.appendChild(actions);

      toggle.addEventListener("click", function () {
        openChannelEditor(card, form.hidden);
      });

      const platform = form.querySelector(".edit-platform");
      platform?.addEventListener("change", function () {
        badge.dataset.platform = platform.value;
        badge.textContent = platform.value === "youtube" ? "YouTube" : "CHZZK";
      });

      const row = form.querySelector(".button-row");
      if (row && !row.querySelector(".lar-channel-edit-close")) {
        const close = makeButton("닫기", "lar-channel-edit-close");
        row.insertBefore(close, row.firstChild);
        close.addEventListener("click", function () {
          if (form.classList.contains("lar-dirty") && !window.confirm("저장하지 않은 변경사항이 있습니다. 설정을 닫을까요?")) return;
          openChannelEditor(card, false);
        });
      }
    });
  }

  function panelHeader(title, copy) {
    const fragment = document.createDocumentFragment();
    const heading = document.createElement("h2");
    heading.textContent = title;
    const description = document.createElement("p");
    description.className = "lar-workspace-copy";
    description.textContent = copy;
    fragment.append(heading, description);
    return fragment;
  }

  function enhanceCookies() {
    if (path !== "/cookies" && !document.body.classList.contains("page-cookies")) return;
    const content = document.getElementById("content");
    const form = document.getElementById("updateCookiesForm");
    const notices = Array.from(content?.querySelectorAll(":scope > .notice") || []);
    const youtubeHeading = Array.from(content?.children || []).find(function (node) {
      return node.tagName === "H2" && /유튜브/.test(node.textContent);
    });
    if (!content || !form || !notices.length || !youtubeHeading) return;

    const grid = document.createElement("div");
    grid.className = "lar-cookie-workspace";
    const chzzkPanel = document.createElement("section");
    chzzkPanel.className = "lar-cookie-panel";
    chzzkPanel.appendChild(panelHeader("치지직 인증", "NID_AUT와 NID_SES를 저장하고 인증 상태를 관리합니다."));
    chzzkPanel.append(notices[0], form);
    const modified = content.querySelector(":scope > .last-modified");
    if (modified) chzzkPanel.appendChild(modified);
    const security = document.createElement("p");
    security.className = "lar-cookie-security";
    security.textContent = "쿠키 값은 비밀번호처럼 가려서 표시합니다. 필요한 경우에만 보기 버튼으로 확인하세요.";
    chzzkPanel.appendChild(security);

    const youtubePanel = document.createElement("section");
    youtubePanel.className = "lar-cookie-panel";
    youtubePanel.appendChild(panelHeader("YouTube 인증", "cookies.txt 파일을 준비하는 절차를 확인합니다."));
    if (notices[1]) youtubePanel.appendChild(notices[1]);

    youtubeHeading.remove();
    content.appendChild(grid);
    grid.append(chzzkPanel, youtubePanel);

    form.querySelectorAll('input[type="text"]:not([type="submit"])').forEach(function (input) {
      input.type = "password";
      input.dataset.larSensitive = "1";
      input.autocomplete = "off";
      input.spellcheck = false;
      addPasswordToggle(input);
    });
  }

  function wrapToolbar(row) {
    if (!row || row.dataset.larToolbarAudit === "1") return;
    row.dataset.larToolbarAudit = "1";
    const children = Array.from(row.children);
    const actions = document.createElement("div");
    actions.className = "lar-toolbar-actions";

    for (let i = 0; i < children.length; i += 1) {
      const node = children[i];
      if (node.tagName === "LABEL") {
        const control = children[i + 1];
        if (control && /^(INPUT|SELECT|TEXTAREA)$/.test(control.tagName)) {
          const field = document.createElement("div");
          field.className = "lar-toolbar-field";
          if (control.id === "pathInput") field.classList.add("lar-toolbar-path");
          row.insertBefore(field, node);
          field.append(node, control);
          i += 1;
          continue;
        }
      }
      if (node.tagName === "BUTTON") actions.appendChild(node);
    }
    if (actions.childElementCount) row.appendChild(actions);
  }

  function visibleFileModal() {
    return Array.from(document.querySelectorAll("body.page-files .modal")).find(function (modal) {
      return !modal.classList.contains("hidden") && getComputedStyle(modal).display !== "none";
    });
  }

  function enhanceFileModals() {
    const modals = document.querySelectorAll("body.page-files .modal");
    modals.forEach(function (modal, index) {
      modal.setAttribute("role", "dialog");
      modal.setAttribute("aria-modal", "true");
      const heading = modal.querySelector("h3");
      if (heading) {
        heading.id = heading.id || `lar-file-modal-title-${index + 1}`;
        modal.setAttribute("aria-labelledby", heading.id);
      }
    });

    document.addEventListener("keydown", function (event) {
      const modal = visibleFileModal();
      if (!modal) return;
      if (event.key === "Escape") {
        const close = modal.querySelector("#close-fm-modal,#mp-cancel,#detail-close,.secondary");
        if (close) {
          event.preventDefault();
          close.click();
        }
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(modal.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])'))
        .filter(function (node) { return node.offsetParent !== null; });
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        const modal = mutation.target;
        if (!(modal instanceof Element) || !modal.classList.contains("modal")) return;
        if (!modal.classList.contains("hidden")) {
          requestAnimationFrame(function () {
            modal.querySelector("button,input,select,textarea,a[href]")?.focus({ preventScroll: true });
          });
        }
      });
    });
    modals.forEach(function (modal) { observer.observe(modal, { attributes: true, attributeFilter: ["class"] }); });
  }

  function enhanceFiles() {
    if (path !== "/files" && !document.body.classList.contains("page-files")) return;
    document.querySelectorAll(".file-toolbar .toolbar-row").forEach(wrapToolbar);
    enhanceFileModals();
  }

  function boot() {
    document.body.classList.add("lar-project-ui-audit");
    enhanceAuth();
    enhanceChannels();
    enhanceCookies();
    enhanceFiles();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
