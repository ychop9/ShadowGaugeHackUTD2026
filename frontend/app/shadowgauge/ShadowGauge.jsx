"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import "./ShadowGauge.css";
import SAMPLE from "./sample.js";

/* ====================================================================
   BACKEND CONTRACT  (change the two URLs / the adapt() function if yours differ)
   GET  /api/datasets                   -> ["full_week","mock_test","test", ...]
   GET  /api/snapshot?dataset=<name>    -> { asOf, facilities:[...], trucks }
   See sample.js for the exact shape. Every number on the page comes from it.
   Open the page with ?sample=1 to test the UI without a backend.
==================================================================== */
const API = process.env.NEXT_PUBLIC_API_URL || "";
const DATASET_FALLBACK = ["full_week", "mock_test", "test"]; // used only if /api/datasets is unreachable
const POLL_MS = 5000;

/* ---------- helpers ---------- */
const D = x => new Date(x);
const hm = x => (x ? D(x).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false }) : "—");
const asOfFmt = x => D(x).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
const minBetween = (a, b) => Math.round((D(a) - D(b)) / 60000);
const dur = m => (m == null ? "—" : `${Math.floor(Math.max(0, m) / 60)}h ${String(Math.max(0, m) % 60).padStart(2, "0")}m`);
const money = n => (n == null ? "—" : "$" + Math.round(n).toLocaleString());
const num = n => (n == null ? "—" : Math.round(n).toLocaleString());

const COLORS = { ok: "#43e0f0", worn: "#f2b24c", failed: "#ff4f93", leak: "#ff4f93" };
const TITLES = { pump_failure: "Complete pump failure", pump_wear: "Pump wear", leak: "Pipeline leak" };
const RANK = { pump_failure: 0, leak: 1, pump_wear: 2 };

const pumpStatus = s => ({ running: "ok", ok: "ok", normal: "ok", degraded: "worn", worn: "worn", failed: "failed" }[String(s).toLowerCase()] ?? "ok");
const issueType = s => {
  const t = String(s || "").toLowerCase();
  return t.includes("fail") ? "pump_failure" : t.includes("leak") ? "leak" : t.includes("wear") || t.includes("degrad") || t.includes("worn") ? "pump_wear" : null;
};

/* turn one raw facility into what the UI needs */
function norm(f) {
  const pump = { ...f.pump, status: pumpStatus(f.pump?.status) };
  const pipe = { ...f.pipeline, status: /leak/i.test(f.pipeline?.status || "") ? "leak" : "ok" };
  const type = issueType(f.issue?.type) ?? (pump.status === "failed" ? "pump_failure" : pipe.status === "leak" ? "leak" : pump.status === "worn" ? "pump_wear" : null);
  if (type === "pump_failure") pump.status = "failed";
  if (type === "pump_wear" && pump.status === "ok") pump.status = "worn";
  if (type === "leak") pipe.status = "leak";
  const startedAt = f.issue?.startedAt ?? (type === "leak" ? pipe.since : pump.since);
  return { ...f, tank: f.tank || {}, pump, pipe, type, startedAt, issue: f.issue || {} };
}
const facColor = f => (f.type === "pump_failure" || f.type === "leak" ? COLORS.failed : f.type === "pump_wear" ? COLORS.worn : "#4fe0a0");

/* ---------- small pieces ---------- */
const Chip = ({ x, w, text }) => (
  <g>
    <rect x={x - w / 2} y="10" width={w} height="26" rx="13" className="chip-r" />
    <text x={x} y="27" textAnchor="middle" className="chip-t">{text}</text>
  </g>
);

/* flowing water inside a pipe (clipped by a nested svg) */
const Stream = ({ x, y, w, h, kind, speed = "" }) => (
  <svg x={x} y={y} width={w} height={h} overflow="hidden">
    <rect className={`stream ${speed}`} x="-40" y="0" width={w + 40} height={h} fill={`url(#sg-wv-${kind})`} />
  </svg>
);

/* how fast the pump spins for each state (1 = normal) */
const SPIN = { pump_wear: 0.4, leak: 0.12, pump_failure: 0.08 };

export default function ShadowGauge() {
  const [datasets, setDatasets] = useState(DATASET_FALLBACK);
  const [dataset, setDataset] = useState(DATASET_FALLBACK[0]);
  const [snap, setSnap] = useState(null);
  const [error, setError] = useState(null);
  const [selId, setSelId] = useState(null);
  const [open, setOpen] = useState(false);
  const [toasts, setToasts] = useState([]);

  /* "sample" if the address ends in ?sample=1, otherwise "live" (decided in the browser) */
  const [mode, setMode] = useState(null);
  useEffect(() => { setMode(new URLSearchParams(window.location.search).has("sample") ? "sample" : "live"); }, []);
  const USE_SAMPLE = mode === "sample";

  /* dataset list */
  useEffect(() => {
    if (mode !== "live") return;
    fetch(`${API}/api/datasets`).then(r => r.json()).then(j => {
      const list = Array.isArray(j) ? j : j.datasets;
      if (list?.length) { setDatasets(list); setDataset(d => (list.includes(d) ? d : list[0])); }
    }).catch(() => {});
  }, [mode]);

  /* snapshot polling */
  useEffect(() => {
    if (!mode) return;
    if (USE_SAMPLE) { setSnap(SAMPLE); return; }
    let stop = false;
    setSnap(null); setError(null);
    const load = async () => {
      try {
        const r = await fetch(`${API}/api/snapshot?dataset=${encodeURIComponent(dataset)}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const j = await r.json();
        if (!stop) { setSnap(j); setError(null); }
      } catch (e) { if (!stop) setError(e.message || "failed"); }
    };
    load();
    const t = setInterval(load, POLL_MS);
    return () => { stop = true; clearInterval(t); };
  }, [dataset, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const facs = useMemo(() => (snap?.facilities || []).map(norm), [snap]);
  const issues = useMemo(() => facs.filter(f => f.type).sort((a, b) =>
    RANK[a.type] - RANK[b.type] ||
    (a.type === "pump_failure" ? D(a.issue.shutdownAt || 9e15) - D(b.issue.shutdownAt || 9e15) : 0)), [facs]);
  const fac = facs.find(f => f.id === selId) || issues[0] || facs[0];
  useEffect(() => { if (facs.length && !facs.some(f => f.id === selId)) setSelId((issues[0] || facs[0]).id); }, [facs]); // eslint-disable-line

  /* notify when a NEW issue appears (first load of a dataset is silent) */
  const seen = useRef(null);
  useEffect(() => { seen.current = null; }, [dataset]);
  useEffect(() => {
    if (!snap) return;
    const keys = issues.map(f => `${f.id}:${f.type}`);
    if (seen.current) {
      issues.filter(f => !seen.current.has(`${f.id}:${f.type}`)).forEach(f => {
        const text = `${f.name} · ${f.pump.id || "pump"} · ${TITLES[f.type]}`;
        setToasts(t => [...t, { id: Date.now() + Math.random(), type: f.type, text }]);
        if ("Notification" in window && Notification.permission === "granted") new Notification("ShadowGauge alert", { body: text });
      });
    }
    seen.current = new Set(keys);
  }, [snap]); // eslint-disable-line

  useEffect(() => {
    const esc = e => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  /* pump rotation: speed = real flow / normal flow, eases down on failure */
  const rotor = useRef(null);
  const ratio = useRef(0);
  ratio.current = fac ? (SPIN[fac.type] ?? 1) : 0;
  useEffect(() => {
    let raf, last = performance.now(), ang = 0, cur = ratio.current;
    const tick = t => {
      const dt = Math.min(0.1, (t - last) / 1000); last = t;
      cur += (ratio.current - cur) * Math.min(1, dt * 0.5);
      if (Math.abs(ratio.current - cur) < 0.005) cur = ratio.current;
      ang = (ang + cur * 360 * dt) % 360;
      rotor.current?.setAttribute("transform", `rotate(${ang} 478 264)`);
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
        {snap && <span className="asof">As of {asOfFmt(snap.asOf)}</span>}
        <label className="dsel">Dataset
          <select value={dataset} onChange={e => setDataset(e.target.value)} disabled={USE_SAMPLE}>
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
            ? <><b>Can’t reach the backend.</b><div className="mu" style={{ marginTop: 6 }}>Tried {API || "this site"}/api/snapshot?dataset={dataset} ({error}). Start your API, or add ?sample=1 to the page address to preview the layout.</div></>
            : <div className="mu">Loading {dataset}…</div>}
        </section></main>
      </div>
    );
  }

  /* ---------- derived values for the selected facility ---------- */
  const { tank, pump, pipe, type } = fac;
  const asOf = snap.asOf;
  const color = type ? facColor(fac) : COLORS.ok;
  const pct = Math.max(0, Math.min(100, tank.levelPct ?? 0));
  const waterTop = 300 - 1.7 * pct;
  const limitY = tank.shutdownPct != null ? 300 - 1.7 * tank.shutdownPct : null;
  const cap = fac.tankCapacityBbl;
  const flowing = pump.status !== "failed";
  const slow = pump.status === "worn";
  const leak = pipe.status === "leak";
  const flowSpeed = type === "pump_failure" ? "crawl dim" : type === "leak" ? "slower" : type === "pump_wear" ? "slow" : "";
  const inKind = type === "pump_failure" ? "leak" : type === "pump_wear" ? "worn" : "ok";
  const outKind = type === "pump_failure" || type === "leak" ? "leak" : type === "pump_wear" ? "worn" : "ok";
  const pipeFill = leak ? "url(#sg-pipeL)" : flowing ? "url(#sg-pipe)" : "url(#sg-pipeD)";
  const elapsed = fac.startedAt ? minBetween(asOf, fac.startedAt) : null;
  const toShutdown = fac.issue.shutdownAt ? minBetween(fac.issue.shutdownAt, asOf) : null;
  const plan = type ? planText(fac, asOf) : null;
  const saved = plan?.cost != null && plan?.nothing != null ? plan.nothing - plan.cost : null;
  const pumpPct = pump.normalFlowBpd ? Math.round((pump.flowBpd / pump.normalFlowBpd) * 100) : null;
  const pill = !type ? ["ok", "● ALL NORMAL"] : type === "pump_failure" ? ["crit", "● TRANSFER INTERRUPTED"] : type === "leak" ? ["crit", "● PIPELINE LEAK"] : ["warn", "● PUMP WORN"];
  const pumpLine = pump.status === "failed" ? `FAILED · FLOW ${num(pump.flowBpd ?? 0)} BPD`
    : pump.status === "worn" ? `WORN · ${pumpPct ?? "—"}% OF NORMAL FLOW`
    : `RUNNING · ${num(pump.flowBpd)} BPD · ${num(pump.dischargePsi)} PSI`;
  const dotPos = type === "leak" ? [790, 252] : [516, 213];
  const n = facs.length;
  const pos = (f, i) => (f.x != null && f.y != null ? [f.x, f.y]
    : [50 + 34 * Math.cos((i / n) * 2 * Math.PI - Math.PI / 2), 50 + 34 * Math.sin((i / n) * 2 * Math.PI - Math.PI / 2)]);
  const select = id => { setSelId(id); };
  const openIssue = id => { setSelId(id); setOpen(true); };

  return (
    <div className="sg">
      {bg}
      <div className="toasts">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type === "pump_wear" ? "warn" : ""}`} role="alert">
            <div><b>New alert</b><span>{t.text}</span></div>
            <button onClick={() => setToasts(x => x.filter(y => y.id !== t.id))} aria-label="Dismiss">✕</button>
          </div>
        ))}
      </div>
      {header}

      <main>
        <div className="top"><div><div className="crumb">{(snap.region || "PRODUCED WATER NETWORK").toUpperCase()}</div><h1>Field operations</h1></div></div>

        <section className="card">
          <div className="fh">
            <div className="fid">{fac.id}</div>
            <div>
              <select className="fsel" value={fac.id} onChange={e => select(e.target.value)} aria-label="Facility">
                {[...issues, ...facs.filter(f => !f.type)].map(f => <option key={f.id} value={f.id}>{f.type ? "● " : ""}{f.name}</option>)}
              </select>
              <small>{[fac.wells != null && `${fac.wells} producing wells`, cap != null && `${num(cap)} bbl capacity`].filter(Boolean).join(" · ")}</small>
            </div>
            <div className={`pill ${pill[0]}`}>{pill[1]}</div>
          </div>
          {type && (
            <div className={`banner ${type === "pump_wear" ? "warn" : ""}`}>
              <span>{type === "leak" ? pipe.id : pump.id} {TITLES[type].toLowerCase()} · started {hm(fac.startedAt)} · ONGOING</span>
              <span>{elapsed != null ? `${elapsed} MIN ELAPSED` : ""}</span>
            </div>
          )}

          <div className="scene">
            <svg className="scene-svg" viewBox="0 0 960 400" role="img" aria-label="Produced water schematic">
              <defs>
                <linearGradient id="sg-steel" x1="0" x2="1"><stop offset="0" stopColor="#1b2a40" /><stop offset=".35" stopColor="#4a6585" /><stop offset=".7" stopColor="#2a3d58" /><stop offset="1" stopColor="#16233a" /></linearGradient>
                <linearGradient id="sg-pipe" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#5b7798" /><stop offset=".5" stopColor="#2c4260" /><stop offset="1" stopColor="#14213a" /></linearGradient>
                <linearGradient id="sg-pipeD" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#3a4258" /><stop offset=".5" stopColor="#232a3e" /><stop offset="1" stopColor="#121726" /></linearGradient>
                <linearGradient id="sg-pipeL" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#c44a6e" /><stop offset=".5" stopColor="#7a2342" /><stop offset="1" stopColor="#3a0f24" /></linearGradient>
                <linearGradient id="sg-wat" x1="0" x2="1"><stop offset="0" stopColor="#1ea9c4" /><stop offset=".4" stopColor="#43e0f0" /><stop offset="1" stopColor="#157f9e" /></linearGradient>
                <linearGradient id="sg-pmp" x1="0" x2="1"><stop offset="0" stopColor="#3a2352" /><stop offset=".4" stopColor="#8a55b8" /><stop offset="1" stopColor="#2a183f" /></linearGradient>
                <linearGradient id="sg-mot" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#7a4aa6" /><stop offset=".5" stopColor="#4a2a6e" /><stop offset="1" stopColor="#22123a" /></linearGradient>
                <radialGradient id="sg-glow"><stop offset="0" stopColor={color} stopOpacity=".3" /><stop offset="1" stopColor={color} stopOpacity="0" /></radialGradient>
                <linearGradient id="sg-gnd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#162338" /><stop offset="1" stopColor="#0c1422" /></linearGradient>
                {[["ok", "#17859e", "#7bf0fb"], ["worn", "#8a6418", "#ffd98a"], ["leak", "#8a2650", "#ff9cc0"]].map(([k, base, wave]) => (
                  <pattern key={k} id={`sg-wv-${k}`} width="40" height="20" patternUnits="userSpaceOnUse">
                    <rect width="40" height="20" fill={base} />
                    <path d="M0 5 Q10 0 20 5 T40 5" fill="none" stroke={wave} strokeWidth="2" opacity=".55" />
                    <path d="M0 11 Q10 6 20 11 T40 11" fill="none" stroke={wave} strokeWidth="2.5" opacity=".9" />
                    <path d="M0 17 Q10 12 20 17 T40 17" fill="none" stroke={wave} strokeWidth="2" opacity=".5" />
                    <circle cx="8" cy="8" r="1.6" fill="#fff" opacity=".7" />
                    <circle cx="29" cy="14" r="1.2" fill="#fff" opacity=".6" />
                  </pattern>
                ))}
              </defs>

              <rect x="0" y="318" width="960" height="82" fill="url(#sg-gnd)" />
              <rect x="0" y="318" width="960" height="3" fill="#25395a" />
              <ellipse cx="480" cy="256" rx="170" ry="110" fill="url(#sg-glow)" />

              <line x1="170" y1="36" x2="170" y2="108" className="leader" />
              <line x1="540" y1="36" x2="540" y2="186" className="leader" />
              <line x1="843" y1="36" x2="843" y2="222" className="leader" />
              <Chip x={170} w={200} text={`1 · WATER TANK${tank.id ? " · " + tank.id : ""}`} />
              <Chip x={540} w={220} text={`2 · TRANSFER PUMP${pump.id ? " · " + pump.id : ""}`} />
              <Chip x={843} w={250} text={`3 · DISPOSAL PIPELINE${pipe.id ? " · " + pipe.id : ""}`} />

              <rect x="20" y="86" width="120" height="16" rx="4" fill="url(#sg-pipe)" />
              <rect x="132" y="86" width="16" height="38" fill="url(#sg-pipe)" />
              <Stream x={28} y={89} w={112} h={10} kind="ok" />
              <text className="lbl" x="20" y="70">FROM {fac.wells != null ? fac.wells + " " : ""}WELLS</text>

              <ellipse cx="170" cy="322" rx="104" ry="14" fill="#06101c" />
              <path d="M76 130 V300 A94 20 0 0 0 264 300 V130Z" fill="url(#sg-steel)" />
              <path d={`M82 ${waterTop} V298 A88 17 0 0 0 258 298 V${waterTop}Z`} fill="url(#sg-wat)" opacity=".92" />
              <ellipse cx="170" cy={waterTop} rx="88" ry="16" fill="#7bf0fb" />
              <path d="M76 130 A94 20 0 0 1 264 130 A94 20 0 0 1 76 130Z" fill="#33465f" />
              <ellipse cx="170" cy="130" rx="94" ry="20" fill="#5a7494" />
              <ellipse cx="170" cy="130" rx="76" ry="14" fill="#233450" />
              {limitY != null && <>
                <line x1="270" y1={limitY} x2="296" y2={limitY} stroke="#ff4f93" strokeWidth="2" strokeDasharray="4 4" />
                <text className="lbl" x="302" y={limitY - 2} style={{ fill: "#ff7fb2" }}>SHUTDOWN {tank.shutdownPct}%</text>
              </>}
              <rect x="120" y="205" width="100" height="36" rx="8" fill="#06101c" opacity=".55" />
              <text className="val" x="170" y="229" textAnchor="middle" style={{ fill: "#e8fdff", fontSize: 20 }}>{Math.round(pct)}%</text>
              <text className="lbl" x="170" y="352" textAnchor="middle">{cap != null ? `${num((pct * cap) / 100)} / ${num(cap)} BBL` : "TANK LEVEL"}</text>

              <rect x="258" y="270" width="150" height="28" fill={flowing ? "url(#sg-pipe)" : "url(#sg-pipeD)"} />
              <rect x="250" y="264" width="12" height="40" rx="3" fill="#3a526f" />
              <Stream x={262} y={274} w={142} h={20} kind={inKind} speed={flowSpeed} />

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
              <rect x="496" y="196" width="40" height="34" rx="6" fill="#4a2a6e" />
              <rect x="490" y="190" width="52" height="10" rx="3" fill="#7a4aa6" />
              <text className="lbl" x="540" y="352" textAnchor="middle" style={{ fill: COLORS[pump.status] }}>{pumpLine}</text>

              <rect x="672" y="270" width="96" height="28" fill={pipeFill} />
              <rect x="762" y="264" width="12" height="40" rx="3" fill="#3a4258" />
              <rect x="774" y="270" width="150" height="28" fill={pipeFill} />
              <rect x="918" y="270" width="28" height="60" fill={pipeFill} />
              <Stream x={680} y={274} w={238} h={20} kind={outKind} speed={flowSpeed} />
              <rect x="838" y="236" width="10" height="36" fill="#4a5a78" />
              <ellipse cx="843" cy="232" rx="30" ry="8" fill="none" stroke="#e05a8e" strokeWidth="5" />
              <ellipse cx="843" cy="232" rx="30" ry="8" fill="none" stroke="#ff9cc0" strokeWidth="1.5" opacity=".6" />
              {leak && <text x="790" y="228" textAnchor="middle" className="leak-t">LEAK</text>}
              <text className="lbl" x="850" y="352" textAnchor="middle" style={leak ? { fill: "#ff7fb2" } : undefined}>
                {leak ? "LEAK · " : ""}{num(pipe.pressurePsi)} PSI · {num(pipe.receiveFlowBpd)} BPD RECEIVED
              </text>
              <text className="lbl" x="900" y="250" textAnchor="middle" style={{ fill: "#5d718d" }}>TO SWD</text>

              {type && (
                <g className="hot" tabIndex={0} role="button" aria-label="Open issue details" onClick={() => setOpen(true)}
                  onKeyDown={e => (e.key === "Enter" || e.key === " ") && setOpen(true)}>
                  <circle cx={dotPos[0]} cy={dotPos[1]} r="14" fill={color} className="ring" opacity=".7" />
                  <circle cx={dotPos[0]} cy={dotPos[1]} r="14" fill={color} className="ring" opacity=".7" style={{ animationDelay: ".8s" }} />
                  <circle cx={dotPos[0]} cy={dotPos[1]} r="9" fill={color} stroke="#fff" strokeWidth="2" />
                  <circle cx={dotPos[0]} cy={dotPos[1]} r="26" fill="transparent" />
                </g>
              )}
            </svg>
          </div>
        </section>

        <aside className="side">
          <div className="card box">
            <h3>Alerts &amp; events <span>{issues.length} OPEN</span></h3>
            {issues.length === 0 && <div className="al"><span className="tag" style={{ color: "var(--gr)" }}>NORMAL</span><b>No active issues</b><small>All facilities operating normally</small></div>}
            {issues.map(f => (
              <div key={f.id + f.type} className={`al ${f.type === "pump_wear" ? "onw" : "on"} ${f.id === fac.id ? "sel" : ""}`} onClick={() => openIssue(f.id)}>
                <span className="tag" style={{ color: facColor(f) }}>ONGOING</span>
                <b>{TITLES[f.type]}</b>
                <small>{f.name} · started {hm(f.startedAt)}{f.type === "pump_failure" && f.issue.shutdownAt ? ` · shutdown in ${dur(minBetween(f.issue.shutdownAt, asOf))}` : ""}</small>
              </div>
            ))}
          </div>

          <div className="card box">
            <h3>Network <span>{n} FACILITIES</span></h3>
            <div className="map">
              <div className="node" style={{ left: "50%", top: "50%", "--c": "var(--cy)" }}><i style={{ width: 22, height: 22 }} />SWD</div>
              {facs.map((f, i) => { const [x, y] = pos(f, i); return (
                <div key={f.id} className={`node click ${f.id === fac.id ? "cur" : ""}`} style={{ left: `${x}%`, top: `${y}%`, "--c": facColor(f) }} onClick={() => select(f.id)}>
                  <i />{f.name.toUpperCase()}
                </div>); })}
            </div>
            <div className="legend"><span><i style={{ background: "var(--gr)" }} />OK</span><span><i style={{ background: "var(--am)" }} />Worn</span><span><i style={{ background: "var(--pk)" }} />Failed / leak</span></div>
          </div>

          {snap.trucks && (
            <div className="card trk">🚚<div>
              <b>{snap.trucks.total} shared trucks · {snap.trucks.slots} load slots</b>
              <small>{snap.trucks.assignments?.length
                ? snap.trucks.assignments.map(a => `${a.slots} for ${facs.find(f => f.id === a.facilityId)?.name || a.facilityId}`).join(" · ")
                : "No trucks needed right now"}</small>
            </div></div>
          )}
        </aside>
      </main>

      {open && type && (
        <div className="ov" onClick={e => e.target === e.currentTarget && setOpen(false)}>
          <div className="pop" role="dialog" aria-modal="true" style={{ borderColor: color }}>
            <button className="x" onClick={() => setOpen(false)} aria-label="Close">✕</button>
            <div className="mu" style={{ color }}>{fac.name.toUpperCase()} · {type === "leak" ? pipe.id : pump.id}</div>
            <h2>{TITLES[type]}</h2>
            <div className="mu">Started {hm(fac.startedAt)} · ongoing{elapsed != null ? ` · ${elapsed} min` : ""}</div>

            <div style={{ marginTop: 10 }}>
              {type === "pump_failure" && <>
                {toShutdown != null && <div className="row"><span>TIME TO TANK SHUTDOWN</span><b style={{ color }}>{dur(toShutdown)}</b></div>}
                {fac.issue.doNothingCost != null && <div className="row"><span>REVENUE AT RISK (DO NOTHING)</span><b style={{ color }}>{money(fac.issue.doNothingCost)}</b></div>}
                {tank.inflowBpd != null && <div className="row"><span>TANK FILLING</span><b style={{ color }}>+{num(tank.inflowBpd)} bpd</b></div>}
                {fac.issue.repairEta && <div className="row"><span>PUMP FIXED BY</span><b className="w">~{hm(fac.issue.repairEta)}</b></div>}
              </>}
              {type === "pump_wear" && <>
                <div className="row"><span>PUMPING</span><b style={{ color }}>{pumpPct ?? "—"}% of normal flow</b></div>
                <div className="row"><span>FLOW</span><b className="w">{num(pump.flowBpd)} / {num(pump.normalFlowBpd)} bpd</b></div>
                <div className="row"><span>SINCE</span><b className="w">{hm(fac.startedAt)}</b></div>
              </>}
              {type === "leak" && <>
                {pipe.normalPressurePsi != null && <div className="row"><span>PRESSURE</span><b style={{ color }}>{num(pipe.pressurePsi)} psi (normal {num(pipe.normalPressurePsi)})</b></div>}
                {pipe.expectedReceiveBpd != null && <div className="row"><span>MISSING AT DISPOSAL</span><b style={{ color }}>{num(pipe.expectedReceiveBpd - pipe.receiveFlowBpd)} bpd</b></div>}
                <div className="row"><span>SINCE</span><b className="w">{hm(fac.startedAt)}</b></div>
              </>}
            </div>

            <div className="plan">
              <div className="mu" style={{ color: "var(--cy)" }}>DO THIS NOW</div>
              {plan.steps.map((s, i) => <p key={i}>{s}</p>)}
              {(plan.cost != null || plan.nothing != null) && (
                <div className="costs">
                  <span>Cost <b>{money(plan.cost)}</b></span>
                  <span>If you do nothing <b>{money(plan.nothing)}</b></span>
                  {saved != null && <span>You save <b className="sv">{money(saved)}</b></span>}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}