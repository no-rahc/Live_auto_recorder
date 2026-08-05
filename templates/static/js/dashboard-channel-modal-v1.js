(function () {
  "use strict";

  if (!document.body.classList.contains("page-index")) return;

  const list = document.getElementById("ch-list");
  if (!list) return;

  const state = {
    channels: [],
    statuses: {},
    selectedId: null,
    editing: false,
    dirty: false,
    loading: false,
    originalRecordEnabled: true,
  };

  const qualityOptions = {
    chzzk: ["best", "1080p", "720p", "480p", "360p"],
    youtube: ["best", "480p", "720p", "1080p", "1440p", "2160p"],
  };

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function requestJson(url, options) {
    return fetch(url, Object.assign({
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }, options || {})).then(async function (response) {
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        throw new Error(data.detail || data.message || ("요청 실패 (HTTP " + response.status + ")"));
      }
      return data;
    });
  }

  const overlay = node("div", "lar-channel-modal");
  overlay.hidden = true;
  overlay.setAttribute("aria-hidden", "true");
  overlay.innerHTML = [
    '<div class="lar-channel-modal-backdrop" data-modal-close></div>',
    '<section class="lar-channel-dialog" role="dialog" aria-modal="true" aria-labelledby="lar-channel-dialog-title">',
    '  <header class="lar-channel-dialog-head">',
    '    <div class="lar-channel-dialog-identity">',
    '      <span class="lar-channel-dialog-icon" id="lar-channel-dialog-icon">치</span>',
    '      <div>',
    '        <div class="lar-channel-dialog-kicker" id="lar-channel-dialog-kicker">채널 세부 설정</div>',
    '        <h2 id="lar-channel-dialog-title">채널</h2>',
    '        <p id="lar-channel-dialog-subtitle">채널 정보를 불러오는 중입니다.</p>',
    '      </div>',
    '    </div>',
    '    <div class="lar-channel-dialog-head-actions">',
    '      <span class="lar-channel-dialog-status" id="lar-channel-dialog-status">대기</span>',
    '      <button type="button" class="lar-channel-dialog-close" data-modal-close aria-label="닫기">×</button>',
    '    </div>',
    '  </header>',
    '  <div class="lar-channel-dialog-scroll">',
    '    <section class="lar-channel-live-summary" aria-label="현재 방송 상태">',
    '      <div><span>현재 방송</span><strong id="lar-channel-live-title">라이브 종료</strong></div>',
    '      <div><span>녹화 시간</span><strong id="lar-channel-duration">-</strong></div>',
    '    </section>',
    '    <div class="lar-channel-recording-note" id="lar-channel-recording-note" hidden>',
    '      현재 녹화 중입니다. 저장 경로·품질·확장자 변경은 다음 녹화부터 적용됩니다.',
    '    </div>',
    '    <form id="lar-channel-detail-form" class="lar-channel-detail-form is-view">',
    '      <label><span>플랫폼</span><select name="platform" disabled></select></label>',
    '      <label><span>채널 ID</span><input name="id" type="text" readonly></label>',
    '      <label class="lar-channel-field-wide"><span>채널명</span><input name="name" type="text" required maxlength="100"></label>',
    '      <label class="lar-channel-field-wide"><span>저장 경로</span><input name="output_dir" type="text" required></label>',
    '      <label><span>녹화 품질</span><select name="quality"></select></label>',
    '      <label><span>파일 확장자</span><select name="extension"></select></label>',
    '      <label><span>같이보기만 녹화</span><select name="recordWatchParty"><option value="false">아니오</option><option value="true">예</option></select></label>',
    '      <label class="lar-channel-switch-field"><span>자동녹화 사용</span><input name="record_enabled" type="checkbox"></label>',
    '      <label class="lar-channel-field-wide"><span>녹화 제외 태그</span><input name="watchPartyExcludeTags" type="text" placeholder="예: LCK, VCT"><small>쉼표로 여러 태그를 구분할 수 있습니다.</small></label>',
    '    </form>',
    '    <p class="lar-channel-modal-message" id="lar-channel-modal-message" role="status" aria-live="polite"></p>',
    '  </div>',
    '  <footer class="lar-channel-dialog-footer">',
    '    <a class="lar-channel-manage-link" href="/channels">전체 채널 관리</a>',
    '    <div class="lar-channel-dialog-buttons">',
    '      <button type="button" class="lar-channel-btn lar-channel-btn-secondary" id="lar-channel-cancel" hidden>취소</button>',
    '      <button type="button" class="lar-channel-btn lar-channel-btn-secondary" id="lar-channel-edit">수정</button>',
    '      <button type="submit" form="lar-channel-detail-form" class="lar-channel-btn lar-channel-btn-primary" id="lar-channel-save" hidden>변경사항 저장</button>',
    '    </div>',
    '  </footer>',
    '</section>',
  ].join("");
  document.body.appendChild(overlay);

  const dialog = overlay.querySelector(".lar-channel-dialog");
  const form = document.getElementById("lar-channel-detail-form");
  const title = document.getElementById("lar-channel-dialog-title");
  const subtitle = document.getElementById("lar-channel-dialog-subtitle");
  const icon = document.getElementById("lar-channel-dialog-icon");
  const statusBadge = document.getElementById("lar-channel-dialog-status");
  const liveTitle = document.getElementById("lar-channel-live-title");
  const duration = document.getElementById("lar-channel-duration");
  const recordingNote = document.getElementById("lar-channel-recording-note");
  const message = document.getElementById("lar-channel-modal-message");
  const editButton = document.getElementById("lar-channel-edit");
  const cancelButton = document.getElementById("lar-channel-cancel");
  const saveButton = document.getElementById("lar-channel-save");
  const manageLink = overlay.querySelector(".lar-channel-manage-link");

  const fields = {
    platform: form.elements.platform,
    id: form.elements.id,
    name: form.elements.name,
    outputDir: form.elements.output_dir,
    quality: form.elements.quality,
    extension: form.elements.extension,
    watchParty: form.elements.recordWatchParty,
    recordEnabled: form.elements.record_enabled,
    tags: form.elements.watchPartyExcludeTags,
  };

  function platformName(platform) {
    return String(platform || "").toLowerCase() === "youtube" ? "유튜브" : "치지직";
  }

  function isRecording(status) {
    return !!(status && (status.recording || status.is_recording || status.state === "recording"));
  }

  function isReserved(status) {
    return !!(status && (status.reserved || status.is_reserved || status.state === "reserved"));
  }

  function currentChannel() {
    return state.channels.find(function (channel) {
      return String(channel.id) === String(state.selectedId);
    }) || null;
  }

  function currentStatus() {
    return state.statuses && state.selectedId != null ? (state.statuses[state.selectedId] || {}) : {};
  }

  function setOptions(select, values, selected) {
    select.innerHTML = "";
    values.forEach(function (value) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      option.selected = String(value) === String(selected);
      select.appendChild(option);
    });
    if (selected && !values.includes(selected)) {
      const option = document.createElement("option");
      option.value = selected;
      option.textContent = selected;
      option.selected = true;
      select.appendChild(option);
    }
  }

  function extensionOptions(platform, quality) {
    if (platform === "youtube") {
      return ["1440p", "2160p"].includes(quality) ? [".mkv"] : [".mp4"];
    }
    return [".ts", ".mp4"];
  }

  function syncFormatOptions(preferredQuality, preferredExtension) {
    const platform = String(fields.platform.value || "chzzk").toLowerCase();
    const qualities = qualityOptions[platform] || qualityOptions.chzzk;
    const quality = preferredQuality || fields.quality.value || qualities[0];
    setOptions(fields.quality, qualities, quality);
    const extensions = extensionOptions(platform, fields.quality.value);
    setOptions(fields.extension, extensions, preferredExtension || fields.extension.value || extensions[0]);
  }

  function tagsValue(value) {
    if (Array.isArray(value)) return value.join(", ");
    return String(value || "");
  }

  function setMessage(text, tone) {
    message.textContent = text || "";
    message.dataset.tone = tone || "";
  }

  function setEditing(editing) {
    state.editing = !!editing;
    form.classList.toggle("is-view", !state.editing);
    form.classList.toggle("is-editing", state.editing);

    [fields.name, fields.outputDir, fields.quality, fields.extension, fields.watchParty, fields.recordEnabled, fields.tags]
      .forEach(function (field) { field.disabled = !state.editing; });
    fields.platform.disabled = true;
    fields.id.readOnly = true;

    editButton.hidden = state.editing;
    cancelButton.hidden = !state.editing;
    saveButton.hidden = !state.editing;
    manageLink.hidden = state.editing;
    setMessage(state.editing ? "수정할 항목만 변경한 뒤 저장하세요." : "", "");

    if (!state.editing) state.dirty = false;
    if (state.editing) fields.name.focus();
  }

  function renderChannel() {
    const channel = currentChannel();
    if (!channel) return;
    const status = currentStatus();
    const platform = String(channel.platform || "chzzk").toLowerCase();
    const recording = isRecording(status);
    const reserved = isReserved(status);
    const name = channel.channel_name || channel.name || channel.id;

    title.textContent = name;
    subtitle.textContent = platformName(platform) + " · " + channel.id;
    icon.textContent = platform === "youtube" ? "▶" : "치";
    icon.dataset.platform = platform;

    statusBadge.textContent = recording ? "녹화 중" : reserved ? "예약녹화" : "대기";
    statusBadge.dataset.state = recording ? "recording" : reserved ? "reserved" : "idle";
    liveTitle.textContent = channel.live_title || status.live_title || status.title || (recording || reserved ? "방송 준비 중" : "라이브 종료");
    duration.textContent = recording ? (status.duration || status.recording_duration || "00:00:00") : "-";
    recordingNote.hidden = !recording;

    setOptions(fields.platform, [platform], platform);
    fields.id.value = channel.id || "";
    fields.name.value = name || "";
    fields.outputDir.value = channel.output_dir || channel.outputDir || "";
    syncFormatOptions(channel.quality || "best", channel.extension || (platform === "youtube" ? ".mp4" : ".ts"));
    fields.watchParty.value = String(!!channel.recordWatchParty);
    fields.tags.value = tagsValue(channel.watchPartyExcludeTags);
    state.originalRecordEnabled = channel.record_enabled !== false;
    fields.recordEnabled.checked = state.originalRecordEnabled;
    fields.tags.disabled = !state.editing || fields.watchParty.value !== "true";

    manageLink.href = "/channels#" + encodeURIComponent(String(channel.id));
    setEditing(false);
  }

  async function refreshCache() {
    if (state.loading) return;
    state.loading = true;
    try {
      const values = await Promise.all([
        requestJson("/api/channels"),
        requestJson("/status"),
      ]);
      state.channels = Array.isArray(values[0]) ? values[0] : [];
      state.statuses = values[1] || {};
      decorateRows();
      if (state.selectedId && !overlay.hidden) renderChannel();
    } catch (error) {
      console.error("채널 정보를 불러오지 못했습니다.", error);
      if (!overlay.hidden) setMessage(error.message, "error");
    } finally {
      state.loading = false;
    }
  }

  function decorateRows() {
    const rows = Array.from(list.querySelectorAll(".ch-row"));
    rows.forEach(function (row, index) {
      const channel = state.channels[index];
      if (!channel) return;
      row.dataset.channelId = channel.id;
      row.classList.add("lar-channel-clickable");
      row.tabIndex = 0;
      row.setAttribute("role", "button");
      row.setAttribute("aria-haspopup", "dialog");
      row.setAttribute("aria-label", (channel.channel_name || channel.name || channel.id) + " 세부 설정 열기");
    });
  }

  async function openModal(id) {
    if (!id) return;
    if (!state.channels.length) await refreshCache();
    state.selectedId = String(id);
    const channel = currentChannel();
    if (!channel) {
      setMessage("선택한 채널 정보를 찾을 수 없습니다.", "error");
      return;
    }

    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("lar-modal-open");
    renderChannel();
    dialog.focus({ preventScroll: true });
  }

  function closeModal(force) {
    if (!force && state.editing && state.dirty && !window.confirm("저장하지 않은 변경사항을 닫을까요?")) return;
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("lar-modal-open");
    state.selectedId = null;
    setEditing(false);
    setMessage("", "");
  }

  async function saveChannel(event) {
    event.preventDefault();
    if (!state.editing || !state.selectedId) return;

    const channel = currentChannel();
    if (!channel) return;
    const name = fields.name.value.trim();
    const outputDir = fields.outputDir.value.trim();
    if (!name || !outputDir) {
      setMessage("채널명과 저장 경로를 입력하세요.", "error");
      return;
    }

    saveButton.disabled = true;
    saveButton.textContent = "저장 중…";
    setMessage("변경사항을 저장하고 있습니다.", "");

    try {
      const payload = {
        platform: channel.platform || "chzzk",
        name: name,
        output_dir: outputDir,
        quality: fields.quality.value,
        extension: fields.extension.value,
        recordWatchParty: fields.watchParty.value === "true",
        watchPartyExcludeTags: fields.tags.value.trim(),
      };

      const result = await requestJson("/api/channels/" + encodeURIComponent(state.selectedId), {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      if (result.status && result.status !== "success") throw new Error(result.message || "채널 수정에 실패했습니다.");

      if (fields.recordEnabled.checked !== state.originalRecordEnabled) {
        const toggleResult = await requestJson("/api/toggle_record_enabled/" + encodeURIComponent(state.selectedId), {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
        });
        if (toggleResult.status && toggleResult.status !== "success") {
          throw new Error(toggleResult.message || "자동녹화 설정 변경에 실패했습니다.");
        }
      }

      state.dirty = false;
      await refreshCache();
      renderChannel();
      setMessage("채널 설정을 저장했습니다.", "success");
      document.dispatchEvent(new CustomEvent("lar:channel-updated", { detail: { channelId: state.selectedId } }));
    } catch (error) {
      console.error("채널 설정 저장 오류:", error);
      setMessage(error.message || "채널 설정을 저장하지 못했습니다.", "error");
    } finally {
      saveButton.disabled = false;
      saveButton.textContent = "변경사항 저장";
    }
  }

  list.addEventListener("click", function (event) {
    const row = event.target.closest(".ch-row");
    if (!row || !list.contains(row)) return;
    const id = row.dataset.channelId;
    if (id) openModal(id);
  });

  list.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = event.target.closest(".ch-row");
    if (!row || !row.dataset.channelId) return;
    event.preventDefault();
    openModal(row.dataset.channelId);
  });

  overlay.querySelectorAll("[data-modal-close]").forEach(function (button) {
    button.addEventListener("click", function () { closeModal(false); });
  });
  editButton.addEventListener("click", function () { setEditing(true); });
  cancelButton.addEventListener("click", function () { renderChannel(); });
  form.addEventListener("submit", saveChannel);
  form.addEventListener("input", function () { if (state.editing) state.dirty = true; });
  form.addEventListener("change", function () { if (state.editing) state.dirty = true; });
  fields.quality.addEventListener("change", function () {
    syncFormatOptions(fields.quality.value, fields.extension.value);
  });
  fields.watchParty.addEventListener("change", function () {
    fields.tags.disabled = !state.editing || fields.watchParty.value !== "true";
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !overlay.hidden) closeModal(false);
  });

  new MutationObserver(function () {
    window.requestAnimationFrame(decorateRows);
  }).observe(list, { childList: true, subtree: false });

  refreshCache();
  window.setInterval(refreshCache, 15000);
})();
