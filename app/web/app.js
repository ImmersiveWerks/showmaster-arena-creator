// ShowMaster Arena Creator: settings panel, live 3D preview, save and build.
import { Viewer } from "./viewer.js";
import { t, setLang, getLang, detectLang, LANGS } from "./i18n.js";

const $ = (s, el = document) => el.querySelector(s);
const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
};
const api = async (path, body) => {
  const r = await fetch(path, body === undefined ? { headers: { "X-Lang": getLang() } } : { method: "POST", headers: { "Content-Type": "application/json", "X-Lang": getLang() }, body: JSON.stringify(body) });
  const ct = r.headers.get("Content-Type") || "";
  if (ct.startsWith("image/")) return r.blob();
  const j = await r.json();
  if (!r.ok && j.error) throw new Error(j.error);
  return j;
};

// ------------------------------------------------------------------ the options

const MAT_LABEL = {
  "TB Seat": "Sitze", "TB Seat frame": "Sitzgestell", "TB Concrete": "Beton (Tribüne)", "TB Steps": "Stufen",
  "TB Rail": "Geländer", "TB Rail infill": "Geländer-Stäbe",
};
const FLEXI_OPTS = [["AUTO", "Automatisch"], ["0", "Feste Farbe"], ["1", "Farbe 1"], ["2", "Farbe 2"], ["3", "Farbe 3"], ["4", "Farbe 4"]];

const PRESET_INFO = {
  STRAIGHT: ["Gerade", "M4 22h24"],
  L: ["Ecke", "M4 8v16h22"],
  U: ["Drei Seiten", "M5 7v17h22V7"],
  ARC: ["Bogen", "M4 24 A20 20 0 0 1 24 4"],
  ARENA: ["Arena", "M5 8v6a11 11 0 0 0 22 0V8"],
  WEDGE: ["Flügel", "M3 12l7 10h12l7-10"],
};

// number: [key, label, min, max, step, unit, help]
const N = (key, label, min, max, step, unit = "m", help = "", extra = {}) => ({ type: "num", key, label, min, max, step, unit, help, ...extra });
const T = (key, label, help = "", extra = {}) => ({ type: "toggle", key, label, help, ...extra });
const S = (key, label, opts, help = "", extra = {}) => ({ type: "select", key, label, opts, help, ...extra });

const STEPS = [
  {
    id: "shape", title: "Form", sub: "Grundriss der Tribüne",
    groups: [
      { title: null, items: [{ type: "presets" }] },
      { title: "Teilstücke der Vorderkante", note: "Die Vorderkante ist die Linie, an der die erste Reihe beginnt. Sie wird aus geraden Stücken und Bögen gebaut.", items: [{ type: "segments" }] },
      { title: "Feinheiten", more: true, items: [
        N("arc_step", "Bogen-Glätte", 2, 20, 0.5, "°", "Grad pro Bogenstück. Kleiner = runder, aber mehr Polygone."),
        N("corner_threshold", "Ecke ab", 5, 90, 1, "°", "Knicke ab diesem Winkel zählen als Ecke (dort kommt eine Treppe hin)."),
      ] },
    ],
  },
  {
    id: "rows", title: "Reihen & Sitze", sub: "Wie viele, wie tief, wie hoch",
    groups: [
      { title: "Reihen", items: [
        N("rows", "Anzahl Reihen", 1, 40, 1, "", ""),
        N("row_depth", "Reihentiefe", 0.6, 3, 0.05, "m", "Tiefe einer Stufe: Sitz plus Gehweg davor."),
        N("row_rise", "Höhe pro Reihe", 0, 1.2, 0.05, "m", "Wie viel höher jede Reihe ist als die davor."),
        N("first_row_depth", "Tiefe der ersten Reihe", 0.6, 4, 0.05, "m", "Etwas tiefer als die anderen, damit vorne mehr Platz ist."),
        N("first_row_height", "Höhe der ersten Reihe", 0, 5, 0.05, "m", "Höhe der ersten Reihe über dem Boden."),
      ] },
      { title: "Sitze", items: [
        N("seat_gap", "Abstand zwischen Sitzen", 0, 1, 0.01, "m"),
        N("seat_height", "Sitzhöhe", -0.4, 0.4, 0.01, "m", "Alle Sitze anheben (+) oder absenken (−). Standard: 4 cm tiefer."),
        N("seat_back_gap", "Abstand zur Stufenkante", -0.6, 1, 0.01, "m", "Lehne bis zur hinteren Kante der Reihe. Negativ: der Sitz ragt über die nächste Stufe.", { more: true }),
        N("clearance", "Beinfreiheit", 0.05, 1, 0.01, "m", "Freier Platz zwischen Sitzkante und Gehweg.", { more: true }),
      ] },
      { title: "Freie Plätze", note: "Echte Zuschauer lassen Lücken zwischen ihren Gruppen. Diese Plätze bleiben frei.", items: [
        T("free_on", "Lücken zwischen Gruppen"),
        N("free_group_min", "Gruppe mindestens", 1, 20, 1, "Plätze", "", { show: (s) => s.free_on, more: true }),
        N("free_group_max", "Gruppe höchstens", 1, 40, 1, "Plätze", "", { show: (s) => s.free_on, more: true }),
        N("free_gap_min", "Lücke mindestens", 0, 10, 1, "Plätze", "", { show: (s) => s.free_on, more: true }),
        N("free_gap_max", "Lücke höchstens", 0, 10, 1, "Plätze", "", { show: (s) => s.free_on, more: true }),
        N("free_seed", "Zufallszahl", 0, 9999, 1, "", "Andere Zahl = andere Verteilung.", { show: (s) => s.free_on }),
      ] },
    ],
  },
  {
    id: "stairs", title: "Treppen & Wege", sub: "Wie Gäste zu ihrem Platz kommen",
    groups: [
      { title: "Treppen", items: [
        T("aisle_left", "Treppe am linken Ende"),
        T("aisle_right", "Treppe am rechten Ende"),
        N("aisle_center_count", "Treppen in der Mitte", 0, 20, 1, "", "Gleichmäßig verteilt zwischen den Enden."),
        T("aisle_corners", "Treppe an jeder Ecke"),
        N("aisle_width", "Treppenbreite", 0.6, 5, 0.05, "m"),
        { type: "text", key: "aisle_custom", label: "Zusätzliche Treppen bei", help: "Positionen in Metern ab dem Anfang der Vorderkante, mit Komma getrennt, z. B. 4.5, 12", more: true },
      ] },
      { title: "Wo die Treppen beginnen", items: [{ type: "stairs" }] },
      { title: "Weg vorne", items: [
        T("front_path", "Verbindungsweg vor der Tribüne", "Verbindet die unteren Enden der Treppen. Ohne ihn können nur die äußeren Treppen bis zum Boden gehen."),
        N("front_walk", "Breite", 0.5, 10, 0.1, "m", "", { more: true }),
      ] },
      { title: "Seitlicher Aufgang zur ersten Reihe", items: [
        S("access_left", "Links", [["NONE", "Keiner"], ["RAMP", "Rampe"], ["STAIRS", "Treppe"]]),
        S("access_right", "Rechts", [["NONE", "Keiner"], ["RAMP", "Rampe"], ["STAIRS", "Treppe"]]),
        N("access_width", "Breite", 0.6, 4, 0.05, "m", "", { show: (s) => s.access_left !== "NONE" || s.access_right !== "NONE" }),
        N("access_slope", "Rampen-Steigung", 3, 30, 0.5, "%", "Weniger = längere, flachere Rampe.", { factor: 100, show: (s) => s.access_left === "RAMP" || s.access_right === "RAMP" }),
      ] },
      { title: "Eingänge und Fläche", more: true, note: "Grüne Linien in der Ansicht sind Eingänge und Ausgänge.", items: [
        T("entrance_left", "Eingang links"), T("entrance_right", "Eingang rechts"),
        T("entrance_front", "Eingang vorne"), T("entrance_back", "Eingang hinten"),
        N("entrance_length", "Länge der seitlichen Eingänge", 0, 100, 0.5, "m", "Beginnt an der vorderen Ecke (0 = ganze Seite)."),
        N("side_walk", "Weg an den Seiten", 0, 10, 0.1, "m"),
        N("back_walk", "Weg hinten", 0, 10, 0.1, "m"),
        N("stage_depth", "Fläche vor der Tribüne", 0, 80, 0.5, "m", "Zusätzliche Fläche vorne, die zur Attraktion gehört (z. B. Bühne)."),
        S("booth", "Häuschen des Mitarbeiters", [["back", "Hinten"], ["left", "Links"], ["right", "Rechts"]]),
      ] },
    ],
  },
  {
    id: "rails", title: "Geländer", sub: "Sicherheit an den Kanten",
    groups: [
      { title: "Wo", items: [
        T("rail_back", "Hinten"), T("rail_sides", "An den Seiten"),
        T("rail_front", "Vorne an der ersten Reihe", "Zwischen den Treppen offen."),
      ] },
      { title: "Form", items: [
        N("rail_height", "Höhe", 0.3, 2, 0.05, "m"),
        N("rail_post_spacing", "Pfostenabstand", 0.3, 10, 0.1, "m"),
        N("rail_hand", "Handlauf-Dicke", 0.01, 0.3, 0.005, "m"),
        N("rail_post_size", "Pfosten-Dicke", 0.01, 0.4, 0.005, "m"),
        T("rail_mid", "Mittlere Stange"),
        N("rail_mid_size", "Dicke der mittleren Stange", 0.005, 0.2, 0.005, "m", "", { show: (s) => s.rail_mid, more: true }),
        N("rail_mid_height", "Höhe der mittleren Stange", 0.05, 2, 0.05, "m", "", { show: (s) => s.rail_mid, more: true }),
      ] },
      { title: "Senkrechte Stäbe", items: [
        T("rail_infill", "Stäbe zwischen den Pfosten", "Gitter-Optik. Jeder Stab ist eine flache Fläche (spart Polygone)."),
        N("rail_infill_spacing", "Stababstand", 0.04, 1, 0.01, "m", "", { show: (s) => s.rail_infill }),
        N("rail_infill_width", "Stabbreite", 0.003, 0.2, 0.001, "m", "", { show: (s) => s.rail_infill, more: true }),
        N("rail_infill_bottom", "Stäbe ab", 0, 2, 0.05, "m", "Unteres Ende über der Stufe.", { show: (s) => s.rail_infill, more: true }),
        N("rail_infill_top", "Stäbe bis", 0, 2, 0.05, "m", "Höchstens bis zum Handlauf.", { show: (s) => s.rail_infill, more: true }),
      ] },
    ],
  },
  {
    id: "look", title: "Aussehen", sub: "Farben und Oberflächen",
    groups: [
      { title: "Farben", note: "Flexicolour: im Spiel unter den Farben der Attraktion umfärbbar.", items: [{ type: "colors" }] },
      { title: "Boden und Stufen", items: [
        { type: "pattern", key: "floor_pattern", group: "floor", opts: [["NONE", "Glatt"], ["DIAMOND", "Riffelblech"], ["STUDS", "Noppen"], ["CONCRETE", "Beton"]] },
        N("floor_pattern_size", "Mustergröße", 0.1, 5, 0.05, "m", "Größe einer Musterkachel.", { show: (s) => s.floor_pattern !== "NONE" }),
      ] },
      { title: "Sitzoberfläche", items: [
        { type: "pattern", key: "seat_pattern", group: "seat", opts: [["NONE", "Glatt"], ["SCRATCHED", "Zerkratzt"]] },
        N("seat_pattern_size", "Kratzer-Größe", 0.05, 3, 0.05, "m", "Größe einer Kratzer-Kachel. Kleiner = feinere Kratzer.", { show: (s) => s.seat_pattern !== "NONE" }),
      ] },
    ],
  },
  {
    id: "finish", title: "Ins Spiel", sub: "Speichern und als Mod installieren",
    groups: [{ title: null, items: [{ type: "finish" }] }],
  },
];

// ------------------------------------------------------------------ state

let state = null, presets = {}, matDefaults = {}, flexiAuto = {}, stat = null;
let stepIdx = 0, showMore = {}, last = null;
const hist = [], fut = [];
let viewer = null, firstFrame = true;

function save() { try { localStorage.setItem("tb_state", JSON.stringify(state)); localStorage.setItem("tb_step", String(stepIdx)); } catch (e) { /* ignore */ } }
let histTimer = null, histBase = null;
function change(fn, { rerender = false } = {}) {
  if (histBase === null) histBase = JSON.stringify(state);
  fn(state);
  if (viewer) { pushMaterials(); pushPatterns(); }
  clearTimeout(histTimer);
  histTimer = setTimeout(() => { if (histBase !== JSON.stringify(state)) { hist.push(histBase); if (hist.length > 100) hist.shift(); fut.length = 0; } histBase = null; updUndo(); }, 400);
  save();
  if (rerender) renderPanel();
  else refreshVisibility();
  schedulePreview();
}
function updUndo() { $("#undoBtn").disabled = !hist.length; $("#redoBtn").disabled = !fut.length; }
function undo() { if (!hist.length) return; fut.push(JSON.stringify(state)); state = JSON.parse(hist.pop()); afterLoad(); }
function redo() { if (!fut.length) return; hist.push(JSON.stringify(state)); state = JSON.parse(fut.pop()); afterLoad(); }
function afterLoad(frame = false) { save(); updUndo(); renderPanel(); if (frame) firstFrame = true; schedulePreview(0); updTitle(); }

// ------------------------------------------------------------------ preview

let pvTimer = null, pvBusy = false, pvAgain = false;
function schedulePreview(delay = 160) { clearTimeout(pvTimer); pvTimer = setTimeout(runPreview, delay); }
async function runPreview() {
  if (pvBusy) { pvAgain = true; return; }
  pvBusy = true;
  try {
    const d = await api("/api/preview", { state });
    const ge = $("#genError");
    if (d.gen_error) { ge.hidden = false; ge.textContent = d.gen_error; renderStatus(null); }
    else {
      ge.hidden = true; last = d;
      viewer.setData(d, firstFrame); firstFrame = false;
      syncStairs(d.info.stairs);
      renderStatus(d);
      updTitle();
    }
  } catch (e) { toast(t("Vorschau fehlgeschlagen: {e}", { e: e.message }), "error"); }
  pvBusy = false;
  if (pvAgain) { pvAgain = false; schedulePreview(0); }
}

function syncStairs(stairs) {
  const sb = state.stair_bottom || [];
  const n = stairs.length;
  const now = stairs.map((s, i) => s.bottom);
  const changed = sb.length !== n;
  state.stair_bottom = now;
  if (changed && STEPS[stepIdx].id === "stairs") renderPanel();
  else if (STEPS[stepIdx].id === "stairs") { const el = $("#stairList"); if (el) fillStairs(el); }
}

function renderStatus(d) {
  const el = $("#status"); el.innerHTML = "";
  if (!d) return;
  const c = d.check, ok = !c.errors.length;
  el.append(
    h("div", { class: "stat big" }, h("b", {}, String(c.used)), h("span", {}, t("Plätze"))),
    h("div", { class: "stat" }, h("b", {}, String(d.info.rows)), h("span", {}, t(d.info.rows === 1 ? "Reihe" : "Reihen"))),
    h("div", { class: "stat" }, h("b", {}, d.info.length.toFixed(1) + " m"), h("span", {}, t("lang"))),
    h("div", { class: "stat" }, h("b", {}, d.info.depth.toFixed(1) + " m"), h("span", {}, t("tief"))),
    h("div", { class: "check " + (ok ? "ok" : "bad") },
      ok ? t("Alle {n} Plätze sind erreichbar", { n: c.ok_seats }) : c.errors.join(" ")),
  );
  const notes = [...d.warnings, ...c.warnings];
  if (notes.length) el.append(h("div", { class: "notes" }, notes.map((w) => h("p", {}, w))));
}

// ------------------------------------------------------------------ panel rendering

function renderSteps() {
  const ol = $("#steps"); ol.innerHTML = "";
  STEPS.forEach((st, i) => {
    ol.append(h("li", {}, h("button", { class: "step" + (i === stepIdx ? " on" : ""), "aria-current": i === stepIdx ? "step" : false, onclick: () => { stepIdx = i; save(); renderSteps(); renderPanel(); } },
      h("span", { class: "plate" }, String(i + 1)), h("span", { class: "st-t" }, t(st.title)), h("span", { class: "st-s" }, t(st.sub)))));
  });
}

function renderPanel() {
  const st = STEPS[stepIdx];
  const p = $("#panel"); p.innerHTML = "";
  p.append(h("div", { class: "panel-head" }, h("h1", {}, t(st.title)), h("p", {}, t(st.sub))));
  for (const g of st.groups) {
    if (g.more && !showMore[st.id + g.title]) {
      p.append(h("button", { class: "more-btn", onclick: () => { showMore[st.id + g.title] = true; renderPanel(); } }, "+ " + t(g.title)));
      continue;
    }
    const sec = h("section", { class: "group" + (g.title ? "" : " plain") });
    if (g.title) sec.append(h("h2", {}, t(g.title)));
    if (g.note) sec.append(h("p", { class: "note" }, t(g.note)));
    const basic = g.items.filter((it) => !it.more), more = g.items.filter((it) => it.more);
    for (const it of basic) sec.append(renderItem(it));
    if (more.length) {
      const key = st.id + "/" + g.title;
      if (showMore[key]) for (const it of more) sec.append(renderItem(it));
      sec.append(h("button", { class: "link", onclick: () => { showMore[key] = !showMore[key]; renderPanel(); } }, t(showMore[key] ? "Weniger anzeigen" : "Mehr Optionen")));
    }
    p.append(sec);
  }
  const nav = h("div", { class: "panel-nav" });
  if (stepIdx > 0) nav.append(h("button", { class: "ghost", onclick: () => { stepIdx--; save(); renderSteps(); renderPanel(); } }, t("Zurück")));
  if (stepIdx < STEPS.length - 1) nav.append(h("button", { class: "primary", onclick: () => { stepIdx++; save(); renderSteps(); renderPanel(); } }, t("Weiter: {s}", { s: t(STEPS[stepIdx + 1].title) })));
  p.append(nav);
  refreshVisibility();
}

function refreshVisibility() {
  document.querySelectorAll("[data-show]").forEach((el) => { const it = el._item; el.hidden = !(it.show(state)); });
}

function fmt(v, step) {
  const d = step >= 1 ? 0 : step >= 0.1 ? 1 : step >= 0.01 ? 2 : 3;
  return Number(v).toFixed(d);
}

function tItem(it) {
  return { ...it, label: t(it.label), help: it.help ? t(it.help) : it.help, unit: it.unit ? t(it.unit) : it.unit,
    opts: it.opts ? it.opts.map(([v, l]) => [v, t(l)]) : it.opts };
}

function renderItem(it0) {
  const it = it0.type && ["num", "toggle", "select", "text", "pattern"].includes(it0.type) ? tItem(it0) : it0;
  let el;
  if (it.type === "num") {
    const f = it.factor || 1;
    const val = () => Number(state[it.key]) * f;
    const range = h("input", { type: "range", min: it.min, max: it.max, step: it.step, value: val(), "aria-label": it.label });
    const num = h("input", { type: "number", min: it.min, max: it.max, step: it.step, value: fmt(val(), it.step), "aria-label": it.label + " " + t("Wert") });
    const set = (v, from) => {
      v = Math.min(it.max, Math.max(it.min, Number(v)));
      if (!isFinite(v)) return;
      if (from !== range) range.value = v;
      if (from !== num) num.value = fmt(v, it.step);
      change((s) => { s[it.key] = it.step >= 1 && !it.factor ? Math.round(v) : v / f; });
    };
    range.addEventListener("input", () => set(range.value, range));
    num.addEventListener("change", () => set(num.value, num));
    el = h("div", { class: "field num" },
      h("label", {}, it.label),
      h("div", { class: "ctl" }, range, h("span", { class: "num-wrap" }, num, it.unit ? h("em", {}, it.unit) : null)),
      it.help ? h("p", { class: "help" }, it.help) : null);
  } else if (it.type === "toggle") {
    const cb = h("input", { type: "checkbox", role: "switch" });
    cb.checked = !!state[it.key];
    cb.addEventListener("change", () => change((s) => { s[it.key] = cb.checked; }));
    el = h("div", { class: "field toggle" }, h("label", {}, cb, h("span", { class: "sw" }), h("span", {}, it.label)), it.help ? h("p", { class: "help" }, it.help) : null);
  } else if (it.type === "select") {
    const seg = h("div", { class: "seg", role: "radiogroup", "aria-label": it.label });
    for (const [v, l] of it.opts) {
      const b = h("button", { role: "radio", "aria-checked": String(state[it.key] === v), class: state[it.key] === v ? "on" : "" }, l);
      b.addEventListener("click", () => { change((s) => { s[it.key] = v; }); seg.querySelectorAll("button").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", String(x === b)); }); });
      seg.append(b);
    }
    el = h("div", { class: "field" }, h("label", {}, it.label), seg, it.help ? h("p", { class: "help" }, it.help) : null);
  } else if (it.type === "text") {
    const inp = h("input", { type: "text", value: (state[it.key] || []).join(", "), placeholder: t("z. B. 4.5, 12") });
    inp.addEventListener("change", () => {
      const vals = inp.value.split(/[,;]/).map((x) => x.trim().replace(/\s/g, "")).filter(Boolean).map(Number).filter((x) => isFinite(x));
      change((s) => { s[it.key] = vals; });
    });
    el = h("div", { class: "field" }, h("label", {}, it.label), inp, it.help ? h("p", { class: "help" }, it.help) : null);
  } else if (it.type === "presets") el = renderPresets();
  else if (it.type === "segments") el = renderSegments();
  else if (it.type === "stairs") { el = h("div", { id: "stairList", class: "stair-list" }); fillStairs(el); }
  else if (it.type === "colors") el = renderColors();
  else if (it.type === "pattern") el = renderPattern(it);
  else if (it.type === "finish") el = renderFinish();
  if (it.show) { el.dataset.show = "1"; el._item = it; }
  return el;
}

function renderPresets() {
  const wrap = h("div", { class: "presets" });
  for (const [k, [label, d]] of Object.entries(PRESET_INFO)) {
    wrap.append(h("button", { class: "preset", onclick: () => { change((s) => { s.segments = JSON.parse(JSON.stringify(presets[k])); s.stair_bottom = []; }, { rerender: true }); firstFrame = true; } },
      svg(d), h("span", {}, t(label))));
  }
  return wrap;
}
function svg(d) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 32 32"); s.setAttribute("aria-hidden", "true");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path"); p.setAttribute("d", d); s.append(p);
  return s;
}

function renderSegments() {
  const wrap = h("div", { class: "segments" });
  state.segments.forEach((sg, i) => {
    const kindSeg = h("div", { class: "seg small" });
    for (const [v, l] of [["straight", t("Gerade")], ["arc", t("Bogen")]]) {
      kindSeg.append(h("button", { class: sg.kind === v ? "on" : "", onclick: () => change((s) => {
        const x = s.segments[i]; x.kind = v;
        if (v === "arc") { x.radius = x.radius || 12; x.angle = x.angle || 90; } else { x.length = x.length || 12; }
      }, { rerender: true }) }, l));
    }
    const card = h("div", { class: "seg-card" },
      h("div", { class: "seg-top" }, h("span", { class: "seg-no" }, t("Stück {n}", { n: i + 1 })), kindSeg,
        state.segments.length > 1 ? h("button", { class: "icon-btn", title: t("Stück entfernen"), "aria-label": t("Stück {n} entfernen", { n: i + 1 }), onclick: () => change((s) => { s.segments.splice(i, 1); }, { rerender: true }) }, "×") : null));
    const item = (key, label, min, max, step, unit, help) => {
      const it = N(key, t(label), min, max, step, unit, help ? t(help) : help);
      const el = renderItemFor(it, () => sg[key] ?? 0, (v) => change((s) => { s.segments[i][key] = v; }));
      return el;
    };
    if (sg.kind === "arc") {
      card.append(item("radius", "Radius", 1, 100, 0.5, "m"), item("angle", "Bogenwinkel", -300, 300, 5, "°", "Positiv: um die Bühne herum."));
    } else card.append(item("length", "Länge", 0.5, 300, 0.5, "m"));
    if (i > 0) card.append(item("turn", "Knick am Anfang", -135, 135, 5, "°", "Positiv: um die Bühne herum."));
    wrap.append(card);
  });
  wrap.append(h("div", { class: "seg-add" },
    h("button", { class: "ghost", onclick: () => change((s) => { s.segments.push({ kind: "straight", length: 8, turn: 30 }); }, { rerender: true }) }, t("+ Gerades Stück")),
    h("button", { class: "ghost", onclick: () => change((s) => { s.segments.push({ kind: "arc", radius: 10, angle: 45, turn: 0 }); }, { rerender: true }) }, t("+ Bogen"))));
  return wrap;
}

function renderItemFor(it, get, setv) {
  const range = h("input", { type: "range", min: it.min, max: it.max, step: it.step, value: get(), "aria-label": it.label });
  const num = h("input", { type: "number", min: it.min, max: it.max, step: it.step, value: fmt(get(), it.step), "aria-label": it.label + " " + t("Wert") });
  const set = (v, from) => {
    v = Math.min(it.max, Math.max(it.min, Number(v))); if (!isFinite(v)) return;
    if (from !== range) range.value = v; if (from !== num) num.value = fmt(v, it.step);
    setv(v);
  };
  range.addEventListener("input", () => set(range.value, range));
  num.addEventListener("change", () => set(num.value, num));
  return h("div", { class: "field num" }, h("label", {}, it.label),
    h("div", { class: "ctl" }, range, h("span", { class: "num-wrap" }, num, h("em", {}, it.unit))), it.help ? h("p", { class: "help" }, it.help) : null);
}

function fillStairs(el) {
  el.innerHTML = "";
  const stairs = (last && last.info.stairs) || [];
  if (!stairs.length) { el.append(h("p", { class: "help" }, t("Keine Treppen. Schalte oben mindestens eine Treppe ein."))); return; }
  const name = { LEFT: "linkes Ende", RIGHT: "rechtes Ende", MIDDLE: "Mitte" };
  stairs.forEach((st, i) => {
    const label = t("Treppe {n} ({p})", { n: i + 1, p: t(name[st.pos] || "Mitte") });
    const row = h("div", { class: "stair-row" }, h("span", {}, label));
    if (st.forced) row.append(h("span", { class: "muted small" }, t("bis zum Boden (erste Reihe ist am Boden)")));
    else {
      const seg = h("div", { class: "seg small" });
      for (const [v, l] of [[true, t("Bis zum Boden")], [false, t("Ab Reihe 1")]]) {
        seg.append(h("button", { class: st.bottom === v ? "on" : "", onclick: () => change((s) => { s.stair_bottom[i] = v; last.info.stairs[i].bottom = v; fillStairs(el); }) }, l));
      }
      row.append(seg);
    }
    el.append(row);
  });
  if (!state.front_path) el.append(h("p", { class: "help" }, t("Ohne Verbindungsweg vorne gehen nur die äußeren Treppen bis zum Boden.")));
}

// colours: state.colors holds linear RGB like Blender, the picker works in sRGB
const lin2s = (c) => (c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
const s2lin = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const toHex = (rgb) => "#" + rgb.map((c) => Math.round(Math.min(1, Math.max(0, lin2s(c))) * 255).toString(16).padStart(2, "0")).join("");
const fromHex = (hx) => [1, 3, 5].map((i) => s2lin(parseInt(hx.slice(i, i + 2), 16) / 255));
function matColor(name) { return (state.colors && state.colors[name]) || matDefaults[name]; }

function renderColors() {
  const wrap = h("div", { class: "colors" });
  for (const name of ["TB Seat", "TB Seat frame", "TB Concrete", "TB Steps", "TB Rail", "TB Rail infill"]) {
    if (name === "TB Rail infill" && !state.rail_infill) continue;
    const inp = h("input", { type: "color", value: toHex(matColor(name)), "aria-label": t("Farbe") + " " + t(MAT_LABEL[name]) });
    inp.addEventListener("input", () => change((s) => { s.colors = { ...(s.colors || {}), [name]: fromHex(inp.value) }; pushMaterials(); }));
    const fx = h("select", { "aria-label": "Flexicolour " + t(MAT_LABEL[name]) }, FLEXI_OPTS.map(([v, l]) => h("option", { value: v }, v === "AUTO" ? t("Auto ({x})", { x: flexiAuto[name] ? t("Farbe {n}", { n: flexiAuto[name] }) : t("fest") }) : (/^\d$/.test(v) && v !== "0" ? t("Farbe {n}", { n: v }) : t(l)))));
    fx.value = String((state.flexi || {})[name] ?? "AUTO");
    fx.addEventListener("change", () => change((s) => { s.flexi = { ...(s.flexi || {}), [name]: fx.value === "AUTO" ? "AUTO" : Number(fx.value) }; }));
    wrap.append(h("div", { class: "color-row" }, h("label", { class: "swatch" }, inp), h("span", { class: "c-name" }, t(MAT_LABEL[name])), fx));
  }
  wrap.append(h("button", { class: "link", onclick: () => change((s) => { s.colors = {}; s.flexi = {}; pushMaterials(); }, { rerender: true }) }, t("Standardfarben")));
  return wrap;
}

function renderPattern(it) {
  const wrap = h("div", { class: "patterns" });
  for (const [v, l] of it.opts) {
    const b = h("button", { class: "pattern" + (state[it.key] === v ? " on" : ""), "aria-pressed": String(state[it.key] === v) },
      v === "NONE" ? h("span", { class: "pat-img none" }) : h("img", { class: "pat-img", src: `/api/pattern?group=${it.group}&kind=${v}&look=1`, alt: "" }),
      h("span", {}, l));
    b.addEventListener("click", () => { change((s) => { s[it.key] = v; }, { rerender: true }); pushPatterns(); });
    wrap.append(b);
  }
  return wrap;
}

function pushMaterials() {
  const R = { "TB Concrete": [0.8, 0], "TB Steps": [0.8, 0], "TB Rail": [0.4, 1], "TB Seat": [0.5, 0], "TB Seat frame": [0.5, 1], "TB Rail infill": [0.4, 1] };
  const m = {};
  for (const [k, [r, mt]] of Object.entries(R)) m[k] = { color: matColor(k), rough: r, metal: mt };
  viewer.setMaterials(m);
}
function pushPatterns() {
  viewer.setPattern("floor", state.floor_pattern, state.floor_pattern_size);
  viewer.setPattern("seat", state.seat_pattern, state.seat_pattern_size || 0.5);
}

// ------------------------------------------------------------------ the last step

function renderFinish() {
  const wrap = h("div", { class: "finish" });
  const auto = h("input", { type: "checkbox", role: "switch" }); auto.checked = state.auto_name !== false;
  const nameIn = h("input", { type: "text", value: state.name || "", placeholder: t("Name im Spiel"), "aria-label": t("Name im Spiel") });
  const autoName = last ? last.auto_name : "Show Arena";
  const nameRow = () => { nameIn.disabled = auto.checked; if (auto.checked) nameIn.value = last ? last.auto_name : autoName; };
  auto.addEventListener("change", () => { change((s) => { s.auto_name = auto.checked; }); nameRow(); });
  nameIn.addEventListener("input", () => change((s) => { s.name = nameIn.value; }));
  nameRow();
  const desc = h("textarea", { rows: 2, placeholder: t("Beschreibung im Spiel (optional)") }, state.description || "");
  desc.addEventListener("input", () => change((s) => { s.description = desc.value; }));

  const iconBox = h("div", { class: "icon-box" }, h("p", { class: "muted small" }, t("Das Bild im Bau-Menü des Spiels wird beim Speichern automatisch erstellt.")));
  const iconBtn = h("button", { class: "ghost", onclick: async () => {
    iconBtn.disabled = true; iconBtn.textContent = t("Erstelle Bild ...");
    try {
      const blob = await api("/api/icon", { state });
      iconBox.innerHTML = ""; iconBox.append(h("img", { src: URL.createObjectURL(blob), alt: t("Vorschau des Icons im Spiel") }));
    } catch (e) { toast(e.message, "error"); }
    iconBtn.disabled = false; iconBtn.textContent = t("Icon-Vorschau aktualisieren");
  } }, t("Icon-Vorschau"));

  const c = last && last.check;
  const ready = c && !c.errors.length;
  const saveBtn = h("button", { class: "ghost wide", disabled: !ready, onclick: () => job("/api/save") }, t("Nur in Bibliothek speichern"));
  const buildBtn = h("button", { class: "primary wide big", disabled: !ready || !(stat && stat.cobra && stat.game), onclick: () => job("/api/build") }, t("Speichern und ins Spiel installieren"));
  const reqs = [];
  if (stat && !stat.cobra) reqs.push(h("p", { class: "warn" }, t("cobra-tools fehlt. Bitte das Programm neu installieren.")));
  if (stat && !stat.game) reqs.push(h("p", { class: "warn" }, t("Planet Coaster 2 wurde nicht automatisch gefunden. Bitte in den Einstellungen den ovldata-Ordner wählen.")));
  if (c && c.errors.length) reqs.push(h("p", { class: "warn" }, t("Noch nicht bereit: {e}", { e: c.errors.join(" ") })));

  const more = showMore.finish;
  const idIn = h("input", { type: "text", value: state.tid || "", placeholder: t("wird automatisch vergeben"), "aria-label": "ID" });
  idIn.addEventListener("change", () => change((s) => { s.tid = idIn.value.trim().toLowerCase(); }));
  const single = h("input", { type: "checkbox", role: "switch" }); single.checked = state.single_guests !== false;
  single.addEventListener("change", () => change((s) => { s.single_guests = single.checked; }));

  wrap.append(
    h("section", { class: "group" }, h("h2", {}, t("Name")),
      h("div", { class: "field toggle" }, h("label", {}, auto, h("span", { class: "sw" }), h("span", {}, t("Automatisch benennen"))),
        h("p", { class: "help" }, t("„Show Arena“ mit der Zahl der Plätze, nummeriert wenn es mehrere gleich große gibt."))),
      h("div", { class: "field" }, nameIn), h("div", { class: "field" }, desc)),
    h("section", { class: "group" }, h("h2", {}, t("Icon im Spiel")), iconBox, iconBtn),
    h("section", { class: "group go" }, ...reqs, buildBtn, saveBtn,
      h("p", { class: "help" }, t("Spiel vorher schließen. Jede Tribüne der Bibliothek wird ein eigener Mod-Ordner Mod_TB_… im ovldata-Ordner.")),
      h("div", { id: "jobLog", class: "job-log", hidden: true })),
    more ? h("section", { class: "group" }, h("h2", {}, t("Mehr")),
      h("div", { class: "field" }, h("label", {}, t("ID (intern)")), idIn, h("p", { class: "help" }, t("3–31 Kleinbuchstaben, Ziffern und _. Bleibt beim Bearbeiten gleich, damit die Tribüne im Spiel ersetzt wird."))),
      h("div", { class: "field toggle" }, h("label", {}, single, h("span", { class: "sw" }), h("span", {}, t("Gäste einzeln"))),
        h("p", { class: "help" }, t("Setzt die maximale Gruppengröße der Station auf 1.")))) :
      h("button", { class: "link", onclick: () => { showMore.finish = true; renderPanel(); } }, t("Mehr Optionen")),
  );
  return wrap;
}

async function job(path) {
  try {
    const r = await api(path, { state });
    if (!r.started) { toast(t("Es läuft schon ein Vorgang."), "error"); return; }
  } catch (e) { toast(e.message, "error"); return; }
  document.querySelectorAll(".go button").forEach((b) => (b.disabled = true));
  const logEl = $("#jobLog"); if (logEl) { logEl.hidden = false; logEl.innerHTML = ""; }
  for (;;) {
    await new Promise((r) => setTimeout(r, 500));
    const j = await api("/api/job");
    const el = $("#jobLog");
    if (el) { el.hidden = false; el.innerHTML = ""; for (const l of j.log.slice(-14)) el.append(h("div", {}, l)); el.scrollTop = el.scrollHeight; }
    if (!j.running) {
      if (j.ok) {
        const res = j.result || {};
        if (res.state) { state.tid = res.state.tid; state.uid = res.state.uid; state.name = res.state.name; save(); updTitle(); }
        if (j.kind === "build") toast(t("Installiert: {n} Tribünen-Mods. Jetzt das Spiel starten.", { n: (res.targets || []).length }), "ok");
        else toast(t("Gespeichert: {n}", { n: res.name }), "ok");
      } else toast(j.error || t("Fehlgeschlagen"), "error", 12000);
      renderPanel();
      return;
    }
  }
}

// ------------------------------------------------------------------ drawers

async function openLibrary() {
  const d = $("#libDrawer"); d.hidden = false; $("#setDrawer").hidden = true; $("#extDrawer").hidden = true;
  $("#libPath").textContent = stat ? (stat.shared ? t("Gemeinsame Bibliothek mit dem Blender-Add-on") : t("Bibliothek: {p}", { p: stat.library })) : "";
  const list = $("#libList"); list.textContent = t("Lade ...");
  const items = await api("/api/library");
  list.innerHTML = "";
  if (!items.length) { list.append(h("p", { class: "muted" }, t("Noch keine Tribünen gespeichert. Bau eine und speichere sie im letzten Schritt."))); return; }
  for (const it of items) {
    const del = h("button", { class: "ghost small", onclick: async () => {
      if (del.dataset.armed !== "1") { del.dataset.armed = "1"; del.textContent = t("Wirklich löschen?"); return; }
      await api("/api/library/remove", { id: it.id }); toast(t("„{n}“ gelöscht. Beim nächsten Installieren wird ihr Mod entfernt.", { n: it.name })); openLibrary();
    } }, t("Löschen"));
    list.append(h("div", { class: "lib-item" + (state.tid === it.id ? " cur" : "") },
      it.icon ? h("img", { src: `/api/library/icon?id=${it.id}`, alt: "" }) : h("div", { class: "noimg" }),
      h("div", { class: "lib-t" }, h("b", {}, it.name), h("span", { class: "muted small" }, t("{n} Plätze", { n: it.seats })), it.editable ? null : h("span", { class: "muted small" }, t("aus dem Blender-Add-on"))),
      h("div", { class: "lib-a" },
        it.editable ? h("button", { class: "ghost small", onclick: async () => {
          const r = await api("/api/library/load", { id: it.id });
          if (r.error) { toast(r.error, "error"); return; }
          pushHist(); state = r.state; d.hidden = true; afterLoad(true); pushMaterials(); pushPatterns(); toast(t("„{n}“ geöffnet", { n: it.name }));
        } }, t("Bearbeiten")) : null, del)));
  }
}
async function openExtras() {
  $("#libDrawer").hidden = true; $("#setDrawer").hidden = true;
  const d = $("#extDrawer"); d.hidden = false;
  const body = $("#extBody"); body.textContent = t("Lade ...");
  const r = (await api("/api/extras")).spawner;
  body.innerHTML = "";
  const state_ = t(r.installed ? (r.current ? "Installiert" : "Installiert (ältere Version)") : "Nicht installiert");
  const act = async (on) => {
    try { await api("/api/extras/spawner", { install: on }); toast(t(on ? "Guest Spawner installiert. Im Spiel oben links: „+500 Gäste“." : "Guest Spawner entfernt.")); }
    catch (e) { toast(e.message, "error"); }
    openExtras();
  };
  body.append(h("section", { class: "group plain extra" },
    h("h3", {}, "Guest Spawner"),
    h("p", {}, t("Zum Testen von Tribünen: im Park erscheint links ein Knopf „+500 Gäste“. Jeder Klick lässt 500 weitere Gäste kommen, auch wenn der Park noch leer ist.")),
    h("p", { class: "muted small" }, t("Status: {s}", { s: state_ })),
    !r.game ? h("p", { class: "warn" }, t("Planet Coaster 2 wurde nicht gefunden. Bitte zuerst in den Einstellungen den ovldata-Ordner wählen.")) : null,
    h("div", { class: "row-btns" },
      h("button", { class: "primary", disabled: !r.game || !r.available, onclick: () => act(true) }, t(r.installed ? (r.current ? "Neu installieren" : "Aktualisieren") : "Installieren")),
      r.installed ? h("button", { class: "ghost", onclick: () => act(false) }, t("Entfernen")) : null),
    h("p", { class: "help" }, t("Spiel vorher schließen. Wird als eigener Mod-Ordner Mod_GuestSpawner installiert."))));
}
function pushHist() { hist.push(JSON.stringify(state)); fut.length = 0; updUndo(); }

function folderRow(key, label, value, ok, help) {
  const inp = h("input", { type: "text", value: value || "", placeholder: t("automatisch") });
  const saveIt = async () => { stat = await api("/api/settings", { [key]: inp.value }); renderSettings(); renderDot(); };
  inp.addEventListener("change", saveIt);
  return h("div", { class: "field folder" },
    h("label", {}, h("i", { class: "dot " + (ok ? "ok" : "bad") }), label),
    h("div", { class: "ctl" }, inp,
      stat.windows ? h("button", { class: "ghost small", onclick: async () => { const r = await api("/api/pick_folder", { start: inp.value }); if (r.path) { inp.value = r.path; saveIt(); } } }, t("Wählen …")) : null,
      h("button", { class: "ghost small", title: t("Ordner öffnen"), onclick: () => api("/api/open_folder", { which: key }) }, t("Öffnen"))),
    h("p", { class: "help" }, help));
}
function renderSettings() {
  const b = $("#setBody"); b.innerHTML = "";
  const s = stat.settings;
  b.append(
    folderRow("game", "Planet Coaster 2 (ovldata)", s.game || stat.game, !!stat.game, stat.game ? t("Gefunden: {p}", { p: stat.game }) : t("…\\steamapps\\common\\Planet Coaster 2\\Win64\\ovldata (Silver-Screen-DLC wird gebraucht)")),
    folderRow("library", t("Bibliothek"), s.library, true, t(stat.shared ? "Wird mit dem Blender-Add-on geteilt: beide bauen alle Tribünen der Bibliothek." : "Hier werden die gespeicherten Tribünen abgelegt.")),
    folderRow("cobra", "cobra-tools", s.cobra || stat.cobra, !!stat.cobra, stat.cobra ? t("Gefunden: {p}", { p: stat.cobra }) : t("cobra-tools fehlt. Bitte das Programm neu installieren.")),
  );
  const yaw = h("div", { class: "seg small" });
  for (const [v, l] of [[1, t("Normal")], [-1, t("Gespiegelt")]]) yaw.append(h("button", { class: Number(s.yaw_sign) === v ? "on" : "", onclick: async () => { stat = await api("/api/settings", { yaw_sign: v }); renderSettings(); } }, l));
  b.append(h("div", { class: "field" }, h("label", {}, t("Sitzdrehung im Spiel")), yaw, h("p", { class: "help" }, t("Nur ändern, wenn Gäste auf schrägen Tribünen falsch herum sitzen."))),
    h("p", { class: "muted small" }, t("Version {v}", { v: stat.version })));
}
function renderDot() { $("#setDot").className = "dot " + (stat.cobra && stat.game ? "ok" : "bad"); }

// ------------------------------------------------------------------ misc

let toastTimer = null;
function toast(msg, kind = "", ms = 5000) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast " + kind; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), ms);
}
function updTitle() {
  const n = state.auto_name !== false ? (last ? last.auto_name : "") : state.name;
  $("#titleName").textContent = (n || t("Neue Tribüne")) + (state.tid ? "" : " " + t("(nicht gespeichert)"));
}

function applyStatic() {
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
}
function initLang() {
  setLang(detectLang());
  const sel = $("#langSel");
  sel.innerHTML = "";
  for (const [k, n] of LANGS) sel.append(h("option", { value: k }, n));
  sel.value = getLang();
  sel.onchange = () => {
    setLang(sel.value);
    try { localStorage.setItem("tb_lang", sel.value); } catch (e) { /* ignore */ }
    applyStatic(); renderSteps(); renderPanel(); updTitle();
    for (const d of document.querySelectorAll(".drawer")) if (!d.hidden) { if (d.id === "libDrawer") openLibrary(); else if (d.id === "extDrawer") openExtras(); else renderSettings(); }
    schedulePreview(0);
  };
  applyStatic();
}

async function init() {
  initLang();
  try { viewer = new Viewer($("#view")); }
  catch (e) { $("#genError").hidden = false; $("#genError").textContent = t("Die 3D-Ansicht braucht WebGL 2: {e}", { e: e.message }); }
  const d = await api("/api/init");
  presets = d.presets; matDefaults = d.materials; flexiAuto = d.flexi_auto; stat = d.status;
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem("tb_state") || "null"); stepIdx = Number(localStorage.getItem("tb_step") || 0) || 0; } catch (e) { saved = null; }
  state = Object.assign({}, d.state, saved || {});
  const fresh = () => JSON.parse(JSON.stringify(d.state));
  $("#undoBtn").onclick = undo; $("#redoBtn").onclick = redo;
  $("#newBtn").onclick = () => { pushHist(); state = fresh(); stepIdx = 0; renderSteps(); afterLoad(true); pushMaterials(); pushPatterns(); toast(t("Neue Tribüne. Die vorige ist mit Rückgängig zurückzuholen.")); };
  $("#libBtn").onclick = openLibrary;
  $("#extBtn").onclick = openExtras;
  $("#setBtn").onclick = async () => { $("#libDrawer").hidden = true; $("#extDrawer").hidden = true; stat = await api("/api/status"); renderSettings(); $("#setDrawer").hidden = false; };
  $("#quitBtn").onclick = async () => { await api("/api/quit", {}); document.body.innerHTML = ""; document.body.append(h("p", { class: "bye" }, t("Die App wurde beendet. Du kannst dieses Fenster schließen."))); };
  document.querySelectorAll("[data-close]").forEach((b) => (b.onclick = () => (b.closest(".drawer").hidden = true)));
  document.querySelectorAll("[data-view]").forEach((b) => (b.onclick = () => viewer.view(b.dataset.view)));
  $("#showNav").onchange = (e) => { viewer.show.nav = e.target.checked; viewer.redraw(); };
  $("#showOutline").onchange = (e) => { viewer.show.outline = e.target.checked; viewer.redraw(); };
  $("#showFree").onchange = (e) => { viewer.show.free = e.target.checked; viewer.redraw(); };
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input[type=text], textarea")) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); }
    if (e.key === "Escape") document.querySelectorAll(".drawer").forEach((x) => (x.hidden = true));
  });
  renderDot(); renderSteps(); renderPanel(); updUndo(); updTitle();
  pushMaterials(); pushPatterns();
  schedulePreview(0);
}
init();
