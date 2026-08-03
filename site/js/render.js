export const CATEGORY_LABELS = {
  app: "Apps", game: "Games", media: "Media",
  gadget: "Gadgets", feature: "Features", other: "Other",
};
export const SECTION_LABELS = {
  "the-drop": "The Drop", intro: "Intro", "pro-tips": "Pro Tips",
  "screen-share": "Screen Share", crowdsourced: "Crowdsourced",
  "group-project": "Group Project", "signing-off": "Signing Off",
  "davids-favorite-things": "David’s Favorite Things",
};

// Any section slug renders — one-off segments ("deep-dive") get auto-labels.
export const sectionLabel = (s) =>
  SECTION_LABELS[s] || (s ? s.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : null);

const CHUNK = 150;
const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
export const fmtDate = (iso) => dateFmt.format(new Date(`${iso}T12:00:00Z`));
export const fmtNum = (n) => n.toLocaleString("en-US");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function sep() { return el("span", "sep", "·"); }

function rowFor(rec, issue, onTag) {
  const li = el("li", "rec");

  const head = el("div", "rec-head");
  let name;
  if (rec.url) {
    name = el("a", "rec-name", rec.name);
    name.href = rec.url;
    name.target = "_blank";
    name.rel = "noopener";
  } else {
    name = el("span", "rec-name no-link", rec.name);
  }
  head.append(name);
  if (rec.category) {
    head.append(el("span", `badge badge-${rec.category}`, rec.category));
  }
  li.append(head);

  if (rec.blurb) li.append(el("p", "rec-blurb", rec.blurb));

  const meta = el("div", "rec-meta");
  for (const tag of rec.tags) {
    const b = el("button", "tag", tag);
    b.type = "button";
    b.addEventListener("click", () => onTag(tag));
    meta.append(b);
  }
  if (rec.tags.length) meta.append(sep());

  if (issue) {
    const a = el("a", null, issue.number ? `Installer No. ${issue.number}` : "Installer");
    a.href = issue.url || "#";
    a.target = "_blank";
    a.rel = "noopener";
    a.title = issue.title;
    meta.append(a, sep());
  }
  meta.append(el("span", null, fmtDate(rec.date)));
  if (rec.section) {
    meta.append(sep(), el("span", null, sectionLabel(rec.section)));
  }
  if (rec.recommender) {
    meta.append(sep(), el("span", null, `via ${rec.recommender}`));
  }
  li.append(meta);
  return li;
}

export function createRenderer(listEl, sentinelEl, issuesByDate, onTag) {
  let list = [];
  let shown = 0;

  function more() {
    const frag = document.createDocumentFragment();
    for (const rec of list.slice(shown, shown + CHUNK)) {
      frag.append(rowFor(rec, issuesByDate.get(rec.date), onTag));
    }
    shown = Math.min(shown + CHUNK, list.length);
    listEl.append(frag);
  }

  const observer = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting) && shown < list.length) more();
  }, { rootMargin: "600px" });
  observer.observe(sentinelEl);

  return {
    set(newList) {
      list = newList;
      shown = 0;
      listEl.textContent = "";
      more();
    },
  };
}
