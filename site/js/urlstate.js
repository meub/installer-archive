// Search/filter/sort state <-> query params, so every view is shareable
// and no CloudFront routing config is needed (SPEC §7.2).

const DEFAULTS = { q: "", cat: null, section: null, tags: [], year: null, sort: "newest" };

export function readState() {
  const p = new URLSearchParams(location.search);
  return {
    q: p.get("q") || "",
    cat: p.get("cat"),
    section: p.get("section"),
    tags: (p.get("tags") || "").split(",").filter(Boolean),
    year: p.get("year"),
    sort: p.get("sort") || "newest",
  };
}

export function writeState(s) {
  const p = new URLSearchParams();
  if (s.q.trim()) p.set("q", s.q.trim());
  if (s.cat) p.set("cat", s.cat);
  if (s.section) p.set("section", s.section);
  if (s.tags.length) p.set("tags", s.tags.join(","));
  if (s.year) p.set("year", s.year);
  if (s.sort !== DEFAULTS.sort) p.set("sort", s.sort);
  const qs = p.toString();
  history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
}

export function resetState(s) {
  Object.assign(s, structuredClone(DEFAULTS));
}
