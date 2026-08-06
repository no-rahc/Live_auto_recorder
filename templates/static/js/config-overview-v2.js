(function () {
  "use strict";

  if (!document.body.classList.contains("page-config")) return;

  const form = document.getElementById("configForm");
  const tabs = document.querySelector(".lar-config-tabs");
  const panelsHost = document.querySelector(".lar-config-panels");
  const systemExtras = document.querySelector(".lar-config-system-extras");
  if (!form || !tabs || !panelsHost || form.dataset.larOverviewReady === "true") return;
  form.dataset.larOverviewReady = "true";

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const truthy = (value) => ["true", "1", "on", "yes"].includes(String(value || "").toLowerCase());
  const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;"
  }[char]));
  const helperNames = new Set(["danger_confirmation", "danger_current_password", "danger_ack"]);
  const restartFields = new Set(["autoRecordingMode", "loginMode"]);
  const fieldNames = {
    autoRecordingMode: "자동 녹화",
    plugin_type: "치지직 플러그인",
    timemachine_time_shift: "타임머신 시프트",
    recheckInterval: "방송 재탐색 주기",
    filenamePattern: "파일명 규칙",
    autoPostProcessing: "자동 후처리",
    deleteAfterPostProcessing: "후처리 후 원본 삭제",
    removeFixedPrefix: "고정 접두사 제거",
    moveAfterProcessingEnabled: "후처리 후 파일 이동",
    moveAfterProcessing: "후처리 이동 경로",
    splitRecordingMode: "분할 녹화",
    splitPostProcessing: "분할 파일 후처리",
    autoStopInterval: "분할 시간",
    splitOverlapSec: "분할 겹침 시간",
    stream_copy: "후처리 방식",
    video_codec: "비디오 코덱",
    preset: "인코딩 프리셋",
    use_bitrate_mode: "비트레이트 모드",
    video_quality: "화질 값",
    video_bitrate: "비디오 비트레이트",
    vbv_maxrate: "최대 비트레이트",
    vbv_bufsize: "버퍼 크기",
    extra_ffmpeg_options: "FFmpeg 추가 옵션",
    audio_codec: "오디오 코덱",
    audio_bitrate: "오디오 비트레이트",
    telegram_enabled: "Telegram 알림",
    telegram_bot_token_action: "Telegram 봇 토큰",
    telegram_chat_id_action: "Telegram 채팅 ID",
    discord_enabled: "Discord 알림",
    discord_webhook_url_action: "Discord 웹훅",
    fileManagerEnabled: "파일 관리자",
    fileManagerMode: "파일 접근 범위",
    fileManagerReadOnly: "읽기 전용",
    trashEnabled: "휴지통",
    fileManagerRoots: "허용 경로",
    loginMode: "로그인 보호"
  };

  function emit(control) {
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function sectionNumber(section) {
    return ($(".section-num", section)?.textContent || "").trim().padStart(2, "0");
  }

  function findSection(number) {
    return $$(".config-section", document).find((section) => sectionNumber(section) === number) || null;
  }

  function buildInformationArchitecture() {
    const securityButton = $("[data-config-tab='system']", tabs);
    const securityPanel = $("[data-config-panel='system']", panelsHost);
    const fileSection = findSection("08");
    if (!securityButton || !securityPanel || !fileSection) return;

    securityButton.dataset.configTab = "security";
    $("strong", securityButton).textContent = "접속 보안";
    $("small", securityButton).textContent = "로그인·계정";
    securityPanel.dataset.configPanel = "security";

    const filesButton = document.createElement("button");
    filesButton.type = "button";
    filesButton.className = "lar-config-tab";
    filesButton.dataset.configTab = "files";
    filesButton.setAttribute("role", "tab");
    filesButton.innerHTML = "<strong>파일 관리</strong><small>접근 범위·삭제 정책</small>";
    tabs.insertBefore(filesButton, securityButton);

    const filesPanel = document.createElement("section");
    filesPanel.className = "lar-config-panel";
    filesPanel.dataset.configPanel = "files";
    filesPanel.setAttribute("role", "tabpanel");
    filesPanel.hidden = true;
    const filesGrid = document.createElement("div");
    filesGrid.className = "lar-config-panel-grid lar-config-files-grid";
    filesGrid.appendChild(fileSection);
    filesPanel.appendChild(filesGrid);
    panelsHost.insertBefore(filesPanel, securityPanel);

    tabs.setAttribute("role", "tablist");
    $$(".lar-config-tab", tabs).forEach((button, index) => {
      const id = button.dataset.configTab;
      button.id = `lar-config-tab-${id}`;
      button.setAttribute("aria-controls", `lar-config-panel-${id}`);
      button.tabIndex = index === 0 ? 0 : -1;
    });
    $$(".lar-config-panel", panelsHost).forEach((panel) => {
      const id = panel.dataset.configPanel;
      panel.id = `lar-config-panel-${id}`;
      panel.setAttribute("aria-labelledby", `lar-config-tab-${id}`);
    });

    function activate(id, focus) {
      const available = new Set($$(".lar-config-tab", tabs).map((button) => button.dataset.configTab));
      const target = available.has(id) ? id : "basic";
      $$(".lar-config-tab", tabs).forEach((button) => {
        const active = button.dataset.configTab === target;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
        button.tabIndex = active ? 0 : -1;
        if (active && focus) button.focus();
      });
      $$(".lar-config-panel", panelsHost).forEach((panel) => {
        const active = panel.dataset.configPanel === target;
        panel.hidden = !active;
        panel.classList.toggle("is-active", active);
      });
      if (systemExtras) systemExtras.hidden = target !== "security";
      try { localStorage.setItem("lar-config-tab", target); } catch (_) { /* ignore */ }
    }

    tabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-config-tab]");
      if (!button) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      activate(button.dataset.configTab, false);
    }, true);

    tabs.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const buttons = $$("[data-config-tab]", tabs);
      const current = Math.max(0, buttons.indexOf(document.activeElement));
      let next = current;
      if (event.key === "Home") next = 0;
      else if (event.key === "End") next = buttons.length - 1;
      else next = (current + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
      activate(buttons[next].dataset.configTab, true);
    }, true);

    let saved = "basic";
    try { saved = localStorage.getItem("lar-config-tab") || "basic"; } catch (_) { /* ignore */ }
    if (saved === "system") saved = "security";
    activate(saved, false);
  }

  function setupBooleanSwitches() {
    $$("select", form).forEach((select) => {
      const values = Array.from(select.options).map((option) => String(option.value).toLowerCase());
      if (!values.includes("true") || !values.includes("false") || select.dataset.larSwitch === "true") return;
      select.dataset.larSwitch = "true";
      select.classList.add("lar-switch-source");

      const label = select.id ? $(`label[for='${CSS.escape(select.id)}']`) : null;
      if (label && !label.id) label.id = `lar-label-${select.id}`;

      const button = document.createElement("button");
      button.type = "button";
      button.className = "lar-setting-switch";
      button.setAttribute("role", "switch");
      if (label?.id) button.setAttribute("aria-labelledby", label.id);
      button.innerHTML = '<span class="lar-switch-track" aria-hidden="true"><span></span></span><strong></strong>';
      select.insertAdjacentElement("afterend", button);

      const render = () => {
        const enabled = truthy(select.value);
        button.setAttribute("aria-checked", enabled ? "true" : "false");
        button.classList.toggle("is-on", enabled);
        button.disabled = select.disabled;
        $("strong", button).textContent = enabled ? "ON" : "OFF";
      };
      button.addEventListener("click", () => {
        if (button.disabled) return;
        select.value = truthy(select.value) ? "false" : "true";
        emit(select);
      });
      select.addEventListener("change", render);
      new MutationObserver(render).observe(select, { attributes: true, attributeFilter: ["disabled"] });
      render();
    });
  }

  function optionText(id) {
    const control = document.getElementById(id);
    if (!control) return "";
    if (control.tagName === "SELECT") return control.selectedOptions[0]?.textContent?.trim() || control.value;
    return control.value || "";
  }

  function encodingSummary() {
    const copy = truthy(document.getElementById("stream_copy")?.value);
    if (copy) {
      return {
        title: "원본 유지",
        detail: "재인코딩 없이 원본 영상과 음성을 유지합니다.",
        compact: "원본 유지"
      };
    }
    const codec = optionText("video_codec") || "비디오 인코딩";
    const bitrateMode = truthy(document.getElementById("use_bitrate_mode")?.value);
    const quality = bitrateMode
      ? (document.getElementById("video_bitrate")?.value || "비트레이트 미지정")
      : `화질 ${document.getElementById("video_quality")?.value || "-"}`;
    const audio = document.getElementById("audio_bitrate")?.value === "copy"
      ? "오디오 원본"
      : `${optionText("audio_codec")} ${optionText("audio_bitrate")}`.trim();
    return {
      title: `${codec} · ${quality}`,
      detail: `${optionText("preset")} 프리셋 · ${audio}`,
      compact: codec.replace(/\s*\([^)]*\)/g, "")
    };
  }

  function setupEncodingDisclosure() {
    const section = findSection("05");
    if (!section || section.dataset.larAdvancedEncoding === "true") return;
    section.dataset.larAdvancedEncoding = "true";

    const profileRow = $(".lar-profile-row", section);
    const diagnostic = $(".lar-encoder-diagnostic", section);
    const card = document.createElement("div");
    card.className = "lar-encoding-current";
    card.innerHTML = '<span>현재 적용 결과</span><strong></strong><p></p>';
    (diagnostic || profileRow || $(".section-head", section)).insertAdjacentElement("afterend", card);

    const details = document.createElement("details");
    details.className = "lar-encoding-advanced";
    details.innerHTML = '<summary><span><strong>고급 인코딩 설정</strong><small>코덱·화질·비트레이트·FFmpeg 옵션</small></span><em>펼치기</em></summary><div class="lar-encoding-advanced-body"></div>';
    card.insertAdjacentElement("afterend", details);
    const body = $(".lar-encoding-advanced-body", details);
    const advancedIds = [
      "stream_copy", "video_codec", "preset", "use_bitrate_mode", "video_quality",
      "video_bitrate", "vbv_maxrate", "vbv_bufsize", "extra_ffmpeg_options",
      "audio_codec", "audio_bitrate"
    ];
    advancedIds.forEach((id) => {
      const row = document.getElementById(id)?.closest(".lar-setting-row");
      if (row) body.appendChild(row);
    });

    const render = () => {
      const summary = encodingSummary();
      $("strong", card).textContent = summary.title;
      $("p", card).textContent = summary.detail;
      $("em", details).textContent = details.open ? "접기" : "펼치기";
    };
    details.addEventListener("toggle", render);
    advancedIds.forEach((id) => {
      document.getElementById(id)?.addEventListener("change", render);
      document.getElementById(id)?.addEventListener("input", render);
      document.getElementById(id)?.addEventListener("invalid", () => { details.open = true; }, true);
    });
    document.getElementById("larEncodingProfile")?.addEventListener("change", () => window.setTimeout(render, 80));
    render();
  }

  function secretConfigured(id) {
    const input = document.getElementById(id);
    if (!input) return false;
    const action = form.elements.namedItem(`${id}_action`);
    const mode = action && !(action instanceof RadioNodeList) ? action.value : "";
    if (mode === "clear") return false;
    if (mode === "replace") return Boolean(input.value.trim());
    return input.dataset.storedSecret === "true" || Boolean(input.value.trim());
  }

  function lastTestLabel(kind) {
    try {
      const raw = localStorage.getItem(`lar-${kind}-test-ok`);
      if (!raw) return "";
      const date = new Date(raw);
      if (Number.isNaN(date.getTime())) return "";
      return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")} 확인`;
    } catch (_) {
      return "";
    }
  }

  function setupNotificationState() {
    const nav = $(".lar-notification-tabs");
    if (!nav) return () => {};
    const buttons = {
      telegram: $("[data-notification='06']", nav),
      discord: $("[data-notification='07']", nav)
    };
    Object.values(buttons).forEach((button) => {
      if (!button || $(".lar-notification-status", button)) return;
      const status = document.createElement("span");
      status.className = "lar-notification-status";
      button.appendChild(status);
    });

    const update = () => {
      const telegramEnabled = truthy(document.getElementById("telegram_enabled")?.value);
      const telegramReady = secretConfigured("telegram_bot_token") && secretConfigured("telegram_chat_id");
      const discordEnabled = truthy(document.getElementById("discord_enabled")?.value);
      const discordReady = secretConfigured("discord_webhook_url");
      const states = [
        [buttons.telegram, telegramEnabled, telegramReady, lastTestLabel("telegram")],
        [buttons.discord, discordEnabled, discordReady, lastTestLabel("discord")]
      ];
      states.forEach(([button, enabled, ready, tested]) => {
        if (!button) return;
        const status = $(".lar-notification-status", button);
        button.classList.toggle("is-configured", enabled && ready);
        button.classList.toggle("is-incomplete", enabled && !ready);
        status.textContent = !enabled ? "사용 안 함" : ready ? (tested || "연결됨") : "설정 필요";
      });
    };

    ["telegram_enabled", "telegram_bot_token", "telegram_chat_id", "discord_enabled", "discord_webhook_url"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", update);
      document.getElementById(id)?.addEventListener("change", update);
      const action = form.elements.namedItem(`${id}_action`);
      if (action && !(action instanceof RadioNodeList)) action.addEventListener("change", update);
    });

    if (!window.__larNotificationFetchWrapped) {
      window.__larNotificationFetchWrapped = true;
      const nativeFetch = window.fetch.bind(window);
      window.fetch = async function (...args) {
        const response = await nativeFetch(...args);
        try {
          const url = String(args[0] instanceof Request ? args[0].url : args[0] || "");
          let kind = "";
          if (url.includes("/api/test_telegram")) kind = "telegram";
          if (url.includes("/api/discord_test")) kind = "discord";
          if (kind && response.ok) {
            const payload = await response.clone().json();
            if (payload.status === "success") {
              localStorage.setItem(`lar-${kind}-test-ok`, new Date().toISOString());
              window.setTimeout(update, 0);
            }
          }
        } catch (_) { /* keep fetch transparent */ }
        return response;
      };
    }
    update();
    return update;
  }

  function ensureTabStatus(button) {
    let status = $(".lar-tab-status", button);
    if (!status) {
      status = document.createElement("span");
      status.className = "lar-tab-status";
      button.appendChild(status);
    }
    return status;
  }

  function setupTabStatuses(updateNotifications) {
    const overview = document.createElement("div");
    overview.className = "lar-config-overview-line";
    overview.setAttribute("role", "status");
    overview.setAttribute("aria-live", "polite");
    tabs.insertAdjacentElement("afterend", overview);

    const set = (id, text, tone) => {
      const button = $(`[data-config-tab='${id}']`, tabs);
      if (!button) return;
      const status = ensureTabStatus(button);
      status.textContent = text;
      status.dataset.tone = tone || "neutral";
    };

    const update = () => {
      const auto = truthy(document.getElementById("autoRecordingMode")?.value);
      const plugin = document.getElementById("plugin_type")?.value === "timemachine_plus" ? "타임머신+" : "기본 모드";
      const encoding = encodingSummary();
      const telegram = truthy(document.getElementById("telegram_enabled")?.value)
        && secretConfigured("telegram_bot_token") && secretConfigured("telegram_chat_id");
      const discord = truthy(document.getElementById("discord_enabled")?.value) && secretConfigured("discord_webhook_url");
      const notificationCount = Number(telegram) + Number(discord);
      const manager = truthy(document.getElementById("fileManagerEnabled")?.value);
      const risks = manager ? [
        document.getElementById("fileManagerMode")?.value === "blacklist",
        !truthy(document.getElementById("fileManagerReadOnly")?.value),
        !truthy(document.getElementById("trashEnabled")?.value)
      ].filter(Boolean).length : 0;
      const login = truthy(document.getElementById("loginMode")?.value);

      set("basic", auto ? "자동 녹화 ON" : "수동 녹화", auto ? "success" : "neutral");
      set("chzzk", plugin, "neutral");
      set("processing", encoding.compact, truthy(document.getElementById("stream_copy")?.value) ? "success" : "neutral");
      set("notifications", notificationCount ? `${notificationCount}개 연결` : "사용 안 함", notificationCount ? "success" : "neutral");
      set("files", !manager ? "사용 안 함" : risks ? `주의 ${risks}` : "안전", risks ? "danger" : manager ? "success" : "neutral");
      set("security", login ? "로그인 ON" : "로컬 전용", login ? "success" : "warning");

      overview.innerHTML = [
        `<span><b>녹화</b>${auto ? "자동" : "수동"}</span>`,
        `<span><b>인코딩</b>${encoding.compact}</span>`,
        `<span><b>알림</b>${notificationCount ? `${notificationCount}개 연결` : "없음"}</span>`,
        `<span class="${risks ? "is-danger" : ""}"><b>파일 관리</b>${!manager ? "꺼짐" : risks ? `주의 ${risks}` : "안전"}</span>`,
        `<span class="${login ? "" : "is-warning"}"><b>접속</b>${login ? "로그인 보호" : "로컬 전용"}</span>`
      ].join("");
      updateNotifications();
    };

    form.addEventListener("input", () => window.setTimeout(update, 0), true);
    form.addEventListener("change", () => window.setTimeout(update, 0), true);
    update();
  }

  function controlLabel(name) {
    if (fieldNames[name]) return fieldNames[name];
    const control = form.elements.namedItem(name);
    const node = control && !(control instanceof RadioNodeList) ? control : null;
    const label = node?.id ? $(`label[for='${CSS.escape(node.id)}']`) : null;
    return label?.textContent?.replace(/\s+/g, " ").replace(/:$/, "").trim() || name;
  }

  function snapshot() {
    const result = new Map();
    const grouped = new Map();
    Array.from(form.elements).forEach((control) => {
      if (!control.name || helperNames.has(control.name) || control.type === "submit" || control.type === "button") return;
      let value = "";
      if ((control.type === "checkbox" || control.type === "radio") && !control.checked) return;
      if (control instanceof HTMLSelectElement) value = control.value;
      else value = control.value || "";
      if (!grouped.has(control.name)) grouped.set(control.name, []);
      grouped.get(control.name).push(String(value));
    });
    grouped.forEach((values, name) => result.set(name, values.join("\u001f")));
    return result;
  }

  function friendlyValue(name, value) {
    if (name.endsWith("_action")) return ({ keep: "유지", replace: "변경", clear: "삭제" })[value] || value;
    if (value === "true") return "ON";
    if (value === "false") return "OFF";
    const control = form.elements.namedItem(name);
    if (control instanceof HTMLSelectElement) {
      return Array.from(control.options).find((option) => option.value === value)?.textContent?.trim() || value;
    }
    if (name === "fileManagerRoots") return value.split("\u001f").filter(Boolean).join(", ") || "없음";
    if (["recheckInterval", "autoStopInterval", "splitOverlapSec", "timemachine_time_shift"].includes(name) && value) return `${value}초`;
    return value || "비어 있음";
  }

  function setupDetailedSaveSummary() {
    const bar = $(".lar-config-savebar");
    const host = bar?.firstElementChild;
    if (!bar || !host) return;
    const oldSummary = $(".lar-config-change-summary", host);
    if (oldSummary) oldSummary.hidden = true;
    const details = document.createElement("div");
    details.className = "lar-config-change-details";
    details.hidden = true;
    host.appendChild(details);

    let baseline = snapshot();
    const update = () => {
      const current = snapshot();
      const names = new Set([...baseline.keys(), ...current.keys()]);
      const changes = Array.from(names)
        .filter((name) => (baseline.get(name) || "") !== (current.get(name) || ""))
        .map((name) => ({ name, before: baseline.get(name) || "", after: current.get(name) || "" }));
      if (!changes.length) {
        details.hidden = true;
        details.innerHTML = "";
        return;
      }
      const shown = changes.slice(0, 3);
      details.hidden = false;
      details.innerHTML = shown.map((change) => {
        const restart = restartFields.has(change.name) ? '<em>재시작</em>' : "";
        return `<span><b>${escapeHtml(controlLabel(change.name))}</b><del>${escapeHtml(friendlyValue(change.name, change.before))}</del><i aria-hidden="true">→</i><ins>${escapeHtml(friendlyValue(change.name, change.after))}</ins>${restart}</span>`;
      }).join("") + (changes.length > shown.length ? `<small>외 ${changes.length - shown.length}개 변경</small>` : "");
    };
    form.addEventListener("input", () => window.setTimeout(update, 0), true);
    form.addEventListener("change", () => window.setTimeout(update, 0), true);
    form.addEventListener("reset", () => window.setTimeout(update, 20), true);
    window.setTimeout(() => { baseline = snapshot(); update(); }, 180);
  }

  buildInformationArchitecture();
  setupBooleanSwitches();
  setupEncodingDisclosure();
  const updateNotifications = setupNotificationState();
  setupTabStatuses(updateNotifications);
  setupDetailedSaveSummary();
})();