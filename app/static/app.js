"use strict";

let state = { loaded: false };
let selection = null;      // {start, end} 1-based inclusive

const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, kids = []) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const kid of [].concat(kids)) n.append(kid);
  return n;
};

function say(msg, isError) {
  const s = $("status");
  s.textContent = msg;
  s.className = "status" + (isError ? " err" : "");
  if (msg) setTimeout(() => { if (s.textContent === msg) s.textContent = ""; }, 5000);
}

async function api(path, body) {
  const res = await fetch(path, body === undefined
    ? {} : { method: "POST", headers: { "Content-Type": "application/json" },
             body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function setState(data) {
  state = data;
  render();
  if (library.dir || (library.recent || []).length) renderLibrary();
}

/** In the native window there is no browser download, so hide that button. */
const NATIVE = new URLSearchParams(location.search).get("native") === "1";
if (NATIVE) $("btn-download").style.display = "none";

/* WKWebView ignores window.prompt/confirm unless the host app implements a UI
   delegate, so the app asks in the page instead — same code in both modes. */
function dialog(message, { value = null, okText = "확인" } = {}) {
  return new Promise((resolve) => {
    const input = value === null ? null
      : el("input", { type: "text", value, class: "grow", style: "width:100%" });
    const close = (result) => { back.remove(); resolve(result); };
    const ok = el("button", { class: "btn primary", text: okText,
      onclick: () => close(input ? input.value : true) });
    const box = el("div", { class: "modal" }, [
      el("p", { text: message }),
      ...(input ? [input] : []),
      el("div", { class: "row", style: "justify-content:flex-end;margin:.7rem 0 0" }, [
        el("button", { class: "btn", text: "취소", onclick: () => close(null) }), ok,
      ]),
    ]);
    const back = el("div", { class: "modalback", onclick: (e) => {
      if (e.target === back) close(null); } }, box);
    document.body.append(back);
    (input || ok).focus();
    if (input) {
      input.select();
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") close(input.value);
        if (e.key === "Escape") close(null);
      });
    }
  });
}
const askText = (message, value) => dialog(message, { value });
const askYesNo = (message) => dialog(message).then((v) => v === true);

// ---------------------------------------------------------------- rendering

function render() {
  $("file-name").textContent = state.loaded
    ? `${state.name} · ${state.length.toLocaleString()} bp · ${state.is_circular ? "circular" : "linear"}`
    : "파일 없음";
  if (!state.loaded) return;
  renderMap();
  renderSequence();
  renderFeatures();
  renderPrimers();
  fillPrimerPickers();
}

/** SnapGene stores some features as white, which disappears on a pale map. */
function displayColor(color) {
  const m = /^#?([0-9a-f]{6})$/i.exec(color || "");
  if (!m) return color || "#aab1bd";
  const n = parseInt(m[1], 16);
  const lum = (0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255;
  return lum > 0.92 ? "#9aa3b2" : color;
}

/* ------------------------------------------------------------------ map */
function renderMap() {
  const svg = $("plasmid-map");
  svg.innerHTML = "";
  const NS = "http://www.w3.org/2000/svg";
  const cx = 260, cy = 260, r = 170, len = state.length;
  const ang = (pos) => (pos / len) * 2 * Math.PI - Math.PI / 2;
  const pt = (pos, rad) => [cx + rad * Math.cos(ang(pos)), cy + rad * Math.sin(ang(pos))];

  const add = (tag, attrs) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    svg.append(n);
    return n;
  };

  add("circle", { cx, cy, r, fill: "none", stroke: "var(--line)", "stroke-width": 10 });
  for (let p = 0; p < len; p += Math.max(500, Math.round(len / 12 / 500) * 500)) {
    const [x1, y1] = pt(p, r + 7), [x2, y2] = pt(p, r + 13);
    add("line", { x1, y1, x2, y2, stroke: "var(--muted)", "stroke-width": 1 });
    const [tx, ty] = pt(p, r + 26);
    const t = add("text", { x: tx, y: ty, fill: "var(--muted)", "font-size": 9,
                            "text-anchor": "middle", "dominant-baseline": "middle" });
    t.textContent = p === 0 ? "1" : p.toLocaleString();
  }

  const lanes = [];
  const ringFor = (f) => {
    for (let i = 0; i < lanes.length; i++) {
      if (!lanes[i].some((o) => f.start <= o.end && o.start <= f.end)) {
        lanes[i].push(f); return i;
      }
    }
    lanes.push([f]); return lanes.length - 1;
  };

  const labelled = new Set();
  const sorted = [...state.features].sort((a, b) => (b.end - b.start) - (a.end - a.start));
  for (const f of sorted) {
    const lane = ringFor(f);
    const rad = r - lane * 15;
    const [x1, y1] = pt(f.start - 1, rad), [x2, y2] = pt(f.end, rad);
    const large = (f.end - f.start + 1) / len > 0.5 ? 1 : 0;
    const path = add("path", {
      d: `M ${x1} ${y1} A ${rad} ${rad} 0 ${large} 1 ${x2} ${y2}`,
      fill: "none", stroke: displayColor(f.color), "stroke-width": 9, "stroke-linecap": "butt",
      opacity: 0.9,
    });
    const tip = document.createElementNS(NS, "title");
    tip.textContent = `${f.name} (${f.type}) ${f.start}–${f.end}`;
    path.append(tip);
    if (f.directionality === 1 || f.directionality === 2) {
      const at = f.directionality === 1 ? f.end : f.start - 1;
      const [ax, ay] = pt(at, rad);
      const a = ang(at) + (f.directionality === 1 ? 0 : Math.PI);
      const wing = 7;
      const back = a + Math.PI;
      add("path", {
        d: `M ${ax} ${ay} ` +
           `L ${ax + wing * Math.cos(back - 0.5)} ${ay + wing * Math.sin(back - 0.5)} ` +
           `L ${ax + wing * Math.cos(back + 0.5)} ${ay + wing * Math.sin(back + 0.5)} Z`,
        fill: displayColor(f.color),
      });
    }
    const mid = (f.start + f.end) / 2;
    const [lx, ly] = pt(mid, rad - 14);
    const key = `${f.name}:${f.start}:${f.end}`;
    if (f.end - f.start > len / 60 && !labelled.has(key)) {
      labelled.add(key);
      const t = add("text", { x: lx, y: ly, fill: "var(--text)", "font-size": 9,
                              "text-anchor": "middle", "dominant-baseline": "middle" });
      t.textContent = f.name;
    }
  }
  const name = add("text", { x: cx, y: cy - 6, fill: "var(--text)", "font-size": 14,
                             "text-anchor": "middle", "font-weight": 600 });
  name.textContent = state.name.replace(/\.dna$/i, "");
  const bp = add("text", { x: cx, y: cy + 14, fill: "var(--muted)", "font-size": 11,
                           "text-anchor": "middle" });
  bp.textContent = `${state.length.toLocaleString()} bp`;

  $("map-title").textContent = state.name;
  $("map-meta").textContent =
    `${state.length.toLocaleString()} bp · ${state.is_circular ? "환형" : "선형"} · ` +
    `feature ${state.features.length}개 · 저장된 프라이머 ${state.primers.length}개`;
  const legend = $("map-legend");
  legend.innerHTML = "";
  for (const f of state.features) {
    legend.append(el("li", {}, [
      el("span", { class: "swatch",
        style: `background:${f.color};border:1px solid ${displayColor(f.color)}` }),
      el("span", { text: `${f.name} (${f.start.toLocaleString()}–${f.end.toLocaleString()})` }),
    ]));
  }
}

/* ------------------------------------------------------------- sequence */
function featureColorMap() {
  const colors = new Array(state.length + 1).fill(null);
  for (const f of state.features) {
    for (const seg of f.segments) {
      for (let p = seg.start; p <= Math.min(seg.end, state.length); p++) colors[p] = f.color;
    }
  }
  return colors;
}

function renderSequence(scrollTo) {
  const view = $("sequence-view");
  const seq = state.sequence;
  const colors = $("show-translation").checked ? featureColorMap() : [];
  const showRc = $("show-revcomp").checked;
  const showTrack = $("show-feature-track").checked;
  const width = 60;
  const comp = { A: "T", C: "G", G: "C", T: "A", N: "N" };
  const frag = document.createDocumentFragment();
  for (let i = 0; i < seq.length; i += width) {
    const chunk = seq.slice(i, i + width);
    const line = el("div", { class: "seqline" });
    line.append(el("span", { class: "seqnum",
      text: String(i + 1).padStart(String(seq.length).length, " ") + "  " }));
    for (let k = 0; k < chunk.length; k++) {
      const pos = i + k + 1;
      const c = colors[pos];
      const inSel = selection && pos >= selection.start && pos <= selection.end;
      line.append(el("span", {
        class: "base" + (inSel ? " sel" : ""),
        "data-pos": pos,
        style: c ? `background:${c}33;border-bottom:2px solid ${c}` : "",
        text: chunk[k],
      }));
      if ((k + 1) % 10 === 0) line.append(document.createTextNode(" "));
    }
    frag.append(line);
    if (showTrack) {
      for (const f of state.features) {
        if (f.end < i + 1 || f.start > i + chunk.length) continue;
        const track = el("div", { class: "track" });
        track.append(el("span", { class: "seqnum",
          text: " ".repeat(String(seq.length).length) + "  " }));
        let row = "";
        for (let k = 0; k < chunk.length; k++) {
          const pos = i + k + 1;
          if (pos < f.start || pos > f.end) row += " ";
          else if (pos === f.start) row += f.directionality === 2 ? "◀" : "├";
          else if (pos === f.end) row += f.directionality === 1 ? "▶" : "┤";
          else row += "─";
          if ((k + 1) % 10 === 0) row += " ";
        }
        track.append(el("span", { style: `color:${displayColor(f.color)}`, text: row }));
        track.append(el("span", { class: "name", style: `color:${displayColor(f.color)}`,
          text: f.name + (f.type && f.type !== "misc_feature" ? ` (${f.type})` : "") }));
        frag.append(track);
      }
    }
    if (showRc) {
      const rc = el("div", { class: "seqline muted" });
      rc.append(el("span", { class: "seqnum",
        text: " ".repeat(String(seq.length).length) + "  " }));
      let text = "";
      for (let k = 0; k < chunk.length; k++) {
        text += comp[chunk[k]] || "N";
        if ((k + 1) % 10 === 0) text += " ";
      }
      rc.append(document.createTextNode(text));
      frag.append(rc);
    }
  }
  view.innerHTML = "";
  view.append(frag);
  if (scrollTo) {
    const target = view.querySelector(`[data-pos="${scrollTo}"]`);
    if (target) target.scrollIntoView({ block: "center" });
  }
}

let dragStart = null;
$("sequence-view").addEventListener("mousedown", (e) => {
  const pos = e.target.dataset && e.target.dataset.pos;
  if (pos) { dragStart = +pos; selection = { start: +pos, end: +pos }; renderSequence(); }
});
$("sequence-view").addEventListener("mousemove", (e) => {
  if (dragStart === null) return;
  const pos = e.target.dataset && e.target.dataset.pos;
  if (!pos) return;
  selection = { start: Math.min(dragStart, +pos), end: Math.max(dragStart, +pos) };
  renderSequence();
  showSelection();
});
document.addEventListener("mouseup", () => { dragStart = null; showSelection(); });

function showSelection() {
  if (!selection) return;
  const { start, end } = selection;
  const sub = state.sequence.slice(start - 1, end);
  const gc = sub ? Math.round(1000 * [...sub].filter((c) => c === "G" || c === "C").length / sub.length) / 10 : 0;
  $("selection-info").textContent =
    `선택: ${start.toLocaleString()}–${end.toLocaleString()} (${sub.length} bp, GC ${gc}%)`;
  $("edit-start").value = start;
  $("edit-end").value = end;
}

/* ------------------------------------------------------------- features */
function renderFeatures() {
  const tbody = $("feature-table").querySelector("tbody");
  tbody.innerHTML = "";
  state.features.forEach((f, idx) => {
    const name = el("input", { value: f.name });
    const type = el("input", { value: f.type });
    const dir = el("select", {}, [
      el("option", { value: "1", text: "→ forward" }),
      el("option", { value: "2", text: "← reverse" }),
      el("option", { value: "0", text: "없음" }),
    ]);
    dir.value = String(f.directionality || 0);
    const start = el("input", { type: "number", value: f.start });
    const end = el("input", { type: "number", value: f.end });
    const color = el("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(f.color) ? f.color : "#cccccc" });
    const save = async () => {
      try {
        setState(await api("/api/features", {
          action: "update", index: idx,
          feature: { name: name.value, type: type.value, directionality: +dir.value,
                     start: +start.value, end: +end.value, color: color.value,
                     notes: f.notes, translation: f.translation },
        }));
        say("feature를 수정했습니다.");
      } catch (err) { say(err.message, true); }
    };
    for (const input of [name, type, dir, start, end, color]) input.addEventListener("change", save);
    const detail = el("tr", { class: "featdetail", style: "display:none" }, [
      el("td", { colspan: 9 }, featureDetail(f)),
    ]);
    const row = el("tr", {}, [
      el("td", {}, name), el("td", {}, type), el("td", {}, dir),
      el("td", { class: "num" }, start), el("td", { class: "num" }, end),
      el("td", { text: (f.end - f.start + 1).toLocaleString() }),
      el("td", {}, color),
      el("td", { text: f.segments.length > 1 ? `${f.segments.length}개` : "1개" }),
      el("td", {}, [
        el("button", { class: "btn small", text: "상세", onclick: () => {
          detail.style.display = detail.style.display === "none" ? "" : "none"; } }),
        el("button", { class: "btn small", text: "보기",
          onclick: () => { selection = { start: f.start, end: f.end };
            switchTab("sequence"); renderSequence(f.start); showSelection(); } }),
        el("button", { class: "btn small danger", text: "삭제", onclick: async () => {
          if (!await askYesNo(`${f.name} feature를 삭제할까요?`)) return;
          try { setState(await api("/api/features", { action: "delete", index: idx }));
            say("삭제했습니다."); } catch (err) { say(err.message, true); }
        } }),
      ]),
    ]);
    tbody.append(row, detail);
  });
}

/** Everything SnapGene stored on a feature that the table has no column for. */
function featureDetail(f) {
  const box = el("div", {});
  const strand = { 1: "forward (top strand)", 2: "reverse (bottom strand)" }[f.directionality]
    || "방향 없음";
  const dl = el("dl", { class: "qualifiers" });
  const add = (k, v) => { dl.append(el("dt", { text: k }), el("dd", { text: v })); };
  add("위치", `${f.start.toLocaleString()}–${f.end.toLocaleString()} ` +
    `(${(f.end - f.start + 1).toLocaleString()} bp, ${strand})`);
  add("종류", f.type);
  add("색", f.color);
  if (f.segments.length > 1) {
    add("조각", f.segments.map((sg) => `${sg.start}–${sg.end}`).join(", "));
  }
  for (const [key, value] of Object.entries(f.notes || {})) {
    if (value) add(key, value);
  }
  box.append(dl);
  if (f.translation) {
    box.append(el("div", { class: "muted", style: "margin-top:.4rem",
      text: `번역 (${f.translation.replace(/\*$/, "").length} aa)` }));
    box.append(el("div", { class: "aa", text: f.translation }));
  }
  return box;
}

$("btn-add-feature").onclick = async () => {
  try {
    setState(await api("/api/features", { action: "add", feature: {
      name: $("nf-name").value || "new feature", type: $("nf-type").value || "misc_feature",
      directionality: +$("nf-dir").value, start: +$("nf-start").value,
      end: +$("nf-end").value, color: $("nf-color").value } }));
    say("feature를 추가했습니다.");
  } catch (err) { say(err.message, true); }
};

/* -------------------------------------------------------------- primers */
async function renderPrimers() {
  const tbody = $("primer-table").querySelector("tbody");
  tbody.innerHTML = "";
  if (!state.primers.length) {
    tbody.append(el("tr", {}, el("td", { colspan: 7, class: "muted",
      text: "저장된 프라이머가 없습니다." })));
    return;
  }
  let analysis = [];
  try {
    const res = await api("/api/pcr", { primers: state.primers.map((p) => ({ name: p.name, sequence: p.sequence })),
                                        conditions: conditions() });
    analysis = res.primers || [];
  } catch (_) { /* Tm 계산 실패는 표에서 비워 둔다 */ }

  state.primers.forEach((p, idx) => {
    const a = analysis[idx] || {};
    const name = el("input", { value: p.name });
    const seq = el("input", { class: "mono", value: p.sequence });
    const save = async () => {
      try {
        setState(await api("/api/primers", { action: "update", index: idx,
          primer: { name: name.value, sequence: seq.value, description: p.description } }));
        say("프라이머를 수정했습니다.");
      } catch (err) { say(err.message, true); }
    };
    name.addEventListener("change", save);
    seq.addEventListener("change", save);
    const b = a.binding;
    tbody.append(el("tr", {}, [
      el("td", {}, name),
      el("td", { class: "seqcell" }, seq),
      el("td", { text: a.length ?? p.sequence.length }),
      el("td", { text: a.gc !== undefined ? a.gc.toFixed(1) : "–" }),
      el("td", { text: a.tm_anneal != null ? `${a.tm_anneal} °C` : "–" }),
      el("td", { text: b ? `${b.start.toLocaleString()}–${b.end.toLocaleString()} ` +
        `(${b.strand === 0 ? "top →" : "bottom ←"}${b.tail_mismatches ? `, tail mismatch ${b.tail_mismatches}` : ""})`
        : "찾지 못함" }),
      el("td", {}, [
        el("button", { class: "btn small", text: "PCR에 쓰기", onclick: () => {
          const side = b && b.strand === 1 ? "rev" : "fwd";
          $(`pcr-${side}-name`).value = p.name;
          $(`pcr-${side}-seq`).value = p.sequence;
          switchTab("pcr");
        } }),
        el("button", { class: "btn small danger", text: "삭제", onclick: async () => {
          if (!await askYesNo(`${p.name} 프라이머를 삭제할까요?`)) return;
          try { setState(await api("/api/primers", { action: "delete", index: idx }));
            say("삭제했습니다."); } catch (err) { say(err.message, true); }
        } }),
      ]),
    ]));
  });
}

$("btn-add-primer").onclick = async () => {
  try {
    setState(await api("/api/primers", { action: "add",
      primer: { name: $("np-name").value || "new primer", sequence: $("np-seq").value } }));
    $("np-name").value = ""; $("np-seq").value = "";
    say("프라이머를 추가했습니다.");
  } catch (err) { say(err.message, true); }
};

function fillPrimerPickers() {
  for (const side of ["fwd", "rev"]) {
    const sel = $(`pcr-${side}-pick`);
    sel.innerHTML = "";
    sel.append(el("option", { value: "", text: "저장된 프라이머에서 선택…" }));
    state.primers.forEach((p, i) => sel.append(el("option", { value: String(i), text: p.name })));
    sel.onchange = () => {
      const p = state.primers[+sel.value];
      if (!p) return;
      $(`pcr-${side}-name`).value = p.name;
      $(`pcr-${side}-seq`).value = p.sequence;
    };
  }
}

/* ------------------------------------------------------------------ pcr */
function conditions() {
  return {
    primer_conc_nM: +$("c-primer").value,
    na_mM: +$("c-na").value,
    mg_mM: +$("c-mg").value,
    dntp_mM: +$("c-dntp").value,
    ta_offset: +$("c-offset").value,
    extension_s_per_kb: +$("c-ext").value,
    cycles: +$("c-cycles").value,
    reaction_uL: +$("c-volume").value,
  };
}

const fmtTime = (s) => s == null ? "∞"
  : s >= 60 ? `${Math.floor(s / 60)}분${s % 60 ? ` ${s % 60}초` : ""}` : `${s}초`;

$("btn-pcr").onclick = async () => {
  const primers = [
    { name: $("pcr-fwd-name").value || "forward", sequence: $("pcr-fwd-seq").value },
    { name: $("pcr-rev-name").value || "reverse", sequence: $("pcr-rev-seq").value },
  ].filter((p) => p.sequence.trim());
  if (!primers.length) { say("프라이머 서열을 입력하세요.", true); return; }
  try {
    const res = await api("/api/pcr", { primers, conditions: conditions(),
                                        ignore_template: $("c-ignore-template").checked });
    renderPcr(res);
    say("계산했습니다.");
  } catch (err) { say(err.message, true); }
};

function renderPcr(res) {
  const out = $("pcr-result");
  out.innerHTML = "";

  for (const p of res.primers) {
    const kv = el("dl", { class: "kv" });
    const add = (k, v) => { kv.append(el("dt", { text: k }), el("dd", { text: v })); };
    add("길이", `${p.length} nt`);
    add("GC", `${p.gc} %`);
    add("Tm (annealing 부분)", p.tm_anneal != null ? `${p.tm_anneal} °C` : "–");
    add("Tm (전체 길이)", p.tm_full != null ? `${p.tm_full} °C` : "–");
    if (p.tail) add("5' tail", `${p.tail.length} nt · ${p.tail}`);
    if (p.binding) {
      add("결합 위치", `${p.binding.start.toLocaleString()}–${p.binding.end.toLocaleString()} ` +
        `(${p.binding.strand === 0 ? "top strand →" : "bottom strand ←"})`);
      add("주형 일치", `${p.binding.matched_len} nt 완전일치` + (p.binding.tail_mismatches ? `, tail 불일치 ${p.binding.tail_mismatches} nt` : ""));
    }
    const card = el("div", { class: "card" }, [
      el("h3", { text: p.name }),
      el("div", { class: "mono muted", style: "overflow-wrap:anywhere;margin-bottom:.5rem",
                  text: `5'-${p.sequence}-3'` }),
      kv,
    ]);
    if (p.warnings.length) {
      card.append(el("ul", { class: "warnlist" }, p.warnings.map((w) => el("li", { text: w }))));
    }
    out.append(card);
  }

  if (!res.program) {
    out.append(el("div", { class: "card wide" }, [
      el("h3", { text: "PCR 프로그램" }),
      el("ul", { class: "notelist" }, (res.notes || []).map((n) => el("li", { text: n }))),
    ]));
    appendAssumptions(out, res.assumptions);
    return;
  }

  const summary = el("dl", { class: "kv" });
  const addS = (k, v) => summary.append(el("dt", { text: k }), el("dd", { text: v }));
  addS("모드", res.mode === "whole_plasmid"
    ? "whole-plasmid site-directed mutagenesis" : "일반 증폭 (amplicon)");
  addS("예상 산물", res.product_length ? `${res.product_length.toLocaleString()} bp` : "계산 불가");
  addS("Annealing", `${res.annealing_temp} °C`);
  const summaryCard = el("div", { class: "card" }, [
    el("h3", { text: "요약" }),
    el("div", { class: "big", text: `Ta ${res.annealing_temp} °C` }),
    summary,
  ]);
  if (res.notes && res.notes.length) {
    summaryCard.append(el("ul", { class: "notelist" }, res.notes.map((n) => el("li", { text: n }))));
  }
  out.append(summaryCard);

  const rows = res.program.map((s) => el("tr", {}, [
    el("td", { text: s.name }),
    el("td", { text: `${s.temp} °C` }),
    el("td", { text: fmtTime(s.time_s) }),
    el("td", { text: s.cycles > 1 ? `${s.cycles} 사이클` : "1회" }),
  ]));
  const prog = el("div", { class: "card" }, [
    el("h3", { text: "싸이클링 프로그램" }),
    el("table", { class: "grid" }, [
      el("thead", {}, el("tr", {}, [el("th", { text: "단계" }), el("th", { text: "온도" }),
        el("th", { text: "시간" }), el("th", { text: "반복" })])),
      el("tbody", {}, rows),
    ]),
  ]);
  if (res.two_stage) {
    prog.append(el("p", { class: "muted", text:
      `2단계 프로그램: ${res.two_stage.stage1.cycles} 사이클 @ ${res.two_stage.stage1.annealing_temp} °C → ` +
      `${res.two_stage.stage2.cycles} 사이클 @ ${res.two_stage.stage2.annealing_temp} °C. ` +
      res.two_stage.stage1.reason }));
  }
  out.append(prog);

  const mixRows = res.mix.rows.map((r) => el("tr", {}, [
    el("td", { text: r.component }),
    el("td", { text: typeof r.volume_uL === "number" ? `${r.volume_uL} µL` : r.volume_uL }),
    el("td", { class: "muted", text: r.final }),
  ]));
  out.append(el("div", { class: "card" }, [
    el("h3", { text: `반응 믹스 (${res.mix.total_uL} µL)` }),
    el("table", { class: "grid" }, [
      el("thead", {}, el("tr", {}, [el("th", { text: "조성" }), el("th", { text: "부피" }),
        el("th", { text: "최종" })])),
      el("tbody", {}, mixRows),
    ]),
    el("p", { class: "muted", text: res.mix.note }),
  ]));

  appendAssumptions(out, res.assumptions);
}

function appendAssumptions(out, assumptions) {
  const kv = el("dl", { class: "kv" });
  const labels = { tm: "Tm 계산", annealing: "Annealing 온도", extension: "신장 시간",
                   cycles: "사이클 수", caveat: "주의" };
  for (const [k, v] of Object.entries(assumptions || {})) {
    kv.append(el("dt", { text: labels[k] || k }), el("dd", { text: v }));
  }
  out.append(el("div", { class: "card wide" }, [
    el("details", {}, [el("summary", { text: "계산 근거와 가정 (펼치기)" }), kv]),
  ]));
}

/* ------------------------------------------------------------- library */
let library = { dir: null, files: [], recent: [] };

async function loadLibrary() {
  try {
    library = await api("/api/library");
  } catch (err) { say(err.message, true); return; }
  if (library.dir) $("lib-path").value = library.dir;
  renderLibrary();
}

function renderLibrary() {
  const tbody = $("library-table").querySelector("tbody");
  tbody.innerHTML = "";
  if (library.error) {
    tbody.append(el("tr", {}, el("td", { colspan: 5, class: "muted", text: library.error })));
  } else if (!library.dir) {
    tbody.append(el("tr", {}, el("td", { colspan: 5, class: "muted",
      text: "폴더를 지정하면 그 안의 .dna 파일이 여기에 나옵니다." })));
  } else if (!library.files.length) {
    tbody.append(el("tr", {}, el("td", { colspan: 5, class: "muted",
      text: "이 폴더에 .dna 파일이 없습니다." })));
  }
  for (const f of library.files) {
    const open = async () => {
      try {
        setState(await api("/api/open", { path: f.path }));
        say(`${f.name}을(를) 열었습니다.`);
        renderLibrary();
        switchTab("map");
      } catch (err) { say(err.message, true); }
    };
    const isOpen = state.loaded && state.path === f.path;
    tbody.append(el("tr", { class: isOpen ? "current" : "" }, [
      el("td", {}, el("button", { class: "btn small", text: f.name, onclick: open })),
      el("td", { class: "muted", text: f.folder || "·" }),
      el("td", { text: `${Math.round(f.size / 1024).toLocaleString()} KB` }),
      el("td", { class: "muted", text: f.modified }),
      el("td", {}, el("button", { class: "btn small", text: isOpen ? "열림" : "열기",
        onclick: open })),
    ]));
  }
  const recent = $("recent-list");
  recent.innerHTML = "";
  for (const r of library.recent || []) {
    recent.append(el("li", {}, el("button", {
      text: `${r.name} — ${r.path}`,
      onclick: async () => {
        try { setState(await api("/api/open", { path: r.path })); say(`${r.name}을(를) 열었습니다.`);
          switchTab("map"); } catch (err) { say(err.message, true); }
      } })));
  }
  if (!(library.recent || []).length) {
    recent.append(el("li", { class: "muted", text: "아직 없습니다." }));
  }
  if (library.truncated) {
    $("lib-note").textContent = `파일이 많아 ${library.files.length}개까지만 표시합니다.`;
  }
}

$("btn-lib-save").onclick = async () => {
  const path = $("lib-path").value.trim();
  if (!path) { say("폴더 경로를 입력하세요.", true); return; }
  try {
    library = await api("/api/library", { path });
    renderLibrary();
    say(`폴더를 기억했습니다: ${library.dir}`);
  } catch (err) { say(err.message, true); }
};
$("btn-lib-refresh").onclick = loadLibrary;
$("btn-lib-clear").onclick = async () => {
  try {
    library = await api("/api/library", { clear: true });
    $("lib-path").value = "";
    renderLibrary();
    say("폴더 지정을 해제했습니다.");
  } catch (err) { say(err.message, true); }
};

/* ----------------------------------------------------------------- misc */
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
}
document.querySelectorAll(".tab").forEach((t) => { t.onclick = () => switchTab(t.dataset.tab); });

$("file-input").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const buf = new Uint8Array(await file.arrayBuffer());
  let bin = "";
  for (const byte of buf) bin += String.fromCharCode(byte);
  try {
    setState(await api("/api/open", { data: btoa(bin), name: file.name }));
    say(`${file.name}을(를) 열었습니다.`);
  } catch (err) { say(err.message, true); }
};

$("btn-save").onclick = async () => {
  const path = await askText("저장할 경로", state.path || "plasmid.dna");
  if (!path) return;
  try { const r = await api("/api/save", { path }); say(`저장했습니다: ${r.saved}`); }
  catch (err) { say(err.message, true); }
};

$("btn-download").onclick = () => { window.location.href = "/api/download"; };

$("btn-edit").onclick = async () => {
  const start = +$("edit-start").value, end = +$("edit-end").value;
  if (!start || !end) { say("편집할 범위를 선택하세요.", true); return; }
  const repl = $("edit-replacement").value.replace(/\s+/g, "");
  if (!await askYesNo(`${start}–${end} (${end - start + 1} bp)를 "${repl || "(삭제)"}"로 바꿀까요?`)) return;
  try {
    setState(await api("/api/sequence/edit", { start, end, replacement: repl }));
    selection = null;
    $("edit-replacement").value = "";
    say("서열을 편집했습니다.");
  } catch (err) { say(err.message, true); }
};

$("btn-goto").onclick = () => {
  const pos = +$("goto-pos").value;
  if (pos >= 1 && pos <= state.length) renderSequence(pos);
};
$("show-revcomp").onchange = () => renderSequence();
$("show-translation").onchange = () => renderSequence();
$("show-feature-track").onchange = () => renderSequence();

api("/api/state").then(setState).catch((err) => say(err.message, true));
loadLibrary();
