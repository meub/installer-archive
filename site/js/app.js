import MiniSearch from "../vendor/minisearch.js";
import { readState, writeState, resetState } from "./urlstate.js?v=8";
import { CATEGORY_LABELS, SECTION_LABELS, sectionLabel, createRenderer, fmtDate, fmtNum } from "./render.js?v=8";

const $ = (id) => document.getElementById(id);
const state = readState();

// ---------------------------------------------------------------- data load

let data;
try {
  data = await fetch("data/archive.json").then((r) => {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  });
} catch (err) {
  $("results").textContent = "";
  $("empty").hidden = false;
  $("empty").querySelector("p").textContent = `Couldn’t load the archive data (${err.message}).`;
  throw err;
}

const recs = data.recommendations;
const issuesByDate = new Map(data.issues.map((i) => [i.date, i]));

if (data.issues.length) $("updated").textContent = `Updated ${fmtDate(data.issues[0].date)}`;

// -------------------------------------------------------------- search index

const mini = new MiniSearch({
  fields: ["name", "blurb", "tagstr", "recommender"],
  storeFields: [],
  searchOptions: { boost: { name: 3, tagstr: 2 }, prefix: true, fuzzy: 0.15 },
});
mini.addAll(recs.map((r) => ({
  id: r.id, name: r.name, blurb: r.blurb, tagstr: r.tags.join(" "), recommender: r.recommender || "",
})));

// ------------------------------------------------------------------- filters

const tagCounts = new Map();
for (const r of recs) for (const t of r.tags) tagCounts.set(t, (tagCounts.get(t) || 0) + 1);
const topTags = [...tagCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 14).map(([t]) => t);
const years = [...new Set(recs.map((r) => r.date.slice(0, 4)))].sort().reverse();

function makeChip(label, isPressed, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "chip";
  b.textContent = label;
  b.setAttribute("aria-pressed", String(isPressed()));
  b.addEventListener("click", () => { onClick(); apply(); });
  b.refresh = () => b.setAttribute("aria-pressed", String(isPressed()));
  return b;
}

const chips = [];
function buildChips() {
  const cat = $("cat-chips");
  cat.append(makeChip("All", () => !state.cat, () => { state.cat = null; }));
  for (const [key, label] of Object.entries(CATEGORY_LABELS)) {
    cat.append(makeChip(label, () => state.cat === key,
      () => { state.cat = state.cat === key ? null : key; }));
  }

  // section chips come from the data: canonical order first, then any
  // recurring one-off segments (>= 20 recs); rare ones stay reachable via URL
  const sec = $("section-chips");
  const secCounts = new Map();
  for (const r of recs) secCounts.set(r.section, (secCounts.get(r.section) || 0) + 1);
  const shown = [
    ...Object.keys(SECTION_LABELS).filter((k) => secCounts.has(k)),
    ...[...secCounts.keys()].filter((k) => !SECTION_LABELS[k] && secCounts.get(k) >= 20).sort(),
  ];
  if (state.section && !shown.includes(state.section)) shown.push(state.section);
  for (const key of shown) {
    sec.append(makeChip(sectionLabel(key), () => state.section === key,
      () => { state.section = state.section === key ? null : key; }));
  }

  const yearRow = $("year-chips");
  for (const y of years) {
    yearRow.append(makeChip(y, () => state.year === y,
      () => { state.year = state.year === y ? null : y; }));
  }

  const tagRow = $("tag-chips");
  const shownTags = [...new Set([...topTags, ...state.tags])];
  for (const t of shownTags) {
    tagRow.append(makeChip(t, () => state.tags.includes(t), () => toggleTag(t, false)));
  }
  chips.push(...cat.children, ...sec.children, ...yearRow.children, ...tagRow.children);
}

function buildStatBadges() {
  const wrap = $("stat-badges");
  const statOf = (num, label) => {
    const s = document.createElement("span");
    s.className = "stat-badge";
    const b = document.createElement("b");
    b.textContent = fmtNum(num);
    s.append(b, document.createTextNode(label));
    return s;
  };
  wrap.append(statOf(data.rec_count, "recs"));

  const catCounts = new Map();
  for (const r of recs) if (r.category) catCounts.set(r.category, (catCounts.get(r.category) || 0) + 1);
  for (const key of Object.keys(CATEGORY_LABELS)) {
    const n = catCounts.get(key);
    if (!n || key === "other") continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `stat-badge stat-badge-cat badge-${key}`;
    const b = document.createElement("b");
    b.textContent = fmtNum(n);
    btn.append(b, document.createTextNode(CATEGORY_LABELS[key].toLowerCase()));
    btn.addEventListener("click", () => {
      state.cat = state.cat === key ? null : key;
      apply();
    });
    btn.refresh = () => btn.setAttribute("aria-pressed", String(state.cat === key));
    chips.push(btn);
    wrap.append(btn);
  }
}

function toggleTag(tag, doApply = true) {
  const i = state.tags.indexOf(tag);
  if (i >= 0) state.tags.splice(i, 1);
  else state.tags.push(tag);
  if (doApply) apply();
}

// ---------------------------------------------------------------- admin mode
// ?admin=1 reveals per-row delete buttons for data cleanup. Marks live in
// localStorage; "Download deletions.json" feeds `python -m scraper delete`.

const adminParam = new URLSearchParams(location.search).get("admin");
if (adminParam === "1") localStorage.setItem("installer-admin", "1");
if (adminParam === "0") localStorage.removeItem("installer-admin");
const admin = {
  enabled: localStorage.getItem("installer-admin") === "1",
  deleted: new Set(JSON.parse(localStorage.getItem("installer-deletions") || "[]")),
};

function saveDeletions() {
  localStorage.setItem("installer-deletions", JSON.stringify([...admin.deleted]));
  $("admin-count").textContent = `${admin.deleted.size} marked`;
}

function markDeleted(rec) {
  admin.deleted.add(rec.id);
  saveDeletions();
  apply();
}

function syncAdminUI() {
  $("admin-bar").hidden = !admin.enabled;
  document.body.classList.toggle("admin-on", admin.enabled);
  if (admin.enabled) saveDeletions();
}

$("admin-download").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({ ids: [...admin.deleted] }, null, 1)],
    { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "deletions.json";
  a.click();
  URL.revokeObjectURL(a.href);
});
$("admin-copy").addEventListener("click", () => {
  navigator.clipboard.writeText([...admin.deleted].join("\n"));
});
$("admin-undo").addEventListener("click", () => {
  admin.deleted.clear();
  saveDeletions();
  apply();
});
$("admin-exit").addEventListener("click", () => {
  localStorage.removeItem("installer-admin");
  admin.enabled = false;
  syncAdminUI();
  apply();
});

// --------------------------------------------------------------------- apply

const renderer = createRenderer($("results"), $("sentinel"), issuesByDate,
  (t) => toggleTag(t), admin, markDeleted);
window.__ia = renderer; // debug handle
let randOrder = null;

function currentList() {
  let list = recs;
  if (admin.deleted.size) list = list.filter((r) => !admin.deleted.has(r.id));
  if (state.cat) list = list.filter((r) => r.category === state.cat);
  if (state.section) list = list.filter((r) => r.section === state.section);
  if (state.year) list = list.filter((r) => r.date.startsWith(state.year));
  for (const t of state.tags) list = list.filter((r) => r.tags.includes(t));

  let rank = null;
  const q = state.q.trim();
  if (q) {
    rank = new Map(mini.search(q).map((res, i) => [res.id, i]));
    list = list.filter((r) => rank.has(r.id));
  }

  list = [...list];
  if (q && state.sort === "newest") {
    list.sort((a, b) => rank.get(a.id) - rank.get(b.id)); // relevance
  } else if (state.sort === "oldest") {
    list.sort((a, b) => a.date.localeCompare(b.date) || a.position - b.position);
  } else if (state.sort === "az") {
    list.sort((a, b) => a.name.localeCompare(b.name));
  } else if (state.sort === "random") {
    if (!randOrder) {
      randOrder = new Map(recs.map((r) => [r.id, Math.random()]));
    }
    list.sort((a, b) => randOrder.get(a.id) - randOrder.get(b.id));
  }
  // "newest" without a query keeps the artifact's (date desc, position) order
  return list;
}

function filtersActive() {
  return Boolean(state.q.trim() || state.cat || state.section || state.tags.length || state.year);
}

function apply() {
  const list = currentList();
  renderer.set(list);
  $("count").textContent = filtersActive()
    ? `${fmtNum(list.length)} of ${fmtNum(recs.length)}`
    : `${fmtNum(recs.length)} recommendations`;
  syncMoreFilters();
  $("empty").hidden = list.length > 0;
  $("clear-btn").hidden = !filtersActive();
  for (const c of chips) c.refresh?.();
  writeState(state);
}

// ------------------------------------------------- more-filters disclosure

const moreWrap = $("more-filters");
const moreBtn = $("more-filters-btn");

function hiddenFilterCount() {
  return (state.section ? 1 : 0) + (state.year ? 1 : 0) + state.tags.length;
}

function syncMoreFilters() {
  const n = hiddenFilterCount();
  const open = !moreWrap.hidden;
  moreBtn.textContent = `${open ? "Fewer filters" : "More filters"}${n ? ` (${n})` : ""} ${open ? "▴" : "▾"}`;
  moreBtn.setAttribute("aria-expanded", String(open));
}

moreBtn.addEventListener("click", () => {
  moreWrap.hidden = !moreWrap.hidden;
  syncMoreFilters();
});
if (hiddenFilterCount()) moreWrap.hidden = false; // don't hide active filters

// -------------------------------------------------------------------- wiring

buildChips();
buildStatBadges();
syncAdminUI();
syncMoreFilters();

const qInput = $("q");
qInput.value = state.q;
$("sort").value = state.sort;

let debounce;
qInput.addEventListener("input", () => {
  clearTimeout(debounce);
  debounce = setTimeout(() => { state.q = qInput.value; apply(); }, 80);
});
$("sort").addEventListener("change", () => {
  state.sort = $("sort").value;
  if (state.sort === "random") randOrder = null; // reshuffle each time it's picked
  apply();
});

function clearAll() {
  const sort = state.sort;
  resetState(state);
  state.sort = sort;
  qInput.value = "";
  apply();
}
$("clear-btn").addEventListener("click", clearAll);
$("empty-clear").addEventListener("click", clearAll);

$("about-btn").addEventListener("click", () => $("about").showModal());

document.addEventListener("keydown", (e) => {
  const inField = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
  if (e.key === "/" && !inField) {
    e.preventDefault();
    qInput.focus();
    qInput.select();
  } else if (e.key === "Escape" && document.activeElement === qInput) {
    if (qInput.value) { qInput.value = ""; state.q = ""; apply(); }
    else qInput.blur();
  } else if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !inField) {
    const links = [...document.querySelectorAll(".rec-name")];
    if (!links.length) return;
    const i = links.indexOf(document.activeElement);
    const next = links[Math.max(0, Math.min(links.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
    next?.focus();
    e.preventDefault();
  } else if (e.key === "ArrowDown" && document.activeElement === qInput) {
    document.querySelector(".rec-name")?.focus();
    e.preventDefault();
  }
});

apply();
