(() => {
/* Daisy Family – messages */
const MSG_CARD_VERSION = "1.0.0";

/* Languages: Finnish (fi) and English (en). All other Home Assistant languages use English. */
const I18N = {
  fi: {
    card_name: "Daisy Family – viestit", card_desc: "Daisyn viestiketjut listana. Klikkaamalla aukeaa koko viesti.",
    linkfail: "Linkin luonti epäonnistui: ", me: "Minä", unavail: "Koko viesti ei ole saatavilla: Daisyn rajapinta antaa koko tekstin vain uusimmille viesteille.",
    attachments: "Liitteet", empty: "Ei viestejä.", count: "LKM", open: "Avaa",
    l_title: "Otsikko (valinnainen)", l_entity: "Kaikki viestit -sensori", l_max: "Näytettävien viestien määrä",
    l_mark_read: "Merkitse viesti luetuksi Daisyssa, kun se avataan",
  },
  en: {
    card_name: "Daisy Family – messages", card_desc: "Daisy message threads as a list. Click to open the full message.",
    linkfail: "Could not create the link: ", me: "Me", unavail: "The full message is not available: the Daisy API only provides the full text for the newest messages.",
    attachments: "Attachments", empty: "No messages.", count: "Msgs", open: "Open",
    l_title: "Title (optional)", l_entity: "All messages sensor", l_max: "Number of messages to show",
    l_mark_read: "Mark the message as read in Daisy when it is opened",
  },
};
const langOf = (hass) =>
  String((hass && (hass.locale?.language || hass.language)) || "fi").toLowerCase().startsWith("fi") ? "fi" : "en";
const tr = (hass, key, ...args) => {
  const v = (I18N[langOf(hass)] || I18N.fi)[key];
  return typeof v === "function" ? v(...args) : v;
};
const MSG_TAG = "daisyfamily-messages-card";
const MSG_EDITOR_TAG = "daisyfamily-messages-card-editor";

const mEsc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function isMessagesEntity(hass, id) {
  const st = hass.states[id];
  return !!st && id.startsWith("sensor.") && Array.isArray(st.attributes?.messages);
}

function findMessagesEntity(hass) {
  return Object.keys(hass.states).find((id) => isMessagesEntity(hass, id)) || null;
}

/* "2026-10-05T15:02:12" -> "15:02, 05.10." */
function fmtTime(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso || "");
  return m ? `${m[4]}:${m[5]}, ${m[3]}.${m[2]}.` : "";
}
function fmtFull(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso || "");
  return m ? `${Number(m[3])}.${Number(m[2])}.${m[1]} ${m[4]}:${m[5]}` : "";
}

function fileIcon(mime, name) {
  const m = (mime || "").toLowerCase();
  const n = (name || "").toLowerCase();
  if (m.includes("pdf") || n.endsWith(".pdf")) return "mdi:file-pdf-box";
  if (m.startsWith("image/")) return "mdi:file-image-outline";
  if (m.includes("word") || /\.docx?$/.test(n)) return "mdi:file-word-outline";
  if (m.includes("sheet") || m.includes("excel") || /\.xlsx?$/.test(n)) return "mdi:file-excel-outline";
  return "mdi:file-outline";
}

class DaisyMessagesCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._sig = "";
    this._open = null;
    this._marked = new Set();
  }

  static getConfigElement() {
    return document.createElement(MSG_EDITOR_TAG);
  }

  static getStubConfig(hass) {
    return { entity: findMessagesEntity(hass) || "", max: 10 };
  }

  setConfig(config) {
    this._config = { max: 10, mark_read: true, ...config };
    this._sig = "";
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    const id = this._config.entity || findMessagesEntity(hass);
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
    const id = cfg.entity || findMessagesEntity(hass);
    const st = id ? hass.states[id] : null;
    const all = st && Array.isArray(st.attributes.messages) ? st.attributes.messages : [];
    const msgs = all.slice(0, Math.max(1, Number(cfg.max) || 10));

    const list = msgs
      .map((m, i) => {
        const clip = m.attachments
          ? `<div class="clip"><ha-icon icon="mdi:paperclip"></ha-icon>${mEsc(m.attachments)}</div>`
          : "";
        return `<div class="msg${m.unread && !this._marked.has(m.thread_id) ? " unread" : ""}" data-i="${i}"><div class="main"><div class="title">${mEsc(m.title)}</div><div class="snip">${mEsc(m.sender)}:<br>${mEsc(
          (m.preview || "").replace(/\s+/g, " ").slice(0, 80)
        )}${(m.preview || "").length > 80 ? "…" : ""}</div></div><div class="side"><div>${mEsc(fmtTime(m.sent))}</div><div class="cnt">${tr(hass, "count")}: ${mEsc(m.messages)}</div>${clip}</div></div>`;
      })
      .join("");

    let popup = "";
    if (this._open !== null && msgs[this._open]) {
      const m = msgs[this._open];
      const people = [...(m.participants || []), tr(hass, "me")]
        .map((n) => `<span class="person"><ha-icon icon="mdi:account-circle-outline"></ha-icon>${mEsc(String(n).toUpperCase())}</span>`)
        .join("");
      const parts = (m.parts && m.parts.length
        ? m.parts
        : [{ sender: m.sender, sent: m.sent, content: null }]
      )
        .map((p) => {
          const body =
            p.content != null
              ? mEsc(p.content)
              : `${mEsc(m.preview || "")}…\n\n<i>${mEsc(tr(hass, "unavail"))}</i>`;
          const files = (p.attachments || [])
            .map(
              (a) =>
                `<div class="file"><ha-icon icon="${fileIcon(a.mime_type, a.name)}"></ha-icon><span class="fname">${mEsc(a.name)}</span><a class="open" target="_blank" rel="noopener" ${this._href(a) ? `href="${mEsc(this._href(a))}"` : ""} data-att="${mEsc(a.id)}" data-name="${mEsc(a.name)}" data-mime="${mEsc(a.mime_type)}"><ha-icon icon="mdi:open-in-new"></ha-icon>${tr(hass, "open")}</a></div>`
            )
            .join("");
          const attach = files
            ? `<div class="attach"><div class="ahead"><ha-icon icon="mdi:email-open-multiple-outline"></ha-icon>${tr(hass, "attachments")}: ${(p.attachments || []).length}</div>${files}</div>`
            : "";
          return `<div class="bubble"><div class="from"><ha-icon icon="mdi:account-circle-outline"></ha-icon>${mEsc(p.sender)}:<span class="when">${mEsc(fmtFull(p.sent))}</span></div><div class="text">${body}</div>${attach}</div>`;
        })
        .join("");
      popup = `<div class="overlay" data-close="1"><div class="panel"><div class="phead"><div class="ptitle">${mEsc(m.title)}</div><button class="x" data-close="1"><ha-icon icon="mdi:close"></ha-icon></button></div><div class="people">${people}</div><div class="pbody">${parts}</div></div></div>`;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { padding:12px; }
        .htitle { font-size:1.2em; font-weight:500; padding:0 4px 10px; }
        .msg { display:flex; gap:12px; justify-content:space-between; background:var(--secondary-background-color); border:1px solid var(--divider-color); border-radius:10px; padding:14px 16px; margin-bottom:10px; cursor:pointer; }
        .msg:hover { filter:brightness(.97); }
        .main { min-width:0; }
        .title { font-size:1.1em; }
        .unread .title { font-weight:700; }
        .unread { border-left:5px solid var(--primary-color, #03a9f4); }
        .snip { margin-top:10px; padding-left:14px; color:var(--secondary-text-color); line-height:1.5; overflow-wrap:anywhere; }
        .side { text-align:right; white-space:nowrap; flex:none; }
        .cnt, .clip { margin-top:6px; color:var(--secondary-text-color); }
        .clip ha-icon { --mdc-icon-size:20px; margin-right:4px; }
        .empty { padding:16px; text-align:center; opacity:.6; }
        .overlay { position:fixed; inset:0; background:rgba(0,0,0,.5); z-index:100; display:flex; align-items:center; justify-content:center; padding:16px; box-sizing:border-box; }
        .panel { background:var(--card-background-color); color:var(--primary-text-color); border-radius:14px; width:100%; max-width:760px; max-height:92vh; overflow:auto; }
        .phead { position:relative; padding:16px 56px 12px 20px; }
        .ptitle { font-size:1.3em; }
        .x { position:absolute; right:12px; top:12px; background:none; border:none; color:var(--secondary-text-color); cursor:pointer; padding:4px; --mdc-icon-size:28px; }
        .people { display:flex; flex-wrap:wrap; gap:8px; padding:12px 20px; background:var(--secondary-background-color); }
        .person { display:inline-flex; align-items:center; gap:6px; background:var(--primary-color, #03a9f4); color:var(--text-primary-color, #fff); border-radius:18px; padding:5px 14px 5px 8px; font-size:.95em; }
        .person ha-icon { --mdc-icon-size:22px; }
        .pbody { padding:16px 20px 20px; display:flex; flex-direction:column; gap:14px; }
        .bubble { background:var(--secondary-background-color); border-radius:10px; padding:12px 16px; }
        .from { display:flex; align-items:center; gap:6px; color:var(--secondary-text-color); margin-bottom:10px; }
        .from ha-icon { --mdc-icon-size:22px; }
        .when { margin-left:auto; font-size:.85em; }
        .attach { margin-top:14px; border-top:1px solid var(--divider-color); padding-top:10px; }
        .ahead { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
        .file { display:flex; align-items:center; gap:14px; padding:8px 4px; border-top:1px solid var(--divider-color); }
        .file ha-icon { --mdc-icon-size:34px; color:var(--secondary-text-color); }
        .open { text-decoration:none; display:inline-flex; flex-direction:column; align-items:center; gap:2px; background:none; border:none; color:var(--primary-text-color); cursor:pointer; padding:4px 10px; font:inherit; }
        .open:not([href]) { opacity:.4; pointer-events:none; }
        .open ha-icon { --mdc-icon-size:26px; }
        .fname { flex:1; overflow-wrap:anywhere; }
        .text { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.55; }
      </style>
      <ha-card>
        ${cfg.title ? `<div class="htitle">${mEsc(cfg.title)}</div>` : ""}
        ${list || '<div class="empty">${tr(hass, "empty")}</div>'}
      </ha-card>${popup}`;

    const root = this.shadowRoot;
    root.querySelectorAll("[data-i]").forEach((el) =>
      el.addEventListener("click", () => {
        this._open = Number(el.dataset.i);
        const m = msgs[this._open];
        if (cfg.mark_read !== false && m && m.unread && m.thread_id && !this._marked.has(m.thread_id)) {
          this._marked.add(m.thread_id);
          this._hass
            .callService("daisyfamily", "mark_thread_read", { thread_id: m.thread_id })
            .catch((err) => {
              this._marked.delete(m.thread_id);
              console.warn("Marking the message as read failed", err);
            });
        }
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

class DaisyMessagesCardEditor extends HTMLElement {
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
    const ids = Object.keys(this._hass.states).filter((id) => isMessagesEntity(this._hass, id));
    this._form.hass = this._hass;
    this._form.schema = [
      { name: "title", selector: { text: {} } },
      { name: "entity", selector: { entity: ids.length ? { include_entities: ids } : { domain: "sensor" } } },
      { name: "max", selector: { number: { min: 1, max: 100, mode: "box" } } },
      { name: "mark_read", selector: { boolean: {} } },
    ];
    this._form.data = { max: 10, mark_read: true, ...this._config };
  }
}

if (!customElements.get(MSG_TAG)) customElements.define(MSG_TAG, DaisyMessagesCard);
if (!customElements.get(MSG_EDITOR_TAG)) customElements.define(MSG_EDITOR_TAG, DaisyMessagesCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === MSG_TAG)) {
  /* The picker reads name and description when it opens, so getters can follow the Home Assistant language. */
  window.customCards.push({
    type: MSG_TAG,
    get name() {
      return tr(document.querySelector("home-assistant")?.hass, "card_name");
    },
    get description() {
      return tr(document.querySelector("home-assistant")?.hass, "card_desc");
    },
    preview: false,
  });
}
console.info(`%c DAISYFAMILY-MESSAGES-CARD %c ${MSG_CARD_VERSION} `, "background:#4fa9db;color:#fff", "");
})();
