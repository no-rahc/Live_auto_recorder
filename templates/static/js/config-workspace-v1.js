(function () {
  "use strict";

  if (!document.body.classList.contains("page-config")) return;

  const form = document.getElementById("configForm");
  if (!form || form.dataset.larWorkspaceReady === "true") return;
  form.dataset.larWorkspaceReady = "true";

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const sectionNumber = (section) => ($(".section-num", section)?.textContent || "").trim().padStart(2, "0");
  const sectionTitle = (section) => ($(".section-head h3", section)?.textContent || "설정").trim();
  const truthy = (value) => ["true", "1", "on", "yes"].includes(String(value).toLowerCase());
  const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  }[char]));

  function dispatchChange(control) {
    control.dispatchEvent(new Event("change", { bubbles: true }));
    control.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function unwrapLegacyGrid() {
    const legacy = $(".lar-config-masonry-grid", form);
    if (!legacy) return;
    const marker = document.createDocumentFragment();
    $$(":scope > .config-section", legacy).forEach((section) => {
      section.style.removeProperty("grid-row-end");
      marker.appendChild(section);
    });
    legacy.replaceWith(marker);
  }

  function wrapSectionFields(section) {
    if (!section || section.dataset.larFieldsWrapped === "true") return;
    section.dataset.larFieldsWrapped = "true";
    const head = $(".section-head", section);
    const nodes = Array.from(section.children).filter((node) => node !== head);
    let current = null;

    nodes.forEach((node) => {
      if (node.matches && node.matches("label")) {
        current = document.createElement("div");
        current.className = "lar-setting-row";
        section.insertBefore(current, node);
      }
      if (current) current.appendChild(node);
      else node.classList?.add("lar-section-lead");
    });

    $$("select", section).forEach((select) => {
      const values = Array.from(select.options).map((option) => String(option.value).toLowerCase());
      if (values.includes("true") && values.includes("false")) select.classList.add("lar-boolean-select");
    });
  }

  function settingRow(controlId) {
    return document.getElementById(controlId)?.closest(".lar-setting-row") || null;
  }

  function moveSetting(controlId, targetSection) {
    const row = settingRow(controlId);
    if (row && targetSection) targetSection.appendChild(row);
    return row;
  }

  function setRowVisible(controlId, visible) {
    const row = settingRow(controlId);
    if (!row) return;
    row.hidden = !visible;
    row.setAttribute("aria-hidden", visible ? "false" : "true");
  }

  function enhanceHelp(section) {
    if (!section) return;
    $$("table.description", section).forEach((table) => {
      if (table.closest("details")) return;
      const details = document.createElement("details");
      details.className = "lar-help-details";
      const summary = document.createElement("summary");
      summary.textContent = "권장값과 호환 정보 보기";
      table.replaceWith(details);
      details.append(summary, table);
    });

    $$("p.description", section).forEach((paragraph) => {
      if (paragraph.closest("details") || paragraph.textContent.trim().length < 180) return;
      const details = document.createElement("details");
      details.className = "lar-help-details";
      const summary = document.createElement("summary");
      summary.textContent = /텔레그램|웹훅|BotFather|Discord/i.test(paragraph.textContent)
        ? "연결 방법 보기"
        : "자세한 설명 보기";
      paragraph.replaceWith(details);
      details.append(summary, paragraph);
    });
  }

  function renameSection(section, title, subtitle) {
    if (!section) return;
    const heading = $(".section-head h3", section);
    const tag = $(".section-tag", section);
    if (heading) heading.textContent = title;
    if (tag) tag.textContent = subtitle || "";
  }

  unwrapLegacyGrid();
  const formSections = $$(".config-section", form);
  formSections.forEach(wrapSectionFields);

  const sections = Object.fromEntries(formSections.map((section) => [sectionNumber(section), section]));
  renameSection(sections["01"], "녹화 기본 설정", "Recording");
  renameSection(sections["02"], "치지직 플러그인", "CHZZK");
  renameSection(sections["03"], "후처리", "Post-processing");
  renameSection(sections["04"], "분할 녹화", "Split recording");
  renameSection(sections["05"], "인코딩", "Encoding");
  renameSection(sections["06"], "Telegram", "Notifications");
  renameSection(sections["07"], "Discord", "Notifications");
  renameSection(sections["08"], "파일 관리자", "Files");
  renameSection(sections["09"], "로그인과 보안", "Security");

  moveSetting("recheckInterval", sections["01"]);
  moveSetting("filenamePattern", sections["01"]);
  formSections.forEach(enhanceHelp);

  const groupDefinitions = [
    { id: "basic", label: "기본 녹화", hint: "자동녹화·탐색·파일명", sections: ["01"] },
    { id: "chzzk", label: "치지직", hint: "플러그인·분할 녹화", sections: ["02", "04"] },
    { id: "processing", label: "후처리·인코딩", hint: "파일 처리·압축", sections: ["03", "05"] },
    { id: "notifications", label: "알림", hint: "Telegram·Discord", sections: ["06", "07"] },
    { id: "system", label: "시스템·보안", hint: "파일·로그인·계정", sections: ["08", "09"] }
  ];

  const workspace = document.createElement("div");
  workspace.className = "lar-config-workspace";
  const tabs = document.createElement("nav");
  tabs.className = "lar-config-tabs";
  tabs.setAttribute("aria-label", "설정 분류");
  const panels = document.createElement("div");
  panels.className = "lar-config-panels";
  const panelMap = new Map();

  groupDefinitions.forEach((group, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lar-config-tab";
    button.dataset.configTab = group.id;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", index === 0 ? "true" : "false");
    button.innerHTML = `<strong>${escapeHtml(group.label)}</strong><small>${escapeHtml(group.hint)}</small>`;
    tabs.appendChild(button);

    const panel = document.createElement("section");
    panel.className = "lar-config-panel" + (index === 0 ? " is-active" : "");
    panel.dataset.configPanel = group.id;
    panel.setAttribute("role", "tabpanel");
    panel.hidden = index !== 0;
    const grid = document.createElement("div");
    grid.className = "lar-config-panel-grid";
    group.sections.forEach((number) => {
      if (sections[number]) grid.appendChild(sections[number]);
    });
    panel.appendChild(grid);
    panels.appendChild(panel);
    panelMap.set(group.id, panel);
  });

  workspace.append(tabs, panels);
  form.prepend(workspace);

  const accountFields = document.getElementById("account-fields");
  const systemExtras = document.createElement("div");
  systemExtras.className = "lar-config-system-extras";
  systemExtras.hidden = true;
  if (accountFields) systemExtras.appendChild(accountFields);

  const maintenanceCard = document.createElement("section");
  maintenanceCard.className = "config-section lar-operations-link-card";
  maintenanceCard.innerHTML = `
    <header class="section-head"><h3>백업과 저장소 정리</h3><span class="section-tag">Operations</span></header>
    <p>설정 백업, 복원, 저장소 임계치와 파일 정리는 운영 관리에서 한 번에 관리합니다.</p>
    <a href="/operations" class="lar-inline-primary">운영 관리 열기</a>`;
  systemExtras.appendChild(maintenanceCard);
  form.insertAdjacentElement("afterend", systemExtras);

  $$(".config-section", document).forEach((section) => {
    const title = sectionTitle(section);
    const number = sectionNumber(section);
    if ((number === "11" || number === "12") || /설정 백업|녹화 파일 정리/.test(title)) {
      if (!section.closest(".lar-config-system-extras")) section.remove();
    }
  });

  function activateGroup(groupId, focus) {
    const id = panelMap.has(groupId) ? groupId : "basic";
    $$(".lar-config-tab", tabs).forEach((button) => {
      const active = button.dataset.configTab === id;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      if (active && focus) button.focus();
    });
    panelMap.forEach((panel, panelId) => {
      const active = panelId === id;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
    systemExtras.hidden = id !== "system";
    try { localStorage.setItem("lar-config-tab", id); } catch (_) { /* ignore */ }
  }

  tabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-config-tab]");
    if (button) activateGroup(button.dataset.configTab, false);
  });
  tabs.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const buttons = $$("[data-config-tab]", tabs);
    const current = buttons.indexOf(document.activeElement);
    const next = (current + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
    activateGroup(buttons[next].dataset.configTab, true);
  });

  let savedTab = "basic";
  try { savedTab = localStorage.getItem("lar-config-tab") || "basic"; } catch (_) { /* ignore */ }
  activateGroup(savedTab, false);

  function addFilenamePreview() {
    const input = document.getElementById("filenamePattern");
    const row = input?.closest(".lar-setting-row");
    if (!input || !row) return;
    const preview = document.createElement("div");
    preview.className = "lar-filename-preview";
    preview.innerHTML = '<span>예상 파일명</span><code></code>';
    row.appendChild(preview);
    const code = $("code", preview);
    const replacements = {
      recording_time: "260805_155400", start_time: "2026-08-05", safe_live_title: "오늘의 라이브 방송",
      channel_name: "샘플채널", record_quality: "1080p", frame_rate: "60fps", file_extension: ".ts"
    };
    const update = () => {
      let result = input.value || "{recording_time}_{channel_name}_{safe_live_title}";
      Object.entries(replacements).forEach(([key, value]) => {
        result = result.replace(new RegExp(`\\{${key}\\}`, "g"), value);
      });
      code.textContent = result;
    };
    input.addEventListener("input", update);
    update();
  }

  function addPathCheck() {
    const input = document.getElementById("moveAfterProcessing");
    const row = input?.closest(".lar-setting-row");
    if (!input || !row) return;
    const actions = document.createElement("div");
    actions.className = "lar-field-actions";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lar-secondary-button";
    button.textContent = "경로 확인";
    const result = document.createElement("span");
    result.className = "lar-field-result";
    result.setAttribute("role", "status");
    actions.append(button, result);
    row.appendChild(actions);
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "확인 중…";
      result.className = "lar-field-result";
      result.textContent = "";
      try {
        const response = await fetch("/api/config-tools/path-check", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: input.value })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || data.message || "경로를 확인하지 못했습니다.");
        result.classList.add(data.writable ? "is-ok" : "is-error");
        result.textContent = `${data.message} 여유 ${data.free_gb} GB`;
      } catch (error) {
        result.classList.add("is-error");
        result.textContent = error.message;
      } finally {
        button.disabled = false;
        button.textContent = "경로 확인";
      }
    });
  }

  function setControlValue(id, value) {
    const control = document.getElementById(id);
    if (!control) return;
    const normalized = String(value);
    if (control.tagName === "SELECT" && !Array.from(control.options).some((option) => option.value === normalized)) return;
    control.value = normalized;
    dispatchChange(control);
  }

  function addEncodingTools() {
    const section = sections["05"];
    if (!section) return;
    const head = $(".section-head", section);
    const profileRow = document.createElement("div");
    profileRow.className = "lar-setting-row lar-profile-row";
    profileRow.innerHTML = `
      <label for="larEncodingProfile">인코딩 프로필</label>
      <select id="larEncodingProfile"><option value="custom">현재 설정 유지</option><option value="original">원본 유지</option><option value="balanced">균형</option><option value="saving">용량 절약</option><option value="quality">고화질</option></select>
      <p class="description">프로필을 고르면 기존 인코딩 필드에 안전한 기본값을 채웁니다. 세부값은 아래에서 다시 조정할 수 있습니다.</p>`;
    head.insertAdjacentElement("afterend", profileRow);
    const diagnostic = document.createElement("div");
    diagnostic.className = "lar-encoder-diagnostic";
    diagnostic.innerHTML = '<button type="button" class="lar-secondary-button">이 서버의 인코더 확인</button><div class="lar-encoder-result" role="status"></div>';
    profileRow.insertAdjacentElement("afterend", diagnostic);
    const profile = $("#larEncodingProfile", profileRow);
    let applying = false;
    const presets = {
      original: { stream_copy: "true", audio_bitrate: "copy" },
      balanced: { stream_copy: "false", video_codec: "libx264", use_bitrate_mode: "false", video_quality: "23", audio_codec: "aac", audio_bitrate: "copy", preset: "veryfast" },
      saving: { stream_copy: "false", video_codec: "libx265", use_bitrate_mode: "false", video_quality: "28", audio_codec: "aac", audio_bitrate: "128k", preset: "fast" },
      quality: { stream_copy: "false", video_codec: "libx264", use_bitrate_mode: "false", video_quality: "18", audio_codec: "aac", audio_bitrate: "192k", preset: "slow" }
    };
    profile.addEventListener("change", () => {
      const values = presets[profile.value];
      if (!values) return;
      applying = true;
      Object.entries(values).forEach(([id, value]) => { if (id !== "preset") setControlValue(id, value); });
      window.setTimeout(() => { setControlValue("preset", values.preset || ""); applying = false; }, 60);
    });
    ["stream_copy", "video_codec", "preset", "use_bitrate_mode", "video_quality", "video_bitrate", "audio_codec", "audio_bitrate"].forEach((id) => {
      document.getElementById(id)?.addEventListener("change", () => { if (!applying) profile.value = "custom"; });
    });
    const button = $("button", diagnostic);
    const result = $(".lar-encoder-result", diagnostic);
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "확인 중…";
      result.textContent = "";
      try {
        const response = await fetch("/api/config-tools/encoders");
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "인코더를 확인하지 못했습니다.");
        result.innerHTML = data.encoders.map((encoder) => `<span class="${encoder.available ? "is-ok" : "is-off"}">${escapeHtml(encoder.label)}</span>`).join("");
      } catch (error) {
        result.innerHTML = `<span class="is-error">${escapeHtml(error.message)}</span>`;
      } finally {
        button.disabled = false;
        button.textContent = "이 서버의 인코더 확인";
      }
    });
  }

  function addNotificationTabs() {
    const panel = panelMap.get("notifications");
    if (!panel || !sections["06"] || !sections["07"]) return;
    const grid = $(".lar-config-panel-grid", panel);
    grid.classList.add("lar-notification-grid");
    const nav = document.createElement("div");
    nav.className = "lar-notification-tabs";
    nav.innerHTML = '<button type="button" data-notification="06" class="is-active">Telegram</button><button type="button" data-notification="07">Discord</button>';
    grid.prepend(nav);
    const activate = (number) => {
      ["06", "07"].forEach((id) => { sections[id].hidden = id !== number; });
      $$("button", nav).forEach((button) => button.classList.toggle("is-active", button.dataset.notification === number));
    };
    nav.addEventListener("click", (event) => {
      const button = event.target.closest("[data-notification]");
      if (button) activate(button.dataset.notification);
    });
    activate(truthy(document.getElementById("telegram_enabled")?.value) ? "06" : "07");
  }

  function updateConditionalRows() {
    setRowVisible("enableTray", false);
    setRowVisible("postNewWindow", false);
    setRowVisible("timemachine_time_shift", document.getElementById("plugin_type")?.value === "timemachine_plus");
    const split = truthy(document.getElementById("splitRecordingMode")?.value);
    ["splitPostProcessing", "autoStopInterval", "splitOverlapSec"].forEach((id) => setRowVisible(id, split));
    const post = truthy(document.getElementById("autoPostProcessing")?.value);
    ["deleteAfterPostProcessing", "removeFixedPrefix", "moveAfterProcessingEnabled"].forEach((id) => setRowVisible(id, post));
    setRowVisible("moveAfterProcessing", post && truthy(document.getElementById("moveAfterProcessingEnabled")?.value));
    const streamCopy = truthy(document.getElementById("stream_copy")?.value);
    ["video_codec", "preset", "use_bitrate_mode", "video_quality", "video_bitrate", "vbv_maxrate", "vbv_bufsize", "extra_ffmpeg_options"].forEach((id) => setRowVisible(id, !streamCopy));
    if (!streamCopy) {
      const bitrate = truthy(document.getElementById("use_bitrate_mode")?.value);
      setRowVisible("video_quality", !bitrate);
      ["video_bitrate", "vbv_maxrate", "vbv_bufsize"].forEach((id) => setRowVisible(id, bitrate));
    }
    const telegram = truthy(document.getElementById("telegram_enabled")?.value);
    ["telegram_bot_token", "telegram_chat_id"].forEach((id) => setRowVisible(id, telegram));
    const telegramButton = document.getElementById("testTelegramBtn")?.closest(".lar-setting-row");
    if (telegramButton) telegramButton.hidden = !telegram;
    const discord = truthy(document.getElementById("discord_enabled")?.value);
    setRowVisible("discord_webhook_url", discord);
    const discordButton = document.getElementById("testDiscordBtn")?.closest(".lar-setting-row");
    if (discordButton) discordButton.hidden = !discord;
    const manager = truthy(document.getElementById("fileManagerEnabled")?.value);
    ["fileManagerMode", "fileManagerReadOnly", "trashEnabled"].forEach((id) => setRowVisible(id, manager));
    const roots = document.getElementById("fm-roots-section");
    if (roots) roots.hidden = !(manager && document.getElementById("fileManagerMode")?.value === "whitelist");
  }

  ["plugin_type", "splitRecordingMode", "autoPostProcessing", "moveAfterProcessingEnabled", "stream_copy", "use_bitrate_mode", "telegram_enabled", "discord_enabled", "fileManagerEnabled", "fileManagerMode"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", updateConditionalRows);
  });

  function serializeForm() {
    const values = {};
    new FormData(form).forEach((value, key) => {
      const normalized = value instanceof File ? value.name : String(value);
      if (Object.prototype.hasOwnProperty.call(values, key)) values[key] = Array.isArray(values[key]) ? values[key].concat(normalized) : [values[key], normalized];
      else values[key] = normalized;
    });
    return JSON.stringify(values);
  }

  function addSaveBar() {
    const originalSubmit = $("input[type='submit'], button[type='submit']", form);
    if (originalSubmit) originalSubmit.classList.add("lar-original-submit");
    const bar = document.createElement("div");
    bar.className = "lar-config-savebar";
    bar.innerHTML = '<div><strong>저장된 상태</strong><span>설정을 변경하면 여기에 표시됩니다.</span></div><div class="lar-config-save-actions"><button type="button" data-config-reset>변경 취소</button><button type="button" data-config-save class="lar-primary-button" disabled>설정 저장</button></div>';
    document.body.appendChild(bar);
    const title = $("strong", bar);
    const subtitle = $("span", bar);
    const reset = $("[data-config-reset]", bar);
    const save = $("[data-config-save]", bar);
    let baseline = "";
    let dirty = false;
    const update = () => {
      const next = serializeForm();
      dirty = Boolean(baseline && next !== baseline);
      bar.classList.toggle("is-dirty", dirty);
      save.disabled = !dirty;
      reset.disabled = !dirty;
      title.textContent = dirty ? "저장하지 않은 변경사항" : "저장된 상태";
      subtitle.textContent = dirty ? "검토한 뒤 저장하세요. 재시작이 필요한 항목은 저장 후 안내됩니다." : "현재 설정이 적용되어 있습니다.";
    };
    window.setTimeout(() => { baseline = serializeForm(); update(); }, 120);
    form.addEventListener("input", update, true);
    form.addEventListener("change", update, true);
    form.addEventListener("submit", () => { dirty = false; });
    reset.addEventListener("click", () => {
      form.reset();
      $$("select, input, textarea", form).forEach(dispatchChange);
      window.setTimeout(update, 20);
    });
    save.addEventListener("click", () => {
      if (originalSubmit) form.requestSubmit(originalSubmit);
      else form.requestSubmit();
    });
    window.addEventListener("beforeunload", (event) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    });
  }

  addFilenamePreview();
  addPathCheck();
  addEncodingTools();
  addNotificationTabs();
  updateConditionalRows();
  addSaveBar();
})();
