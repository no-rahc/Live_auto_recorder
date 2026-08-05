(function () {
  "use strict";

  const METRICS_PATH = "/api/sys_metrics";
  const METRICS_SOCKET_PATH = "/ws/sys_metrics";
  const CACHE_TTL_MS = 1750;
  const HIDDEN_CACHE_TTL_MS = 30000;
  const EMA_ALPHA = 0.28;

  const nativeFetch = window.fetch.bind(window);
  const NativeWebSocket = window.WebSocket;
  let inflight = null;
  let cachedPayload = null;
  let cachedAt = 0;
  let pollBusy = false;
  let managedSocket = null;
  let reconnectTimer = null;
  let latestSocketPayload = null;
  let shuttingDown = false;
  const smooth = Object.create(null);
  const diskNodes = new Map();

  function resolvePath(input) {
    try {
      const raw = typeof input === "string" ? input : input && input.url;
      return raw ? new URL(raw, location.href).pathname : "";
    } catch (_) {
      return "";
    }
  }

  function isMetricsRequest(input) {
    return resolvePath(input) === METRICS_PATH;
  }

  function isMetricsSocket(input) {
    return resolvePath(input) === METRICS_SOCKET_PATH;
  }

  function responseFrom(payload) {
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "content-type": "application/json; charset=utf-8" },
    });
  }

  async function fetchMetrics(input, init) {
    const now = Date.now();
    const ttl = document.hidden ? HIDDEN_CACHE_TTL_MS : CACHE_TTL_MS;
    if (cachedPayload && now - cachedAt < ttl) return responseFrom(cachedPayload);
    if (inflight) return responseFrom(await inflight);

    inflight = nativeFetch(input, init)
      .then(async function (response) {
        if (!response.ok) throw new Error("sys_metrics request failed: " + response.status);
        const payload = await response.clone().json();
        cachedPayload = payload;
        cachedAt = Date.now();
        window.dispatchEvent(new CustomEvent("lar:sys-metrics", { detail: payload }));
        return payload;
      })
      .finally(function () {
        inflight = null;
      });

    return responseFrom(await inflight);
  }

  window.fetch = function (input, init) {
    if (!isMetricsRequest(input)) return nativeFetch(input, init);
    return fetchMetrics(input, init);
  };

  function number(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function normalizeSocketPayload(payload) {
    return {
      cpu: {
        name: payload && payload.cpu_name,
        percent: number(payload && payload.cpu_percent),
      },
      memory: {
        percent: number(payload && payload.mem_percent),
        used: number(payload && payload.mem_used),
        total: number(payload && payload.mem_total),
      },
      network: {
        up_bps: number(payload && payload.net_up_bps),
        down_bps: number(payload && payload.net_down_bps),
        bytes_sent: number(payload && payload.net_bytes_sent),
        bytes_recv: number(payload && payload.net_bytes_recv),
      },
      disks: Array.isArray(payload && payload.disks) ? payload.disks : [],
    };
  }

  function renderPayload(payload) {
    latestSocketPayload = payload;
    cachedPayload = payload;
    cachedAt = Date.now();
    window.dispatchEvent(new CustomEvent("lar:sys-metrics", { detail: payload }));
    if (!document.getElementById("sys-dashboard")) return;
    requestAnimationFrame(function () {
      renderMain(payload);
      renderDisks(payload.disks || []);
    });
  }

  function scheduleSocketReconnect(url, protocols) {
    if (shuttingDown || reconnectTimer) return;
    reconnectTimer = window.setTimeout(function () {
      reconnectTimer = null;
      connectMetricsSocket(url, protocols);
    }, 3000);
  }

  function connectMetricsSocket(url, protocols) {
    if (!NativeWebSocket || shuttingDown) return;
    if (
      managedSocket &&
      (managedSocket.readyState === NativeWebSocket.CONNECTING ||
        managedSocket.readyState === NativeWebSocket.OPEN)
    ) {
      return;
    }

    try {
      managedSocket =
        protocols === undefined
          ? new NativeWebSocket(url)
          : new NativeWebSocket(url, protocols);
    } catch (_) {
      scheduleSocketReconnect(url, protocols);
      return;
    }

    managedSocket.onmessage = function (event) {
      try {
        renderPayload(normalizeSocketPayload(JSON.parse(event.data)));
      } catch (_) {}
    };
    managedSocket.onerror = function () {
      try {
        managedSocket.close();
      } catch (_) {}
    };
    managedSocket.onclose = function () {
      managedSocket = null;
      scheduleSocketReconnect(url, protocols);
    };
  }

  function createSocketFacade(url) {
    return {
      url: String(url),
      protocol: "",
      extensions: "",
      binaryType: "blob",
      bufferedAmount: 0,
      readyState: NativeWebSocket ? NativeWebSocket.CONNECTING : 0,
      onopen: null,
      onmessage: null,
      onerror: null,
      onclose: null,
      close: function () {},
      send: function () {
        throw new DOMException(
          "Metrics WebSocket is managed by the dashboard controller.",
          "InvalidStateError"
        );
      },
      addEventListener: function () {},
      removeEventListener: function () {},
      dispatchEvent: function () {
        return true;
      },
    };
  }

  if (NativeWebSocket) {
    function WebSocketProxy(url, protocols) {
      if (!isMetricsSocket(url)) {
        return protocols === undefined
          ? new NativeWebSocket(url)
          : new NativeWebSocket(url, protocols);
      }
      connectMetricsSocket(url, protocols);
      return createSocketFacade(url);
    }

    WebSocketProxy.prototype = NativeWebSocket.prototype;
    ["CONNECTING", "OPEN", "CLOSING", "CLOSED"].forEach(function (key) {
      WebSocketProxy[key] = NativeWebSocket[key];
    });
    window.WebSocket = WebSocketProxy;
  }

  function ema(key, next) {
    const value = number(next);
    const previous = smooth[key];
    const result = previous == null ? value : previous + EMA_ALPHA * (value - previous);
    smooth[key] = result;
    return result;
  }

  function clampPercent(value) {
    return Math.max(0, Math.min(100, number(value)));
  }

  function setText(id, value) {
    const element = document.getElementById(id);
    if (element && element.textContent !== String(value)) element.textContent = String(value);
  }

  function setBar(id, value) {
    const element = document.getElementById(id);
    if (!element) return;
    const next = clampPercent(value).toFixed(2) + "%";
    if (element.style.width !== next) element.style.width = next;
  }

  function fmtBytes(value) {
    if (typeof window._fmtBytes === "function") return window._fmtBytes(number(value));
    const units = ["B", "KB", "MB", "GB", "TB", "PB"];
    let n = number(value);
    let index = 0;
    while (n >= 1024 && index < units.length - 1) {
      n /= 1024;
      index += 1;
    }
    return n.toFixed(n >= 100 ? 0 : n >= 10 ? 1 : 2) + " " + units[index];
  }

  function fmtRate(value) {
    return (number(value) / (1024 * 1024)).toFixed(2) + " MB/s";
  }

  function renderMain(metrics) {
    const cpuRaw = number(metrics && metrics.cpu && metrics.cpu.percent);
    const memoryRaw = number(metrics && metrics.memory && metrics.memory.percent);
    const upRaw = number(metrics && metrics.network && metrics.network.up_bps);
    const downRaw = number(metrics && metrics.network && metrics.network.down_bps);

    const cpu = ema("cpu", cpuRaw);
    const memory = ema("memory", memoryRaw);
    const networkScore = ema(
      "network",
      Math.min(100, ((upRaw + downRaw) / (1024 * 1024)) * 10)
    );

    setText("cpu-name", (metrics && metrics.cpu && metrics.cpu.name) || "-");
    setText("cpu-percent", Math.round(cpuRaw));
    setBar("cpu-bar", cpu);

    setText("mem-percent", Math.round(memoryRaw));
    setText(
      "mem-brief",
      fmtBytes(metrics && metrics.memory && metrics.memory.used) +
        " / " +
        fmtBytes(metrics && metrics.memory && metrics.memory.total)
    );
    setBar("mem-bar", memory);

    setText("net-rate", "↑ " + fmtRate(upRaw) + " · ↓ " + fmtRate(downRaw));
    setText(
      "net-brief",
      "누적 ↑" + fmtBytes(metrics && metrics.network && metrics.network.bytes_sent) +
        " / ↓" + fmtBytes(metrics && metrics.network && metrics.network.bytes_recv)
    );
    setBar("net-bar", networkScore);
  }

  function diskKey(disk, index) {
    return String(
      (disk && (disk.mountpoint || disk.device || disk.label)) || "disk-" + index
    );
  }

  function normalizeDisks(disks) {
    const seen = new Set();
    return (Array.isArray(disks) ? disks : [])
      .filter(function (disk) {
        return disk && number(disk.total) > 0;
      })
      .filter(function (disk, index) {
        const key = diskKey(disk, index);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort(function (a, b) {
        return diskKey(a, 0).localeCompare(diskKey(b, 0), "ko");
      })
      .slice(0, 10);
  }

  function createDiskNode(key) {
    const host = document.createElement("div");
    host.className = "tile disk lar-metric-tile";
    host.dataset.larDiskKey = key;
    host.innerHTML =
      '<div class="tile-head">' +
      '<span class="tile-title"></span>' +
      '<span class="tile-sub"></span>' +
      "</div>" +
      '<div class="tile-value mono">0%</div>' +
      '<div class="progress"><div class="progress-bar" style="width:0%"></div></div>' +
      '<div class="tile-brief mono">- / -</div>';
    diskNodes.set(key, host);
    return host;
  }

  function updateDiskNode(node, disk) {
    const percent = clampPercent(disk && disk.percent);
    const title = node.querySelector(".tile-title");
    const sub = node.querySelector(".tile-sub");
    const value = node.querySelector(".tile-value");
    const brief = node.querySelector(".tile-brief");
    const bar = node.querySelector(".progress-bar");

    if (title) title.textContent = disk.label || disk.mountpoint || disk.device || "Disk";
    if (sub) {
      sub.textContent = disk.fstype
        ? String(disk.fstype).toUpperCase()
        : disk.mountpoint || "";
    }
    if (value) value.textContent = Math.round(percent) + "%";
    if (brief) brief.textContent = fmtBytes(disk.used) + " / " + fmtBytes(disk.total);
    if (bar) bar.style.width = percent.toFixed(2) + "%";
  }

  function renderDisks(disks) {
    const row1 = document.getElementById("disk-row-1");
    const row2 = document.getElementById("disk-row-2");
    if (!row1 || !row2) return;

    const normalized = normalizeDisks(disks);
    const activeKeys = new Set();

    normalized.forEach(function (disk, index) {
      const key = diskKey(disk, index);
      activeKeys.add(key);
      const node = diskNodes.get(key) || createDiskNode(key);
      updateDiskNode(node, disk);
      const target = index < 5 ? row1 : row2;
      const expected = target.children[index < 5 ? index : index - 5];
      if (expected !== node) target.insertBefore(node, expected || null);
    });

    diskNodes.forEach(function (node, key) {
      if (!activeKeys.has(key)) {
        node.remove();
        diskNodes.delete(key);
      }
    });

    row1.classList.toggle("lar-empty-row", row1.childElementCount === 0);
    row2.classList.toggle("lar-empty-row", row2.childElementCount === 0);
  }

  async function guardedPoll(originalPoll) {
    if (document.hidden || pollBusy) return;
    pollBusy = true;
    try {
      await originalPoll();
    } finally {
      pollBusy = false;
    }
  }

  function installStableRenderer() {
    if (
      typeof window._renderMainTiles !== "function" ||
      typeof window._renderDisks !== "function"
    ) {
      return false;
    }

    window._renderMainTiles = function (metrics) {
      requestAnimationFrame(function () {
        renderMain(metrics || {});
      });
    };
    window._renderDisks = function (disks) {
      requestAnimationFrame(function () {
        renderDisks(disks);
      });
    };

    if (typeof window._pollSys === "function") {
      const originalPoll = window._pollSys;
      window._pollSys = function () {
        return guardedPoll(originalPoll);
      };
    }
    return true;
  }

  function boot() {
    if (!document.getElementById("sys-dashboard")) return;
    if (!installStableRenderer()) return;

    document.querySelectorAll("#tile-cpu,#tile-mem,#tile-net").forEach(function (node) {
      node.classList.add("lar-metric-tile");
    });

    if (location.pathname === "/recording") {
      window.setupSysDashboard = function () {};
      if (latestSocketPayload) renderPayload(latestSocketPayload);
    } else if (typeof window.setupSysDashboard === "function") {
      window.setupSysDashboard();
    }
  }

  window.addEventListener("pagehide", function () {
    shuttingDown = true;
    if (reconnectTimer) window.clearTimeout(reconnectTimer);
    if (managedSocket) {
      try {
        managedSocket.close(1000, "page hidden");
      } catch (_) {}
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
