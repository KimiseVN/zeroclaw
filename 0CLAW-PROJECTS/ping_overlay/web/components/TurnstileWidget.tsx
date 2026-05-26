"use client";
import Script from "next/script";
import { useEffect, useRef } from "react";
import { useTurnstile } from "@/lib/turnstile-context";

// ─────────────────────────────────────────────────────────────────────────────
// Cloudflare Turnstile — invisible widget
//
// Real users:  token arrives silently in ~1 s, zero interaction required.
// Bots:        either blocked outright or shown a lightweight challenge.
// Fail-open:   if Turnstile errors / times out / is blocked by an ad-blocker,
//              we emit a "bypass" token so real users are never stuck.
//
// Site key setup:
//   1. Go to https://dash.cloudflare.com/ → Turnstile → Add site
//   2. Widget type: Invisible
//   3. Copy the Site Key into .env.local:
//        NEXT_PUBLIC_TURNSTILE_SITE_KEY=your_real_key_here
//
//   The default below is Cloudflare's official always-pass test key —
//   safe for development but provides no real bot protection.
// ─────────────────────────────────────────────────────────────────────────────

const SITE_KEY =
  process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "1x00000000000000000000AA";

// Extend Window with Cloudflare Turnstile globals
declare global {
  interface Window {
    turnstile?: {
      render(el: HTMLElement, opts: Record<string, unknown>): string;
      remove(widgetId: string): void;
    };
    onTurnstileLoad?: () => void;
  }
}

export default function TurnstileWidget() {
  const { setToken } = useTurnstile();
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetId     = useRef<string | null>(null);

  function mount() {
    if (widgetId.current) return;                 // already rendered
    if (!containerRef.current) return;
    if (!window.turnstile) return;

    widgetId.current = window.turnstile.render(containerRef.current, {
      sitekey:            SITE_KEY,
      size:               "invisible",            // no visible UI for real users
      // ── Callbacks ───────────────────────────────────────────
      callback:           (tok: string) => setToken(tok),         // ✅ human confirmed
      "error-callback":   ()            => setToken("bypass"),    // ⚠️ fail-open on error
      "expired-callback": ()            => setToken(null),        // token expired → re-verify
      "timeout-callback": ()            => setToken("bypass"),    // ⚠️ fail-open on timeout
    });
  }

  useEffect(() => {
    // If script already loaded (e.g., client-side navigation), mount immediately
    if (window.turnstile) { mount(); return; }

    // Otherwise register a global callback for when the script fires its onload
    window.onTurnstileLoad = mount;

    return () => {
      window.onTurnstileLoad = undefined;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      {/*
        ?onload=onTurnstileLoad  → calls window.onTurnstileLoad() when ready
        &render=explicit         → we control when render() is called
      */}
      <Script
        src="https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onTurnstileLoad&render=explicit"
        strategy="afterInteractive"
      />

      {/*
        Invisible anchor element — Turnstile needs a DOM node to attach to.
        Placed off-screen so it never affects layout or accessibility.
      */}
      <div
        ref={containerRef}
        aria-hidden="true"
        style={{
          position:      "fixed",
          bottom:        0,
          right:         0,
          width:         1,
          height:        1,
          overflow:      "hidden",
          opacity:       0,
          pointerEvents: "none",
        }}
      />
    </>
  );
}
