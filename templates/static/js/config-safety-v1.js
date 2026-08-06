(function () {
  "use strict";

  if (!document.body.classList.contains("page-config")) return;

  const form = document.getElementById("configForm");
  if (!form || form.dataset.larSafetyReady === "true") return;
  form.dataset.larSafetyReady = "true";

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const truthy = (value) => ["true", "1", "on", "yes"].includes(String(value || "").toLowerCase());
  const helperNames = new Set([
    "danger_confirmation",
    "danger_current_password",
    "danger_ack",
    "telegram_bot_token_action",
    "telegram_chat_id_action",
    "discord_webhook_url_action"
  ]);
  const restartFields = new Set(["autoRecordingMode", "loginMode"]);
  const labels = {
    autoRecordingMode: "자동 녹화",
    plugin_type: "치지직 플러그인",
    timemachine_time_shift: "타임머신 시프트",
    recheckInterval: "방송 재탐색 주기",
    filenamePattern: "파일명 규칙",
    autoPostProcessing: "자동 후처리",
    moveAfterProcessing: "후처리 이동 경로",
    splitRecordingMode: "분할 녹화",
    autoStopInterval: "분할 시간",
    stream_copy: "후처리 방식",
    video_codec: "비디오 코덱",
    preset: "인코딩 프리셋",
    telegram_enabled: "Telegram 알림",
    discord_enabled: "Discord 알림",
    fileManagerEnabled: "파일 관리자",
    fileManagerMode: "파일 관리자 경로 모드",
    fileManagerReadOnly: "파일 관리자 읽기 전용",
    trashEnabled: "파일 관리자 휴지통",
    loginMode: "로그인 모드"
  };

  function dispatchChange(control) {
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function ensureHidden(name, value) {
    let input = form.elements.namedItem(name);
    if (!input || input instanceof RadioNodeList) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      form.appendChild(input);
    }
    input.value = value;
    input.defaultValue = value;
    return input;
  }

  function fieldLabel(control) {
    if (!control) return "설정";
    return labels[control.name]
      || $(`label[for="${CSS.escape(control.id || "")}"]`)?.textContent?.replace(/\s+/g, " ").trim()
      || control.name
      || control.id
      || "설정";
  }

  function setStatus(message, kind) {
    const bar = $(".lar-config-savebar");
    if (!bar) return;
    const title = $("strong", bar);
    const subtitle = $("span", bar);
    bar.classList.toggle("is-error", kind === "error");
    bar.classList.toggle("is-saving", kind === "saving");
    bar.classList.toggle("is-success", kind === "success");
    if (title) title.textContent = message;
    if (subtitle && kind === "error") subtitle.textContent = "입력값을 확인한 뒤 다시 저장하세요.";
    if (subtitle && kind === "saving") subtitle.textContent = "검증 후 설정 파일에 반영하고 있습니다.";
    if (subtitle && kind === "success") subtitle.textContent = "저장이 완료되어 화면을 이동합니다.";
  }

  function setupSecretField(id, title) {
    const input = document.getElementById(id);
    const row = input?.closest(".lar-setting-row");
    if (!input || !row) return;

    const configured = input.dataset.storedSecret === "true";
    const action = ensureHidden(`${id}_action`, configured ? "keep" : "replace");
    input.type = "password";
    input.autocomplete = "new-password";
    input.spellcheck = false;
    input.value = "";

    const shell = document.createElement("div");
    shell.className = "lar-secret-actions";
    const state = document.createElement("span");
    state.className = "lar-secret-state";
    state.setAttribute("role", "status");
    const change = document.createElement("button");
    change.type = "button";
    change.className = "lar-secondary-button";
    const reveal = document.createElement("button");
    reveal.type = "button";
    reveal.className = "lar-secondary-button";
    reveal.textContent = "표시";
    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "lar-danger-ghost";
    clear.textContent = "삭제";
    shell.append(state, change, reveal, clear);
    row.appendChild(shell);

    function render() {
      const mode = action.value;
      row.classList.toggle("is-secret-cleared", mode === "clear");
      if (mode === "keep") {
        input.disabled = true;
        input.value = "";
        input.placeholder = `${title} 저장됨`;
        state.textContent = "저장된 값을 그대로 사용합니다.";
        change.textContent = "변경";
        reveal.hidden = true;
        clear.hidden = !configured;
      } else if (mode === "clear") {
        input.disabled = true;
        input.value = "";
        input.placeholder = "저장 시 삭제됩니다";
        state.textContent = "저장하면 기존 값이 삭제됩니다.";
        change.textContent = configured ? "삭제 취소" : "입력";
        reveal.hidden = true;
        clear.hidden = true;
      } else {
        input.disabled = false;
        input.placeholder = `새 ${title} 입력`;
        state.textContent = configured ? "새 값을 입력하면 기존 값을 교체합니다." : "저장할 값을 입력하세요.";
        change.textContent = configured ? "변경 취소" : "입력 중";
        reveal.hidden = false;
        clear.hidden = !configured;
      }
      dispatchChange(action);
    }

    change.addEventListener("click", () => {
      if (action.value === "replace" && configured) action.value = "keep";
      else if (action.value === "clear" && configured) action.value = "keep";
      else action.value = "replace";
      render();
      if (action.value === "replace") input.focus();
    });
    clear.addEventListener("click", () => {
      action.value = "clear";
      render();
    });
    reveal.addEventListener("click", () => {
      input.type = input.type === "password" ? "text" : "password";
      reveal.textContent = input.type === "password" ? "표시" : "숨김";
    });
    input.addEventListener("input", () => {
      if (action.value !== "replace") {
        action.value = "replace";
        render();
      }
    });

    render();
  }

  function validationNode(input) {
    const row = input.closest(".lar-setting-row") || input.parentElement;
    let node = $(".lar-field-validation", row);
    if (!node) {
      node = document.createElement("div");
      node.className = "lar-field-validation";
      node.setAttribute("role", "status");
      row.appendChild(node);
    }
    return node;
  }

  function setValidation(input, message, kind) {
    const node = validationNode(input);
    node.textContent = message || "";
    node.className = `lar-field-validation${kind ? ` is-${kind}` : ""}`;
    input.setCustomValidity(kind === "error" ? message : "");
  }

  function configureNumber(id, options) {
    const input = document.getElementById(id);
    if (!input) return;
    input.type = "number";
    Object.entries(options).forEach(([key, value]) => {
      if (["warningBelow", "warningText"].includes(key)) return;
      input.setAttribute(key, String(value));
    });
    const validate = () => {
      if (input.disabled || input.value === "") {
        setValidation(input, "", "");
        return true;
      }
      const value = Number(input.value);
      const min = input.min === "" ? -Infinity : Number(input.min);
      const max = input.max === "" ? Infinity : Number(input.max);
      if (!Number.isFinite(value) || value < min || value > max) {
        setValidation(input, `${min}~${max} 범위의 값을 입력하세요.`, "error");
        return false;
      }
      if (options.warningBelow != null && value < options.warningBelow) {
        setValidation(input, options.warningText, "warning");
      } else {
        setValidation(input, "", "");
      }
      return true;
    };
    input.addEventListener("input", validate);
    input.addEventListener("change", validate);
    validate();
  }

  function setupNumericValidation() {
    configureNumber("timemachine_time_shift", { min: 0, max: 3600, step: 1 });
    configureNumber("recheckInterval", {
      min: 10,
      max: 86400,
      step: 1,
      warningBelow: 120,
      warningText: "짧은 탐색 주기는 요청 제한이나 방송 누락을 유발할 수 있습니다. 120초 이상을 권장합니다."
    });
    configureNumber("autoStopInterval", { min: 60, max: 604800, step: 1 });
    configureNumber("splitOverlapSec", { min: 0, max: 30, step: 1 });
    configureNumber("video_quality", { min: 0, max: 51, step: 1 });

    const plugin = document.getElementById("plugin_type");
    const shift = document.getElementById("timemachine_time_shift");
    const updateShiftLimit = () => {
      if (!shift) return;
      shift.max = plugin?.value === "timemachine_plus" ? "3600" : "10";
      shift.dispatchEvent(new Event("input", { bubbles: true }));
    };
    plugin?.addEventListener("change", updateShiftLimit);
    updateShiftLimit();

    ["video_bitrate", "vbv_maxrate", "vbv_bufsize"].forEach((id) => {
      const input = document.getElementById(id);
      if (!input) return;
      const validate = () => {
        const value = input.value.trim();
        if (!value && id !== "video_bitrate") {
          setValidation(input, "", "");
          return true;
        }
        if (!/^\d+(?:\.\d+)?[kKmM]$/.test(value)) {
          setValidation(input, "5000k 또는 8M 형식으로 입력하세요.", "error");
          return false;
        }
        setValidation(input, "", "");
        return true;
      };
      input.addEventListener("input", validate);
      validate();
    });
  }

  function setupFilenameValidation() {
    const input = document.getElementById("filenamePattern");
    if (!input) return;
    const allowed = new Set([
      "recording_time", "start_time", "safe_live_title", "channel_name",
      "record_quality", "frame_rate", "file_extension"
    ]);
    const validate = () => {
      const value = input.value.trim();
      const tokens = Array.from(value.matchAll(/\{([^{}]+)\}/g), (match) => match[1]);
      const unknown = tokens.filter((token) => !allowed.has(token));
      const withoutTokens = value.replace(/\{[^{}]+\}/g, "");
      if (!value) {
        setValidation(input, "파일명 규칙을 입력하세요.", "error");
        return false;
      }
      if (unknown.length || /[{}]/.test(withoutTokens)) {
        setValidation(input, `지원하지 않는 변수: ${unknown.join(", ") || "중괄호 형식 오류"}`, "error");
        return false;
      }
      if (/[\\/:*?"<>|]/.test(withoutTokens)) {
        setValidation(input, "파일명에 사용할 수 없는 문자(\\ / : * ? \" < > |)가 있습니다.", "error");
        return false;
      }
      setValidation(input, "", "");
      return true;
    };
    input.addEventListener("input", validate);
    validate();
  }

  async function checkPath(input, result, button) {
    const path = input.value.trim();
    if (!path) {
      result.className = "lar-field-result is-error";
      result.textContent = "경로를 입력하세요.";
      return;
    }
    button.disabled = true;
    button.textContent = "확인 중…";
    result.className = "lar-field-result";
    result.textContent = "";
    try {
      const response = await fetch("/api/config-tools/path-check", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ path })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.message || "경로를 확인하지 못했습니다.");
      result.classList.add(data.writable ? "is-ok" : "is-error");
      result.textContent = `${data.message} · 여유 ${data.free_gb} GB`;
    } catch (error) {
      result.classList.add("is-error");
      result.textContent = error.message;
    } finally {
      button.disabled = false;
      button.textContent = "경로 확인";
    }
  }

  function enhanceRootRow(row) {
    if (row.dataset.larPathCheck === "true") return;
    const input = $("input[name='fileManagerRoots']", row);
    if (!input) return;
    row.dataset.larPathCheck = "true";
    row.classList.add("lar-root-row");
    const result = document.createElement("span");
    result.className = "lar-field-result lar-root-result";
    result.setAttribute("role", "status");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lar-secondary-button lar-root-check";
    button.textContent = "경로 확인";
    const remove = $(".rm-root", row);
    row.insertBefore(button, remove || null);
    row.appendChild(result);
    button.addEventListener("click", () => checkPath(input, result, button));
  }

  function setupRootPathChecks() {
    const host = document.getElementById("fm-roots-list");
    if (!host) return;
    const enhance = () => $$(".fm-root-row", host).forEach(enhanceRootRow);
    enhance();
    new MutationObserver(enhance).observe(host, { childList: true, subtree: true });
  }

  function dangerNote(controlId, message) {
    const control = document.getElementById(controlId);
    const row = control?.closest(".lar-setting-row");
    if (!control || !row) return null;
    let note = $(".lar-danger-note", row);
    if (!note) {
      note = document.createElement("div");
      note.className = "lar-danger-note";
      note.setAttribute("role", "alert");
      row.appendChild(note);
    }
    note.textContent = message;
    return note;
  }

  function setupDangerWarnings() {
    const login = document.getElementById("loginMode");
    const manager = document.getElementById("fileManagerEnabled");
    const mode = document.getElementById("fileManagerMode");
    const readOnly = document.getElementById("fileManagerReadOnly");
    const trash = document.getElementById("trashEnabled");

    const loginNote = dangerNote("loginMode", "로그인을 끄면 로컬 접속만 허용됩니다. 저장 시 현재 비밀번호와 확인 문구가 필요합니다.");
    const modeNote = dangerNote("fileManagerMode", "블랙리스트 모드는 허용 범위가 넓습니다. 공개·외부 접속 환경에서는 화이트리스트를 사용하세요.");
    const readNote = dangerNote("fileManagerReadOnly", "읽기 전용을 끄면 웹에서 이동·이름 변경·삭제가 가능해집니다.");
    const trashNote = dangerNote("trashEnabled", "휴지통을 끄면 삭제한 파일을 복구할 수 없습니다.");

    const update = () => {
      if (loginNote) loginNote.hidden = truthy(login?.value);
      if (modeNote) modeNote.hidden = !(truthy(manager?.value) && mode?.value === "blacklist");
      if (readNote) readNote.hidden = !(truthy(manager?.value) && !truthy(readOnly?.value));
      if (trashNote) trashNote.hidden = !(truthy(manager?.value) && !truthy(trash?.value));
    };
    [login, manager, mode, readOnly, trash].forEach((control) => control?.addEventListener("change", update));
    update();
  }

  function snapshot() {
    const values = new Map();
    const data = new FormData(form);
    data.forEach((value, key) => {
      if (helperNames.has(key)) return;
      const normalized = value instanceof File ? value.name : String(value);
      const current = values.get(key);
      if (current == null) values.set(key, normalized);
      else values.set(key, `${current}\u001f${normalized}`);
    });
    return values;
  }

  let baseline = snapshot();

  function changedFields() {
    const current = snapshot();
    const keys = new Set([...baseline.keys(), ...current.keys()]);
    return Array.from(keys).filter((key) => (baseline.get(key) || "") !== (current.get(key) || ""));
  }

  function setupChangeSummary() {
    const install = () => {
      const bar = $(".lar-config-savebar");
      const host = bar?.firstElementChild;
      if (!bar || !host) return false;
      let summary = $(".lar-config-change-summary", host);
      if (!summary) {
        summary = document.createElement("div");
        summary.className = "lar-config-change-summary";
        host.appendChild(summary);
      }
      const update = () => {
        const changed = changedFields();
        if (!changed.length) {
          summary.hidden = true;
          summary.textContent = "";
          return;
        }
        const restartCount = changed.filter((name) => restartFields.has(name)).length;
        const names = changed.slice(0, 4).map((name) => fieldLabel(form.elements.namedItem(name))).join(" · ");
        const extra = changed.length > 4 ? ` 외 ${changed.length - 4}개` : "";
        summary.hidden = false;
        summary.textContent = `변경 ${changed.length}개${restartCount ? ` · 재시작 필요 ${restartCount}개` : ""} — ${names}${extra}`;
      };
      form.addEventListener("input", () => window.setTimeout(update, 0), true);
      form.addEventListener("change", () => window.setTimeout(update, 0), true);
      update();
      return true;
    };
    if (!install()) window.setTimeout(install, 80);
  }

  function fileRisk(values) {
    return truthy(values.get("fileManagerEnabled")) && (
      values.get("fileManagerMode") === "blacklist"
      || !truthy(values.get("fileManagerReadOnly"))
      || !truthy(values.get("trashEnabled"))
    );
  }

  function currentValues() {
    const values = new Map();
    ["loginMode", "fileManagerEnabled", "fileManagerMode", "fileManagerReadOnly", "trashEnabled"].forEach((name) => {
      const control = form.elements.namedItem(name);
      values.set(name, control && !(control instanceof RadioNodeList) ? control.value : "");
    });
    return values;
  }

  function dangerTransitions() {
    const next = currentValues();
    const currentLogin = truthy(baseline.get("loginMode"));
    const nextLogin = truthy(next.get("loginMode"));
    const loginOff = currentLogin && !nextLogin;

    const baseRiskValues = new Map([
      ["fileManagerEnabled", baseline.get("fileManagerEnabled") || "false"],
      ["fileManagerMode", baseline.get("fileManagerMode") || "whitelist"],
      ["fileManagerReadOnly", baseline.get("fileManagerReadOnly") || "true"],
      ["trashEnabled", baseline.get("trashEnabled") || "true"]
    ]);
    const riskyFieldsChanged = ["fileManagerEnabled", "fileManagerMode", "fileManagerReadOnly", "trashEnabled"]
      .some((name) => (baseRiskValues.get(name) || "") !== (next.get(name) || ""));
    const riskyFileManager = fileRisk(next) && (!fileRisk(baseRiskValues) || riskyFieldsChanged);
    return { loginOff, riskyFileManager };
  }

  function buildDangerDialog() {
    let dialog = document.getElementById("lar-config-danger-dialog");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.id = "lar-config-danger-dialog";
    dialog.className = "lar-config-danger-dialog";
    dialog.innerHTML = `
      <form method="dialog">
        <div class="lar-danger-dialog-head"><strong>위험 설정 확인</strong><button value="cancel" aria-label="닫기">×</button></div>
        <p data-danger-summary></p>
        <label data-danger-password-row>현재 비밀번호<input type="password" data-danger-password autocomplete="current-password"></label>
        <label>확인 문구 <code data-danger-phrase-label></code><input type="text" data-danger-phrase autocomplete="off"></label>
        <div class="lar-danger-dialog-actions"><button value="cancel">취소</button><button value="confirm" class="lar-danger-confirm">확인하고 적용</button></div>
      </form>`;
    document.body.appendChild(dialog);
    return dialog;
  }

  async function confirmDanger(transitions) {
    if (!transitions.loginOff && !transitions.riskyFileManager) return true;
    const expected = transitions.loginOff ? "로그인 해제" : "위험 설정 적용";
    const summary = [
      transitions.loginOff ? "로그인 보호를 해제합니다." : "",
      transitions.riskyFileManager ? "파일 관리자에서 넓은 경로 접근 또는 복구 불가능한 삭제를 허용합니다." : ""
    ].filter(Boolean).join(" ");

    const confirmation = ensureHidden("danger_confirmation", "");
    const password = ensureHidden("danger_current_password", "");
    const acknowledgement = ensureHidden("danger_ack", "");

    if (typeof HTMLDialogElement === "undefined") {
      const phrase = window.prompt(`${summary}\n확인 문구를 입력하세요: ${expected}`) || "";
      if (phrase !== expected) return false;
      const currentPassword = transitions.loginOff ? (window.prompt("현재 비밀번호를 입력하세요.") || "") : "";
      confirmation.value = phrase;
      password.value = currentPassword;
      acknowledgement.value = phrase;
      return !transitions.loginOff || Boolean(currentPassword);
    }

    const dialog = buildDangerDialog();
    $("[data-danger-summary]", dialog).textContent = summary;
    $("[data-danger-phrase-label]", dialog).textContent = expected;
    const passwordRow = $("[data-danger-password-row]", dialog);
    const passwordInput = $("[data-danger-password]", dialog);
    const phraseInput = $("[data-danger-phrase]", dialog);
    passwordRow.hidden = !transitions.loginOff;
    passwordInput.value = "";
    phraseInput.value = "";

    return new Promise((resolve) => {
      const onClose = () => {
        dialog.removeEventListener("close", onClose);
        const accepted = dialog.returnValue === "confirm"
          && phraseInput.value.trim() === expected
          && (!transitions.loginOff || Boolean(passwordInput.value));
        if (accepted) {
          confirmation.value = expected;
          password.value = passwordInput.value;
          acknowledgement.value = expected;
          dispatchChange(confirmation);
          dispatchChange(acknowledgement);
        }
        resolve(accepted);
      };
      dialog.addEventListener("close", onClose);
      dialog.showModal();
      phraseInput.focus();
    });
  }

  function validateAll() {
    $$("input, select, textarea", form).forEach((control) => {
      if (!control.disabled) control.dispatchEvent(new Event("input", { bubbles: true }));
    });
    if (!form.checkValidity()) {
      form.reportValidity();
      const invalid = $(":invalid", form);
      invalid?.focus();
      setStatus("저장할 수 없는 값이 있습니다", "error");
      return false;
    }
    return true;
  }

  function normalizedFormData() {
    const data = new FormData(form);
    if (!data.has("enableTray")) data.append("enableTray", "false");
    if (!data.has("timemachine_time_shift")) data.append("timemachine_time_shift", "0");
    [
      "autoPostProcessing", "deleteAfterPostProcessing", "removeFixedPrefix",
      "moveAfterProcessingEnabled", "postNewWindow", "stream_copy",
      "use_bitrate_mode", "splitRecordingMode", "fileManagerEnabled",
      "loginMode", "fileManagerReadOnly", "trashEnabled", "enableTray"
    ].forEach((name) => { if (!data.has(name)) data.append(name, "false"); });
    const mode = String(data.get("fileManagerMode") || "");
    if (!["blacklist", "whitelist"].includes(mode)) data.set("fileManagerMode", "whitelist");
    ["autoStopInterval", "splitOverlapSec"].forEach((name) => {
      if (String(data.get(name) || "") === "") data.delete(name);
    });
    [
      "moveAfterProcessing", "vbv_maxrate", "vbv_bufsize", "extra_ffmpeg_options",
      "telegram_enabled", "telegram_bot_token", "telegram_chat_id",
      "discord_enabled", "discord_webhook_url"
    ].forEach((name) => { if (!data.has(name)) data.append(name, ""); });
    return data;
  }

  let submitting = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (submitting) return;

    if (!validateAll()) return;
    const loginModeOn = document.getElementById("loginMode")?.value === "true";
    if (loginModeOn && form.dataset.hasAccount !== "1") {
      setStatus("로그인 모드를 켜려면 관리자 계정이 필요합니다", "error");
      window.location.href = "/register?need_account=1";
      return;
    }

    if (!await confirmDanger(dangerTransitions())) {
      setStatus("위험 설정 적용이 취소되었습니다", "error");
      return;
    }

    submitting = true;
    setStatus("설정을 저장하는 중", "saving");
    const saveButton = $("[data-config-save]", document);
    if (saveButton) saveButton.disabled = true;

    try {
      const payload = new URLSearchParams();
      normalizedFormData().forEach((value, key) => payload.append(key, String(value)));
      const response = await fetch(form.action || "/config", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "Accept": "application/json, text/html"
        },
        credentials: "same-origin",
        body: payload,
        redirect: "follow"
      });

      if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        const data = contentType.includes("application/json")
          ? await response.json()
          : { message: "설정 저장 중 오류가 발생했습니다." };
        throw new Error(data.message || data.detail || "설정 저장 중 오류가 발생했습니다.");
      }

      setStatus("설정이 저장되었습니다", "success");
      baseline = snapshot();
      form.reset();
      $$("input, select, textarea", form).forEach(dispatchChange);
      const destination = response.redirected && response.url ? response.url : "/";
      window.setTimeout(() => window.location.replace(destination), 80);
    } catch (error) {
      setStatus(error.message || "설정 저장에 실패했습니다", "error");
      if (saveButton) saveButton.disabled = false;
      submitting = false;
    }
  }, true);

  setupSecretField("telegram_bot_token", "봇 토큰");
  setupSecretField("telegram_chat_id", "채팅 ID");
  setupSecretField("discord_webhook_url", "웹훅 URL");
  setupNumericValidation();
  setupFilenameValidation();
  setupRootPathChecks();
  setupDangerWarnings();
  baseline = snapshot();
  setupChangeSummary();
})();
