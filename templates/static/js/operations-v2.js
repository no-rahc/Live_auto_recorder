(function () {
  "use strict";

  const path = location.pathname.replace(/\/$/, "") || "/";
  const state = { summary: null, settings: null, health: [], jobs: [], backups: [], statistics: null, audit: [], cleanupPreview: null };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char];
    });
  }

  async function request(url, options) {
    const response = await fetch(url, options);
    const type = response.headers.get("content-type") || "";
    const body = type.includes("json") ? await response.json() : await response.text();
    if (!response.ok) throw new Error(body?.detail || body?.message || String(body) || `HTTP ${response.status}`);
    return body;
  }

  function notice(message, tone) {
    const node = document.getElementById("ops-notice");
    if (!node) return;
    node.hidden = false;
    node.dataset.tone = tone || "info";
    node.textContent = message;
    clearTimeout(notice.timer);
    notice.timer = setTimeout(function () { node.hidden = true; }, 5000);
  }

  function ensureOperationsLink() {
    const nav = document.getElementById("mySidenav");
    if (!nav || nav.querySelector('a[href="/operations"]')) return;
    const link = document.createElement("a");
    link.href = "/operations";
    link.className = "restricted-menu ops-nav-link";
    link.textContent = "운영 관리";
    const user = nav.querySelector("#user-info");
    nav.insertBefore(link, user || null);
  }

  function formatDuration(seconds) {
    const total = Math.max(0, Number(seconds) || 0);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    return `${h}시간 ${m}분`;
  }

  function statusLabel(status) {
    const labels = { ok: "정상", warning: "주의", critical: "위험", recording: "녹화 중", checking: "확인 중", waiting: "대기", stalled: "기록 멈춤", failed: "실패", reconnecting: "재연결", blocked: "차단", completed: "완료", running: "진행 중", queued: "대기", cancelled: "취소", cancelling: "취소 중" };
    return labels[status] || status || "-";
  }

  async function loadLightweightStatus() {
    try {
      const [summary, health] = await Promise.all([
        request("/api/operations/summary"),
        request("/api/operations/health")
      ]);
      showStorageBanner(summary.storage);
      applyHealthBadges(health.channels || []);
    } catch (_) {}
  }

  function showStorageBanner(storage) {
    if (!storage || storage.status === "ok" || !["/", "/recording"].includes(path)) return;
    let banner = document.querySelector(".ops-storage-banner");
    if (!banner) {
      banner = document.createElement("a");
      banner.href = "/operations";
      banner.className = "ops-storage-banner";
      const content = document.getElementById("content");
      content?.insertBefore(banner, content.firstChild);
    }
    banner.dataset.tone = storage.status;
    banner.textContent = `녹화 저장소 남은 공간 ${storage.free_text} (${storage.free_percent}%) · 운영 관리에서 확인`;
  }

  function applyHealthBadges(items) {
    items.forEach(function (item) {
      const card = document.querySelector(`.channel[data-channel-id="${CSS.escape(String(item.channel_id))}"]`);
      if (!card) return;
      let badge = card.querySelector(".ops-health-badge");
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "ops-health-badge";
        card.querySelector(".channel-name")?.appendChild(badge);
      }
      badge.dataset.state = item.state;
      badge.textContent = item.label || statusLabel(item.state);
      badge.title = [item.write_rate_text, item.last_error].filter(Boolean).join(" · ");
    });
  }

  function bindTabs() {
    document.querySelectorAll("[data-ops-tab]").forEach(function (button) {
      button.addEventListener("click", function () {
        document.querySelectorAll("[data-ops-tab]").forEach(function (node) { node.classList.toggle("is-active", node === button); });
        document.querySelectorAll("[data-ops-panel]").forEach(function (node) { node.classList.toggle("is-active", node.dataset.opsPanel === button.dataset.opsTab); });
      });
    });
  }

  function summaryCard(label, value, sub, tone) {
    return `<article class="ops-kpi" data-tone="${escapeHtml(tone || "")}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(sub || "")}</small></article>`;
  }

  function renderSummary() {
    const root = document.getElementById("ops-summary");
    if (!root || !state.summary) return;
    const storage = state.summary.storage || {};
    const health = state.summary.health_counts || {};
    const jobs = state.summary.jobs || {};
    root.innerHTML = [
      summaryCard("녹화 저장소", `${storage.free_percent ?? 0}% 남음`, `${storage.free_text || "-"} 사용 가능`, storage.status),
      summaryCard("현재 녹화", state.summary.active_recordings || 0, `확인 중 ${health.checking || 0}개`, "recording"),
      summaryCard("상태 이상", (health.stalled || 0) + (health.failed || 0) + (health.blocked || 0), `재연결 ${health.reconnecting || 0}개`, (health.stalled || health.failed || health.blocked) ? "critical" : "ok"),
      summaryCard("후처리", (jobs.running || 0) + (jobs.queued || 0), `실패 ${jobs.failed || 0}건`, jobs.failed ? "warning" : "ok"),
      summaryCard("백업", state.summary.backups || 0, "보관 중", "ok")
    ].join("");
  }

  function renderStorage() {
    const node = document.getElementById("ops-storage-detail");
    const storage = state.summary?.storage || {};
    const runway = state.runway || {};
    const runwayText = runway.hours_remaining == null ? "예측 데이터 부족" : `약 ${escapeHtml(runway.hours_remaining)}시간`;
    if (node) node.innerHTML = `<div class="ops-storage-card" data-tone="${escapeHtml(storage.status)}"><div><span>녹화 저장소</span><strong>${escapeHtml(storage.path || "-")}</strong></div><div class="ops-storage-number"><strong>${escapeHtml(storage.free_text || "-")}</strong><span>${escapeHtml(storage.free_percent ?? 0)}% 남음</span></div><div class="ops-progress"><i style="width:${Math.max(0, Math.min(100, Number(storage.used_percent) || 0))}%"></i></div><small>${escapeHtml(storage.used_text || "-")} / ${escapeHtml(storage.total_text || "-")} · ${escapeHtml(runway.bytes_per_hour_text || "0 B/h")} · ${runwayText}</small></div>`;
    const form = document.getElementById("ops-storage-form");
    const cfg = state.settings?.storage;
    if (form && cfg && !form.dataset.filled) {
      ["warning_free_percent", "block_free_percent", "cleanup_mode", "retention_days", "max_total_gb", "keep_recent_per_channel"].forEach(function (name) { if (form.elements[name]) form.elements[name].value = cfg[name] ?? ""; });
      form.elements.auto_cleanup.checked = Boolean(cfg.auto_cleanup);
      form.dataset.filled = "1";
    }
  }

  function renderHealth() {
    const root = document.getElementById("ops-health-list");
    if (!root) return;
    root.innerHTML = state.health.length ? state.health.map(function (item) {
      return `<article class="ops-health-card" data-state="${escapeHtml(item.state)}"><div class="ops-card-head"><div><strong>${escapeHtml(item.channel_name)}</strong><small>${escapeHtml(item.platform).toUpperCase()}</small></div><span class="ops-status">${escapeHtml(item.label || statusLabel(item.state))}</span></div><dl><div><dt>기록 속도</dt><dd>${escapeHtml(item.write_rate_text || "-")}</dd></div><div><dt>파일 크기</dt><dd>${escapeHtml(item.file_size_text || "-")}</dd></div><div><dt>마지막 기록</dt><dd>${escapeHtml(item.last_write_at || "-")}</dd></div><div><dt>재연결</dt><dd>${escapeHtml(item.restart_attempts || 0)}회</dd></div><div><dt>시작 지연</dt><dd>${escapeHtml(item.start_delay_seconds || 0)}초</dd></div><div><dt>녹화 도구</dt><dd>${escapeHtml(item.tool || "-")}</dd></div></dl>${item.last_error ? `<p class="ops-error">${escapeHtml(item.last_error)}</p>` : ""}<div class="ops-inline-buttons"><button type="button" class="ops-action-secondary" data-health-recover="${escapeHtml(item.channel_id)}">복구</button><button type="button" class="ops-action-secondary" data-health-trace="${escapeHtml(item.channel_id)}">실시간 로그</button></div><pre class="ops-trace" data-trace-output="${escapeHtml(item.channel_id)}" hidden></pre></article>`;
    }).join("") : '<div class="ops-empty">등록된 채널 상태가 없습니다.</div>';
    const form = document.getElementById("ops-health-form");
    const cfg = state.settings?.health;
    if (form && cfg && !form.dataset.filled) {
      ["stall_seconds", "max_restart_attempts", "restart_cooldown_seconds", "missed_recording_seconds", "circuit_breaker_after", "circuit_breaker_seconds"].forEach(function (name) { if (form.elements[name]) form.elements[name].value = cfg[name] ?? ""; });
      form.elements.auto_restart.checked = Boolean(cfg.auto_restart);
      form.dataset.filled = "1";
    }
  }

  function jobActions(job) {
    const retry = ["failed", "cancelled", "completed"].includes(job.status) ? `<button data-job-retry="${escapeHtml(job.id)}">재시도</button>` : "";
    const cancel = ["running", "queued"].includes(job.status) ? `<button class="ops-danger-text" data-job-cancel="${escapeHtml(job.id)}">취소</button>` : "";
    return retry + cancel || "-";
  }

  function renderJobs() {
    const body = document.getElementById("ops-jobs-body");
    if (!body) return;
    body.innerHTML = state.jobs.length ? state.jobs.map(function (job) {
      return `<tr><td><span class="ops-pill" data-state="${escapeHtml(job.status)}">${escapeHtml(statusLabel(job.status))}</span></td><td><div class="ops-job-progress"><i style="width:${Math.max(0, Math.min(100, Number(job.progress) || 0))}%"></i></div><small>${escapeHtml(job.progress || 0)}%</small></td><td>${escapeHtml(job.channel_name || job.channel_id)}</td><td class="ops-path" title="${escapeHtml(job.source)}">${escapeHtml(job.source || "-")}</td><td>${escapeHtml(job.started_at || job.created_at || "-")}</td><td>${escapeHtml(job.finished_at || "-")}</td><td>${jobActions(job)}</td></tr>`;
    }).join("") : '<tr><td colspan="7" class="ops-empty">후처리 작업 이력이 없습니다.</td></tr>';
  }

  function renderBackups() {
    const body = document.getElementById("ops-backups-body");
    if (!body) return;
    body.innerHTML = state.backups.length ? state.backups.map(function (item) {
      const name = encodeURIComponent(item.name);
      return `<tr><td class="ops-path">${escapeHtml(item.name)}</td><td>${escapeHtml(item.size_text)}</td><td>${escapeHtml(item.created_at)}</td><td><a class="ops-button-small" href="/api/operations/backups/${name}/download">다운로드</a><button class="ops-danger-text" data-backup-restore="${escapeHtml(item.name)}">복원</button></td></tr>`;
    }).join("") : '<tr><td colspan="4" class="ops-empty">생성된 백업이 없습니다.</td></tr>';
    const form = document.getElementById("ops-backup-form");
    const cfg = state.settings?.backup;
    if (form && cfg && !form.dataset.filled) {
      form.elements.interval_hours.value = cfg.interval_hours ?? 24;
      form.elements.keep.value = cfg.keep ?? 7;
      form.elements.scheduled.checked = Boolean(cfg.scheduled);
      form.dataset.filled = "1";
    }
  }

  function renderStatistics() {
    const stats = state.statistics;
    if (!stats) return;
    const cards = document.getElementById("ops-stat-cards");
    if (cards) cards.innerHTML = [summaryCard("전체 녹화", stats.total_recordings, "이력 기준"), summaryCard("실패", stats.total_failures, "녹화·후처리"), summaryCard("성공률", `${stats.success_rate}%`, "전체 기간"), summaryCard("누적 시간", formatDuration(stats.total_duration_seconds), "기록된 종료 이력")].join("");
    const chart = document.getElementById("ops-daily-chart");
    const max = Math.max(1, ...stats.daily.map(function (item) { return item.recordings; }));
    if (chart) chart.innerHTML = stats.daily.map(function (item) { const height = Math.max(4, item.recordings / max * 100); return `<div title="${escapeHtml(item.date)} · 녹화 ${item.recordings} · 실패 ${item.failures}"><span style="height:${height}%"></span><small>${escapeHtml(item.date.slice(5))}</small></div>`; }).join("");
    const body = document.getElementById("ops-channel-stats");
    if (body) body.innerHTML = stats.by_channel.length ? stats.by_channel.map(function (item) { return `<tr><td>${escapeHtml(item.channel)}</td><td>${item.recordings}</td><td>${item.failures}</td><td>${escapeHtml(formatDuration(item.duration_seconds))}</td><td>${escapeHtml(item.storage_text || "-")}</td></tr>`; }).join("") : '<tr><td colspan="5" class="ops-empty">통계 데이터가 없습니다.</td></tr>';
  }

  function renderAudit() {
    const body = document.getElementById("ops-audit-body");
    if (!body) return;
    body.innerHTML = state.audit.length ? state.audit.map(function (item) { return `<tr><td>${escapeHtml(item.ts)}</td><td>${escapeHtml(item.action)}</td><td><span class="ops-pill" data-state="${escapeHtml(item.result)}">${escapeHtml(item.result)}</span></td><td>${escapeHtml(item.detail || "-")}</td></tr>`; }).join("") : '<tr><td colspan="4" class="ops-empty">작업 기록이 없습니다.</td></tr>';
  }

  function renderCleanup(result) {
    const root = document.getElementById("ops-cleanup-result");
    if (!root || !result) return;
    const deleted = result.deleted?.length ? `<p>${result.deleted.length}개 파일을 삭제했습니다.</p>` : "";
    root.innerHTML = `<div class="ops-cleanup-box"><strong>삭제 대상 ${result.candidate_count}개 · ${escapeHtml(result.candidate_text)}</strong><span>보호된 파일 ${result.protected_count}개</span>${deleted}<ul>${(result.candidates || []).slice(0, 20).map(function (item) { return `<li><span>${escapeHtml(item.name)}</span><small>${escapeHtml(item.size_text)} · ${escapeHtml(item.modified_at)}</small></li>`; }).join("")}</ul></div>`;
  }

  async function loadAll() {
    const [summary, settings, health, jobs, backups, statistics, audit] = await Promise.all([
      request("/api/operations/summary"), request("/api/operations/settings"), request("/api/operations/health"), request("/api/operations/jobs"), request("/api/operations/backups"), request("/api/operations/statistics"), request("/api/operations/audit?limit=150")
    ]);
    Object.assign(state, { summary, settings, health: health.channels || [], runway: health.storage_runway || {}, jobs: jobs.jobs || [], backups: backups.backups || [], statistics, audit: audit.entries || [] });
    renderSummary(); renderStorage(); renderHealth(); renderJobs(); renderBackups(); renderStatistics(); renderAudit(); applyHealthBadges(state.health);
  }

  async function saveSection(section, data) {
    const next = JSON.parse(JSON.stringify(state.settings));
    next[section] = Object.assign({}, next[section], data);
    state.settings = await request("/api/operations/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(next) });
    notice("설정을 저장했습니다.", "success");
  }

  function commaList(value) { return String(value || "").split(",").map(function (item) { return item.trim(); }).filter(Boolean); }

  function bindForms() {
    document.getElementById("ops-storage-form")?.addEventListener("submit", async function (event) { event.preventDefault(); const f = event.currentTarget.elements; try { const retention = Object.assign({}, state.settings?.storage?.retention_days_by_channel || {}); if (f.retention_channel.value) { const days = Number(f.retention_channel_days.value || 0); if (days > 0) retention[f.retention_channel.value] = days; else delete retention[f.retention_channel.value]; } await saveSection("storage", { warning_free_percent: Number(f.warning_free_percent.value), block_free_percent: Number(f.block_free_percent.value), cleanup_mode: f.cleanup_mode.value, retention_days: Number(f.retention_days.value), max_total_gb: Number(f.max_total_gb.value), keep_recent_per_channel: Number(f.keep_recent_per_channel.value || 0), retention_days_by_channel: retention, auto_cleanup: f.auto_cleanup.checked }); await loadAll(); } catch (error) { notice(error.message, "error"); } });
    document.getElementById("ops-health-form")?.addEventListener("submit", async function (event) { event.preventDefault(); const f = event.currentTarget.elements; const payload = { stall_seconds: Number(f.stall_seconds.value), max_restart_attempts: Number(f.max_restart_attempts.value), restart_cooldown_seconds: Number(f.restart_cooldown_seconds.value), missed_recording_seconds: Number(f.missed_recording_seconds.value || 0), circuit_breaker_after: Number(f.circuit_breaker_after.value || 5), circuit_breaker_seconds: Number(f.circuit_breaker_seconds.value || 300), auto_restart: f.auto_restart.checked, enabled: true }; try { if (f.channel_id.value) { await request(`/api/operations/channels/${encodeURIComponent(f.channel_id.value)}/health-settings`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); notice("채널별 감시 설정을 저장했습니다.", "success"); } else { await saveSection("health", payload); } await loadAll(); } catch (error) { notice(error.message, "error"); } });
    document.querySelector('#ops-health-form [name="channel_id"]')?.addEventListener("change", async function (event) { const form = document.getElementById("ops-health-form"); const id = event.currentTarget.value; try { const cfg = id ? await request(`/api/operations/channels/${encodeURIComponent(id)}/health-settings`) : state.settings?.health; ["stall_seconds", "max_restart_attempts", "restart_cooldown_seconds", "missed_recording_seconds", "circuit_breaker_after", "circuit_breaker_seconds"].forEach(function (name) { if (form.elements[name]) form.elements[name].value = cfg?.[name] ?? ""; }); form.elements.auto_restart.checked = Boolean(cfg?.auto_restart); } catch (error) { notice(error.message, "error"); } });
    document.querySelector('#ops-storage-form [name="retention_channel"]')?.addEventListener("change", function (event) { const form = document.getElementById("ops-storage-form"); form.elements.retention_channel_days.value = state.settings?.storage?.retention_days_by_channel?.[event.currentTarget.value] || 0; });
    document.getElementById("ops-backup-form")?.addEventListener("submit", async function (event) { event.preventDefault(); const f = event.currentTarget.elements; try { await saveSection("backup", { interval_hours: Number(f.interval_hours.value), keep: Number(f.keep.value), scheduled: f.scheduled.checked }); await loadAll(); } catch (error) { notice(error.message, "error"); } });

    const ruleChannel = document.getElementById("ops-rule-channel");
    ruleChannel?.addEventListener("change", async function () {
      const form = document.getElementById("ops-rule-form");
      if (!ruleChannel.value || !form) return;
      try {
        const rule = await request(`/api/operations/rules/${encodeURIComponent(ruleChannel.value)}`);
        ["title_include", "title_exclude", "categories"].forEach(function (name) { form.elements[name].value = (rule[name] || []).join(", "); });
        ["time_start", "time_end", "start_delay_seconds", "max_duration_minutes", "minimum_duration_minutes", "quality_override"].forEach(function (name) { form.elements[name].value = rule[name] ?? ""; });
        form.elements.enabled.checked = rule.enabled !== false;
        form.querySelectorAll(".ops-days input").forEach(function (box) { box.checked = (rule.days || []).includes(Number(box.value)); });
      } catch (error) { notice(error.message, "error"); }
    });
    document.getElementById("ops-rule-form")?.addEventListener("submit", async function (event) {
      event.preventDefault(); const f = event.currentTarget; const channel = f.elements.channel_id.value; if (!channel) return notice("채널을 선택해 주세요.", "error");
      const payload = { enabled: f.elements.enabled.checked, title_include: commaList(f.elements.title_include.value), title_exclude: commaList(f.elements.title_exclude.value), categories: commaList(f.elements.categories.value), days: Array.from(f.querySelectorAll(".ops-days input:checked")).map(function (box) { return Number(box.value); }), time_start: f.elements.time_start.value, time_end: f.elements.time_end.value, start_delay_seconds: Number(f.elements.start_delay_seconds.value || 0), max_duration_minutes: Number(f.elements.max_duration_minutes.value || 0), minimum_duration_minutes: Number(f.elements.minimum_duration_minutes.value || 0), quality_override: f.elements.quality_override.value };
      try { await request(`/api/operations/rules/${encodeURIComponent(channel)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); notice("채널 규칙을 저장했습니다.", "success"); } catch (error) { notice(error.message, "error"); }
    });
  }

  function cleanupPayload(confirm) {
    const f = document.getElementById("ops-storage-form").elements;
    return { mode: f.cleanup_mode.value, retention_days: Number(f.retention_days.value), max_total_gb: Number(f.max_total_gb.value), warning_free_percent: Number(f.warning_free_percent.value), confirm: Boolean(confirm) };
  }

  function bindActions() {
    document.getElementById("ops-refresh")?.addEventListener("click", function () { loadAll().then(function () { notice("최신 상태로 갱신했습니다.", "success"); }).catch(function (error) { notice(error.message, "error"); }); });
    document.getElementById("ops-cleanup-preview")?.addEventListener("click", async function () { try { state.cleanupPreview = await request("/api/operations/cleanup/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cleanupPayload(false)) }); renderCleanup(state.cleanupPreview); } catch (error) { notice(error.message, "error"); } });
    document.getElementById("ops-cleanup-run")?.addEventListener("click", async function () { if (!state.cleanupPreview) return notice("먼저 삭제 대상을 미리 확인해 주세요.", "error"); if (!confirm(`${state.cleanupPreview.candidate_count}개 파일을 삭제할까요? 녹화 중 파일은 제외됩니다.`)) return; try { const result = await request("/api/operations/cleanup/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cleanupPayload(true)) }); state.cleanupPreview = result; renderCleanup(result); await loadAll(); notice("파일 정리를 완료했습니다.", "success"); } catch (error) { notice(error.message, "error"); } });
    document.getElementById("ops-backup-create")?.addEventListener("click", async function () { try { await request("/api/operations/backups", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ include_secrets: document.getElementById("ops-backup-secrets").checked }) }); await loadAll(); notice("백업을 생성했습니다.", "success"); } catch (error) { notice(error.message, "error"); } });
    document.addEventListener("click", async function (event) {
      const retry = event.target.closest("[data-job-retry]"); const cancel = event.target.closest("[data-job-cancel]"); const restore = event.target.closest("[data-backup-restore]"); const recover = event.target.closest("[data-health-recover]"); const trace = event.target.closest("[data-health-trace]");
      try {
        if (retry) { await request(`/api/operations/jobs/${retry.dataset.jobRetry}/retry`, { method: "POST" }); notice("후처리 재시도를 요청했습니다.", "success"); await loadAll(); }
        if (cancel && confirm("실행 중인 후처리 작업을 취소할까요?")) { await request(`/api/operations/jobs/${cancel.dataset.jobCancel}/cancel`, { method: "POST" }); notice("취소를 요청했습니다.", "success"); await loadAll(); }
        if (restore) { const name = restore.dataset.backupRestore; const typed = prompt(`복원하려면 백업 파일명을 입력하세요.\n${name}`); if (typed !== name) return; await request(`/api/operations/backups/${encodeURIComponent(name)}/restore`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: name }) }); notice("백업을 복원했습니다. 컨테이너 재시작을 권장합니다.", "success"); await loadAll(); }
        if (recover) { const id = recover.dataset.healthRecover; await request(`/api/operations/channels/${encodeURIComponent(id)}/recover`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "restart" }) }); notice("채널 복구를 요청했습니다.", "success"); await loadAll(); }
        if (trace) { const id = trace.dataset.healthTrace; const output = document.querySelector(`[data-trace-output="${id}"]`); const data = await request(`/api/operations/channels/${encodeURIComponent(id)}/trace`); if (output) { output.hidden = false; output.textContent = data.process_stderr_tail || "현재 수집된 stderr 로그가 없습니다."; } }
      } catch (error) { notice(error.message, "error"); }
    });
  }

  function initOperationsPage() {
    bindTabs(); bindForms(); bindActions();
    loadAll().catch(function (error) { notice(`운영 정보를 불러오지 못했습니다: ${error.message}`, "error"); });
    setInterval(function () { loadAll().catch(function () {}); }, 15000);
  }

  ensureOperationsLink();
  if (path === "/operations") initOperationsPage();
  else { loadLightweightStatus(); setInterval(loadLightweightStatus, 15000); }
})();
