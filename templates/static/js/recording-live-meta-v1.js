(function () {
  "use strict";

  if (!document.body.classList.contains("page-recording")) return;

  const ACTIVE_REFRESH_MS = 10000;
  const MIN_REQUEST_GAP_MS = 7000;
  const PLACEHOLDER_RETRY_MS = 4000;
  const placeholderTitles = new Set([
    "",
    "방송 준비 중",
    "방송 제목 없음",
    "불러오는 중...",
    "정보 없음",
  ]);
  const lastRequestedAt = new Map();
  const inFlight = new Map();
  const retryTimers = new Map();
  const placeholderRetryCount = new Map();

  function isRecordingCard(card) {
    const text = card.querySelector(".channel-name")?.textContent || "";
    return text.includes("녹화 중") || text.includes("예약녹화 중");
  }

  function metadataTitle(metadata) {
    return String(
      metadata?.live_title ||
      metadata?.liveTitle ||
      metadata?.video_title ||
      metadata?.title ||
      ""
    ).trim();
  }

  function metadataCategory(metadata) {
    return String(
      metadata?.category ||
      metadata?.liveCategoryValue ||
      metadata?.category_name ||
      metadata?.game_name ||
      ""
    ).trim();
  }

  function applyMetadata(card, metadata) {
    const channelId = card.dataset.channelId || "";
    const title = metadataTitle(metadata);
    const category = metadataCategory(metadata);
    const adult = Boolean(metadata?.adult);

    const titleNode = document.getElementById(`title-${channelId}`) || card.querySelector(".channel-title, .title");
    if (titleNode && title && !placeholderTitles.has(title)) {
      titleNode.textContent = adult ? `${title} (연령제한)` : title;
      titleNode.dataset.larLiveTitle = "current";
      placeholderRetryCount.delete(channelId);
    }

    const categoryNode = document.getElementById(`category-${channelId}`) || card.querySelector(".channel-category, .category");
    if (categoryNode && category && category !== "카테고리 없음") {
      categoryNode.innerHTML = `<strong>카테고리</strong>: ${category}`;
    }

    const thumbnail = metadata?.thumbnail_url || metadata?.thumbnailUrl || metadata?.thumbnail;
    const thumbnailNode = document.getElementById(`thumbnail-${channelId}`) || card.querySelector("img.channel-thumbnail, img.thumbnail, .thumb img");
    if (thumbnailNode && typeof thumbnail === "string" && /^https?:\/\//.test(thumbnail)) {
      thumbnailNode.src = thumbnail;
    }

    return title;
  }

  function schedulePlaceholderRetry(card) {
    const channelId = card.dataset.channelId || "";
    const retries = placeholderRetryCount.get(channelId) || 0;
    if (!channelId || retries >= 1 || retryTimers.has(channelId) || !isRecordingCard(card)) return;

    placeholderRetryCount.set(channelId, retries + 1);
    const timer = window.setTimeout(function () {
      retryTimers.delete(channelId);
      refreshCard(card, true);
    }, PLACEHOLDER_RETRY_MS);
    retryTimers.set(channelId, timer);
  }

  async function refreshCard(card, force) {
    const channelId = card.dataset.channelId || "";
    if (!channelId || !isRecordingCard(card)) return;

    const now = Date.now();
    if (!force && now - (lastRequestedAt.get(channelId) || 0) < MIN_REQUEST_GAP_MS) return;
    if (inFlight.has(channelId)) return inFlight.get(channelId);

    lastRequestedAt.set(channelId, now);
    const request = fetch(`/api/update_metadata/${encodeURIComponent(channelId)}`, {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) throw new Error(`metadata HTTP ${response.status}`);
        return response.json();
      })
      .then(function (payload) {
        const metadata = payload?.metadata || {};
        const title = applyMetadata(card, metadata);
        if (placeholderTitles.has(title) && isRecordingCard(card)) {
          schedulePlaceholderRetry(card);
        }
      })
      .catch(function (error) {
        console.warn(`[recording-meta] ${channelId} 갱신 실패`, error);
      })
      .finally(function () {
        inFlight.delete(channelId);
      });

    inFlight.set(channelId, request);
    return request;
  }

  function refreshRecordingCards(force) {
    if (document.visibilityState === "hidden") return;
    document.querySelectorAll(".channel[data-channel-id]").forEach(function (card) {
      if (isRecordingCard(card)) refreshCard(card, force);
    });
  }

  function watchRecordingTransitions() {
    const list = document.getElementById("channel-list");
    if (!list) return;

    const observer = new MutationObserver(function (mutations) {
      const cards = new Set();
      mutations.forEach(function (mutation) {
        const target = mutation.target instanceof Element
          ? mutation.target
          : mutation.target.parentElement;
        const statusNode = target?.closest?.(".channel-name");
        if (!statusNode) return;
        const card = statusNode.closest(".channel[data-channel-id]");
        if (card) cards.add(card);
      });
      cards.forEach(function (card) {
        if (isRecordingCard(card)) {
          placeholderRetryCount.delete(card.dataset.channelId || "");
          refreshCard(card, true);
        }
      });
    });

    observer.observe(list, {
      subtree: true,
      childList: true,
      characterData: true,
    });
  }

  function boot() {
    watchRecordingTransitions();
    refreshRecordingCards(true);
    window.setInterval(function () {
      refreshRecordingCards(false);
    }, ACTIVE_REFRESH_MS);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") refreshRecordingCards(true);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
