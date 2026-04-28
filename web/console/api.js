/* AbuseRadar Console — API client + render helpers
 * Tüm console sayfaları bu modülü kullanır.
 */

(function () {
  // Base URL: aynı origin altında /api/ (nginx ile proxy ediliyor)
  // Lokal dev için: window.AR_API_BASE override
  const API_BASE = window.AR_API_BASE || "/api";

  /**
   * Generic fetch wrapper.
   * Hatada exception fırlatır, başarıda JSON döner.
   */
  async function api(method, path, body) {
    const url = API_BASE + path;
    const opts = {
      method,
      headers: { "Accept": "application/json" },
      credentials: "same-origin",
    };
    if (body !== undefined) {
      if (body instanceof FormData) {
        opts.body = body;
      } else {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
    }
    let resp;
    try {
      resp = await fetch(url, opts);
    } catch (e) {
      throw new Error(`Ağ hatası: ${e.message}`);
    }
    if (!resp.ok) {
      let detail = "";
      try {
        const j = await resp.json();
        detail = j.detail || JSON.stringify(j);
      } catch {
        detail = await resp.text();
      }
      throw new Error(`HTTP ${resp.status}: ${detail}`);
    }
    const ct = resp.headers.get("content-type") || "";
    if (ct.includes("application/json")) return await resp.json();
    return await resp.text();
  }

  // ─── Format helpers ─────────────────────────────────
  const fmt = {
    num(n) {
      if (n === null || n === undefined) return "—";
      return Number(n).toLocaleString("en-US");
    },
    bytes(b) {
      if (!b) return "—";
      if (b < 1024) return `${b} B`;
      if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
      if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
      return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`;
    },
    date(iso) {
      if (!iso) return "—";
      try {
        const d = new Date(iso);
        return d.toLocaleString("en-GB", {
          day: "2-digit", month: "short", year: "numeric",
          hour: "2-digit", minute: "2-digit",
        });
      } catch { return iso; }
    },
    relative(iso) {
      if (!iso) return "—";
      const d = new Date(iso);
      const sec = Math.floor((Date.now() - d.getTime()) / 1000);
      if (sec < 60) return `${sec}s ago`;
      if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
      if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
      return `${Math.floor(sec / 86400)}d ago`;
    },
    domain(url) {
      if (!url) return "";
      try {
        return new URL(url.startsWith("http") ? url : "https://" + url).hostname;
      } catch { return url; }
    },
    truncate(s, n) {
      if (!s) return "";
      return s.length > n ? s.slice(0, n - 1) + "…" : s;
    },
  };

  // ─── Render helpers ─────────────────────────────────
  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function badge(text, kind) {
    const safe = escapeHtml(text || "—");
    const cls = kind ? ` ${kind}` : "";
    return `<span class="badge${cls}">${safe}</span>`;
  }

  function statusBadge(status) {
    const s = (status || "").toLowerCase();
    const map = {
      "completed": "green", "delivered": "green", "resolved": "green",
      "sent": "green", "remediated": "green", "closed": "green", "ok": "green",
      "running": "orange", "pending": "muted", "submitted": "orange",
      "awaiting": "orange", "investigating": "teal", "acknowledged": "teal",
      "active": "red", "confirmed": "red", "escalated": "red", "bounced": "red",
      "verified": "gold", "notified": "orange", "reopened": "red",
    };
    return badge(status, map[s] || "muted");
  }

  function setKpi(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = fmt.num(value);
    el.dataset.target = String(value || 0);
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value === null || value === undefined ? "—" : value;
  }

  function setHtml(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  function showError(containerId, msg) {
    const el = document.getElementById(containerId);
    if (el) {
      el.innerHTML = `<div class="error-banner">⚠ ${escapeHtml(msg)}</div>`;
    } else {
      console.error("API error:", msg);
    }
  }

  function showLoading(id) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="loading-spinner">Yükleniyor…</div>';
  }

  function showEmpty(id, msg) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = `<div class="empty-state">${escapeHtml(msg || "Veri yok")}</div>`;
  }

  /** Animate KPI count-up (target değer kadar say) */
  function animateKpi(el, target, duration = 700) {
    if (!el || isNaN(target)) return;
    const start = performance.now();
    function tick(now) {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt.num(Math.floor(target * eased));
      if (p < 1) requestAnimationFrame(tick);
      else el.textContent = fmt.num(target);
    }
    requestAnimationFrame(tick);
  }

  /** Tüm `data-kpi="key"` elementlerini stats objesinden doldur */
  function fillKpis(stats) {
    document.querySelectorAll("[data-kpi]").forEach(el => {
      const key = el.dataset.kpi;
      if (key in stats) {
        const val = stats[key];
        el.dataset.target = String(val || 0);
        animateKpi(el, val);
      }
    });
  }

  // ─── Toast / notify ─────────────────────────────────
  function toast(msg, kind = "info") {
    let host = document.getElementById("ar-toast-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "ar-toast-host";
      document.body.appendChild(host);
    }
    const t = document.createElement("div");
    t.className = `ar-toast ar-toast-${kind}`;
    t.textContent = msg;
    host.appendChild(t);
    setTimeout(() => t.classList.add("show"), 10);
    setTimeout(() => {
      t.classList.remove("show");
      setTimeout(() => t.remove(), 250);
    }, kind === "error" ? 5000 : 3000);
  }

  // Expose globally
  window.AR = {
    api,
    get: (path) => api("GET", path),
    post: (path, body) => api("POST", path, body),
    put: (path, body) => api("PUT", path, body),
    del: (path) => api("DELETE", path),
    fmt,
    escapeHtml,
    badge,
    statusBadge,
    setKpi,
    setText,
    setHtml,
    showError,
    showLoading,
    showEmpty,
    animateKpi,
    fillKpis,
    toast,
  };
})();
