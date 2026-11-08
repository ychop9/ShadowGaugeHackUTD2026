"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

// Fixed star positions (same on server and browser, so no hydration mismatch)
const STARS = Array.from({ length: 70 }, (_, i) => {
  const r = (n: number) => ((Math.sin(i * 12.9898 + n * 78.233) * 43758.5453) % 1 + 1) % 1;
  return {
    // rounded to fixed strings so server and browser render the exact same value
    left: `${(r(1) * 100).toFixed(2)}%`,
    top: `${(r(2) * 100).toFixed(2)}%`,
    size: r(3) > 0.85 ? 2 : 1,
    cyan: r(4) > 0.9,
  };
});

const RIVETS_X = [14, 34, 54, 74, 94];

function DoorPanel({ side }: { side: "left" | "right" }) {
  return (
    <div className="relative h-full w-full border border-black/60 bg-[#221636] bg-[repeating-linear-gradient(0deg,rgba(255,255,255,0.025)_0px,rgba(255,255,255,0.025)_1px,transparent_1px,transparent_4px)] shadow-[inset_0_0_40px_rgba(0,0,0,0.6)]">
      {/* top + bottom rivet rows */}
      <div className="absolute inset-x-0 top-2 flex justify-around px-10">
        {RIVETS_X.map((x) => (
          <span key={x} className="h-2 w-2 rounded-full bg-[#3a2c4f]" />
        ))}
      </div>
      <div className="absolute inset-x-0 bottom-2 flex justify-around px-10">
        {RIVETS_X.map((x) => (
          <span key={x} className="h-2 w-2 rounded-full bg-[#3a2c4f]" />
        ))}
      </div>
      {/* outer-edge hinge bars */}
      <div
        className={`absolute top-[12%] h-[25%] w-1.5 rounded bg-black/50 ${side === "left" ? "left-1" : "right-1"}`}
      />
      <div
        className={`absolute bottom-[12%] h-[25%] w-1.5 rounded bg-black/50 ${side === "left" ? "left-1" : "right-1"}`}
      />
      {/* little handle plate on the left door */}
      {side === "left" && (
        <div className="absolute bottom-[18%] right-2 h-3 w-10 rounded-sm border border-white/10 bg-[#2e2244]" />
      )}
    </div>
  );
}

function Wheel() {
  return (
    <svg viewBox="0 0 220 220" className="h-full w-full">
      <defs>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {/* soft outer halo */}
      <circle cx="110" cy="110" r="104" fill="#2a1240" opacity="0.9" />
      {/* bolts around rim */}
      {[45, 135, 225, 315].map((a) => {
        const rad = (a * Math.PI) / 180;
        return (
          <circle
            key={a}
            cx={(110 + 92 * Math.cos(rad)).toFixed(2)}
            cy={(110 + 92 * Math.sin(rad)).toFixed(2)}
            r="3"
            fill="#5b4a72"
          />
        );
      })}
      {/* neon rings */}
      <circle cx="110" cy="110" r="98" fill="none" stroke="#e040fb" strokeWidth="3" filter="url(#glow)" />
      <circle cx="110" cy="110" r="88" fill="#1a1028" stroke="#c026d3" strokeWidth="2" opacity="0.95" />
      {/* spokes */}
      {[0, 45, 90, 135].map((a) => (
        <rect
          key={a}
          x="104"
          y="26"
          width="12"
          height="168"
          rx="2"
          fill="#2c2140"
          transform={`rotate(${a} 110 110)`}
        />
      ))}
      {/* grips on the main spokes */}
      {[0, 90, 180, 270].map((a) => (
        <rect
          key={a}
          x="104"
          y="20"
          width="12"
          height="10"
          rx="2"
          fill="#4a3b60"
          transform={`rotate(${a} 110 110)`}
        />
      ))}
      {/* hub */}
      <circle cx="110" cy="110" r="32" fill="#1c1430" stroke="#4a3b60" strokeWidth="3" />
      <circle cx="110" cy="110" r="17" fill="#2a1240" stroke="#e040fb" strokeWidth="2.5" filter="url(#glow)" />
      <circle cx="110" cy="110" r="6" fill="#22d3ee" filter="url(#glow)" />
    </svg>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const [stage, setStage] = useState<"idle" | "turning" | "opening" | "entering">("idle");

  // load the login page in the background so the switch is instant
  useEffect(() => {
    router.prefetch("/login");
  }, [router]);

  function enter() {
    if (stage !== "idle") return;
    setStage("turning");
    setTimeout(() => setStage("opening"), 1100); // wheel finishes spinning -> doors start opening
    setTimeout(() => setStage("entering"), 1400); // zoom through the opening doors
    setTimeout(() => router.push("/login"), 2100); // zoom done -> login picks up the motion
  }

  const open = stage === "opening" || stage === "entering";
  const entering = stage === "entering";
  const doorEase = "ease-[cubic-bezier(0.65,0,0.35,1)]";

  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-[radial-gradient(ellipse_at_center,#1e0a33_0%,#0c0518_70%)] px-4 font-mono">
      {/* stars */}
      {STARS.map((s, i) => (
        <span
          key={i}
          aria-hidden
          className={`absolute rounded-full ${s.cyan ? "bg-cyan-300/70" : "bg-white/60"}`}
          style={{ left: s.left, top: s.top, width: s.size, height: s.size }}
        />
      ))}

      {/* everything that zooms forward when entering */}
      <div
        className={`relative z-10 flex w-full flex-col items-center transition-[transform,opacity] duration-[700ms] ease-in ${entering ? "scale-[1.8] opacity-0" : ""}`}
      >
      {/* vault frame */}
      <div className="relative z-10 w-full max-w-3xl rounded-lg border border-fuchsia-900/40 bg-[#160c24] shadow-[0_0_40px_rgba(168,85,247,0.15)]">
        {/* top bar */}
        <div className="relative flex h-7 items-center justify-between border-b border-black/60 px-5">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-[#3a2c4f]" />
            <span className="h-2 w-2 rounded-full bg-[#3a2c4f]" />
            <span className="ml-2 h-1 w-20 rounded bg-[#2a2038]" />
          </div>
          <div className="absolute left-1/2 flex -translate-x-1/2 items-center gap-2">
            <span className="h-px w-16 bg-fuchsia-500/70" />
            <span className="h-2 w-2 rounded-full bg-fuchsia-500 shadow-[0_0_8px_#e040fb]" />
            <span className="h-px w-16 bg-fuchsia-500/70" />
          </div>
          <div className="flex items-center gap-2">
            <span className="mr-2 h-1 w-20 rounded bg-[#2a2038]" />
            <span className="h-2 w-2 rounded-full bg-[#3a2c4f]" />
            <span className="h-2 w-2 rounded-full bg-[#3a2c4f]" />
          </div>
        </div>

        {/* door area */}
        <div className="relative aspect-[16/9] overflow-hidden bg-black/80 p-3">
          {/* light behind the doors, seen when they open */}
          <div
            className={`absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(232,121,249,0.35),transparent_60%)] transition-opacity duration-1000 ${open ? "opacity-100" : "opacity-0"}`}
          />

          {/* corner brackets */}
          {["left-0 top-0", "right-0 top-0", "left-0 bottom-0", "right-0 bottom-0"].map((p) => (
            <span key={p} className={`absolute z-20 h-8 w-12 border border-white/5 bg-[#2a2038] ${p}`} />
          ))}

          <div className="relative flex h-full gap-0">
            <div
              className={`h-full w-1/2 transition-transform duration-[1200ms] ${doorEase} ${open ? "-translate-x-full" : ""}`}
            >
              <DoorPanel side="left" />
            </div>
            <div
              className={`h-full w-1/2 transition-transform duration-[1200ms] ${doorEase} ${open ? "translate-x-full" : ""}`}
            >
              <DoorPanel side="right" />
            </div>

            {/* center seam with lock squares */}
            <div
              className={`pointer-events-none absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-fuchsia-500 shadow-[0_0_8px_#e040fb] transition-opacity duration-500 ${open ? "opacity-0" : ""}`}
            >
              <span className="absolute left-1/2 top-[8%] h-3.5 w-3.5 -translate-x-1/2 border-2 border-fuchsia-500 bg-[#160c24]" />
              <span className="absolute bottom-[8%] left-1/2 h-3.5 w-3.5 -translate-x-1/2 border-2 border-fuchsia-500 bg-[#160c24]" />
            </div>

            {/* the wheel */}
            <button
              type="button"
              onClick={enter}
              aria-label="Turn the wheel to enter"
              className={`absolute left-1/2 top-1/2 aspect-square w-[30%] -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full drop-shadow-[0_0_25px_rgba(217,70,239,0.6)] transition-[opacity,filter] duration-700 ease-out hover:drop-shadow-[0_0_35px_rgba(217,70,239,0.9)] ${open ? "opacity-0" : ""}`}
            >
              <div
                className={`h-full w-full transition-transform duration-[1100ms] ease-in-out ${stage !== "idle" ? "rotate-[360deg]" : ""}`}
              >
                <Wheel />
              </div>
            </button>
          </div>
        </div>

        {/* bottom bar */}
        <div className="flex h-7 items-center justify-between border-t border-black/60 px-5">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-[#3a2c4f]" />
            <span className="h-2 w-2 rounded-full bg-[#3a2c4f]" />
            <span className="ml-2 h-1 w-20 rounded bg-[#2a2038]" />
          </div>
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-3 rounded-sm border border-white/10" />
            <span className="h-2.5 w-2.5 rounded-sm bg-[#3a2c4f]" />
            <span className="h-1.5 w-3 rounded-sm border border-white/10" />
          </div>
          <div className="flex items-center gap-2">
            <span className="mr-2 h-1 w-20 rounded bg-[#2a2038]" />
            <span className="h-2 w-2 rounded-full bg-[#3a2c4f]" />
            <span className="h-2 w-2 rounded-full bg-[#3a2c4f]" />
          </div>
        </div>
      </div>

      {/* label */}
      <button
        type="button"
        onClick={enter}
        className="relative z-10 mt-8 text-xl font-bold tracking-[0.35em] text-fuchsia-500 [text-shadow:0_0_10px_rgba(217,70,239,0.8)] transition hover:text-fuchsia-400"
      >
        {stage === "idle" ? "TURN TO ENTER" : "UNLOCKING..."}
      </button>
      <span className="relative z-10 mt-3 h-px w-24 bg-fuchsia-500/60" />
      </div>

      {/* cover that fades to the login page's background color while zooming, so there's no visible cut */}
      <div
        aria-hidden
        className={`pointer-events-none fixed inset-0 z-50 bg-[#12041f] transition-opacity duration-[700ms] ease-in ${entering ? "opacity-100" : "opacity-0"}`}
      />

      {/* floor reflection */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-24 border-t border-white/5 bg-gradient-to-b from-[#0f0820] to-[#07030f]"
      >
        <div className="absolute left-1/2 top-0 h-full w-px bg-fuchsia-500/40" />
        <div className="absolute left-1/2 top-2 h-16 w-72 -translate-x-1/2 rounded-full bg-[radial-gradient(ellipse,rgba(217,70,239,0.25),rgba(34,211,238,0.1)_40%,transparent_70%)] blur-md" />
      </div>
    </main>
  );
}
