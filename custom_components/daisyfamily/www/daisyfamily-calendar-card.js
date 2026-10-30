(() => {
/* Daisy Family – reservation calendar */
const CARD_VERSION = "1.0.0";
const CARD_TAG = "daisyfamily-calendar-card";
const EDITOR_TAG = "daisyfamily-calendar-card-editor";

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const pad = (n) => String(n).padStart(2, "0");
const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const hoursOf = (hhmm) => {
  const [h, m] = String(hhmm).split(":").map(Number);
  return h + (m || 0) / 60;
};
function isoWeek(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const day = dt.getUTCDay() || 7;
  dt.setUTCDate(dt.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(dt.getUTCFullYear(), 0, 1));
  return Math.ceil(((dt - yearStart) / 86400000 + 1) / 7);
}

function isReservationEntity(hass, entityId) {
  const st = hass.states[entityId];
  return !!st && entityId.startsWith("sensor.") && Array.isArray(st.attributes?.reservations);
}

/* A child's reservation sensor: either the selected entity itself or the reservation sensor of the same device. */
function resolveReservationEntity(hass, entityId) {
  if (isReservationEntity(hass, entityId)) return entityId;
  const dev = hass.entities?.[entityId]?.device_id;
  if (!dev) return null;
  const hit = Object.values(hass.entities).find(
    (e) => e.device_id === dev && isReservationEntity(hass, e.entity_id)
  );
  return hit ? hit.entity_id : null;
}

/* Languages: Finnish (fi) and English (en). All other Home Assistant languages use English. */
const I18N = {
  fi: {
    card_name: "Daisy Family – varauskalenteri", card_desc: "Lasten varatut hoitoajat, poissaolot ja loma-ajat päivittäin.",
    wd: ["su", "ma", "ti", "ke", "to", "pe", "la"],
    reserved: "Varattu", week: "Viikko", wk: "vko.", absent: "Poissa", nokid: "entiteettiä ei löydy",
    updated: "Päivitetty", noupdate: "Päivitysaika ei tiedossa", failed: " · päivitys epäonnistui",
    refresh: "Päivitä tiedot nyt", empty: "Ei tulevia varauksia.", vacation: "Loma-aika", unknown: "ei tiedossa",
    today: (hm) => `tänään klo ${hm}`, dayAt: (d, m, hm) => `${d}.${m}. klo ${hm}`, sep: ".",
    l_title: "Otsikko (valinnainen)",
    l_entities: "Lapset (valitse kunkin lapsen \"Varatut hoitoajat\")",
    l_days: "Näytettävät päivät (kalenteripäiviä tästä päivästä)",
    l_show_holidays: "Näytä loma-ajat ja pyhäpäivät",
    l_show_absences: "Näytä poissaolomerkinnät",
    l_scroll_to_today: "Vieritä automaattisesti kuluvan päivän kohdalle",
    l_scroll_peek: "Vieritys: kuinka paljon edellistä päivää jää näkyviin (px)",
    l_max_height: "Kortin enimmäiskorkeus (px, 0 = ei rajaa; vieritys käyttää oletuksena 600)",
    l_show_updated: "Näytä päivitysaika ja päivityspainike",
    l_days_back: "Näytettävät edelliset päivät (toteutuneine aikoineen, 0 = vain tämä päivä ja tulevat)",
    l_show_empty: "Näytä myös lapset, joilla ei ole hoitoa kyseisenä päivänä",
  },
  en: {
    card_name: "Daisy Family – reservation calendar", card_desc: "Children's care reservations, absences and holiday periods day by day.",
    wd: ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"],
    reserved: "Reserved", week: "Week", wk: "wk ", absent: "Absent", nokid: "entity not found",
    updated: "Updated", noupdate: "Update time unknown", failed: " · refresh failed",
    refresh: "Refresh data now", empty: "No upcoming reservations.", vacation: "Holiday period", unknown: "unknown",
    today: (hm) => `today at ${hm}`, dayAt: (d, m, hm) => `${d}.${m}. at ${hm}`, sep: ":",
    l_title: "Title (optional)",
    l_entities: "Children (select each child's \"Care reservations\")",
    l_days: "Days to show (calendar days from today)",
    l_show_holidays: "Show holiday periods and public holidays",
    l_show_absences: "Show absence markers",
    l_scroll_to_today: "Scroll automatically to the current day",
    l_scroll_peek: "Scrolling: how much of the previous day stays visible (px)",
    l_max_height: "Maximum card height (px, 0 = no limit; scrolling uses 600 by default)",
    l_show_updated: "Show update time and refresh button",
    l_days_back: "Previous days to show (with actual times, 0 = only today and upcoming)",
    l_show_empty: "Also show children without care on that day",
  },
};
const langOf = (hass) =>
  String((hass && (hass.locale?.language || hass.language)) || "fi").toLowerCase().startsWith("fi") ? "fi" : "en";
const tr = (hass, key, ...args) => {
  const v = (I18N[langOf(hass)] || I18N.fi)[key];
  return typeof v === "function" ? v(...args) : v;
};

/* The account's holiday periods and public holidays (from the sensor attributes). */
function findCalendarData(hass) {
  const periods = [];
  const holidays = {};
  for (const [id, st] of Object.entries(hass.states)) {
    if (!id.startsWith("sensor.")) continue;
    const a = st.attributes || {};
    if (Array.isArray(a.periods)) periods.push(...a.periods);
    if (Array.isArray(a.holidays)) for (const h of a.holidays) holidays[h.date] = h.name;
  }
  return { periods, holidays };
}

function childInfo(hass, reservationEntity) {
  const reg = hass.entities?.[reservationEntity];
  const dev = reg?.device_id;
  let name = dev && hass.devices?.[dev]?.name_by_user
    ? hass.devices[dev].name_by_user
    : dev && hass.devices?.[dev]?.name;
  if (!name) {
    name = (hass.states[reservationEntity]?.attributes?.friendly_name || reservationEntity)
      .replace(/\s*(Varatut hoitoajat|Care reservations)$/i, "");
  }
  let picture = null;
  if (dev) {
    const img = Object.values(hass.entities).find(
      (e) => e.device_id === dev && e.entity_id.startsWith("image.")
    );
    picture = img ? hass.states[img.entity_id]?.attributes?.entity_picture || null : null;
  }
  return { name, picture };
}

class DaisyCalendarCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._sig = "";
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  static getStubConfig(hass) {
    const ids = Object.keys(hass.states).filter((id) => isReservationEntity(hass, id));
    return { entities: ids, days: 14, show_empty: true, days_back: 7 };
  }

  setConfig(config) {
    if (!config || !Array.isArray(config.entities) || config.entities.length === 0) {
      throw new Error("Select at least one child (entities). / Valitse vähintään yksi lapsi.");
    }
    this._config = { days: 14, show_empty: true, ...config };
    this._sig = "";
    this._scrolled = false;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    const ids = this._config.entities.map((e) => resolveReservationEntity(hass, e));
    const sig = ids
      .map((id) => (id ? hass.states[id]?.last_updated + (hass.entities?.[id]?.device_id || "") : "-"))
      .join("|") + isoDate(new Date()) + JSON.stringify(this._config);
    const calSig = Object.entries(hass.states)
      .filter(([id, st]) => id.startsWith("sensor.") && (st.attributes?.periods || st.attributes?.holidays))
      .map(([id, st]) => id + st.last_updated)
      .join("|");
    const upd = this._updatedInfo(hass);
    const picSig = calSig + (upd ? upd.ts : "") + ids.map((id) => (id ? childInfo(hass, id).picture : "")).join("|");
    if (sig + picSig !== this._sig) {
      this._sig = sig + picSig;
      this._render();
    }
  }

  /* The integration's "Last successful update" sensor is found by its `logins` attribute. */
  _updatedInfo(hass) {
    for (const [id, st] of Object.entries(hass.states)) {
      if (id.startsWith("sensor.") && st.attributes && st.attributes.logins !== undefined && st.attributes.device_class === "timestamp") {
        return { id, ts: st.state };
      }
    }
    return null;
  }

  _fmtUpdated(ts) {
    const d = new Date(ts);
    if (isNaN(d)) return tr(this._hass, "unknown");
    const hm = `${d.getHours()}${tr(this._hass, "sep")}${String(d.getMinutes()).padStart(2, "0")}`;
    const now = new Date();
    if (d.toDateString() === now.toDateString()) return tr(this._hass, "today", hm);
    return tr(this._hass, "dayAt", d.getDate(), d.getMonth() + 1, hm);
  }

  async _refresh() {
    if (this._refreshing || !this._hass) return;
    const upd = this._updatedInfo(this._hass);
    const id = upd ? upd.id : resolveReservationEntity(this._hass, this._config.entities[0]);
    if (!id) return;
    this._refreshing = true;
    this._refreshFailed = false;
    this._render();
    try {
      await this._hass.callService("homeassistant", "update_entity", { entity_id: id });
    } catch (err) {
      this._refreshFailed = true;
    }
    this._refreshing = false;
    this._render();
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  /* The card can render before it is attached to the page: scroll only once its height is known. */
  _applyScroll() {
    if (!this._wantScroll) return;
    const list = this.shadowRoot.querySelector(".list");
    if (!list || !list.clientHeight) return;
    const row = [...list.querySelectorAll(".day")].find((el) => el.dataset.open >= this._todayStr);
    const peek = Number.isFinite(Number(this._config.scroll_peek)) ? Number(this._config.scroll_peek) : 90;
    if (row) list.scrollTop = Math.max(0, row.offsetTop - peek); /* leave the end of the previous day visible */
    this._scrolled = true;
    this._wantScroll = false;
  }

  /* The card becomes visible again (e.g. view switch): scroll to the current day again. */
  _rescroll() {
    if (!this._config || !this._config.scroll_to_today || !this.shadowRoot) return;
    this._wantScroll = true;
    requestAnimationFrame(() => this._applyScroll());
  }

  connectedCallback() {
    this._rescroll();
    if (typeof IntersectionObserver !== "undefined") {
      this._io = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) this._rescroll();
      });
      this._io.observe(this);
    }
    this._onKey = (ev) => {
      if (ev.key === "Escape" && this._popup) this._closePopup();
    };
    document.addEventListener("keydown", this._onKey);
  }

  disconnectedCallback() {
    if (this._io) {
      this._io.disconnect();
      this._io = null;
    }
    document.removeEventListener("keydown", this._onKey);
  }

  _openPopup(date) {
    this._popup = date;
    this._render();
  }

  _closePopup() {
    this._popup = null;
    this._render();
  }

  _shiftPopup(delta) {
    const [y, m, d] = this._popup.split("-").map(Number);
    const next = isoDate(new Date(y, m - 1, d + delta));
    if (next < (this._startStr || isoDate(new Date()))) return;
    this._popup = next;
    this._render();
  }

  _render() {
    const t = (k, ...a) => tr(this._hass, k, ...a);
    const hass = this._hass;
    const cfg = this._config;
    const today = new Date();
    const todayStr = isoDate(today);
    const nDays = Math.max(1, Number(cfg.days) || 14);
    const last = new Date(today.getFullYear(), today.getMonth(), today.getDate() + nDays - 1);
    const lastStr = isoDate(last);
    const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - ((today.getDay() + 6) % 7));
    /* days_back: how many previous days are shown (default 7). */
    const hasBack = cfg.days_back !== undefined && cfg.days_back !== null && cfg.days_back !== "";
    const backDays = hasBack ? Math.max(0, Number(cfg.days_back) || 0) : 7;
    const startStr = isoDate(new Date(today.getFullYear(), today.getMonth(), today.getDate() - backDays));
    this._startStr = startStr;
    const nowH = today.getHours() + today.getMinutes() / 60;

    const showCal = cfg.show_holidays !== false;
    const showAbs = cfg.show_absences !== false;
    const cal = showCal ? findCalendarData(hass) : { periods: [], holidays: {} };

    const kids = [];
    for (const eid of cfg.entities) {
      const res = resolveReservationEntity(hass, eid);
      if (!res) {
        kids.push({ name: eid, picture: null, byDate: {}, actual: {}, absent: new Set(), missing: true });
        continue;
      }
      const info = childInfo(hass, res);
      const attrs = hass.states[res].attributes;
      const byDate = {};
      const actual = {};
      const absent = new Set();
      /* Past days and today: history (reservation + actual times). Future days: reservations. */
      for (const h of attrs.history || []) {
        if (h.date < startStr) continue;
        if (h.start) (byDate[h.date] ||= []).push({ date: h.date, weekday: h.weekday, start: h.start, end: h.end });
        if (h.arrived || h.departed) actual[h.date] = { arrived: h.arrived, departed: h.departed };
        if (h.absent && showAbs) absent.add(h.date);
      }
      for (const r of attrs.reservations || []) {
        if (r.date > todayStr) (byDate[r.date] ||= []).push(r);
      }
      if (showAbs) for (const d of attrs.absences || []) if (d > todayStr) absent.add(d);
      kids.push({ ...info, byDate, actual, absent, centre: attrs.centre, group: attrs.group });
    }

    const vacationOf = (d) => cal.periods.find((p) => p.start <= d && d <= p.end);

    let lo = 6, hi = 18;
    for (const k of kids) {
      for (const list of Object.values(k.byDate)) {
        for (const r of list) {
          lo = Math.min(lo, Math.floor(hoursOf(r.start)));
          hi = Math.max(hi, Math.ceil(hoursOf(r.end)));
        }
      }
      for (const a of Object.values(k.actual || {})) {
        if (a.arrived) lo = Math.min(lo, Math.floor(hoursOf(a.arrived)));
        if (a.departed) hi = Math.max(hi, Math.ceil(hoursOf(a.departed)));
      }
    }
    const span = hi - lo;
    const pct = (h) => Math.min(100, Math.max(0, ((h - lo) / span) * 100));

    const label = (l, w, from, to) =>
      w < 22
        ? `<span class="t" style="left:${Math.min(88, Math.max(12, l + w / 2))}%">${esc(from)}–${esc(to)}</span>`
        : `<span class="t" style="left:${Math.min(96, Math.max(4, l))}%">${esc(from)}</span>` +
          `<span class="t" style="left:${Math.min(96, Math.max(4, l + w))}%">${esc(to)}</span>`;

    /* The reservation as a bar; if actual times exist they are drawn in full colour over a faded reservation. */
    const barHtml = (list, act, isToday) => {
      list = list || [];
      if (!act) {
        return list
          .map((r) => {
            const l = pct(hoursOf(r.start)), w = Math.max(1.5, pct(hoursOf(r.end)) - l);
            return `<div class="track"><div class="fill" style="left:${l}%;width:${w}%"></div></div><div class="times">${label(l, w, r.start, r.end)}</div>`;
          })
          .join("");
      }
      const aS = act.arrived ? hoursOf(act.arrived) : null;
      const aE = act.departed ? hoursOf(act.departed) : isToday && aS !== null ? Math.max(aS, nowH) : null;
      const res = list
        .map((r) => {
          const l = pct(hoursOf(r.start)), w = Math.max(1.5, pct(hoursOf(r.end)) - l);
          return `<div class="fill res" style="left:${l}%;width:${w}%"></div>`;
        })
        .join("");
      let actBar = "";
      let times = "";
      if (aS !== null) {
        const l = pct(aS), w = Math.max(1.5, pct(aE ?? aS + 0.1) - l);
        actBar = `<div class="fill" style="left:${l}%;width:${w}%"></div>`;
        times = act.departed ? label(l, w, act.arrived, act.departed) : `<span class="t" style="left:${Math.min(96, Math.max(4, l))}%">${esc(act.arrived)} →</span>`;
      } else if (aE !== null) {
        const w = 1.5, l = pct(aE) - w;
        actBar = `<div class="fill" style="left:${l}%;width:${w}%"></div>`;
        times = `<span class="t" style="left:${Math.min(96, Math.max(4, l))}%">→ ${esc(act.departed)}</span>`;
      }
      const cap = list.length
        ? `<div class="cap">${t("reserved")} ${list.map((r) => `${esc(r.start)}–${esc(r.end)}`).join(", ")}</div>`
        : "";
      return `<div class="track">${res}${actBar}</div><div class="times">${times}</div>${cap}`;
    };

    const avatar = (k, cls = "av") =>
      k.picture
        ? `<img class="${cls}" src="${esc(k.picture)}" alt="">`
        : `<span class="${cls} ph">${esc((k.name || "?")[0].toUpperCase())}</span>`;

    const dayInfo = (d) => {
      const [y, mo, da] = d.split("-").map(Number);
      const holidayName = cal.holidays[d];
      const vac = vacationOf(d);
      return {
        da, mo,
        wd: t("wd")[new Date(y, mo - 1, da).getDay()],
        holidayName,
        off: !!(holidayName || vac),
        tip: vac ? vac.name || t("vacation") : holidayName || "",
      };
    };

    /* Day list: reservation or absence, plus holiday periods and public holidays on weekdays. */
    const dateSet = new Set();
    for (const k of kids) {
      Object.keys(k.byDate).forEach((d) => d <= lastStr && dateSet.add(d));
      Object.keys(k.actual).forEach((d) => d <= lastStr && dateSet.add(d));
      k.absent.forEach((d) => d <= lastStr && dateSet.add(d));
    }
    const back = Math.round((today - new Date(startStr + "T00:00:00")) / 86400000);
    for (let i = -back; i < nDays; i++) {
      const dt = new Date(today.getFullYear(), today.getMonth(), today.getDate() + i);
      const d = isoDate(dt);
      const weekday = dt.getDay() !== 0 && dt.getDay() !== 6;
      if (weekday && (vacationOf(d) || cal.holidays[d])) dateSet.add(d);
    }
    const dates = [...dateSet].sort();

    let prevWeek = null;
    const rows = dates.map((d) => {
      const all = kids.flatMap((k) => k.byDate[d] || []);
      const locked = all.some((r) => r.locked);
      const info = dayInfo(d);
      const wk = isoWeek(d);
      const divider =
        wk !== prevWeek
          ? `<div class="weekdiv"><span class="line"></span><span class="wkpill">${t("week")} ${wk}</span><span class="line"></span></div>`
          : "";
      prevWeek = wk;
      const banner = info.holidayName ? `<div class="banner"><span>${esc(info.holidayName)}</span></div>` : "";
      const kidHtml = kids
        .map((k) => {
          const list = k.byDate[d];
          const act = k.actual[d];
          const isAbsent = k.absent.has(d);
          if (!list && !act && !isAbsent && !cfg.show_empty) return "";
          const pill = isAbsent
            ? `<span class="abs"><ha-icon icon="mdi:home-outline"></ha-icon>${t("absent")}</span>`
            : "";
          return `<div class="kid"><div class="head"><div class="chip">${avatar(k)}<span class="nm">${esc(k.name)}</span>${
            list || act || isAbsent ? "" : '<span class="none">ei hoitoa</span>'
          }${k.missing ? `<span class="none">${t("nokid")}</span>` : ""}</div>${pill}</div>${list || act ? barHtml(list, act, d === todayStr) : ""}</div>`;
        })
        .join("");
      return `${divider}<div class="day${d === todayStr ? " today" : ""}" data-open="${d}"><div class="date${info.off ? " off" : ""}" title="${esc(info.tip)}"><div class="dm">${info.da}.${info.mo}.</div><div class="wd">${esc(info.wd)}</div><div class="wk">${t("wk")}${wk}</div>${
        locked ? '<ha-icon class="lock" icon="mdi:lock"></ha-icon>' : ""
      }</div><div class="kids">${banner}${kidHtml}</div></div>`;
    });

    let popup = "";
    if (this._popup) {
      const d = this._popup;
      const info = dayInfo(d);
      const cards = kids
        .map((k) => {
          const list = k.byDate[d];
          const act = k.actual[d];
          const isAbsent = k.absent.has(d);
          const chips = (list || act) && !isAbsent
            ? [k.centre, k.group]
                .filter(Boolean)
                .map((t) => `<span class="pchip"><ha-icon icon="mdi:home-outline"></ha-icon>${esc(t)}</span>`)
                .join("")
            : "";
          return `<div class="pcard"><div class="phead">${avatar(k, "pav")}<span class="pname">${esc(k.name)}</span>${
            isAbsent ? `<span class="abs"><ha-icon icon="mdi:home-outline"></ha-icon>${t("absent")}</span>` : ""
          }</div>${chips ? `<div class="pchips">${chips}</div>` : ""}${(list || act) && !isAbsent ? barHtml(list, act, d === this._popup && d === todayStr) : ""}</div>`;
        })
        .join("");
      popup = `<div class="overlay" data-close="1"><div class="panel"><div class="ptop"><button class="nav" data-shift="-1" ${
        d <= startStr ? "disabled" : ""
      }><ha-icon icon="mdi:chevron-left"></ha-icon></button><span class="ptitle">${esc(info.wd)} ${pad(info.da)}.${pad(info.mo)}.</span><button class="nav" data-shift="1"><ha-icon icon="mdi:chevron-right"></ha-icon></button><button class="x" data-close="1"><ha-icon icon="mdi:close"></ha-icon></button></div>${
        info.holidayName ? `<div class="banner pb"><span>${esc(info.holidayName)}</span></div>` : ""
      }<div class="pbody">${cards}</div></div></div>`;
    }

    const maxH = Number(cfg.max_height) > 0 ? Number(cfg.max_height) : cfg.scroll_to_today ? 600 : 0;
    const prevScroll = this.shadowRoot.querySelector(".list")?.scrollTop;

    let footer = "";
    if (cfg.show_updated !== false) {
      const upd = this._updatedInfo(this._hass);
      const old = upd && Date.now() - new Date(upd.ts).getTime() > 3600 * 1000;
      footer = `<div class="foot${old ? " stale" : ""}">
          <span>${upd ? `${t("updated")} ${esc(this._fmtUpdated(upd.ts))}` : t("noupdate")}${this._refreshFailed ? t("failed") : ""}</span>
          <button class="rf${this._refreshing ? " spin" : ""}" data-refresh title="${esc(t("refresh"))}" ${this._refreshing ? "disabled" : ""}><ha-icon icon="mdi:refresh"></ha-icon></button>
        </div>`;
    }
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        .list { position:relative; }
        ha-card { padding:12px; }
        .title { font-size:1.2em; font-weight:500; padding:0 4px 10px; }
        .weekdiv { display:flex; align-items:center; gap:18px; margin:6px 0 12px; }
        .weekdiv .line { flex:1; height:2px; background:var(--primary-color, #03a9f4); }
        .wkpill { background:var(--primary-color, #03a9f4); color:var(--text-primary-color, #fff); border-radius:20px; padding:10px 24px; font-size:1.15em; }
        .day { cursor:pointer; display:flex; gap:10px; margin-bottom:10px; border-radius:14px; padding:6px; border:3px solid transparent; }
        .day.today { border-color: var(--success-color, #4caf50); }
        .date { flex:0 0 84px; width:84px; min-width:84px; background:var(--secondary-background-color); border-radius:12px; padding:10px 12px; align-self:stretch; box-sizing:border-box; }
        .date.off { background:var(--warning-color, #f09c3a); color:#212121; }
        .dm { font-size:1.35em; line-height:1.2; }
        .wd, .wk { margin-top:4px; }
        .lock { display:block; margin-top:10px; --mdc-icon-size:26px; color:var(--primary-text-color); }
        .kids { flex:1; min-width:0; display:flex; flex-direction:column; gap:8px; }
        .banner { background:var(--warning-color, #f09c3a); color:#212121; border-radius:6px; padding:10px; text-align:center; font-size:1.4em; }
        .banner span { background:rgba(255,255,255,.22); border-radius:16px; padding:3px 14px; }
        .kid { border:1px solid var(--divider-color); border-radius:10px; padding:8px 12px 6px; background:var(--card-background-color); }
        .head { display:flex; align-items:center; }
        .chip { display:inline-flex; align-items:center; gap:8px; background:var(--secondary-background-color); border-radius:18px; padding:4px 12px 4px 5px; }
        .day:hover .kid { filter:brightness(.98); }
        .av { width:26px; height:26px; border-radius:50%; object-fit:cover; flex:none; }
        .av.ph, .pav.ph { display:inline-flex; align-items:center; justify-content:center; background:var(--divider-color); font-size:.8em; }
        .nm { font-size:1.05em; }
        .none { opacity:.55; margin-left:4px; font-size:.9em; }
        .abs { display:inline-flex; align-items:center; gap:6px; margin-left:28%; background:#e07b2d; color:#fff; border-radius:18px; padding:5px 16px 5px 10px; font-size:1.05em; }
        .abs ha-icon { --mdc-icon-size:22px; }
        .track { position:relative; height:16px; background:var(--divider-color); margin:12px 0 2px; border-radius:2px; }
        .fill { position:absolute; top:0; bottom:0; background:var(--info-color, #4fa9db); }
        .times { position:relative; height:1.4em; font-size:.95em; margin-bottom:2px; }
        .fill.res { opacity:.35; }
        .cap { font-size:.85em; color:var(--secondary-text-color); margin:0 0 4px; }
        .t { position:absolute; transform:translateX(-50%); white-space:nowrap; }
        .foot { display:flex; align-items:center; justify-content:flex-end; gap:6px; padding:6px 4px 0; font-size:.85em; color:var(--secondary-text-color); }
        .foot.stale { color:var(--warning-color, #f09c3a); }
        .rf { background:none; border:none; color:inherit; cursor:pointer; padding:4px; border-radius:50%; --mdc-icon-size:20px; display:inline-flex; }
        .rf[disabled] { cursor:default; }
        .rf.spin ha-icon { animation:dsy-spin 1s linear infinite; }
        @keyframes dsy-spin { to { transform:rotate(360deg); } }
        .empty { padding:16px; text-align:center; opacity:.6; }
        .overlay { position:fixed; inset:0; background:rgba(0,0,0,.5); z-index:100; display:flex; align-items:center; justify-content:center; padding:16px; box-sizing:border-box; }
        .panel { background:var(--card-background-color); color:var(--primary-text-color); border-radius:14px; width:100%; max-width:640px; max-height:92vh; overflow:auto; }
        .ptop { display:flex; align-items:center; justify-content:center; gap:14px; padding:14px 56px 14px 16px; border-bottom:1px solid var(--divider-color); position:relative; }
        .ptitle { font-size:1.35em; min-width:120px; text-align:center; }
        .nav, .x { background:none; border:none; color:var(--secondary-text-color); cursor:pointer; padding:4px; border-radius:50%; --mdc-icon-size:28px; }
        .nav[disabled] { opacity:.3; cursor:default; }
        .x { position:absolute; right:12px; top:50%; transform:translateY(-50%); }
        .pb { margin:12px 14px 0; }
        .pbody { padding:14px; display:flex; flex-direction:column; gap:12px; }
        .pcard { border:1px solid var(--divider-color); border-radius:10px; padding:10px 16px 10px; }
        .phead { display:flex; align-items:center; gap:18px; min-height:56px; }
        .pav { width:56px; height:56px; border-radius:50%; object-fit:cover; flex:none; }
        .pname { font-size:1.35em; }
        .phead .abs { margin-left:0; }
        .pchips { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
        .pchip { display:inline-flex; align-items:center; gap:6px; background:var(--info-color, #4fa9db); color:#fff; border-radius:18px; padding:5px 14px 5px 8px; }
        .pchip ha-icon { --mdc-icon-size:20px; }
        .pnone { margin:10px 0 6px; }
        @media (max-width:500px) { .date { flex-basis:64px; width:64px; min-width:64px; padding:8px; } .dm { font-size:1.15em; } .day { gap:6px; padding:4px; } .abs { margin-left:12px; } }
      </style>
      <ha-card>
        ${cfg.title ? `<div class="title">${esc(cfg.title)}</div>` : ""}
        <div class="list"${maxH ? ` style="max-height:${maxH}px;overflow-y:auto"` : ""}>${
          rows.length ? rows.join("") : `<div class="empty">${t("empty")}</div>`
        }</div>
        ${footer}
      </ha-card>${popup}`;

    /* Scrolling: on the first visible render scroll to the current day, afterwards keep the position. */
    const list = this.shadowRoot.querySelector(".list");
    this._wantScroll = !!(maxH && cfg.scroll_to_today && !this._scrolled);
    if (list && maxH && !this._wantScroll && prevScroll) list.scrollTop = prevScroll;
    this._todayStr = todayStr;
    this._applyScroll();
    if (this._wantScroll) requestAnimationFrame(() => this._applyScroll());

    const root = this.shadowRoot;
    root.querySelectorAll("[data-open]").forEach((el) =>
      el.addEventListener("click", () => this._openPopup(el.dataset.open))
    );
    root.querySelectorAll("[data-refresh]").forEach((el) =>
      el.addEventListener("click", () => this._refresh())
    );
    root.querySelectorAll("[data-shift]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._shiftPopup(Number(el.dataset.shift));
      })
    );
    root.querySelectorAll("[data-close]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        if (ev.target === el || el.classList.contains("x") || el.closest(".x")) this._closePopup();
      })
    );
  }
}

class DaisyCalendarCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._draw();
  }

  set hass(hass) {
    this._hass = hass;
    this._draw();
  }

  _schema() {
    const ids = Object.keys(this._hass.states).filter((id) => isReservationEntity(this._hass, id));
    return [
      { name: "title", selector: { text: {} } },
      {
        name: "entities",
        required: true,
        selector: { entity: { multiple: true, ...(ids.length ? { include_entities: ids } : { domain: "sensor" }) } },
      },
      {
        type: "grid",
        name: "",
        schema: [
          { name: "days", selector: { number: { min: 1, max: 90, mode: "box" } } },
          { name: "show_empty", selector: { boolean: {} } },
          { name: "show_updated", selector: { boolean: {} } },
          { name: "days_back", selector: { number: { min: 0, max: 365, step: 1, mode: "box" } } },
          { name: "scroll_to_today", selector: { boolean: {} } },
          { name: "scroll_peek", selector: { number: { min: 0, max: 300, step: 10, mode: "box", unit_of_measurement: "px" } } },
          { name: "max_height", selector: { number: { min: 0, max: 2000, step: 10, mode: "box", unit_of_measurement: "px" } } },
          { name: "show_holidays", selector: { boolean: {} } },
          { name: "show_absences", selector: { boolean: {} } },
        ],
      },
    ];
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
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = { days: 14, show_empty: true, days_back: 7, show_updated: true, show_holidays: true, show_absences: true, ...this._config };
  }
}

if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, DaisyCalendarCard);
if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, DaisyCalendarCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CARD_TAG)) {
  /* The picker reads name and description when it opens, so getters can follow the Home Assistant language. */
  window.customCards.push({
    type: CARD_TAG,
    get name() {
      return tr(document.querySelector("home-assistant")?.hass, "card_name");
    },
    get description() {
      return tr(document.querySelector("home-assistant")?.hass, "card_desc");
    },
    preview: false,
  });
}
console.info(`%c DAISYFAMILY-TIMELINE-CARD %c ${CARD_VERSION} `, "background:#4fa9db;color:#fff", "");
})();
