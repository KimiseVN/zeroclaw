"use client";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import type { GlobePoint } from "@/components/GlobeViz";
import aStyles from "./analytics.module.css";

// Dynamic import — Three.js must not run on server
const GlobeViz = dynamic(() => import("@/components/GlobeViz"), {
  ssr: false,
  loading: () => (
    <div className={aStyles.globePlaceholder}>
      <div className="spinner" />
    </div>
  ),
});

// ── Types ─────────────────────────────────────────────────────────────────────
export type VisitRow = {
  ip: string | null;
  country: string | null;
  country_code: string | null;
  city: string | null;
  lat: number | null;
  lng: number | null;
  visited_at: string;
};

type CountryStat = { country: string; code: string; count: number; pct: number };

// ── Helpers ───────────────────────────────────────────────────────────────────
function flag(code: string) {
  if (!code || code.length !== 2) return "🌐";
  return String.fromCodePoint(
    ...[...code.toUpperCase()].map(c => 0x1f1e6 + c.charCodeAt(0) - 65),
  );
}

function fmtNum(n: number) {
  return n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n);
}

const PERIODS = [
  { label: "7d",  days: 7  },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
];

// ── Component ─────────────────────────────────────────────────────────────────
export default function Analytics({ visits: allVisits }: { visits: VisitRow[] }) {
  const [periodDays, setPeriodDays] = useState(30);

  // Filter to period
  const cutoff = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - periodDays);
    return d;
  }, [periodDays]);

  const visits = useMemo(
    () => allVisits.filter(v => new Date(v.visited_at) >= cutoff),
    [allVisits, cutoff],
  );

  // Stats
  const totalVisits  = visits.length;
  const uniqueIPs    = new Set(visits.map(v => v.ip).filter(Boolean)).size;
  const uniqueCtries = new Set(visits.map(v => v.country_code).filter(Boolean)).size;
  const today        = useMemo(() => {
    const d = new Date(); d.setHours(0,0,0,0);
    return allVisits.filter(v => new Date(v.visited_at) >= d).length;
  }, [allVisits]);

  // Globe points — aggregate by rounded lat/lng
  const globePoints = useMemo<GlobePoint[]>(() => {
    const map = new Map<string, GlobePoint>();
    visits.forEach(v => {
      if (v.lat == null || v.lng == null) return;
      const key = `${(v.lat).toFixed(1)},${(v.lng).toFixed(1)}`;
      const existing = map.get(key);
      if (existing) existing.weight++;
      else map.set(key, { lat: v.lat, lng: v.lng, weight: 1 });
    });
    return Array.from(map.values());
  }, [visits]);

  // Top 10 countries
  const topCountries = useMemo<CountryStat[]>(() => {
    const map = new Map<string, CountryStat>();
    visits.forEach(v => {
      if (!v.country_code) return;
      const existing = map.get(v.country_code);
      if (existing) existing.count++;
      else map.set(v.country_code, { country: v.country ?? v.country_code, code: v.country_code, count: 1, pct: 0 });
    });
    const sorted = Array.from(map.values()).sort((a, b) => b.count - a.count).slice(0, 10);
    const total  = sorted.reduce((s, c) => s + c.count, 0) || 1;
    return sorted.map(c => ({ ...c, pct: Math.round(c.count / total * 100) }));
  }, [visits]);

  return (
    <div className={aStyles.wrap}>
      {/* Period selector */}
      <div className={aStyles.periodRow}>
        <span className={aStyles.periodLabel}>Period:</span>
        {PERIODS.map(p => (
          <button
            key={p.days}
            className={`${aStyles.periodBtn} ${periodDays === p.days ? aStyles.periodActive : ""}`}
            onClick={() => setPeriodDays(p.days)}
          >
            {p.label}
          </button>
        ))}
        <span className={aStyles.totalHint}>{fmtNum(allVisits.length)} visits total in DB</span>
      </div>

      {/* Stats row */}
      <div className={aStyles.stats}>
        {[
          { label: "Visits",     val: fmtNum(totalVisits),  accent: false },
          { label: "Unique IPs", val: fmtNum(uniqueIPs),    accent: false },
          { label: "Countries",  val: String(uniqueCtries), accent: false },
          { label: "Today",      val: fmtNum(today),        accent: true  },
        ].map(s => (
          <div key={s.label} className={aStyles.stat}>
            <span className={`${aStyles.statNum} ${s.accent ? aStyles.statAccent : ""}`}>{s.val}</span>
            <span className={aStyles.statLabel}>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Globe + countries */}
      <div className={aStyles.main}>
        {/* Globe */}
        <div className={aStyles.globeWrap}>
          <GlobeViz points={globePoints} />
          <p className={aStyles.globeHint}>
            {globePoints.length} location{globePoints.length !== 1 ? "s" : ""} · Drag to rotate
          </p>
        </div>

        {/* Top countries */}
        <div className={aStyles.countries}>
          <p className={aStyles.countriesTitle}>Top Countries</p>
          {topCountries.length === 0 ? (
            <p className={aStyles.noData}>No location data yet.</p>
          ) : (
            <div className={aStyles.countryList}>
              {topCountries.map((c, i) => (
                <div key={c.code} className={aStyles.countryRow}>
                  <span className={aStyles.rank}>#{i + 1}</span>
                  <span className={aStyles.flagEmoji}>{flag(c.code)}</span>
                  <div className={aStyles.countryInfo}>
                    <div className={aStyles.countryName}>{c.country}</div>
                    <div className={aStyles.countryBar}>
                      <div className={aStyles.countryBarFill} style={{ width: `${c.pct}%` }} />
                    </div>
                  </div>
                  <div className={aStyles.countryCount}>
                    <span className={aStyles.countryNum}>{fmtNum(c.count)}</span>
                    <span className={aStyles.countryPct}>{c.pct}%</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
