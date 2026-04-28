/* AbuseRadar Console — theme toggle, sidebar inject, mobile, small enhancements */

(function(){
  const THEME_KEY = "abuseradar:console:theme";

  // Sidebar markup — injected into <aside class="rail" data-active="..."></aside>
  const RAIL_HTML = `
    <div class="rail-brand">
      <svg viewBox="0 0 64 64" fill="none">
        <circle cx="32" cy="32" r="28" stroke="#1ACEC9" stroke-width="2" fill="rgba(26,206,201,0.05)"/>
        <circle cx="32" cy="32" r="9"  stroke="#1ACEC9" stroke-opacity=".75" stroke-width="2" fill="none"/>
        <circle cx="32" cy="32" r="3"  fill="#EADA24"/>
        <line x1="32" y1="32" x2="54" y2="12" stroke="#1ACEC9" stroke-width="2"/>
      </svg>
      <span class="rail-brand-text">Abuse<em>Radar</em></span>
    </div>

    <div class="rail-section">Operate</div>
    <nav class="rail-nav">
      <a href="index.html" data-key="overview">
        <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
        Overview
      </a>
      <a href="csv.html" data-key="csv">
        <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        CSV ingest
      </a>
      <a href="pipeline.html" data-key="pipeline">
        <svg viewBox="0 0 24 24"><polygon points="6,4 20,12 6,20"/></svg>
        Pipeline
        <span class="badge" style="background:var(--green-soft);color:var(--green)">Live</span>
      </a>
      <a href="backlinks.html" data-key="backlinks">
        <svg viewBox="0 0 24 24"><line x1="10" y1="14" x2="21" y2="3"/><path d="M21 3v6h-6"/><path d="M3 21l9-9"/></svg>
        Backlinks
      </a>
      <a href="victims.html" data-key="victims">
        <svg viewBox="0 0 24 24"><path d="M12 2L4 6v6c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V6l-8-4z"/></svg>
        Compromised
      </a>
      <a href="attackers.html" data-key="attackers">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></svg>
        Attackers
      </a>
      <a href="c2.html" data-key="c2">
        <svg viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        C2 servers
      </a>
    </nav>

    <div class="rail-section">Action</div>
    <nav class="rail-nav">
      <a href="notifications.html" data-key="notifications">
        <svg viewBox="0 0 24 24"><path d="M3 6l9 7 9-7"/><rect x="3" y="5" width="18" height="14" rx="2"/></svg>
        Notifications
      </a>
      <a href="complaints.html" data-key="complaints">
        <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        Complaints
      </a>
      <a href="evidence.html" data-key="evidence">
        <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>
        Evidence
      </a>
    </nav>

    <div class="rail-section">System</div>
    <nav class="rail-nav">
      <a href="settings.html" data-key="settings">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        Settings
      </a>
    </nav>

    <div class="rail-foot">
      <button class="theme-toggle" data-toggle-theme aria-label="Toggle theme">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
        <span>Theme</span>
        <span class="switch" aria-hidden="true"></span>
      </button>
      <a href="../index.html" class="rail-user" title="Back to website">
        <span class="rail-user-avatar">AR</span>
        <span class="rail-user-info">
          <span class="rail-user-name">analyst@cert.tr</span>
          <span class="rail-user-role">Standing monitor</span>
        </span>
      </a>
    </div>
  `;

  function applyTheme(t){
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem(THEME_KEY, t);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", t === "light" ? "#FFFFFF" : "#001016");
  }
  function detectTheme(){
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  applyTheme(detectTheme());

  document.addEventListener("DOMContentLoaded", () => {
    // Inject sidebar (only into empty .rail elements)
    const rail = document.querySelector(".rail");
    if (rail && rail.dataset.active !== undefined && !rail.children.length){
      rail.innerHTML = RAIL_HTML;
      const active = rail.dataset.active;
      if (active){
        const link = rail.querySelector(`[data-key="${active}"]`);
        if (link) link.classList.add("active");
      }
    }

    // Theme toggle
    document.querySelectorAll("[data-toggle-theme]").forEach(btn => {
      btn.addEventListener("click", () => {
        const cur = document.documentElement.getAttribute("data-theme") || "dark";
        applyTheme(cur === "dark" ? "light" : "dark");
      });
    });

    // Mobile sidebar toggle
    const railToggle = document.querySelector("[data-toggle-rail]");
    if (railToggle && rail){
      railToggle.addEventListener("click", () => rail.classList.toggle("open"));
    }

    // Animate KPI numbers (legacy: data-target hardcoded sayfalar için)
    // Yeni sayfalar AR.fillKpis() ile dinamik dolduruyor — bu sadece fallback.
    document.querySelectorAll(".kpi-value[data-target]").forEach(el => {
      if (el.dataset.dynamic === "1") return; // dinamik dolan KPI'ları es geç
      const target = parseInt(el.dataset.target, 10);
      if (isNaN(target)) return;
      window.AR && window.AR.animateKpi
        ? window.AR.animateKpi(el, target)
        : (el.textContent = target.toLocaleString("en-US"));
    });

    // Animate chart bars (set width from data-pct)
    requestAnimationFrame(() => {
      document.querySelectorAll(".chart-bar-fill[data-pct]").forEach(el => {
        el.style.width = el.dataset.pct + "%";
      });
    });

    // Cmd/Ctrl-K focus search
    const search = document.querySelector(".search input");
    if (search){
      document.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k"){
          e.preventDefault();
          search.focus();
        }
      });
    }
  });
})();
