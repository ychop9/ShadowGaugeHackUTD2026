"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      // Send POST request to backend authentication endpoint
      const response = await fetch("http://localhost:8000/api/v1/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: username,
          password: password,
        }),
      });

      const data = await response.json();

      // Check if response was successful
      if (!response.ok) {
        throw new Error(data.detail || "Invalid operator credentials");
      }

      // Save authentication token and user data to localStorage
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));

      // Redirect operator to the main dashboard
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Failed to connect to authentication server");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#12041f] px-4 font-mono">
      {/* Blurred city background */}
      <div
        aria-hidden
        className="absolute inset-0 scale-110 bg-cover bg-center blur-xs"
        style={{ backgroundImage: "url('/city-bg.png')" }}
      />
      {/* Dark purple tint so the card stands out */}
      <div aria-hidden className="absolute inset-0 bg-[#12041f]/50" />

      {/* Sign-in card */}
      <form
        onSubmit={handleSubmit}
        className="relative z-10 w-full max-w-md rounded-xl border border-fuchsia-500/50 bg-[#1a0b2e]/85 px-8 py-8 shadow-[0_0_30px_rgba(217,70,239,0.45)] backdrop-blur-sm"
      >
        <h1 className="mt-3 text-center text-4xl font-bold tracking-wider text-white [text-shadow:0_0_12px_rgba(232,121,249,0.9)]">
          SIGN IN
        </h1>

        {/* Error Notification Alert */}
        {error && (
          <div className="mt-4 rounded border border-red-500/50 bg-red-950/60 p-3 text-center text-xs font-bold tracking-wider text-red-300 shadow-[0_0_10px_rgba(239,68,68,0.3)]">
            ⚠️ {error}
          </div>
        )}

        {/* Username */}
        <label
          htmlFor="username"
          className="mt-6 block text-xs font-semibold tracking-wider text-violet-200/80"
        >
          OPERATOR USERNAME
        </label>
        <div className="relative mt-2">
          <input
            id="username"
            type="text"
            autoComplete="username"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. admin"
            className="w-full rounded-md border border-violet-700/60 bg-[#0d0418] px-3 py-3 pr-10 text-sm tracking-wider text-violet-100 placeholder:text-violet-400/40 outline-none transition focus:border-fuchsia-500 focus:shadow-[0_0_10px_rgba(217,70,239,0.5)]"
          />
          {/* ID badge icon */}
          <svg
            aria-hidden
            viewBox="0 0 24 24"
            className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-violet-400/60"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <rect x="3" y="6" width="18" height="15" rx="2" />
            <path d="M9 6V4h6v2" />
            <circle cx="12" cy="12" r="2.5" />
            <path d="M8 18c.8-1.8 2.2-2.5 4-2.5s3.2.7 4 2.5" />
          </svg>
        </div>

        {/* Password */}
        <label
          htmlFor="password"
          className="mt-6 block text-xs font-semibold tracking-wider text-violet-200/80"
        >
          PASSWORD
        </label>
        <div className="relative mt-2">
          <input
            id="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••••••"
            className="w-full rounded-md border border-violet-700/60 bg-[#0d0418] px-3 py-3 pr-10 text-sm tracking-wider text-violet-100 placeholder:text-violet-400/40 outline-none transition focus:border-fuchsia-500 focus:shadow-[0_0_10px_rgba(217,70,239,0.5)]"
          />
          <button
            type="button"
            onClick={() => setShowPassword((s) => !s)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-cyan-400 transition hover:text-cyan-300"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
              <circle cx="12" cy="12" r="3" />
              {showPassword && <path d="M3 3l18 18" />}
            </svg>
          </button>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="mt-8 flex w-full items-center justify-center gap-2 rounded-md bg-fuchsia-500 py-3 text-sm font-bold tracking-[0.2em] text-[#1a0b2e] shadow-[0_0_20px_rgba(217,70,239,0.7)] transition hover:bg-fuchsia-400 active:scale-[0.99] disabled:opacity-50"
        >
          {loading ? "AUTHENTICATING..." : "SIGN IN"}
          <svg
            aria-hidden
            viewBox="0 0 24 24"
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
          >
            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
            <path d="M10 17l5-5-5-5" />
            <path d="M15 12H3" />
          </svg>
        </button>

        <p className="mt-6 flex items-center justify-center gap-2 text-[10px] font-semibold tracking-[0.15em] text-cyan-400">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-400 shadow-[0_0_6px_rgba(34,211,238,0.9)]" />
          SYSTEM ONLINE
        </p>
      </form>
    </main>
  );
}