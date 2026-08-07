(function () {
  "use strict";
  if (!document.body.classList.contains("page-operations")) return;

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>'"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const api = async (url, options) => {
    const response = await fetch(url, {headers:{"Accept":"application/json","Content-Type":"application/json", ...(options?.headers || {})}, ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.message || `HTTP ${response.status}`);
    return data;
  };
  const notice = (message, type) => {
    const host = $("#ops-notice");
    if (!host) return;
    host.hidden = false;
    host.textContent = message;
    host.classList.toggle("is-error", type === "error");
    window.clearTimeout(notice.timer);
    notice.timer = window.setTimeout(() => { host.hidden = true; }, 4500);
  };

  const tabs = $(".ops-tabs");
  const main = $(".ops-page");
  if (!tabs || !main || document.body.dataset.platformV3 === "1") return;
  document.body.dataset.platformV3 = "1";

  const tabDefs = [
    ["history", "녹화 기록"],
    ["notifications", "알림 센터"],
    ["archive", "외부 보관"],
    ["automation", "API·웹훅"]
  ];
  tabDefs.forEach(([id, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.id = `ops-tab-${id}`;
    button.dataset.opsTab = id;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", `ops-panel-${id}`);
    button.setAttribute("aria-selected", "false");
    button.tabIndex = -1;
    button.textContent = label;
    tabs.appendChild(button);
  });

  function panel(id, title, description, inner) {
    const section = document.createElement("section");
    section.id = `ops-panel-${id}`;
    section.className = "ops-panel";
    section.dataset.opsPanel = id;
    section.setAttribute("role", "tabpanel");
    section.setAttribute("aria-labelledby", `ops-tab-${id}`);
    section.setAttribute("aria-hidden", "true");
    section.tabIndex = 0;
    section.innerHTML = `<div class="ops-section-head"><div><h2>${title}</h2><p>${description}</p></div></div>${inner}`;
    main.appendChild(section);
    return section;
  }

  panel("history", "녹화 기록", "SQLite에 누적된 녹화 이력, 파일 검증, 복구와 외부 보관 상태를 확인합니다.", `
    <div class="ops-platform-toolbar">
      <label>검색<input id="ops-history-query" placeholder="채널·제목·파일·오류"></label>
      <label>상태<select id="ops-history-status"><option value="">전체</option><option value="recording">녹화 중</option><option value="completed">완료</option><option value="failed">실패</option></select></label>
      <button id="ops-history-refresh" type="button" class="ops-action-secondary">조회</button>
    </div>
    <div class="ops-table-wrap"><table><thead><tr><th>시작</th><th>채널</th><th>파일</th><th>녹화</th><th>검증</th><th>보관</th><th>작업</th></tr></thead><tbody id="ops-history-body"></tbody></table></div>
    <div id="ops-history-meta" class="ops-empty"></div>`);

  panel("notifications", "알림 센터", "이벤트별 알림을 선택하고 실패한 전송을 자동 재시도합니다.", `
    <form id="ops-notification-form" class="ops-platform-form">
      <label>알림 센터<select name="enabled"><option value="true">사용</option><option value="false">사용 안 함</option></select></label>
      <label>최대 재시도<input type="number" name="max_attempts" min="1" max="20"></label>
      <label>조용한 시간 시작<input type="time" name="quiet_start"></label>
      <label>조용한 시간 종료<input type="time" name="quiet_end"></label>
      <div id="ops-notification-events" class="ops-event-grid"></div>
      <div class="ops-platform-actions"><button class="ops-action-primary" type="submit">알림 설정 저장</button><button id="ops-notification-refresh" class="ops-action-secondary" type="button">전송 기록 새로고침</button></div>
    </form>
    <div class="ops-table-wrap"><table><thead><tr><th>이벤트</th><th>상태</th><th>시도</th><th>오류</th><th>작업</th></tr></thead><tbody id="ops-notification-body"></tbody></table></div>`);

  panel("archive", "외부 보관", "rclone remote로 녹화 파일을 복사하고 원격 크기 검증 후 선택적으로 로컬 파일을 삭제합니다.", `
    <div class="ops-platform-card" style="margin-bottom:14px"><h3>rclone 준비</h3><p>컨테이너의 <code>/app/json/rclone.conf</code>에 rclone 설정을 두세요. Google Drive, S3, WebDAV, OneDrive 등 rclone이 지원하는 원격 저장소를 사용할 수 있습니다.</p></div>
    <form id="ops-archive-form" class="ops-platform-form">
      <label>외부 보관<select name="enabled"><option value="true">사용</option><option value="false">사용 안 함</option></select></label>
      <label>rclone remote 경로<input name="remote" placeholder="예: gdrive:LiveAutoRecorder"></label>
      <label>검증 완료 후 자동 업로드<select name="auto_after_validation"><option value="true">사용</option><option value="false">사용 안 함</option></select></label>
      <label>원격 크기 확인<select name="verify_size"><option value="true">확인</option><option value="false">건너뜀</option></select></label>
      <label>업로드 후 로컬 삭제<select name="delete_after"><option value="false">보존</option><option value="true">삭제</option></select></label>
      <div class="ops-platform-actions"><button class="ops-action-primary" type="submit">보관 설정 저장</button><span class="ops-platform-status is-warn">로컬 삭제는 원격 검증 성공 후에만 실행됩니다</span></div>
    </form>`);

  panel("automation", "API 토큰·웹훅", "외부 자동화에는 비밀번호 대신 범위 제한 토큰을 사용하고 이벤트 웹훅을 연결합니다.", `
    <div class="ops-platform-grid">
      <div class="ops-platform-card">
        <h3>API 토큰</h3><p>토큰 원문은 생성 직후 한 번만 표시됩니다.</p>
        <form id="ops-token-form" class="ops-platform-form" style="margin-top:12px">
          <label>이름<input name="name" required placeholder="Home Assistant"></label>
          <label>만료 일수<input type="number" name="expires_days" min="0" max="3650" value="90"><small>0 = 만료 없음</small></label>
          <div class="is-wide ops-event-grid"><label><input type="checkbox" name="scope" value="read" checked> read</label><label><input type="checkbox" name="scope" value="control"> control</label><label><input type="checkbox" name="scope" value="admin"> admin</label></div>
          <div class="ops-platform-actions"><button class="ops-action-primary" type="submit">토큰 생성</button></div>
        </form>
        <div id="ops-token-once"></div>
        <div class="ops-table-wrap"><table><thead><tr><th>이름</th><th>범위</th><th>마지막 사용</th><th></th></tr></thead><tbody id="ops-token-body"></tbody></table></div>
      </div>
      <div class="ops-platform-card">
        <h3>이벤트 웹훅</h3><p>요청 본문은 JSON이며 secret이 있으면 <code>X-LAR-Signature-256</code> HMAC 서명을 보냅니다.</p>
        <div id="ops-webhook-list"></div>
        <button id="ops-webhook-add" class="ops-action-secondary" type="button" style="margin-top:10px">웹훅 추가</button>
        <div class="ops-platform-actions" style="margin-top:12px"><button id="ops-webhook-save" class="ops-action-primary" type="button">웹훅 저장</button></div>
      </div>
    </div>
    <div class="ops-platform-card" style="margin-top:14px"><h3>자동화 API</h3><p><code>GET /api/v3/automation/status</code> · <code>GET /api/v3/automation/recordings</code> · <code>POST /api/v3/automation/channels/{id}/start</code> · <code>/stop</code><br>헤더: <code>Authorization: Bearer lar_...</code></p></div>`);

  function activate(id) {
    $$('[data-ops-tab]', tabs).forEach((button) => {
      const active = button.dataset.opsTab === id;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
    $$('[data-ops-panel]', main).forEach((section) => {
      const active = section.dataset.opsPanel === id;
      section.classList.toggle("is-active", active);
      section.setAttribute("aria-hidden", active ? "false" : "true");
    });
    if (id === "history") loadHistory();
    if (id === "notifications") loadNotifications();
    if (id === "archive" || id === "automation") loadPlatformSettings();
    if (id === "automation") loadTokens();
  }
  tabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-ops-tab]");
    if (!button) return;
    activate(button.dataset.opsTab);
  }, true);

  const boolValue = (v) => String(v) === "true";
  const statusBadge = (value) => {
    const map = {ok:["정상","is-ok"], repaired:["복구 완료","is-ok"], invalid:["손상","is-error"], missing:["파일 없음","is-error"], completed:["완료","is-ok"], failed:["실패","is-error"], uploading:["업로드 중","is-warn"], recording:["녹화 중","is-warn"]};
    const item = map[value] || [value || "미검사", ""];
    return `<span class="ops-platform-status ${item[1]}">${esc(item[0])}</span>`;
  };

  async function loadHistory() {
    const body = $("#ops-history-body");
    if (!body) return;
    const q = encodeURIComponent($("#ops-history-query")?.value || "");
    const status = encodeURIComponent($("#ops-history-status")?.value || "");
    try {
      const data = await api(`/api/v3/recordings?limit=150&q=${q}&status=${status}`);
      body.innerHTML = data.items.length ? data.items.map((item) => `<tr>
        <td>${esc(item.started_at || "-")}</td>
        <td><strong>${esc(item.channel_name || item.channel_id || "-")}</strong><br><small>${esc(item.platform || "")}</small></td>
        <td class="ops-recording-title">${esc(item.title || item.filename || "-")}<span class="ops-recording-path" title="${esc(item.file_path || "")}">${esc(item.file_path || item.filename || "")}</span></td>
        <td>${statusBadge(item.status)}<br><small>${esc(item.duration || "")}</small></td>
        <td>${statusBadge(item.validation_status)}<br><small>${esc((item.validation_detail || "").slice(0,90))}</small></td>
        <td>${statusBadge(item.archive_status)}<br><small>${esc(item.archive_target || "")}</small></td>
        <td><div class="ops-inline-buttons"><button type="button" class="ops-action-secondary" data-verify="${item.id}">검증·복구</button><button type="button" class="ops-action-secondary" data-archive="${item.id}">외부 보관</button></div></td>
      </tr>`).join("") : '<tr><td colspan="7" class="ops-empty">녹화 기록이 없습니다.</td></tr>';
      $("#ops-history-meta").textContent = `총 ${data.total}건 · SQLite 기록은 JSONL 500건 제한과 별도로 유지됩니다.`;
    } catch (error) { body.innerHTML = `<tr><td colspan="7" class="ops-empty">${esc(error.message)}</td></tr>`; }
  }
  $("#ops-history-refresh")?.addEventListener("click", loadHistory);
  $("#ops-history-query")?.addEventListener("keydown", (e) => { if (e.key === "Enter") loadHistory(); });
  $("#ops-history-body")?.addEventListener("click", async (event) => {
    const verify = event.target.closest("[data-verify]");
    const archive = event.target.closest("[data-archive]");
    try {
      if (verify) { verify.disabled = true; notice("파일을 검사하고 있습니다."); await api(`/api/v3/recordings/${verify.dataset.verify}/verify`, {method:"POST", body:JSON.stringify({repair:true})}); notice("파일 검증을 완료했습니다."); await loadHistory(); }
      if (archive) { archive.disabled = true; await api(`/api/v3/recordings/${archive.dataset.archive}/archive`, {method:"POST", body:"{}"}); notice("외부 보관 대기열에 추가했습니다."); }
    } catch (error) { notice(error.message, "error"); if (verify) verify.disabled = false; if (archive) archive.disabled = false; }
  });

  let platformSettings = null;
  const eventLabels = {"recording.started":"녹화 시작","recording.completed":"녹화 완료","recording.failed":"녹화 실패","recording.validated":"파일 검증","postprocess.failed":"후처리 실패","storage.warning":"저장소 경고","archive.completed":"외부 보관 완료","archive.failed":"외부 보관 실패"};
  async function loadPlatformSettings() {
    try {
      platformSettings = await api("/api/v3/platform/settings");
      const nf = $("#ops-notification-form");
      const n = platformSettings.notifications || {};
      if (nf) {
        nf.elements.enabled.value = String(n.enabled !== false);
        nf.elements.max_attempts.value = n.max_attempts || 5;
        nf.elements.quiet_start.value = n.quiet_start || "";
        nf.elements.quiet_end.value = n.quiet_end || "";
        $("#ops-notification-events").innerHTML = Object.entries(eventLabels).map(([key,label]) => `<label><input type="checkbox" data-notify-event="${esc(key)}" ${n.events?.[key] ? "checked" : ""}> ${esc(label)}</label>`).join("");
      }
      const af = $("#ops-archive-form");
      const a = platformSettings.archive || {};
      if (af) {
        ["enabled","auto_after_validation","verify_size","delete_after"].forEach((name) => af.elements[name].value = String(Boolean(a[name])));
        af.elements.remote.value = a.remote || "";
      }
      renderWebhooks(platformSettings.webhooks || []);
    } catch (error) { notice(error.message, "error"); }
  }
  async function savePlatform(partial) {
    const data = await api("/api/v3/platform/settings", {method:"PUT", body:JSON.stringify(partial)});
    platformSettings = data;
    notice("설정을 저장했습니다.");
    return data;
  }
  $("#ops-notification-form")?.addEventListener("submit", async (event) => {
    event.preventDefault(); const f = event.currentTarget;
    const events = {}; $$('[data-notify-event]', f).forEach((input) => events[input.dataset.notifyEvent] = input.checked);
    try { await savePlatform({notifications:{enabled:boolValue(f.elements.enabled.value),max_attempts:Number(f.elements.max_attempts.value || 5),quiet_start:f.elements.quiet_start.value,quiet_end:f.elements.quiet_end.value,events}}); } catch (error) { notice(error.message,"error"); }
  });
  $("#ops-archive-form")?.addEventListener("submit", async (event) => {
    event.preventDefault(); const f = event.currentTarget;
    try { await savePlatform({archive:{enabled:boolValue(f.elements.enabled.value),remote:f.elements.remote.value.trim(),auto_after_validation:boolValue(f.elements.auto_after_validation.value),verify_size:boolValue(f.elements.verify_size.value),delete_after:boolValue(f.elements.delete_after.value)}}); } catch (error) { notice(error.message,"error"); }
  });

  async function loadNotifications() {
    await loadPlatformSettings();
    const body = $("#ops-notification-body"); if (!body) return;
    try {
      const data = await api("/api/v3/notifications?limit=100");
      body.innerHTML = data.items.length ? data.items.map((item) => `<tr><td>${esc(eventLabels[item.event_type] || item.event_type)}</td><td>${statusBadge(item.status)}</td><td>${item.attempts}</td><td><small>${esc(item.last_error || "-")}</small></td><td>${item.status === "failed" ? `<button type="button" class="ops-action-secondary" data-notify-retry="${item.id}">재시도</button>` : ""}</td></tr>`).join("") : '<tr><td colspan="5" class="ops-empty">전송 기록이 없습니다.</td></tr>';
    } catch (error) { body.innerHTML = `<tr><td colspan="5">${esc(error.message)}</td></tr>`; }
  }
  $("#ops-notification-refresh")?.addEventListener("click", loadNotifications);
  $("#ops-notification-body")?.addEventListener("click", async (event) => { const button = event.target.closest("[data-notify-retry]"); if (!button) return; try { await api(`/api/v3/notifications/${button.dataset.notifyRetry}/retry`, {method:"POST",body:"{}"}); await loadNotifications(); } catch(error){notice(error.message,"error");} });

  async function loadTokens() {
    const body = $("#ops-token-body"); if (!body) return;
    try {
      const data = await api("/api/v3/tokens");
      body.innerHTML = data.items.length ? data.items.map((item) => `<tr><td>${esc(item.name)}<br><small>${esc(item.token_prefix)}…</small></td><td>${esc(item.scopes)}</td><td>${item.last_used_epoch ? new Date(item.last_used_epoch*1000).toLocaleString() : "사용 전"}</td><td>${item.revoked ? "폐기됨" : `<button type="button" class="ops-action-danger" data-token-revoke="${item.id}">폐기</button>`}</td></tr>`).join("") : '<tr><td colspan="4" class="ops-empty">API 토큰이 없습니다.</td></tr>';
    } catch (error) { body.innerHTML = `<tr><td colspan="4">${esc(error.message)}</td></tr>`; }
  }
  $("#ops-token-form")?.addEventListener("submit", async (event) => {
    event.preventDefault(); const f = event.currentTarget; const scopes = $$('input[name="scope"]:checked', f).map((x) => x.value);
    try {
      const data = await api("/api/v3/tokens", {method:"POST", body:JSON.stringify({name:f.elements.name.value,expires_days:Number(f.elements.expires_days.value || 0),scopes})});
      $("#ops-token-once").innerHTML = `<div class="ops-token-once"><strong>지금 복사하세요. 다시 표시되지 않습니다.</strong><code>${esc(data.token)}</code></div>`;
      f.reset(); f.elements.expires_days.value = 90; $('input[value="read"]', f).checked = true; await loadTokens();
    } catch (error) { notice(error.message,"error"); }
  });
  $("#ops-token-body")?.addEventListener("click", async (event) => { const button = event.target.closest("[data-token-revoke]"); if (!button || !confirm("이 API 토큰을 폐기할까요?")) return; try { await api(`/api/v3/tokens/${button.dataset.tokenRevoke}`, {method:"DELETE"}); await loadTokens(); } catch(error){notice(error.message,"error");} });

  function renderWebhooks(items) {
    const host = $("#ops-webhook-list"); if (!host) return;
    host.innerHTML = "";
    (items || []).forEach((item) => addWebhook(item));
  }
  function addWebhook(item) {
    const host = $("#ops-webhook-list"); if (!host) return;
    const row = document.createElement("div"); row.className = "ops-webhook-row";
    row.innerHTML = `<input data-webhook-url placeholder="https://example.com/webhook" value="${esc(item?.url || "")}"><input data-webhook-events placeholder="recording.completed,archive.completed 또는 *" value="${esc((item?.events || ["*"]).join(","))}"><input data-webhook-secret type="password" placeholder="서명 secret (선택)" value="${item?.secret === "••••••••" ? "••••••••" : esc(item?.secret || "")}"><button type="button" class="ops-action-danger" data-webhook-remove>삭제</button>`;
    row.querySelector("[data-webhook-remove]").addEventListener("click", () => row.remove()); host.appendChild(row);
  }
  $("#ops-webhook-add")?.addEventListener("click", () => addWebhook({events:["*"]}));
  $("#ops-webhook-save")?.addEventListener("click", async () => {
    const webhooks = $$(".ops-webhook-row", $("#ops-webhook-list")).map((row) => ({url:$("[data-webhook-url]",row).value.trim(),events:$("[data-webhook-events]",row).value.split(",").map((x)=>x.trim()).filter(Boolean),secret:$("[data-webhook-secret]",row).value,enabled:true})).filter((x)=>x.url);
    try { await savePlatform({webhooks}); } catch(error){notice(error.message,"error");}
  });

  loadPlatformSettings();
})();
