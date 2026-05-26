"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useGeneralSettings } from "@/lib/use-site-settings";
import type { GlobePoint } from "@/components/GlobeViz";
import styles from "./VisitorStats.module.css";

// Three.js must not run on server
const GlobeViz = dynamic(() => import("@/components/GlobeViz"), {
  ssr: false,
  loading: () => <div className={styles.globePlaceholder}><div className="spinner" /></div>,
});

type TopCountry = { country: string; code: string; count: number; pct: number };

function flag(code: string) {
  if (!code || code.length !== 2) return "🌐";
  return String.fromCodePoint(
    ...[...code.toUpperCase()].map(c => 0x1f1e6 + c.charCodeAt(0) - 65),
  );
}

function fmtNum(n: number) {
  return n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n);
}

export default function VisitorStats() {
  const general = useGeneralSettings();

  const [loading,      setLoading]      = useState(true);
  const [totals,       setTotals]       = useState({ total_visits: 0, countries: 0, today: 0 });
  const [topCountries, setTopCountries] = useState<TopCountry[]>([]);
  const [globePoints,  setGlobePoints]  = useState<GlobePoint[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const { data, error } = await createClient().rpc("public_visit_stats", { days_back: 30 });
        if (error || !data) return;

        setTotals({
          total_visits: Number(data.total_visits ?? 0),
          countries:    Number(data.countries    ?? 0),
          today:        Number(data.today        ?? 0),
        });

        // Top countries — compute % share
        const raw: { country: string; code: string; count: number }[] = data.top_countries ?? [];
        const total = raw.reduce((s, c) => s + Number(c.count), 0) || 1;
        setTopCountries(
          raw.map(c => ({ ...c, count: Number(c.count), pct: Math.round(Number(c.count) / total * 100) })),
        );

        // Globe aggregated points
        setGlobePoints(
          (data.globe_points ?? []).map((p: any) => ({
            lat: Number(p.lat), lng: Number(p.lng), weight: Number(p.weight),
          })),
        );
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const STATS = [
    { label: "Visits (30d)", val: fmtNum(totals.total_visits), accent: false },
    { label: "Countries",    val: String(totals.countries),    accent: false },
    { label: "Today",        val: fmtNum(totals.today),        accent: true  },
  ];

  // Admin can hide this section via Website Settings → Visitor Stats toggle
  if (general.show_visitor_stats === false) return null;

  return (
    <section id="visitors" className={`section-pad ${styles.section}`}>
      <div className="container">
      <div className="section-label center">
        <p className="eyebrow"><span className="dot" /> Live Stats</p>
        <h2>Players Around the World</h2>
        <p className="section-lead" style={{ margin: "10px auto 0", textAlign: "center" }}>
          Real-time visitor activity · last 30 days
        </p>
      </div>

      {loading ? (
        <div className={styles.loadingWrap}><div className="spinner" /></div>
      ) : (
        <>
          {/* ── Stats row ─────────────────────────────────────────────────── */}
          <div className={styles.stats}>
            {STATS.map(s => (
              <div key={s.label} className={styles.stat}>
                <span className={`${styles.statNum} ${s.accent ? styles.statAccent : ""}`}>{s.val}</span>
                <span className={styles.statLabel}>{s.label}</span>
              </div>
            ))}
          </div>

          {/* ── Globe + countries ─────────────────────────────────────────── */}
          <div className={styles.main}>
            <div className={styles.globeWrap}>
              <GlobeViz points={globePoints} />
              <p className={styles.globeHint}>
                {globePoints.length} location{globePoints.length !== 1 ? "s" : ""} · Drag to rotate
              </p>
            </div>

            <div className={styles.countries}>
              <p className={styles.countriesTitle}>Top Countries</p>
              {topCountries.length === 0 ? (
                <p className={styles.noData}>No location data yet.</p>
              ) : (
                <div className={styles.countryList}>
                  {topCountries.map((c, i) => (
                    <div key={c.code} className={styles.countryRow}>
                      <span className={styles.rank}>#{i + 1}</span>
                      <span className={styles.flagEmoji}>{flag(c.code)}</span>
                      <div className={styles.countryInfo}>
                        <div className={styles.countryName}>{c.country}</div>
                        <div className={styles.countryBar}>
                          <div className={styles.countryBarFill} style={{ width: `${c.pct}%` }} />
                        </div>
                      </div>
                      <div className={styles.countryCount}>
                        <span className={styles.countryNum}>{fmtNum(c.count)}</span>
                        <span className={styles.countryPct}>{c.pct}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
      </div>
    </section>
  );
}
