"use client";
import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCookieConsent } from "@/lib/cookie-consent";

const SESSION_KEY = "wwm_tracked";

// ipapi.co — free geo API that supports CORS, no key needed
// Returns the caller's own IP + location (lat/lng/country/city)
async function getGeo(): Promise<{
  ip: string; country: string; country_code: string;
  city: string; lat: number | null; lng: number | null;
} | null> {
  try {
    const res = await fetch("https://ipapi.co/json/", {
      signal: AbortSignal.timeout(4_000),
    });
    if (!res.ok) return null;
    const d = await res.json();
    // ipapi.co returns { error: true } when rate-limited or invalid
    if (d.error) return null;
    return {
      ip:           d.ip           || null,
      country:      d.country_name || null,
      country_code: d.country_code || null,
      city:         d.city         || null,
      lat:          typeof d.latitude  === "number" ? d.latitude  : null,
      lng:          typeof d.longitude === "number" ? d.longitude : null,
    };
  } catch {
    return null;
  }
}

export default function VisitTracker() {
  const { prefs } = useCookieConsent();

  useEffect(() => {
    // Skip if user has explicitly rejected analytics
    if (prefs.decided && !prefs.analytics) return;

    // Skip obvious bots
    const ua = navigator.userAgent.toLowerCase();
    if (
      ua.includes("bot") || ua.includes("crawler") ||
      ua.includes("spider") || ua.includes("prerender")
    ) return;

    // Already tracked this browser session
    if (sessionStorage.getItem(SESSION_KEY)) return;

    async function track() {
      if (sessionStorage.getItem(SESSION_KEY)) return;
      try {
        const geo = await getGeo();
        const sb  = createClient();
        const { error } = await sb.from("visits").insert({
          ip:           geo?.ip           ?? null,
          country:      geo?.country      ?? null,
          country_code: geo?.country_code ?? null,
          city:         geo?.city         ?? null,
          lat:          geo?.lat          ?? null,
          lng:          geo?.lng          ?? null,
          page:         window.location.pathname,
          visited_at:   new Date().toISOString(),
        });
        if (!error) sessionStorage.setItem(SESSION_KEY, "1");
      } catch {
        // Never break user experience
      }
    }

    // Slight delay so page renders first, then track
    const timer = setTimeout(track, 1_500);
    return () => clearTimeout(timer);

  // Re-run if user changes consent decision
  }, [prefs.decided, prefs.analytics]);

  return null;
}
