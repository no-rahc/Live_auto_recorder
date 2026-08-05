(function () {
  "use strict";

  if (!document.getElementById("sys-dashboard")) return;

  const SYSTEM_MOUNTS = [
    "/etc/hostname",
    "/etc/hosts",
    "/etc/resolv.conf",
    "/proc",
    "/sys",
    "/dev",
  ];

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function mountOf(disk) {
    return String((disk && (disk.mountpoint || disk.mount || disk.label || disk.device)) || "");
  }

  function isSystemMount(disk) {
    const mount = mountOf(disk);
    return SYSTEM_MOUNTS.some(function (prefix) {
      return mount === prefix || mount.indexOf(prefix + "/") === 0;
    });
  }

  function diskScore(disk) {
    const mount = mountOf(disk).toLowerCase();
    const type = String((disk && disk.fstype) || "").toLowerCase();
    let score = 0;

    if (mount === "/app/chzzk") score += 100000;
    else if (mount.indexOf("/app/chzzk/") === 0) score += 90000;
    else if (mount.indexOf("chzzk") >= 0 || mount.indexOf("record") >= 0) score += 80000;

    if (["cifs", "smb", "smbfs", "nfs", "nfs4"].indexOf(type) >= 0) score += 70000;
    if (mount === "/") score += 1000;

    return score + Math.min(number(disk && disk.total) / (1024 * 1024 * 1024), 50000);
  }

  function chooseRecordingDisk(disks) {
    return (Array.isArray(disks) ? disks : [])
      .filter(function (disk) {
        return disk && number(disk.total) > 0 && !isSystemMount(disk);
      })
      .sort(function (a, b) {
        return diskScore(b) - diskScore(a);
      })[0] || null;
  }

  function compactLabels(payload) {
    const cpuName = document.getElementById("cpu-name");
    if (cpuName) {
      const actualName =
        (payload && payload.cpu && payload.cpu.name) ||
        (payload && payload.cpu_name) ||
        cpuName.textContent;
      if (actualName && actualName !== "사용률") cpuName.title = actualName;
      cpuName.textContent = "사용률";
    }

    const networkBrief = document.getElementById("net-brief");
    if (networkBrief) networkBrief.textContent = "실시간 송수신";
  }

  function compactDisks(payload) {
    const row1 = document.getElementById("disk-row-1");
    const row2 = document.getElementById("disk-row-2");
    if (!row1 || !row2) return;

    if (location.pathname !== "/recording") {
      row1.hidden = true;
      row2.hidden = true;
      return;
    }

    const chosen = chooseRecordingDisk(payload && payload.disks);
    const chosenKey = chosen ? mountOf(chosen) : "";
    const nodes = Array.prototype.slice.call(
      document.querySelectorAll("#disk-row-1 .tile.disk, #disk-row-2 .tile.disk")
    );

    let primary = null;
    nodes.forEach(function (node) {
      const key = String(node.dataset.larDiskKey || "");
      const title = node.querySelector(".tile-title");
      const titleValue = title ? title.textContent.trim() : "";
      const selected = !!chosen && (key === chosenKey || titleValue === chosenKey);

      node.classList.toggle("lar-primary-storage", selected);
      node.hidden = !selected;
      if (selected) primary = node;
    });

    if (primary) {
      row1.insertBefore(primary, row1.firstChild);
      const title = primary.querySelector(".tile-title");
      const sub = primary.querySelector(".tile-sub");
      if (title) title.textContent = "녹화 저장소";
      if (sub) sub.textContent = chosenKey || "/app/chzzk";
      primary.setAttribute("aria-label", "녹화 저장소 사용량");
    }

    row1.hidden = !primary;
    row2.hidden = true;
  }

  function apply(payload) {
    compactLabels(payload || {});
    compactDisks(payload || {});
  }

  function applyAfterRenderer(payload) {
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        apply(payload);
      });
    });
  }

  window.addEventListener("lar:sys-metrics", function (event) {
    applyAfterRenderer(event.detail || {});
  });

  document.addEventListener("DOMContentLoaded", function () {
    window.setTimeout(function () {
      fetch("/api/sys_metrics", { cache: "no-store" })
        .then(function (response) {
          return response.ok ? response.json() : null;
        })
        .then(function (payload) {
          if (payload) applyAfterRenderer(payload);
        })
        .catch(function () {});
    }, 0);
  }, { once: true });
})();
