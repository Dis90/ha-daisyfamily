(() => {
/* Daisy Family – bulletin board */
const BUL_VERSION = "1.0.1";

/* Languages: Finnish (fi) and English (en). All other Home Assistant languages use English. */
const I18N = {
  fi: {
    card_name: "Daisy Family – ilmoitustaulu", card_desc: "Ilmoitustaulun ilmoitukset listana. Klikkaamalla aukeaa koko ilmoitus liitteineen.",
    linkfail: "Linkin luonti epäonnistui: ", attachments: "Liitteet", empty: "Ei ilmoituksia.", open: "Avaa",
    published: "Julkaistu", valid: (d) => `, voimassa ${d} asti`,
    l_title: "Otsikko (valinnainen)", l_entity: "Ilmoitustaulun ilmoitukset -sensori", l_max: "Näytettävien ilmoitusten määrä",
  },
  en: {
    card_name: "Daisy Family – bulletin board", card_desc: "Bulletin board posts as a list. Click to open the full post with attachments.",
    linkfail: "Could not create the link: ", attachments: "Attachments", empty: "No bulletins.", open: "Open",
    published: "Published", valid: (d) => `, valid until ${d}`,
    l_title: "Title (optional)", l_entity: "Bulletin board posts sensor", l_max: "Number of posts to show",
  },
};
const langOf = (hass) =>
  String((hass && (hass.locale?.language || hass.language)) || "fi").toLowerCase().startsWith("fi") ? "fi" : "en";
const tr = (hass, key, ...args) => {
  const v = (I18N[langOf(hass)] || I18N.fi)[key];
  return typeof v === "function" ? v(...args) : v;
};
const BUL_TAG = "daisyfamily-bulletins-card";
const BUL_EDITOR_TAG = "daisyfamily-bulletins-card-editor";

const bEsc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function isBulletinsEntity(hass, id) {
  const st = hass.states[id];
  return !!st && id.startsWith("sensor.") && Array.isArray(st.attributes?.posts);
}
function findBulletinsEntity(hass) {
  return Object.keys(hass.states).find((id) => isBulletinsEntity(hass, id)) || null;
}
const dmy = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${Number(m[3])}.${Number(m[2])}.${m[1]}` : "";
};
const dm = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${Number(m[3])}.${Number(m[2])}.` : "";
};
function bFileIcon(mime, name) {
  const m = (mime || "").toLowerCase();
  const n = (name || "").toLowerCase();
  if (m.includes("pdf") || n.endsWith(".pdf")) return "mdi:file-pdf-box";
  if (m.startsWith("image/")) return "mdi:file-image-outline";
  if (m.includes("word") || /\.docx?$/.test(n)) return "mdi:file-word-outline";
  if (m.includes("sheet") || m.includes("excel") || /\.xlsx?$/.test(n)) return "mdi:file-excel-outline";
  return "mdi:file-outline";
}

class DaisyBulletinsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._sig = "";
    this._open = null;
  }

  static getConfigElement() {
    return document.createElement(BUL_EDITOR_TAG);
  }

  static getStubConfig(hass) {
    return { entity: findBulletinsEntity(hass) || "", max: 10 };
  }

  setConfig(config) {
    this._config = { max: 10, ...config };
    this._sig = "";
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    const id = this._config.entity || findBulletinsEntity(hass);
    const sig = (id ? hass.states[id]?.last_updated : "-") + JSON.stringify(this._config);
    if (sig !== this._sig) {
      this._sig = sig;
      this._render();
    }
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  connectedCallback() {
    this._onKey = (ev) => {
      if (ev.key === "Escape" && this._open !== null) this._close();
    };
    document.addEventListener("keydown", this._onKey);
  }

  disconnectedCallback() {
    document.removeEventListener("keydown", this._onKey);
  }


  _key(a) {
    return `${a.id}|${a.name}|${a.mime_type}`;
  }

  _href(a) {
    const hit = this._signed && this._signed[this._key(a)];
    return hit && Date.now() - hit.t < 50 * 60 * 1000 ? hit.url : null;
  }

  /* Signed links are fetched in advance so that Open is a plain link.
     This also works in the Home Assistant mobile app (no window is opened after an await). */
  _signLinks() {
    this._signed = this._signed || {};
    this.shadowRoot.querySelectorAll("a[data-att]").forEach(async (el) => {
      const a = { id: el.dataset.att, name: el.dataset.name, mime_type: el.dataset.mime };
      if (this._href(a)) return;
      try {
        const path = `/api/daisyfamily/attachment/${encodeURIComponent(a.id)}?name=${encodeURIComponent(a.name || "liite")}&mime=${encodeURIComponent(a.mime_type || "application/octet-stream")}`;
        const signed = await this._hass.callWS({ type: "auth/sign_path", path, expires: 3600 });
        const url = this._hass.hassUrl ? this._hass.hassUrl(signed.path) : signed.path;
        this._signed[this._key(a)] = { url, t: Date.now() };
        el.setAttribute("href", url);
      } catch (err) {
        el.setAttribute("title", tr(this._hass, "linkfail") + (err?.message || err));
      }
    });
  }

  _close() {
    this._open = null;
    this._render();
  }

  _render() {
    const hass = this._hass;
    const cfg = this._config;
    const id = cfg.entity || findBulletinsEntity(hass);
    const st = id ? hass.states[id] : null;
    const all = st && Array.isArray(st.attributes.posts) ? st.attributes.posts : [];
    const posts = all.slice(0, Math.max(1, Number(cfg.max) || 10));

    const list = posts
      .map((p, i) => {
        const files = (p.files || []).length;
        const snip = (p.content || "").replace(/\s+/g, " ");
        return `<div class="post" data-i="${i}"><div class="main"><div class="title">${bEsc(p.title)}</div><div class="snip">${bEsc(
          snip.slice(0, 110)
        )}${snip.length > 110 ? "…" : ""}</div>${p.recipient ? `<div class="rcp">${bEsc(p.recipient)}</div>` : ""}</div><div class="side"><div>${bEsc(dm(p.date))}</div>${
          files ? `<div class="clip"><ha-icon icon="mdi:paperclip"></ha-icon>${files}</div>` : ""
        }</div></div>`;
      })
      .join("");

    let popup = "";
    if (this._open !== null && posts[this._open]) {
      const p = posts[this._open];
      const files = (p.files || [])
        .map(
          (a) =>
            `<div class="file"><ha-icon icon="${bFileIcon(a.mime_type, a.name)}"></ha-icon><span class="fname">${bEsc(a.name)}</span><a class="open" target="_blank" rel="noopener" ${this._href(a) ? `href="${bEsc(this._href(a))}"` : ""} data-att="${bEsc(a.id)}" data-name="${bEsc(a.name)}" data-mime="${bEsc(a.mime_type)}"><ha-icon icon="mdi:open-in-new"></ha-icon>${tr(hass, "open")}</a></div>`
        )
        .join("");
      popup = `<div class="overlay" data-close="1"><div class="panel"><div class="phead"><div class="ptitle">${bEsc(p.title)}</div><button class="x" data-close="1"><ha-icon icon="mdi:close"></ha-icon></button></div><div class="meta">${
        p.recipient ? `<span class="chip"><ha-icon icon="mdi:account-group-outline"></ha-icon>${bEsc(p.recipient)}</span>` : ""
      }<span class="valid">${tr(hass, "published")} ${bEsc(dmy(p.date))}${p.valid_until ? bEsc(tr(hass, "valid", dmy(p.valid_until))) : ""}</span></div><div class="pbody"><div class="text">${bEsc(
        p.content
      )}</div>${
        files ? `<div class="attach"><div class="ahead"><ha-icon icon="mdi:email-open-multiple-outline"></ha-icon>${tr(hass, "attachments")}: ${(p.files || []).length}</div>${files}</div>` : ""
      }</div></div></div>`;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { padding:12px; }
        .htitle { font-size:1.2em; font-weight:500; padding:0 4px 10px; }
        .post { display:flex; gap:12px; justify-content:space-between; background:var(--secondary-background-color); border:1px solid var(--divider-color); border-radius:10px; padding:14px 16px; margin-bottom:10px; cursor:pointer; }
        .post:hover { filter:brightness(.97); }
        .main { min-width:0; }
        .title { font-size:1.1em; font-weight:600; }
        .snip { margin-top:8px; color:var(--secondary-text-color); line-height:1.5; overflow-wrap:anywhere; }
        .rcp { margin-top:8px; font-size:.85em; color:var(--secondary-text-color); }
        .side { text-align:right; white-space:nowrap; flex:none; }
        .clip { margin-top:6px; color:var(--secondary-text-color); }
        .clip ha-icon { --mdc-icon-size:20px; margin-right:4px; }
        .empty { padding:16px; text-align:center; opacity:.6; }
        .overlay { position:fixed; inset:0; background:rgba(0,0,0,.5); z-index:100; display:flex; align-items:center; justify-content:center; padding:16px; box-sizing:border-box; }
        .panel { background:var(--card-background-color); color:var(--primary-text-color); border-radius:14px; width:100%; max-width:760px; max-height:92vh; overflow:auto; }
        .phead { position:relative; padding:16px 56px 12px 20px; }
        .ptitle { font-size:1.3em; }
        .x { position:absolute; right:12px; top:12px; background:none; border:none; color:var(--secondary-text-color); cursor:pointer; padding:4px; --mdc-icon-size:28px; }
        .meta { display:flex; flex-wrap:wrap; align-items:center; gap:10px; padding:12px 20px; background:var(--secondary-background-color); }
        .chip { display:inline-flex; align-items:center; gap:6px; background:var(--primary-color, #03a9f4); color:var(--text-primary-color, #fff); border-radius:18px; padding:5px 14px 5px 8px; font-size:.95em; }
        .chip ha-icon { --mdc-icon-size:22px; }
        .valid { color:var(--secondary-text-color); font-size:.9em; }
        .pbody { padding:16px 20px 20px; }
        .text { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.55; }
        .attach { margin-top:18px; border-top:1px solid var(--divider-color); padding-top:10px; }
        .ahead { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
        .file { display:flex; align-items:center; gap:14px; padding:8px 4px; border-top:1px solid var(--divider-color); }
        .file ha-icon { --mdc-icon-size:34px; color:var(--secondary-text-color); }
        .fname { flex:1; overflow-wrap:anywhere; }
        .open { text-decoration:none; display:inline-flex; flex-direction:column; align-items:center; gap:2px; background:none; border:none; color:var(--primary-text-color); cursor:pointer; padding:4px 10px; font:inherit; }
        .open:not([href]) { opacity:.4; pointer-events:none; }
        .open ha-icon { --mdc-icon-size:26px; }
      </style>
      <ha-card>
        ${cfg.title ? `<div class="htitle">${bEsc(cfg.title)}</div>` : ""}
        ${list || '<div class="empty">${tr(hass, "empty")}</div>'}
      </ha-card>${popup}`;

    const root = this.shadowRoot;
    root.querySelectorAll("[data-i]").forEach((el) =>
      el.addEventListener("click", () => {
        this._open = Number(el.dataset.i);
        this._render();
      })
    );
    this._signLinks();
    root.querySelectorAll("[data-close]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        if (ev.target === el || el.classList.contains("x")) this._close();
      })
    );
  }
}

class DaisyBulletinsCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._draw();
  }

  set hass(hass) {
    this._hass = hass;
    this._draw();
  }

  _draw() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => tr(this._hass, "l_" + s.name) || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        this._config = { ...this._config, ...ev.detail.value };
        this.dispatchEvent(
          new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true })
        );
      });
      this.appendChild(this._form);
    }
    const ids = Object.keys(this._hass.states).filter((id) => isBulletinsEntity(this._hass, id));
    this._form.hass = this._hass;
    this._form.schema = [
      { name: "title", selector: { text: {} } },
      { name: "entity", selector: { entity: ids.length ? { include_entities: ids } : { domain: "sensor" } } },
      { name: "max", selector: { number: { min: 1, max: 100, mode: "box" } } },
    ];
    this._form.data = { max: 10, ...this._config };
  }
}

if (!customElements.get(BUL_TAG)) customElements.define(BUL_TAG, DaisyBulletinsCard);
if (!customElements.get(BUL_EDITOR_TAG)) customElements.define(BUL_EDITOR_TAG, DaisyBulletinsCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === BUL_TAG)) {
  /* The picker reads name and description when it opens, so getters can follow the Home Assistant language. */
  window.customCards.push({
    type: BUL_TAG,
    get name() {
      return tr(document.querySelector("home-assistant")?.hass, "card_name");
    },
    get description() {
      return tr(document.querySelector("home-assistant")?.hass, "card_desc");
    },
    preview: false,
  });
}
console.info(`%c DAISYFAMILY-BULLETINS-CARD %c ${BUL_VERSION} `, "background:#4fa9db;color:#fff", "");
})();
