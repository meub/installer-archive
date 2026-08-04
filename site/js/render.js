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

// Category icons — Lucide (ISC, lucide.dev), inlined so the page stays
// self-contained. Stroke inherits the badge's color via currentColor.
const ICON_SVG = {
  app: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M10 4v4"/><path d="M2 8h20"/><path d="M6 4v4"/>',
  game: '<line x1="6" x2="10" y1="11" y2="11"/><line x1="8" x2="8" y1="9" y2="13"/><line x1="15" x2="15.01" y1="12" y2="12"/><line x1="18" x2="18.01" y1="10" y2="10"/><path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z"/>',
  media: '<path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3Z"/><path d="m6.2 5.3 3.1 3.9"/><path d="m12.4 3.4 3.1 4"/><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  gadget: '<rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
  feature: '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/>',
  other: '<path d="M8.3 10a.7.7 0 0 1-.626-1.079L11.4 3a.7.7 0 0 1 1.198-.043L16.3 8.9a.7.7 0 0 1-.572 1.1Z"/><rect x="3" y="14" width="7" height="7" rx="1"/><circle cx="17.5" cy="17.5" r="3.5"/>',
};

export function categoryIcon(cat) {
  const span = el("span", "cat-ico");
  span.innerHTML =
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" ` +
    `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">` +
    `${ICON_SVG[cat] || ICON_SVG.other}</svg>`;
  return span;
}

function sep() { return el("span", "sep", "·"); }

function issueLink(issue, label) {
  const a = el("a", null, label);
  a.href = issue.url || "#";
  a.target = "_blank";
  a.rel = "noopener";
  a.title = issue.title;
  return a;
}

// One row inside an expanded group: the same item as it appeared in one issue.
function mentionRow(rec, issue, onDelete) {
  const li = el("li", "mention");
  const meta = el("div", "mention-meta");
  if (onDelete) {
    const del = el("button", "del-btn", "✕");
    del.type = "button";
    del.title = "Mark this mention for deletion";
    del.addEventListener("click", () => onDelete(rec));
    meta.append(del);
  }
  if (issue) meta.append(issueLink(issue, issue.number ? `No. ${issue.number}` : "Issue"), sep());
  meta.append(el("span", null, fmtDate(rec.date)));
  if (rec.section) meta.append(sep(), el("span", null, sectionLabel(rec.section)));
  if (rec.recommender) meta.append(sep(), el("span", null, `via ${rec.recommender}`));
  li.append(meta);
  if (rec.blurb) li.append(el("p", "mention-blurb", rec.blurb));
  return li;
}

function rowFor(group, issuesByDate, onTag, onDelete) {
  const members = group.members;
  const rec = group.primary || members[0]; // best-described mention fronts the card
  const li = el("li", "rec");
  const body = el("div", "rec-body");

  const head = el("div", "rec-head");
  if (onDelete) {
    const del = el("button", "del-btn", "✕");
    del.type = "button";
    del.title = `Mark ${rec.name} for deletion`;
    del.addEventListener("click", () => onDelete(rec));
    head.append(del);
  }
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
    const badge = el("span", `badge badge-${rec.category}`);
    badge.append(categoryIcon(rec.category), document.createTextNode(rec.category));
    head.append(badge);
  }
  let pill = null;
  if (members.length > 1) {
    pill = el("button", "dupe-pill", `${members.length}×`);
    pill.type = "button";
    pill.setAttribute("aria-expanded", "false");
    pill.title = `Recommended ${members.length} times — show every mention`;
    head.append(pill);
  }
  body.append(head);

  if (rec.blurb) body.append(el("p", "rec-blurb", rec.blurb));

  const meta = el("div", "rec-meta");
  for (const tag of rec.tags) {
    const b = el("button", "tag", tag);
    b.type = "button";
    b.addEventListener("click", () => onTag(tag));
    meta.append(b);
  }
  if (rec.tags.length) meta.append(sep());

  const issue = issuesByDate.get(rec.date);
  if (issue) {
    meta.append(issueLink(issue, issue.number ? `Installer No. ${issue.number}` : "Installer"), sep());
  }
  meta.append(el("span", null, fmtDate(rec.date)));
  if (rec.section) {
    meta.append(sep(), el("span", null, sectionLabel(rec.section)));
  }
  if (rec.recommender) {
    meta.append(sep(), el("span", null, `via ${rec.recommender}`));
  }
  body.append(meta);

  if (pill) {
    const mentions = el("ul", "mentions");
    mentions.hidden = true;
    for (const m of members) mentions.append(mentionRow(m, issuesByDate.get(m.date), onDelete));
    body.append(mentions);
    pill.addEventListener("click", () => {
      mentions.hidden = !mentions.hidden;
      pill.setAttribute("aria-expanded", String(!mentions.hidden));
    });
  }

  li.append(body);
  return li;
}

export function createRenderer(listEl, sentinelEl, issuesByDate, onTag, admin, onDelete) {
  let list = [];
  let shown = 0;

  function more() {
    const frag = document.createDocumentFragment();
    for (const group of list.slice(shown, shown + CHUNK)) {
      frag.append(rowFor(group, issuesByDate, onTag, admin?.enabled ? onDelete : null));
    }
    shown = Math.min(shown + CHUNK, list.length);
    listEl.append(frag);
  }

  // Load-more must not depend on IntersectionObserver or rAF alone: both are
  // gated on rendering frames, which Chrome suspends for occluded windows and
  // can skip under fast momentum scrolling — stalling the feed permanently.
  // maybeMore() is synchronous and idempotent; it fills until the sentinel is
  // safely below the viewport. Wired to observer + scroll + a slow interval
  // backstop so no stall state can survive.
  function maybeMore() {
    if (!list.length || shown >= list.length) return;
    while (shown < list.length &&
           sentinelEl.getBoundingClientRect().top < window.innerHeight + 600) {
      more();
    }
  }

  const observer = new IntersectionObserver(() => maybeMore(), { rootMargin: "600px" });
  observer.observe(sentinelEl);
  window.addEventListener("scroll", maybeMore, { passive: true });
  setInterval(maybeMore, 700);

  return {
    set(newList) {
      list = newList;
      shown = 0;
      listEl.textContent = "";
      more();
      maybeMore();
    },
    maybeMore,
    debug: () => ({ shown, listLen: list.length }),
  };
}
