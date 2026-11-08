"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import "./ShadowGauge.css";
import SAMPLE from "./sample.js";

/* ====================================================================
   BACKEND CONTRACT  (see app/main.py)
   GET /api/v1/datasets                 -> [{ name, path, has_answer_key }, ...]
   GET /api/v1/datasets/<name>/dashboard -> { now_ts, now_unix, time_range, systems:[...],
                                             facilities:[...], alerts:[...], emergency_trucking, ... }
   Field names follow the challenge data files (network.json / ops.json / telemetry.csv).
   Every number on the page comes from that response; norm() maps it onto the drawing.
   The page always shows the latest reading of the selected dataset.
   Open the page with ?sample=1 to test the UI without a backend (sample.js is a real response).
==================================================================== */
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const POLL_MS = 5000;          // refresh interval

/* ---------- helpers (all times shown in UTC, like the data) ---------- */
const D = x => new Date(x);
const hm = x => (x ? D(x).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }) : "—");
const asOfFmt = x => D(x).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }) + " UTC";
const plusMin = (iso, m) => new Date(D(iso).getTime() + m * 60000).toISOString();
const minBetween = (a, b) => Math.round((D(a) - D(b)) / 60000);
const dur = m => (m == null ? "—" : `${Math.floor(Math.max(0, m) / 60)}h ${String(Math.max(0, m) % 60).padStart(2, "0")}m`);
const money = n => (n == null ? "—" : "$" + Math.round(n).toLocaleString());
const num = n => (n == null ? "—" : Math.round(n).toLocaleString());

/* Usual alert colors, used everywhere (alerts, map, schematic, legend):
   pump failure = red (critical), leak = orange (urgent), worn pump = amber (watch), normal = green.
   Water itself is always the same blue. */
const COLORS = { ok: "#4fe0a0", idle: "#7d8fb0", worn: "#ffc233", failed: "#ff4d4d", leak: "#ff7a29" };
const TYPE_COLOR = { pump_failure: COLORS.failed, leak: COLORS.leak, pump_wear: COLORS.worn };
const SEVERITY = { critical: "CRITICAL", high: "URGENT", watch: "WATCH" };
const TITLES = { pump_failure: "Complete pump failure", pump_wear: "Pump wear", leak: "Pipeline leak" };
// Backend categories (docs/SPEC.md) -> the page's issue types.
const CATEGORY = { pump_failure: "pump_failure", pipeline_leak: "leak", pump_degradation: "pump_wear" };
// Network map: one tint per system (rings, feed lines, disposal site).
const SYS_TINT = ["#2fd6e6", "#b06cff", "#e879f9", "#7aa2ff", "#5eead4"];

/* One open issue (backend event) in the shape the page needs. */
function mkIssue(ev, f, nowTs) {
  const type = CATEGORY[ev.category] ?? null;
  const htl = ev.hours_to_limit?.p50, rep = ev.repair_remaining_h;
  // A countdown only matters if the tank reaches shutdown before the pump is repaired.
  const beforeRepair = type === "pump_failure" && htl != null && (rep == null || htl < rep);
  return {
    ev, type,
    key: ev.event_id ?? `${f.id}:${ev.category}`,
    facId: f.id,
    severity: ev.severity === "critical" && !beforeRepair ? "high" : ev.severity ?? null,
    rank: ev.rank ?? null,
    startedAt: ev.onset_ts ?? null,
    shutdownAt: beforeRepair ? plusMin(nowTs, htl * 60) : null,
    repairEta: rep != null ? plusMin(nowTs, rep * 60) : null,
    doNothingCost: ev.do_nothing?.cost ?? null,
  };
}

/* Turn one backend facility into what the drawing needs. `order` = its place in the
   backend's alerts list (already sorted: soonest shutdown first, then leaks / worn pumps). */
function norm(f, order, nowTs) {
  const p = f.pump || {}, pl = f.pipeline || {}, t = f.tank || {};
  // every open issue at this facility, most urgent first
  const events = (f.issues || []).map(ev => mkIssue(ev, f, nowTs)).filter(i => i.type)
    .sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity));
  const has = k => events.some(i => i.type === k);
  // Pump status code 0 is normal on/off cycling (SPEC), not a fault: show it as "idle".
  let pumpStatus = p.health === "failed" ? "failed" : p.health === "degraded" ? "worn"
    : p.state === "stopped" ? "idle" : "ok";
  if (has("pump_failure")) pumpStatus = "failed";
  else if (has("pump_wear")) pumpStatus = "worn";
  return {
    ...f,
    name: f.id,
    order,
    wellsProducing: (f.wells || []).filter(w => w.status === 1).length,
    wellsTotal: (f.wells || []).length,
    tankCapacityBbl: t.capacity_bbl,
    tank: { id: t.id, levelPct: t.level_pct, shutdownPct: t.shutdown_pct, warningPct: t.warning_pct, inflowBpd: f.inflow_bpd },
    pump: { id: p.id, status: pumpStatus, flowBpd: p.flow_bpd, normalFlowBpd: p.max_flow_bpd,
            dischargePsi: p.discharge_psi, startLevelPct: p.start_level_pct, stopLevelPct: p.stop_level_pct },
    pipe: { id: pl.id, status: pl.health === "leak" || has("leak") ? "leak" : "ok", pressurePsi: pl.pressure_psi,
            normalPressurePsi: pl.normal_running_pressure_psi, receiveFlowBpd: pl.receive_flow_bpd,
            expectedReceiveBpd: p.flow_bpd },        // conservation: what the pump sends should arrive
    type: events[0]?.type ?? null,
    events,
  };
}

/* "Do this now" checklist for one issue, from the backend's recommended_actions.
   steps = things to do (each with the time to do it); notes = context, not a task. */
function planSteps(i, asOf, truckCapBbl) {
  const ev = i.ev;
  const steps = [], notes = [];
  for (const a of ev.recommended_actions || []) {
    if (a.type === "dispatch_truck") {
      const times = (ev.truck_arrivals_min || []).map(m => hm(plusMin(asOf, m))).join(", ");
      const each = truckCapBbl != null ? ` Each arrival removes ${num(a.trucks * truckCapBbl)} bbl.` : "";
      const trucks = `${a.trucks} truck${a.trucks > 1 ? "s" : ""}`;
      const trips = `${a.trips_per_truck} trip${a.trips_per_truck > 1 ? "s" : ""}${a.trucks > 1 ? " each" : ""}`;
      steps.push({ text: `Send ${trucks}, ${trips}. Arriving ${times}.${each}`, at: asOf });
    } else if (a.type === "shut_in_wells") {
      steps.push({ text: `Shut in ${a.wells.join(", ")} until the pump is repaired.`, at: plusMin(asOf, a.start_after_min || 0) });
    } else if (a.type === "field_inspection") {
      steps.push({ text: `Send an inspector to ${a.asset_id}.`, at: asOf });
    } else if (a.type === "none") {
      notes.push(ev.do_nothing?.shutdown_after_min == null
        ? "No action needed: the tank stays below shutdown until the repair."
        : "Let the automatic shut-in happen: every alternative costs more.");
    }
  }
  if (ev.do_nothing?.shutdown_after_min != null && ev.category === "pump_failure") {
    notes.push(`Doing nothing: tank reaches shutdown at ${hm(plusMin(asOf, ev.do_nothing.shutdown_after_min))} and all wells stop until the repair.`);
  }
  return { steps, notes, cost: ev.est_cost ?? null, nothing: ev.do_nothing?.cost ?? null };
}
const facColor = f => TYPE_COLOR[f.type] ?? COLORS.ok;

/* One line with the number that matters most for each alert. */
function alertLine(i, asOf) {
  const ev = i.ev || {}, imp = ev.impact || {};
  if (i.type === "pump_failure") {
    if (ev.hours_to_limit?.p50 === 0) return "Tank already at shutdown · wells off until repair";
    if (!i.shutdownAt) return "Pump down · tank holds until repair";
    return `shutdown in ${dur(minBetween(i.shutdownAt, asOf))}${ev.est_cost != null ? ` · plan ${money(ev.est_cost)}` : ""}${ev.savings > 0 ? `, saves ${money(ev.savings)}` : ""}`;
  }
  if (i.type === "leak") return imp.lost_bpd_while_pumping != null ? `~${num(imp.lost_bpd_while_pumping)} bpd lost while pumping · −${num(imp.pressure_drop_psi)} psi` : "water missing at disposal";
  if (i.type === "pump_wear") return imp.flow_pct_of_rated != null ? `pumping ${imp.flow_pct_of_rated}% of rated${imp.keeps_up === false ? " · can't keep up with wells" : imp.keeps_up ? " · still keeps up" : ""}` : "flow below rated";
  return "";
}
const short = id => id.replace(/_FACILITY_/, "-");

/* ---------- small pieces ---------- */
/* Label bubble sized to its text and kept inside the drawing (0..960); text is squeezed
   only if an unusually long asset id would not fit. */
const CHAR_W = 6.6, CHIP_PAD = 26;
const Chip = ({ x, text, maxW = 300 }) => {
  const need = text.length * CHAR_W + CHIP_PAD, w = Math.min(maxW, need);
  const cx = Math.min(952 - w / 2, Math.max(8 + w / 2, x));
  return (
    <g>
      <rect x={cx - w / 2} y="10" width={w} height="26" rx="13" className="chip-r" />
      <text x={cx} y="27" textAnchor="middle" className="chip-t"
        {...(need > maxW ? { textLength: w - CHIP_PAD, lengthAdjust: "spacingAndGlyphs" } : {})}>{text}</text>
    </g>
  );
};

/* Water: one look everywhere (pipes, the drop into the tank, the tank itself).
   speed "" = full flow, "slow"/"slower"/"crawl" = less flow, "still" = no flow (shown gray).
   Drawn in the drawing's own coordinates and clipped, so the wave pattern runs on unbroken
   from one pipe section to the next. */
const Stream = ({ x, y, w, h, speed = "" }) => {
  const id = useId().replace(/:/g, "");
  return (
    <g clipPath={`url(#${id})`}>
      <clipPath id={id}><rect x={x} y={y} width={w} height={h} /></clipPath>
      <rect className={`stream ${speed}`} x={x - 40} y={y} width={w + 40} height={h} fill="url(#sg-wv)" />
    </g>
  );
};
/* the same water falling straight down (pattern turned 90°) */
const Fall = ({ x, y, w, h, speed = "" }) => {
  const id = useId().replace(/:/g, "");
  const hh = Math.max(0, h);
  return (
    <g clipPath={`url(#${id})`}>
      <clipPath id={id}><rect x={x} y={y} width={w} height={hh} /></clipPath>
      <rect className={`stream-v ${speed}`} x={x} y={y - 40} width={w} height={hh + 40} fill="url(#sg-wv-v)" />
    </g>
  );
};
/* pipe flow speed class from a 0..1+ flow ratio */
const speedFor = r => (!(r > 0) ? "still" : r > 0.8 ? "" : r > 0.5 ? "slow" : r > 0.2 ? "slower" : "crawl");

/* Pump spin speed (1 = rated flow). Follows the real flow: a stopped or failed pump doesn't
   spin, a leaking pipeline's pump still runs at full speed, and a worn pump's 5-15 % loss is
   exaggerated 4x so it's visible (the label shows the true %). */
function spinFor(pump) {
  if (!pump || !pump.normalFlowBpd || !(pump.flowBpd > 0)) return 0;
  const r = pump.flowBpd / pump.normalFlowBpd;
  return pump.status === "worn" ? Math.max(0.25, 1 - 4 * (1 - r)) : Math.min(1.1, r);
}

/* Network map: real lat/lon, scaled to the box. Each facility feeds its system's disposal site.
   Small map: opens zoomed in on the cluster (system) of the facility shown in the main drawing.
   Lines and labels only for that system; other systems are faint dots; labels show on hover,
   for the selected facility, and for facilities with a problem.
   Zoom (+/−) keeps the selected facility in place, ◀ ▶ (or dragging) moves the map, Fit shows
   the whole network. big = the expanded map, which starts fitted and draws everything.
   The parent remounts it (key) when the selected facility changes, so the view resets. */
const MAX_ZOOM = 16;
const FIT = { z: 1, cx: 50, cy: 50 };
function NetMap({ facs, systems, cur, onPick, big = false }) {
  const sysIds = systems.map(s => s.id);
  const tint = id => SYS_TINT[Math.max(0, sysIds.indexOf(id)) % SYS_TINT.length];
  const pts = [...facs.map(f => [f.lon, f.lat]), ...systems.map(s => [s.disposal_site?.lon, s.disposal_site?.lat])]
    .filter(([x, y]) => x != null && y != null);
  const [x0, x1] = [Math.min(...pts.map(p => p[0])), Math.max(...pts.map(p => p[0]))];
  const [y0, y1] = [Math.min(...pts.map(p => p[1])), Math.max(...pts.map(p => p[1]))];
  const toMap = (lon, lat) => [8 + 84 * (x1 > x0 ? (lon - x0) / (x1 - x0) : 0.5), 8 + 84 * (y1 > y0 ? (y1 - lat) / (y1 - y0) : 0.5)];
  const swd = Object.fromEntries(systems.filter(s => s.disposal_site?.lat != null)
    .map(s => [s.id, toMap(s.disposal_site.lon, s.disposal_site.lat)]));
  const focus = sid => big || sid === cur.system_id;
  const here = cur.lat != null ? toMap(cur.lon, cur.lat) : [50, 50];

  /* default view: tight around the selected facility's cluster (its facilities + disposal site) */
  const [view, setView] = useState(() => {
    if (big) return FIT;
    const cl = [...facs.filter(f => f.system_id === cur.system_id && f.lat != null).map(f => toMap(f.lon, f.lat)),
      ...(swd[cur.system_id] ? [swd[cur.system_id]] : [])];
    if (!cl.length) return FIT;
    const xs = cl.map(p => p[0]), ys = cl.map(p => p[1]);
    const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
    const z = Math.min(MAX_ZOOM, Math.max(1, Math.min(64 / Math.max(w, 1), 64 / Math.max(h, 1))));
    return { z, cx: (Math.max(...xs) + Math.min(...xs)) / 2, cy: (Math.max(...ys) + Math.min(...ys)) / 2 };
  });
  const scr = ([x, y]) => [50 + (x - view.cx) * view.z, 50 + (y - view.cy) * view.z];   // map % -> box %
  const zoom = k => setView(v => {
    const z = Math.min(MAX_ZOOM, Math.max(1, v.z * k));
    // keep the selected facility at the same spot on screen while zooming
    return { z, cx: here[0] + (v.cx - here[0]) * (v.z / z), cy: here[1] + (v.cy - here[1]) * (v.z / z) };
  });
  const pan = dir => setView(v => ({ ...v, cx: v.cx + (dir * 25) / v.z }));

  /* drag to move the map (like an online map); a drag doesn't count as a click on a facility */
  const box = useRef(null), drag = useRef(null);
  const down = e => {
    if (e.button !== 0 || e.target.closest(".mapctl")) return;
    const r = box.current.getBoundingClientRect();
    drag.current = { x: e.clientX, y: e.clientY, v: view, w: r.width, h: r.height, moved: false };
    const move = ev => {
      const d = drag.current; if (!d) return;
      const dx = ev.clientX - d.x, dy = ev.clientY - d.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) d.moved = true;
      setView({ ...d.v, cx: d.v.cx - (100 * dx) / d.w / d.v.z, cy: d.v.cy - (100 * dy) / d.h / d.v.z });
    };
    const up = () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      setTimeout(() => { drag.current = null; }, 0);
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  const pick = id => { if (!drag.current?.moved) onPick(id); };

  return (
    <div className={`map ${big ? "big" : ""}`} ref={box} onPointerDown={down}>
      <svg className="links" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        {facs.filter(f => focus(f.system_id) && swd[f.system_id] && f.lat != null).map(f => {
          const [x, y] = scr(toMap(f.lon, f.lat)), [sx, sy] = scr(swd[f.system_id]);
          return <line key={f.id} x1={x} y1={y} x2={sx} y2={sy} stroke={tint(f.system_id)} />;
        })}
      </svg>
      {systems.filter(s => swd[s.id]).map(s => { const [x, y] = scr(swd[s.id]); return (
        <div key={s.id} className={`node swd ${focus(s.id) ? "lab" : "faint"}`} style={{ left: `${x}%`, top: `${y}%`, "--c": tint(s.id), "--t": tint(s.id) }} title={s.disposal_site.id}>
          <i /><span className="nl">{s.id} SWD</span>
        </div>); })}
      {facs.map(f => {
        const [x, y] = scr(toMap(f.lon, f.lat));
        const problem = !!f.type, on = focus(f.system_id), isCur = f.id === cur.id;
        const cls = ["node", "click", isCur && "cur", !on && !problem && "faint",
          f.pump.status === "failed" && "pulse", (big || (on && (problem || isCur || view.z >= 3))) && "lab"].filter(Boolean).join(" ");
        return (
          <div key={f.id} className={cls} style={{ left: `${x}%`, top: `${y}%`, "--c": facColor(f), "--t": tint(f.system_id) }} onClick={() => pick(f.id)} title={f.id}>
            <i /><span className="nl">{short(f.id)}</span>
          </div>);
      })}
      <div className="mapctl">
        <button type="button" onClick={() => zoom(1.6)} aria-label={`Zoom in on ${cur.id}`} title={`Zoom in on ${short(cur.id)}`}>+</button>
        <button type="button" onClick={() => zoom(1 / 1.6)} aria-label="Zoom out" title="Zoom out">−</button>
        <button type="button" onClick={() => pan(-1)} aria-label="Move map left" title="Move left">◀</button>
        <button type="button" onClick={() => pan(1)} aria-label="Move map right" title="Move right">▶</button>
        <button type="button" className="fit" onClick={() => setView(FIT)} title="Show the whole network">Fit</button>
      </div>
      <div className="mapz">{view.z.toFixed(1)}×</div>
    </div>
  );
}

/* Plain-language summary of the main drawing for field workers:
   what each part is doing right now, and why the system reached its assessment. */
function FacilitySummary({ fac, asOf, onOpen }) {
  const { tank, pump, pipe } = fac;
  const pct = tank.levelPct != null ? Math.round(tank.levelPct) : null;
  const cap = fac.tankCapacityBbl;
  const vol = pct != null && cap != null ? (tank.levelPct * cap) / 100 : null;
  const pumpPct = pump.normalFlowBpd && pump.flowBpd > 0 ? Math.round((pump.flowBpd / pump.normalFlowBpd) * 100) : null;
  const running = pump.flowBpd > 0;
  const ago = t => { const m = minBetween(asOf, t); return m < 60 ? `${m} min ago` : `${dur(m)} ago`; };

  const headline = !fac.events.length
    ? `Everything at ${fac.id} is working normally.`
    : fac.events.length === 1 ? `1 problem at ${fac.id}: ${TITLES[fac.events[0].type].toLowerCase()}.`
    : `${fac.events.length} problems at ${fac.id}: ${fac.events.map(i => TITLES[i.type].toLowerCase()).join(" and ")}.`;

  const pumpText = pump.status === "failed"
    ? "The pump has stopped because of a fault. No water is leaving the tank, so the tank keeps filling up."
    : pump.status === "idle"
      ? `The pump is resting. That is normal: it switches on by itself when the tank reaches ${pump.startLevelPct ?? "its start level"}%${pump.stopLevelPct != null ? ` and off again at ${pump.stopLevelPct}%` : ""}.`
      : pump.status === "worn"
        ? (pumpPct != null
          ? `The pump is running but only moving ${pumpPct}% of what it is built for (${num(pump.flowBpd)} of ${num(pump.normalFlowBpd)} barrels a day).`
          : `The pump is resting right now. When it runs, it moves less water than it is built for (see below).`)
        : `The pump is running normally, moving ${num(pump.flowBpd)} barrels a day (it is built for ${num(pump.normalFlowBpd)}).`;

  const pipeText = !running
    ? `No water is being pumped right now, so the pipeline is quiet (${num(pipe.pressurePsi)} psi).`
    : `The pipeline carries the water to the disposal well. Pressure is ${num(pipe.pressurePsi)} psi${pipe.normalPressurePsi != null ? ` (normal while pumping: about ${num(pipe.normalPressurePsi)} psi)` : ""}, and ${num(pipe.receiveFlowBpd)} barrels a day are arriving.${pipe.status === "leak" ? " Some of the water is not arriving: see below." : ""}`;

  /* plain-English version of each detector rule, filled with this issue's own numbers */
  const why = i => {
    const ev = i.ev, imp = ev.impact || {};
    if (i.type === "pump_failure") {
      const toShut = i.shutdownAt ? minBetween(i.shutdownAt, asOf) : null;
      return {
        how: `Every few minutes the pump reports one of three states: off, running, or fault. Since ${hm(i.startedAt)} it has been reporting “fault”. A pump in fault cannot move any water, so everything the wells produce (${num(tank.inflowBpd)} barrels a day) stays in the tank.`,
        means: ev.hours_to_limit?.p50 === 0
          ? `The tank has already reached its ${tank.shutdownPct}% shutdown level, so the wells are shut off until the pump is repaired${i.repairEta ? ` (around ${hm(i.repairEta)})` : ""}.`
          : toShut != null
            ? `At this rate the tank reaches its ${tank.shutdownPct}% shutdown level at ${hm(i.shutdownAt)} (in ${dur(toShut)}). The repair is not expected until about ${hm(i.repairEta)}, so the tank would fill first. That is why there is a countdown and an action plan.`
            : `The repair should be finished around ${hm(i.repairEta)}, before the tank fills up, so no shutdown is expected. Keep an eye on it.`,
      };
    }
    if (i.type === "leak") return {
      how: `Whatever the pump pushes into the pipeline should come out at the disposal end. The system compares both meters every hour. Here about ${imp.lost_pct ?? "—"}% of the water goes missing (roughly ${num(imp.lost_bpd_while_pumping)} barrels a day while pumping), and at the same time the pipeline pressure is ${num(imp.pressure_drop_psi)} psi lower than normal. It is only called a leak when both signs show up together, because one meter on its own can drift or be noisy.`,
      means: "Water is escaping from the pipeline. It does not fill the tank, so there is no shutdown countdown, but someone should go and inspect the pipeline.",
    };
    return {
      how: `The system compares how much the pump moves while it is running with what it is built to move (${num(imp.rated_bpd ?? pump.normalFlowBpd)} barrels a day). It has been averaging ${imp.flow_pct_of_rated ?? pumpPct ?? "—"}% of that. The gap is bigger than normal meter noise and has lasted for hours, which is how a worn pump looks.`,
      means: imp.keeps_up === false
        ? "The pump can no longer keep up with what the wells produce, so the tank will slowly rise. Plan a repair soon."
        : "The pump still keeps up with the wells, so this is not urgent. Plan an inspection before it gets worse.",
    };
  };

  return (
    <section className="card box summ">
      <h3>Facility summary <span>WHAT THE DRAWING SHOWS · {hm(asOf)} UTC</span></h3>
      <p className="hl" style={{ color: fac.events.length ? TYPE_COLOR[fac.events[0].type] : COLORS.ok }}>{headline}</p>

      <div className="parts">
        <div><b>1 · Water tank</b><p>Water from {fac.wellsProducing} of {fac.wellsTotal} wells comes in at {num(tank.inflowBpd)} barrels a day. The tank is {pct ?? "—"}% full{vol != null ? ` (${num(vol)} of ${num(cap)} barrels)` : ""}. If it reaches {tank.shutdownPct ?? "—"}%, the wells shut off automatically and oil stops flowing.</p></div>
        <div><b>2 · Transfer pump</b><p>{pumpText}</p></div>
        <div><b>3 · Disposal pipeline</b><p>{pipeText}</p></div>
      </div>

      {/* collapsed by default; click to see the full reasoning */}
      <details className="whyd" key={fac.id}>
        <summary>
          <h4>Why the system reached this assessment</h4>
          <span className="more">{fac.events.length ? `How it found ${fac.events.length === 1 ? "this problem" : "these problems"}` : "What it checked"} · <span className="sh">show details</span><span className="hd">hide details</span></span>
        </summary>
      {fac.events.length === 0 ? (
        <>
          <p className="mu2">No problems were found. Every reading, the system runs these checks on this facility:</p>
          <ul className="checks">
            <li><i>✓</i><div><b>Is the pump reporting a fault?</b> No. The pump is {pump.status === "idle" ? "resting, which is normal" : "running"}.</div></li>
            <li><i>✓</i><div><b>Is water going missing in the pipeline?</b> {running
              ? `No. The water arriving at disposal (${num(pipe.receiveFlowBpd)} barrels a day) matches what the pump sends (${num(pump.flowBpd)}), and pressure (${num(pipe.pressurePsi)} psi) is normal.`
              : "This can only be measured while the pump runs. The last time it ran, nothing was missing."}</div></li>
            <li><i>✓</i><div><b>Is the pump wearing out?</b> {pumpPct != null ? `No. It is moving ${pumpPct}% of what it is built for, which is within normal meter noise.` : "This is measured while the pump runs. Its recent runs were normal."}</div></li>
            <li><i>✓</i><div><b>Is the tank close to shutdown?</b> No. It is {pct ?? "—"}% full and shutdown is at {tank.shutdownPct ?? "—"}%.</div></li>
          </ul>
          <p className="mu2">Alarm levels are learned from this dataset’s own normal readings, so ordinary noise in the meters does not set off false alarms.</p>
        </>
      ) : fac.events.map(i => { const w = why(i); return (
        <div key={i.key} className="whyi" style={{ "--c": TYPE_COLOR[i.type] }}>
          <div className="wt"><b>{TITLES[i.type]}</b> · {i.ev.asset_id} <span>found at {hm(i.startedAt)} ({ago(i.startedAt)}){i.ev.confidence != null ? ` · ${Math.round(i.ev.confidence * 100)}% sure` : ""}</span></div>
          <p><b>How the system knows:</b> {w.how}</p>
          <p><b>What it means:</b> {w.means}</p>
          {i.ev.evidence?.length > 0 && <>
            <p><b>The sensor readings behind it:</b></p>
            <ul>{i.ev.evidence.map((e, k) => <li key={k}>{e}</li>)}</ul>
          </>}
          <button type="button" className="howb" onClick={() => onOpen(i)}>Open the action plan</button>
        </div>); })}
      </details>
    </section>
  );
}

/* Operator guide (pop-up): what an operator needs to read this screen and act on it.
   Numbers come from the selected dataset. */
function OperatorGuide({ snap, onClose }) {
  const pr = snap.prices || {}, tr = snap.emergency_trucking || {}, t0 = snap.facilities?.[0]?.tank || {};
  const repair = snap.expected_repair_hours?.pump_failure;
  const sw = (c, round) => <i style={{ background: c, borderRadius: round ? "50%" : 2 }} />;
  return (
    <div className="ov" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="pop how" role="dialog" aria-modal="true" aria-label="Operator guide">
        <button className="x" onClick={onClose} aria-label="Close">✕</button>
        <div className="mu" style={{ color: "var(--cy)" }}>OPERATOR GUIDE</div>
        <h2>Reading this screen and what to do</h2>
        <p className="lead">Every well brings up water along with oil and gas. The water collects in a tank, and a pump sends it down a pipeline to a disposal well. If a tank reaches its shutdown level ({t0.shutdown_pct ?? "—"}%), the wells feeding it shut off automatically and oil stops flowing. This screen warns you early and tells you the cheapest way to keep wells producing.</p>
        <ol className="steps">
          <li><b>The drawing</b>
            <span>{sw("#22d3ee")}Blue, moving water: water is flowing through that section. Slower movement means less flow, for example from a worn pump.</span>
            <span>{sw("#5b6478")}Gray pipe: no water is flowing there right now, because the pump is resting or stopped, or nothing is arriving at disposal. It does not mean the water is dirty.</span>
            <span>{sw(COLORS.leak)}Orange pipeline: a leak was detected on it.</span>
            <span>{sw(COLORS.failed)}Red dashed line on the tank: the shutdown level. The water in the tank shows how full it is.</span>
            <span>Water can keep coming in from the wells even while the pump is stopped. That is how a tank fills up.</span>
            <span>Click the flashing <b style={{ display: "inline", color: "var(--tx)" }}>!</b> on the pump or pipeline to open that problem.</span></li>
          <li><b>The three kinds of alerts</b>
            <span>{sw(COLORS.failed, 1)}<b style={{ display: "inline", color: COLORS.failed }}>Pump failure</b>: the pump has stopped and the tank is filling. It is marked CRITICAL when the tank will hit shutdown in under 2 hours, before the repair is done. Follow the action plan.</span>
            <span>{sw(COLORS.leak, 1)}<b style={{ display: "inline", color: COLORS.leak }}>Leak</b>, URGENT: water is escaping from the pipeline. Send someone to inspect it.</span>
            <span>{sw(COLORS.worn, 1)}<b style={{ display: "inline", color: COLORS.worn }}>Worn pump</b>, WATCH: the pump moves less water than it should. Plan an inspection.</span>
            <span>The most urgent alert is always at the top of the list.</span></li>
          <li><b>The countdown</b> For a stopped pump, the screen shows how long until the tank reaches shutdown. A repair usually takes about {repair ?? "—"} hours. If the repair will finish before the tank fills, you will see “Pump down · tank holds until repair” instead of a countdown.</li>
          <li><b>The action plan</b> Click an alert to see what to do, step by step, with the time for each step. Tick the steps off as you go. The plan is the cheapest option among:
            <span>sending vacuum trucks ({money(tr.cost_per_trip)} per trip, {num(tr.truck_capacity_bbl)} barrels each) to empty the tank,</span>
            <span>shutting in some wells for a while (you lose their oil at {money(pr.oil_per_bbl)}/bbl and gas at {money(pr.gas_per_mcf)}/mcf),</span>
            <span>or letting the tank shut down on its own.</span>
            Trucks are shared by all facilities in a system, so the truck card shows how many are still free. “Why this plan” shows the options it beat and what each would cost.</li>
          <li><b>The network map</b> Each dot is a facility, and lines show which disposal site it sends water to. The map starts zoomed in on the facility you are looking at. Use + and − to zoom, ◀ ▶ or drag to move around, and Fit to see the whole network. Failed pumps pulse. Click any dot to switch to that facility.</li>
          <li><b>Switching datasets</b> Use the Dataset menu at the top. The screen dims until the new data arrives.</li>
        </ol>
      </div>
    </div>
  );
}

export default function ShadowGauge() {
  const [datasets, setDatasets] = useState([]);
  const [dataset, setDataset] = useState(null);
  const [snap, setSnap] = useState(null);
  const [error, setError] = useState(null);
  const [selId, setSelId] = useState(null);
  const [selKey, setSelKey] = useState(null);         // which issue the details panel shows
  const [open, setOpen] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [loading, setLoading] = useState(false);      // a new dataset is on its way (old one dimmed)
  const [mapBig, setMapBig] = useState(false);        // expanded network map
  const [guideOpen, setGuideOpen] = useState(false);  // operator guide pop-up
  const [done, setDone] = useState({});               // checked "Do this now" steps, by `${issue}:${step}`

  /* "sample" if the address ends in ?sample=1, otherwise "live" (decided in the browser) */
  const [mode, setMode] = useState(null);
  useEffect(() => { setMode(new URLSearchParams(window.location.search).has("sample") ? "sample" : "live"); }, []);
  const USE_SAMPLE = mode === "sample";

  /* dataset list: every folder the backend found (a `test` folder appears automatically) */
  useEffect(() => {
    if (mode !== "live") return;
    fetch(`${API}/api/v1/datasets`).then(r => r.json()).then(j => {
      const list = (Array.isArray(j) ? j : []).map(d => d.name);
      setDatasets(list);
      // ?dataset=<name> in the address opens that dataset; otherwise test/ if present, else the first.
      const want = new URLSearchParams(window.location.search).get("dataset");
      setDataset(d => (list.includes(d) ? d : list.includes(want) ? want : list.includes("test") ? "test" : list[0] ?? null));
      if (!list.length) setError("the backend found no dataset folders");
    }).catch(e => setError(e.message || "failed"));
  }, [mode]);

  /* switching dataset: the old screen is dimmed behind a spinner until the new one arrives */
  const changeDataset = d => { setOpen(false); setDone({}); setLoading(true); setDataset(d); };

  /* load the dashboard: poll the latest reading */
  useEffect(() => {
    if (!mode) return;
    if (USE_SAMPLE) { setSnap(SAMPLE); return; }
    if (!dataset) return;
    let stop = false;
    const load = async () => {
      try {
        const r = await fetch(`${API}/api/v1/datasets/${encodeURIComponent(dataset)}/dashboard`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const j = await r.json();
        if (!stop) { setSnap(j); setError(null); setLoading(false); }
      } catch (e) { if (!stop) { setError(e.message || "failed"); setLoading(false); } }
    };
    load();
    const t = setInterval(load, POLL_MS);
    return () => { stop = true; clearInterval(t); };
  }, [dataset, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const facs = useMemo(() => {
    if (!snap) return [];
    const order = new Map();
    (snap.alerts || []).forEach((a, i) => { if (!order.has(a.facility_id)) order.set(a.facility_id, i); });
    return (snap.facilities || []).map(f => norm(f, order.get(f.id) ?? Infinity, snap.now_ts));
  }, [snap]);
  /* backend already ranks alerts (SPEC alerts view); keep its order */
  const issueFacs = useMemo(() => facs.filter(f => f.type).sort((a, b) => a.order - b.order), [facs]);
  /* every open issue at every facility (a facility can have more than one) */
  const allIssues = useMemo(() => issueFacs.flatMap(f => f.events)
    .sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity)), [issueFacs]);
  const fac = facs.find(f => f.id === selId) || issueFacs[0] || facs[0];
  useEffect(() => { if (facs.length && !facs.some(f => f.id === selId)) setSelId((issueFacs[0] || facs[0]).id); }, [facs]); // eslint-disable-line

  /* notify when a NEW issue appears (first load of a dataset is silent) */
  const seen = useRef(null);
  useEffect(() => { seen.current = null; }, [dataset]);
  useEffect(() => {
    if (!snap) return;
    const keys = allIssues.map(i => `${i.facId}:${i.type}`);
    if (seen.current) {
      allIssues.filter(i => !seen.current.has(`${i.facId}:${i.type}`)).forEach(i => {
        const text = [i.facId, i.ev.asset_id, TITLES[i.type]].filter(Boolean).join(" · ");
        const id = Date.now() + Math.random();
        setToasts(t => [...t.slice(-3), { id, type: i.type, text }]);
        setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 8000);
        if ("Notification" in window && Notification.permission === "granted") new Notification("ShadowGauge alert", { body: text });
      });
    }
    seen.current = new Set(keys);
  }, [snap]); // eslint-disable-line

  useEffect(() => {
    const esc = e => { if (e.key === "Escape") { setOpen(false); setMapBig(false); setGuideOpen(false); } };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  /* alerts list: show 3 alerts, then scroll inside the card */
  const alList = useRef(null);
  useEffect(() => {
    const el = alList.current;
    if (!el) return;
    const k = el.children;
    el.style.maxHeight = k.length > 3 ? `${k[2].offsetTop + k[2].offsetHeight}px` : "";
  });

  /* pump rotation: speed = real flow / normal flow, eases down on failure */
  const rotor = useRef(null);
  const ratio = useRef(0);
  ratio.current = fac ? spinFor(fac.pump) : 0;
  useEffect(() => {
    let raf, last = performance.now(), ang = 0, cur = ratio.current;
    const tick = t => {
      const dt = Math.min(0.1, (t - last) / 1000); last = t;
      cur += (ratio.current - cur) * Math.min(1, dt * 0.9);
      if (Math.abs(ratio.current - cur) < 0.005) cur = ratio.current;
      ang = (ang + cur * 360 * dt) % 360;
      rotor.current?.setAttribute("transform", `rotate(${ang} 478 264)`);   // eases over ~2 s, so a failure visibly winds down
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  /* ---------- shell shown while loading / on error ---------- */
  const header = (
    <header>
      <div className="logo"><i />SHADOWGAUGE</div>
      <div className="tab">Operations</div>
      <div className="hr">
        {snap && <span className="asof">As of {asOfFmt(snap.now_ts)}</span>}
        <button type="button" className="howb" onClick={() => setGuideOpen(true)}>Operator guide</button>
        <label className="dsel">Dataset
          <select value={dataset ?? ""} onChange={e => changeDataset(e.target.value)} disabled={USE_SAMPLE || !datasets.length}>
            {USE_SAMPLE && <option value="">sample</option>}
            {datasets.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
      </div>
    </header>
  );
  const bg = <div className="bg"><div className="sky" /><div className="stars" /></div>;

  if (!snap || !fac) {
    return (
      <div className="sg">{bg}{header}
        <main><section className="card box" style={{ gridColumn: "1/-1" }}>
          {error
            ? <><b>Can’t reach the backend.</b><div className="mu" style={{ marginTop: 6 }}>Tried {API}/api/v1/datasets{dataset ? `/${dataset}/dashboard` : ""} ({error}). Start the API (uvicorn app.main:app --port 8000), or add ?sample=1 to the page address to preview the layout.</div></>
            : <div className="mu">Loading {dataset ?? "datasets"}…</div>}
        </section></main>
      </div>
    );
  }

  /* ---------- derived values for the selected facility ---------- */
  const { tank, pump, pipe, type } = fac;
  const asOf = snap.now_ts;
  const color = type ? facColor(fac) : COLORS.ok;
  const pct = Math.max(0, Math.min(100, tank.levelPct ?? 0));
  const waterTop = 300 - 1.7 * pct;
  const limitY = tank.shutdownPct != null ? 300 - 1.7 * tank.shutdownPct : null;
  const cap = fac.tankCapacityBbl;
  /* Water moves only where the data says it moves:
     wells -> tank whenever wells produce (even if the pump is broken: that's why the tank fills);
     tank -> pipeline only while the pump runs, at a speed that follows the pump's real flow;
     past a leak, less water arrives (shown one step slower) and drops fall from the pipe. */
  const filling = tank.inflowBpd > 0;
  const inSpeed = filling ? "" : "still";
  const flowing = pump.flowBpd > 0;               // a healthy pump is off about half the time
  const leak = pipe.status === "leak";
  const outSpeed = speedFor(spinFor(pump));
  const SLOWER = { "": "slow", slow: "slower", slower: "crawl", crawl: "crawl", still: "still" };
  /* Gray = no flow in that section: the pump outlet goes gray when the pump isn't moving water,
     the pipeline also when disposal receives zero flow. A leak keeps the pipeline orange. */
  const pipeActive = flowing && pipe.receiveFlowBpd !== 0;
  const pipeSpeed = pipeActive ? outSpeed : "still";
  const afterLeak = leak && pipeActive ? SLOWER[pipeSpeed] : pipeSpeed;
  const pipeFill = leak ? "url(#sg-pipeL)" : pipeActive ? "url(#sg-pipe)" : "url(#sg-pipeD)";
  const pumpAlarm = pump.status === "failed" ? COLORS.failed : pump.status === "worn" ? COLORS.worn : null;
  const pumpPct = pump.normalFlowBpd && pump.flowBpd > 0 ? Math.round((pump.flowBpd / pump.normalFlowBpd) * 100) : null;
  /* status message: "all normal" only when nothing is wrong anywhere */
  const elsewhere = allIssues.filter(i => i.facId !== fac.id).length;
  const more = fac.events.length > 1 ? ` +${fac.events.length - 1}` : "";
  const pill = !type
    ? (elsewhere ? ["ok", `● THIS FACILITY NORMAL · ${elsewhere} ISSUE${elsewhere > 1 ? "S" : ""} NEED${elsewhere > 1 ? "" : "S"} ATTENTION ELSEWHERE`] : ["ok", "● ALL FACILITIES NORMAL"])
    : type === "pump_failure" ? ["crit", `● TRANSFER INTERRUPTED${more}`] : type === "leak" ? ["leak", `● PIPELINE LEAK${more}`] : ["warn", `● PUMP WORN${more}`];
  const pumpLine = pump.status === "failed" ? `FAULT · NOT PUMPING · TANK +${num(tank.inflowBpd ?? 0)} BPD`
    : pump.status === "idle" ? `STANDBY · STARTS AT ${pump.startLevelPct ?? "—"}% TANK`
    : pump.status === "worn" ? (pumpPct != null ? `WORN · ${pumpPct}% OF RATED FLOW` : "WORN · STANDBY")
    : `RUNNING · ${num(pump.flowBpd)} BPD · ${num(pump.dischargePsi)} PSI`;
  const assetOf = i => i.ev.asset_id || (i.type === "leak" ? pipe.id : pump.id);
  // one beacon per issue on the drawing: pump problems on the pump, leaks on the pipeline
  const beacons = fac.events.filter((i, k, a) => a.findIndex(j => (j.type === "leak") === (i.type === "leak")) === k)
    .map(i => ({ i, pos: i.type === "leak" ? [790, 248] : [540, 206] }));
  const crit = allIssues.filter(i => i.severity === "critical" && i.shutdownAt);
  const n = facs.length;
  const system = (snap.systems || []).find(s => s.id === fac.system_id);
  const select = id => { setSelId(id); };
  const openIssue = i => { setSelId(i.facId); setSelKey(i.key); setOpen(true); };

  /* ---------- details panel (opens over the right sidebar) ---------- */
  const cur = open ? (fac.events.find(i => i.key === selKey) || fac.events[0] || null) : null;
  const cType = cur?.type;
  const cColor = cur ? TYPE_COLOR[cType] : null;
  const cElapsed = cur?.startedAt ? minBetween(asOf, cur.startedAt) : null;
  const cToShut = cur?.shutdownAt ? minBetween(cur.shutdownAt, asOf) : null;
  const plan = cur ? planSteps(cur, asOf, snap.emergency_trucking?.truck_capacity_bbl) : null;
  const saved = plan?.cost != null && plan?.nothing != null ? plan.nothing - plan.cost : null;
  const doneN = plan ? plan.steps.filter((_, k) => done[`${cur.key}:${k}`]).length : 0;

  return (
    <div className="sg">
      {bg}
      <div className="toasts">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type === "pump_wear" ? "warn" : t.type === "leak" ? "leak" : ""}`} role="alert">
            <div><b>New alert</b><span>{t.text}</span></div>
            <button onClick={() => setToasts(x => x.filter(y => y.id !== t.id))} aria-label="Dismiss">✕</button>
          </div>
        ))}
      </div>
      {header}
      {loading && <div className="spin" role="status" aria-label={`Loading ${dataset}`}><i /><span>Loading {dataset}…</span></div>}

      <main className={loading ? "dim" : ""}>
        <div className="top"><div><div className="crumb">{(snap.region || "PRODUCED WATER NETWORK").toUpperCase()}</div><h1>Field operations</h1></div></div>

        <div className="left">
        <section className="card">
          <div className="fh">
            <div>
              <select className="fsel" value={fac.id} onChange={e => select(e.target.value)} aria-label="Facility">
                {[...issueFacs, ...facs.filter(f => !f.type)].map(f => <option key={f.id} value={f.id}>{f.type ? "● " : ""}{f.name}</option>)}
              </select>
              <small>{[`System ${fac.system_id}`, `${fac.wellsProducing} of ${fac.wellsTotal} wells producing`, cap != null && `${num(cap)} bbl tank`].filter(Boolean).join(" · ")}</small>
            </div>
            <div className={`pill ${pill[0]}`}>{pill[1]}</div>
          </div>
          {fac.events.map(i => {
            const el = i.startedAt ? minBetween(asOf, i.startedAt) : null;
            return (
              <div key={i.key} className={`banner ${i.type === "pump_wear" ? "warn" : i.type === "leak" ? "leak" : ""}`}>
                <span>{assetOf(i)} {TITLES[i.type].toLowerCase()} · started {hm(i.startedAt)} · ONGOING</span>
                <span>{el != null ? `${el} MIN ELAPSED` : ""}</span>
              </div>
            );
          })}

          <div className="scene">
            {/* critical alerts only: a short banner over the drawing; click opens the full alert */}
            {crit.length > 0 && (
              <div className="crit">
                {crit.map(i => { const m = minBetween(i.shutdownAt, asOf); return (
                  <button key={i.key} type="button" onClick={() => openIssue(i)}>
                    CRITICAL · {short(i.facId)} {m <= 0 ? "is at shutdown" : `shuts down in ${dur(m)}`}
                  </button>); })}
              </div>
            )}
            <svg className="scene-svg" viewBox="0 0 960 400" role="img" aria-label="Produced water schematic">
              <defs>
                <linearGradient id="sg-steel" x1="0" x2="1"><stop offset="0" stopColor="#1b2a40" /><stop offset=".35" stopColor="#4a6585" /><stop offset=".7" stopColor="#2a3d58" /><stop offset="1" stopColor="#16233a" /></linearGradient>
                <linearGradient id="sg-pipe" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#5b7798" /><stop offset=".5" stopColor="#2c4260" /><stop offset="1" stopColor="#14213a" /></linearGradient>
                <linearGradient id="sg-pipeD" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#3a4258" /><stop offset=".5" stopColor="#232a3e" /><stop offset="1" stopColor="#121726" /></linearGradient>
                <linearGradient id="sg-pipeL" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#d9783f" /><stop offset=".5" stopColor="#8a3f1c" /><stop offset="1" stopColor="#3a1a0c" /></linearGradient>
                <linearGradient id="sg-wat" x1="0" x2="1"><stop offset="0" stopColor="#1ea9c4" /><stop offset=".4" stopColor="#43e0f0" /><stop offset="1" stopColor="#157f9e" /></linearGradient>
                <linearGradient id="sg-pmp" x1="0" x2="1"><stop offset="0" stopColor="#3a2352" /><stop offset=".4" stopColor="#8a55b8" /><stop offset="1" stopColor="#2a183f" /></linearGradient>
                <linearGradient id="sg-mot" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#7a4aa6" /><stop offset=".5" stopColor="#4a2a6e" /><stop offset="1" stopColor="#22123a" /></linearGradient>
                <radialGradient id="sg-glow"><stop offset="0" stopColor={color} stopOpacity=".3" /><stop offset="1" stopColor={color} stopOpacity="0" /></radialGradient>
                <linearGradient id="sg-gnd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#162338" /><stop offset="1" stopColor="#0c1422" /></linearGradient>
                {/* the one water texture: pipes, the drop into the tank, and the tank itself */}
                {[["sg-wv", undefined], ["sg-wv-v", "rotate(90)"]].map(([id, rot]) => (
                  <pattern key={id} id={id} width="40" height="20" patternUnits="userSpaceOnUse" patternTransform={rot}>
                    <rect width="40" height="20" fill="#17859e" />
                    <path d="M0 5 Q10 0 20 5 T40 5" fill="none" stroke="#7bf0fb" strokeWidth="2" opacity=".55" />
                    <path d="M0 11 Q10 6 20 11 T40 11" fill="none" stroke="#7bf0fb" strokeWidth="2.5" opacity=".9" />
                    <path d="M0 17 Q10 12 20 17 T40 17" fill="none" stroke="#7bf0fb" strokeWidth="2" opacity=".5" />
                    <circle cx="8" cy="8" r="1.6" fill="#fff" opacity=".7" />
                    <circle cx="29" cy="14" r="1.2" fill="#fff" opacity=".6" />
                  </pattern>
                ))}
                <clipPath id="sg-tankwater"><path d={`M82 ${waterTop} V298 A88 17 0 0 0 258 298 V${waterTop}Z`} /></clipPath>
              </defs>

              <rect x="0" y="318" width="960" height="82" fill="url(#sg-gnd)" />
              <rect x="0" y="318" width="960" height="3" fill="#25395a" />
              <ellipse cx="480" cy="256" rx="170" ry="110" fill="url(#sg-glow)" />

              <line x1="170" y1="36" x2="170" y2="108" className="leader" />
              <line x1="540" y1="36" x2="540" y2="186" className="leader" />
              <line x1="843" y1="36" x2="843" y2="222" className="leader" />
              {/* chips stay inside the drawing and never overlap: 8..260 | 420..660 | 662..952 */}
              <Chip x={170} maxW={250} text={`1 · WATER TANK${tank.id ? " · " + tank.id : ""}`} />
              <Chip x={540} maxW={240} text={`2 · TRANSFER PUMP${pump.id ? " · " + pump.id : ""}`} />
              <Chip x={843} maxW={290} text={`3 · DISPOSAL PIPELINE${pipe.id ? " · " + pipe.id : ""}`} />

              <rect x="20" y="86" width="128" height="16" rx="4" fill="url(#sg-pipe)" />
              <rect x="132" y="86" width="16" height="38" fill="url(#sg-pipe)" />
              <Stream x={22} y={88} w={124} h={12} speed={inSpeed} />
              <Fall x={134} y={98} w={12} h={26} speed={inSpeed} />
              <text className="lbl" x="20" y="70">FROM {fac.wellsProducing} WELLS · {num(tank.inflowBpd)} BPD</text>

              <ellipse cx="170" cy="322" rx="104" ry="14" fill="#06101c" />
              <path d="M76 130 V300 A94 20 0 0 0 264 300 V130Z" fill="url(#sg-steel)" />
              {/* tank water: same texture as the pipes, drifting slowly */}
              <g clipPath="url(#sg-tankwater)">
                <rect className="stream crawl" x="42" y={waterTop - 20} width="260" height={320 - waterTop} fill="url(#sg-wv)" />
              </g>
              <ellipse cx="170" cy={waterTop} rx="88" ry="16" fill="#1d9bb5" stroke="#7bf0fb" strokeWidth="2" />
              <path d="M76 130 A94 20 0 0 1 264 130 A94 20 0 0 1 76 130Z" fill="#33465f" />
              <ellipse cx="170" cy="130" rx="94" ry="20" fill="#5a7494" />
              <ellipse cx="170" cy="130" rx="76" ry="14" fill="#233450" />
              {/* inflow pouring in from the wells pipe, with ripples where it lands */}
              {filling && waterTop > 152 && <>
                <Fall x={135} y={124} w={10} h={waterTop - 124} speed="" />
                <ellipse cx="140" cy={waterTop} rx="10" ry="3" fill="none" stroke="#bff8ff" strokeWidth="1.5">
                  <animate attributeName="rx" values="6;26" dur="1.4s" repeatCount="indefinite" />
                  <animate attributeName="ry" values="2;6" dur="1.4s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values=".9;0" dur="1.4s" repeatCount="indefinite" />
                </ellipse>
              </>}
              {limitY != null && <>
                <line x1="270" y1={limitY} x2="296" y2={limitY} stroke={COLORS.failed} strokeWidth="2" strokeDasharray="4 4" />
                <text className="lbl" x="302" y={limitY - 2} style={{ fill: "#ff8a8a" }}>SHUTDOWN {tank.shutdownPct}%</text>
              </>}
              <rect x="120" y="205" width="100" height="36" rx="8" fill="#06101c" opacity=".55" />
              <text className="val" x="170" y="229" textAnchor="middle" style={{ fill: "#e8fdff", fontSize: 20 }}>{Math.round(pct)}%</text>
              <text className="lbl" x="170" y="352" textAnchor="middle">{cap != null ? `${num((pct * cap) / 100)} / ${num(cap)} BBL` : "TANK LEVEL"}</text>

              {/* pump outlet: one continuous run from the tank into the pump (the pump body covers the end) */}
              <rect x="258" y="270" width="166" height="28" fill={flowing ? "url(#sg-pipe)" : "url(#sg-pipeD)"} />
              <Stream x={260} y={272} w={164} h={24} speed={outSpeed} />
              <rect x="250" y="264" width="12" height="40" rx="3" fill="#3a526f" />

              <ellipse cx="540" cy="322" rx="140" ry="12" fill="#06101c" />
              <rect x="400" y="302" width="280" height="16" rx="4" fill="url(#sg-steel)" />
              <rect x="470" y="226" width="190" height="76" rx="14" fill="url(#sg-mot)" />
              <g stroke="#1a0d2c" strokeWidth="3" opacity=".8">{[540, 560, 580, 600, 620].map(x => <line key={x} x1={x} y1="232" x2={x} y2="298" />)}</g>
              <rect x="470" y="226" width="190" height="14" rx="7" fill="#b88ce0" opacity=".25" />
              <rect x="650" y="244" width="22" height="40" rx="5" fill="#2c1a45" />
              <circle cx="478" cy="264" r="62" fill="url(#sg-pmp)" />
              <circle cx="478" cy="264" r="62" fill="none" stroke="#b88ce0" strokeOpacity=".35" strokeWidth="2" />
              <circle cx="478" cy="264" r="48" fill="#1a0d2c" />
              <g ref={rotor}>
                {[0, 60, 120, 180, 240, 300].map((a, i) => (
                  <rect key={a} x="473" y="222" width="10" height="42" rx="5" fill={i % 2 ? "#8a55b8" : "#c9a3f0"} transform={`rotate(${a} 478 264)`} />
                ))}
                <circle cx="478" cy="264" r="13" fill="#2a183f" />
              </g>
              <circle cx="478" cy="264" r="8" fill={COLORS[pump.status]} />
              {/* alarm halo around a failed (red) or worn (amber) pump */}
              {pumpAlarm && (
                <circle cx="478" cy="264" r="66" fill="none" stroke={pumpAlarm} strokeWidth="4">
                  <animate attributeName="stroke-opacity" values=".9;.15;.9" dur="1.4s" repeatCount="indefinite" />
                  <animate attributeName="r" values="64;72;64" dur="1.4s" repeatCount="indefinite" />
                </circle>
              )}
              <rect x="496" y="196" width="40" height="34" rx="6" fill="#4a2a6e" />
              <rect x="490" y="190" width="52" height="10" rx="3" fill="#7a4aa6" />
              <text className="lbl" x="540" y="352" textAnchor="middle" style={{ fill: COLORS[pump.status] }}>{pumpLine}</text>

              {/* pipeline: water fills the whole pipe and runs on unbroken; past a leak it moves slower */}
              <rect x="672" y="270" width="274" height="28" fill={pipeFill} />
              <rect x="918" y="270" width="28" height="60" fill={pipeFill} />
              <Stream x={672} y={272} w={118} h={24} speed={pipeSpeed} />
              <Stream x={790} y={272} w={154} h={24} speed={afterLeak} />
              <Fall x={920} y={296} w={24} h={34} speed={afterLeak} />
              <rect x="762" y="264" width="12" height="40" rx="3" fill="#3a4258" />
              <rect x="838" y="236" width="10" height="36" fill="#4a5a78" />
              <ellipse cx="843" cy="232" rx="30" ry="8" fill="none" stroke="#8a55b8" strokeWidth="5" />
              <ellipse cx="843" cy="232" rx="30" ry="8" fill="none" stroke="#c9a3f0" strokeWidth="1.5" opacity=".6" />
              {/* leak: water dripping out of the pipe while the pump pushes water through it */}
              {leak && flowing && [0, 0.45, 0.9].map((d, i) => (
                <circle key={i} cx={786 + i * 5} cy="300" r="3.2" fill="#7bf0fb">
                  <animate attributeName="cy" values="300;318" dur="1.35s" begin={`${d}s`} repeatCount="indefinite" />
                  <animate attributeName="opacity" values="1;0" dur="1.35s" begin={`${d}s`} repeatCount="indefinite" />
                </circle>
              ))}
              {leak && <ellipse cx="792" cy="320" rx="22" ry="3" fill="#7bf0fb" opacity=".35" />}
              {leak && <text x="790" y="228" textAnchor="middle" className="leak-t">LEAK</text>}
              <text className="lbl" x="950" y="352" textAnchor="end" style={leak ? { fill: COLORS.leak } : undefined}>
                {leak ? (flowing ? "LEAK · " : "LEAK · PUMP IDLE · ") : ""}{num(pipe.pressurePsi)} PSI · {num(pipe.receiveFlowBpd)} BPD RECEIVED
              </text>
              <text className="lbl" x="900" y="250" textAnchor="middle" style={{ fill: "#5d718d" }}>TO SWD</text>

              {beacons.map(({ i, pos }) => { const c = TYPE_COLOR[i.type]; return (
                <g key={i.key} className="hot" tabIndex={0} role="button" aria-label={`Open ${TITLES[i.type].toLowerCase()} details`} onClick={() => openIssue(i)}
                  onKeyDown={e => (e.key === "Enter" || e.key === " ") && openIssue(i)}>
                  {/* pulsing beacon (SMIL, so it animates the same in every browser) */}
                  {[0, 0.8].map(d => (
                    <circle key={d} cx={pos[0]} cy={pos[1]} r="10" fill={c}>
                      <animate attributeName="r" values="10;34" dur="1.6s" begin={`${d}s`} repeatCount="indefinite" />
                      <animate attributeName="opacity" values=".8;0" dur="1.6s" begin={`${d}s`} repeatCount="indefinite" />
                    </circle>
                  ))}
                  <circle cx={pos[0]} cy={pos[1]} r="11" fill={c} stroke="#fff" strokeWidth="2.5" style={{ filter: `drop-shadow(0 0 8px ${c})` }} />
                  <text x={pos[0]} y={pos[1] + 4} textAnchor="middle" style={{ font: "700 11px Inter,sans-serif", fill: "#1a0b1e" }}>!</text>
                  <circle cx={pos[0]} cy={pos[1]} r="28" fill="transparent" />
                </g>); })}
            </svg>
          </div>
        </section>

        <FacilitySummary fac={fac} asOf={asOf} onOpen={openIssue} />
        </div>

        <aside className="side">
          <div className="card box">
            <h3>Alerts &amp; events <span>{allIssues.length} OPEN</span></h3>
            {allIssues.length === 0 && <div className="al"><span className="tag" style={{ color: "var(--gr)" }}>NORMAL</span><b>No active issues</b><small>All facilities normal</small></div>}
            <div className="alist" ref={alList}>
              {allIssues.map(i => (
                <div key={i.key} className={`al ${(cur ? i.key === cur.key : i.facId === fac.id) ? "sel" : ""}`} style={{ "--c": TYPE_COLOR[i.type] }} onClick={() => openIssue(i)}>
                  <span className="tag sev" data-sev={i.severity}>{i.rank != null ? `#${i.rank} · ` : ""}{SEVERITY[i.severity] ?? "ONGOING"}</span>
                  <b>{TITLES[i.type]} · {short(i.facId)}</b>
                  <small className="key">{alertLine(i, asOf)}</small>
                  <small>started {hm(i.startedAt)}</small>
                </div>
              ))}
            </div>
          </div>

          <div className="card box">
            <h3>Network <span>{n} FACILITIES · <button type="button" className="lnk" onClick={() => setMapBig(true)}>Expand map</button></span></h3>
            <NetMap key={fac.id} facs={facs} systems={snap.systems || []} cur={fac} onPick={select} />
            <div className="legend"><span><i style={{ background: COLORS.ok }} />OK</span><span><i style={{ background: COLORS.failed }} />Pump failed</span><span><i style={{ background: COLORS.leak }} />Leak</span><span><i style={{ background: COLORS.worn }} />Worn</span><span><i style={{ background: "var(--cy)", borderRadius: 2 }} />Disposal</span></div>
          </div>

          {system && (
            <div className="card trk">🚚<div>
              <b>System {system.id}: {system.emergency_fleet_size} truck{system.emergency_fleet_size === 1 ? "" : "s"} · {system.trucks_free} free</b>
              <small>{system.trucks_assigned?.length
                ? system.trucks_assigned.map(a => `${a.trucks} × ${a.trips_per_truck} trip${a.trips_per_truck > 1 ? "s" : ""} → ${short(a.facility_id)}`).join(" · ")
                : "No trucks needed in this system right now"}</small>
            </div></div>
          )}

          {/* alert details: on top of the sidebar, never over the drawing */}
          {cur && (
            <div className="dock" role="dialog" aria-label="Alert details" style={{ borderColor: cColor }}>
              <button className="x" onClick={() => setOpen(false)} aria-label="Close">✕</button>
              <div className="mu" style={{ color: cColor }}>{fac.name.toUpperCase()} · {assetOf(cur)}</div>
              <h2>{TITLES[cType]}</h2>
              <div className="mu">Started {hm(cur.startedAt)} · ongoing{cElapsed != null ? ` · ${cElapsed} min` : ""}</div>
              {/* every issue at this facility */}
              {fac.events.length > 1 && (
                <div className="itabs">
                  {fac.events.map(i => (
                    <button key={i.key} type="button" className={i.key === cur.key ? "on" : ""} style={{ "--c": TYPE_COLOR[i.type] }} onClick={() => setSelKey(i.key)}>{TITLES[i.type]}</button>
                  ))}
                </div>
              )}

              <div style={{ marginTop: 10 }}>
                {cType === "pump_failure" && <>
                  {cToShut != null
                    ? <div className="row"><span>TIME TO TANK SHUTDOWN</span><b style={{ color: cColor }}>{dur(cToShut)}</b></div>
                    : <div className="row"><span>TANK</span><b className="w">Pump down · tank holds until repair</b></div>}
                  {cur.doNothingCost != null && <div className="row"><span>REVENUE AT RISK (DO NOTHING)</span><b style={{ color: cColor }}>{money(cur.doNothingCost)}</b></div>}
                  {tank.inflowBpd != null && <div className="row"><span>TANK FILLING</span><b style={{ color: cColor }}>+{num(tank.inflowBpd)} bpd</b></div>}
                  {cur.repairEta && <div className="row"><span>PUMP FIXED BY</span><b className="w">~{hm(cur.repairEta)}</b></div>}
                </>}
                {cType === "pump_wear" && (() => { const imp = cur.ev.impact || {}; return <>
                  <div className="row"><span>PUMPING (HOURLY AVERAGE WHILE RUNNING)</span><b style={{ color: cColor }}>{imp.flow_pct_of_rated ?? pumpPct ?? "—"}% of rated</b></div>
                  <div className="row"><span>FLOW</span><b className="w">{num(imp.pumping_bpd ?? pump.flowBpd)} / {num(imp.rated_bpd ?? pump.normalFlowBpd)} bpd</b></div>
                  {imp.keeps_up != null && <div className="row"><span>WELLS PRODUCE</span><b className="w">{num(imp.inflow_bpd)} bpd · {imp.keeps_up ? "pump still keeps up" : "pump can't keep up"}</b></div>}
                </>; })()}
                {cType === "leak" && (() => { const imp = cur.ev.impact || {}; return <>
                  {imp.lost_pct != null && <div className="row"><span>PUMPED WATER NOT ARRIVING</span><b style={{ color: cColor }}>{imp.lost_pct}%</b></div>}
                  {imp.lost_bpd_while_pumping != null && <div className="row"><span>WATER ESCAPING WHILE PUMPING</span><b style={{ color: cColor }}>~{num(imp.lost_bpd_while_pumping)} bpd</b></div>}
                  {imp.pressure_drop_psi != null && <div className="row"><span>PIPELINE PRESSURE</span><b className="w">{num(imp.pressure_drop_psi)} psi below normal</b></div>}
                </>; })()}
              </div>

              <div className="plan">
                <div className="ph">
                  <span className="mu" style={{ color: "var(--cy)" }}>DO THIS NOW</span>
                  {plan.steps.length > 0 && <span className="mu">{doneN} of {plan.steps.length} done</span>}
                </div>
                <ul className="chk">
                  {plan.steps.map((s, k) => {
                    const id = `${cur.key}:${k}`, left = minBetween(s.at, asOf);
                    return (
                      <li key={k} className={done[id] ? "done" : ""}>
                        <label>
                          <input type="checkbox" checked={!!done[id]} onChange={() => setDone(d => ({ ...d, [id]: !d[id] }))} />
                          <span className="t">{s.text}</span>
                          <span className="when">{hm(s.at)} · {left <= 0 ? "now" : `in ${dur(left)}`}</span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
                {plan.notes.map((s, k) => <p key={k}>{s}</p>)}
                {cType !== "pump_failure" && <p className="mu" style={{ marginTop: 8 }}>Challenge rule: leaks and worn pumps get a field inspection. They don’t fill the tank, so there’s no shutdown countdown or trucking cost.</p>}
                {(plan.cost != null || plan.nothing != null) && (
                  <div className="costs">
                    <span>Cost <b>{money(plan.cost)}</b></span>
                    <span>If you do nothing <b>{money(plan.nothing)}</b></span>
                    {saved != null && <span>You save <b className="sv">{money(saved)}</b></span>}
                  </div>
                )}
              </div>

              {/* why this plan: the pure strategies side by side, all from the same tank simulation */}
              {cType === "pump_failure" && cur.ev.decision && (() => { const d = cur.ev.decision; return (
                <div className="why">
                  <div className="mu" style={{ color: "var(--cy)" }}>WHY THIS PLAN</div>
                  <table>
                    <tbody>
                      {d.options.map(o => (
                        <tr key={o.label}><td>{o.label}</td><td className="s">{o.summary.replace(/ \(~\$[\d,]+\)$/, "")}</td><td className="c">{money(o.cost)}</td></tr>
                      ))}
                      <tr className="best"><td>Recommended</td><td className="s">{cur.ev.plan_summary?.replace(/ \(~\$[\d,]+\)$/, "")}</td><td className="c">{money(cur.ev.est_cost)}</td></tr>
                    </tbody>
                  </table>
                  <p className="mu">
                    Simulated the tank minute by minute for each of {num(d.plans_compared)} candidate plans (0–{d.fleet_size} trucks × every trip count × every set of wells × shut-in timing) until the pump repair finishes, and kept the cheapest.
                    {d.sharing_with?.length ? ` ${fac.system_id} has ${d.fleet_size} truck${d.fleet_size === 1 ? "" : "s"} shared with ${d.sharing_with.map(short).join(", ")}, so ${num(d.fleet_splits_compared)} ways of splitting them were compared.` : ""}
                  </p>
                  <p className="mu">Inputs: tank {num(tank.levelPct)}% of {num(d.capacity_bbl)} bbl, filling {num(d.inflow_bpd)} bpd, shutdown at {d.shutdown_pct}% · trucks arrive after {d.response_min} min, then every {d.cycle_min} min · lost revenue per well: {d.wells.map(w => `${w.id.split("_").pop()} ${money(w.revenue_per_hour)}/h`).join(", ")}.</p>
                </div>); })()}

              {cur.ev.evidence?.length > 0 && (
                <div className="evid">
                  <div className="mu">WHAT THE SENSORS SHOW</div>
                  <ul>{cur.ev.evidence.map((e, k) => <li key={k}>{e}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </aside>
      </main>

      {guideOpen && <OperatorGuide snap={snap} onClose={() => setGuideOpen(false)} />}

      {/* expanded network map */}
      {mapBig && (
        <div className="ov" onClick={e => e.target === e.currentTarget && setMapBig(false)}>
          <div className="pop mapbig" role="dialog" aria-modal="true" aria-label="Network map">
            <button className="x" onClick={() => setMapBig(false)} aria-label="Close">✕</button>
            <div className="mu" style={{ color: "var(--cy)" }}>NETWORK · {n} FACILITIES · {(snap.systems || []).length} SYSTEMS</div>
            <NetMap key={fac.id} facs={facs} systems={snap.systems || []} cur={fac} onPick={id => { select(id); setMapBig(false); }} big />
            <div className="legend"><span><i style={{ background: COLORS.ok }} />OK</span><span><i style={{ background: COLORS.failed }} />Pump failed</span><span><i style={{ background: COLORS.leak }} />Leak</span><span><i style={{ background: COLORS.worn }} />Worn</span><span><i style={{ background: "var(--cy)", borderRadius: 2 }} />Disposal</span><span>Ring and line color = system</span></div>
          </div>
        </div>
      )}
    </div>
  );
}
