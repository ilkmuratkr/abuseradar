/* ────────────────────────────────────────────────────────────
   AbuseRadar — main.js
   • i18n (EN/TR/PT/ES/FR)
   • lang switcher persistence
   • Subtle scroll reveal
   ──────────────────────────────────────────────────────────── */

const SUPPORTED = ["en", "tr", "pt", "es", "fr"];
const DEFAULT_LANG = "en";
const LS_KEY = "abuseradar:lang";

function detectLang() {
  const saved = localStorage.getItem(LS_KEY);
  if (saved && SUPPORTED.includes(saved)) return saved;
  const url = new URL(location.href);
  const q = url.searchParams.get("lang");
  if (q && SUPPORTED.includes(q)) return q;
  const browser = (navigator.language || "en").slice(0, 2).toLowerCase();
  if (SUPPORTED.includes(browser)) return browser;
  return DEFAULT_LANG;
}

async function loadDict(lang) {
  try {
    const r = await fetch(`locales/${lang}.json`, { cache: "no-cache" });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) {
    if (lang !== DEFAULT_LANG) return loadDict(DEFAULT_LANG);
    return null;
  }
}

function getPath(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

function applyDict(dict) {
  if (!dict) return;
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const v = getPath(dict, el.dataset.i18n);
    if (v == null) return;
    if (Array.isArray(v)) {
      el.innerHTML = v.map(s => `<span>${s}</span>`).join("");
    } else if (typeof v === "object") {
      // skip; objects rendered by template
    } else {
      el.textContent = v;
    }
  });
  document.querySelectorAll("[data-i18n-html]").forEach(el => {
    const v = getPath(dict, el.dataset.i18nHtml);
    if (typeof v === "string") el.innerHTML = v;
  });
  // page lang attr
  document.documentElement.lang = dict.__lang || document.documentElement.lang;
}

function paintLangSwitch(lang) {
  document.querySelectorAll(".lang-menu button").forEach(b => {
    b.classList.toggle("active", b.dataset.lang === lang);
  });
  const cur = document.querySelector(".lang-current");
  if (cur) cur.textContent = lang.toUpperCase();
}

async function setLang(lang) {
  if (!SUPPORTED.includes(lang)) lang = DEFAULT_LANG;
  localStorage.setItem(LS_KEY, lang);
  document.documentElement.lang = lang;
  const dict = await loadDict(lang);
  if (dict) {
    dict.__lang = lang;
    applyDict(dict);
  }
  paintLangSwitch(lang);
}

document.addEventListener("DOMContentLoaded", () => {
  // Language dropdown
  const langWrap = document.querySelector(".lang-switch");
  const langTrig = document.querySelector(".lang-trigger");
  if (langWrap && langTrig) {
    langTrig.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = langWrap.classList.toggle("open");
      langTrig.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", (e) => {
      if (!langWrap.contains(e.target)) {
        langWrap.classList.remove("open");
        langTrig.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        langWrap.classList.remove("open");
        langTrig.setAttribute("aria-expanded", "false");
      }
    });
  }
  document.querySelectorAll(".lang-menu button").forEach(btn => {
    btn.addEventListener("click", () => {
      setLang(btn.dataset.lang);
      if (langWrap) {
        langWrap.classList.remove("open");
        langTrig && langTrig.setAttribute("aria-expanded", "false");
      }
    });
  });
  setLang(detectLang());

  // Soft scroll reveal
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add("in");
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll(".reveal").forEach(el => io.observe(el));

  // Live counter pulse: cycle the alert dot every n seconds
  const yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();
});
