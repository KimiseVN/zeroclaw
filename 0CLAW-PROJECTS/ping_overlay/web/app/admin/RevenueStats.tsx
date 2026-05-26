"use client";
import { useMemo, useState } from "react";
import type { Order, PaymentConfig } from "@/lib/supabase/types";
import styles from "./revenue-stats.module.css";

// ─────────────────────────────────────────────────────────────────────────────
const METHOD_META: Record<string, { icon: string; label: string; color: string }> = {
  paypal: { icon: "💳", label: "PayPal",    color: "#00B2FF" },
  stripe: { icon: "💎", label: "Stripe",    color: "#9B59FF" },
  usdt:   { icon: "🪙", label: "USDT",      color: "#26A17B" },
  btc:    { icon: "₿",  label: "Bitcoin",   color: "#F7931A" },
  eth:    { icon: "⟠",  label: "Ethereum",  color: "#627EEA" },
  bank:   { icon: "🏦", label: "Bank (VN)", color: "#00FF88" },
};

const PERIODS = [
  { label: "7d",  days: 7  },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
  { label: "All", days: -1 },
];

function fmt(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

type Props = { orders: Order[]; paymentConfigs: PaymentConfig[] };

export default function RevenueStats({ orders, paymentConfigs }: Props) {
  const [days, setDays] = useState(30);

  const enabledMethods = useMemo(
    () => new Set(paymentConfigs.filter(c => c.enabled).map(c => c.id)),
    [paymentConfigs],
  );

  // Only paid orders within the selected period
  const paid = useMemo(() => {
    const cutoff = days < 0 ? null : new Date(Date.now() - days * 86_400_000);
    return orders.filter(o =>
      o.status === "paid" &&
      (cutoff === null || new Date(o.created_at) >= cutoff),
    );
  }, [orders, days]);

  const totalRevenue = paid.reduce((s, o) => s + (o.amount_usd ?? 0), 0);
  const totalOrders  = paid.length;
  const avgOrder     = totalOrders ? totalRevenue / totalOrders : 0;

  // ── Aggregate by payment method ────────────────────────────────────────────
  const byMethod = useMemo(() => {
    const map = new Map<string, { count: number; revenue: number }>();
    paid.forEach(o => {
      const m = o.payment_method;
      const ex = map.get(m);
      if (ex) { ex.count++; ex.revenue += o.amount_usd ?? 0; }
      else      map.set(m, { count: 1, revenue: o.amount_usd ?? 0 });
    });
    return [...map.entries()]
      .map(([method, d]) => ({
        method, ...d,
        pct: totalRevenue ? Math.round(d.revenue / totalRevenue * 100) : 0,
      }))
      .sort((a, b) => b.revenue - a.revenue);
  }, [paid, totalRevenue]);

  // ── Aggregate by plan ──────────────────────────────────────────────────────
  const byPlan = useMemo(() => {
    const map = new Map<string, { label: string; count: number; revenue: number }>();
    paid.forEach(o => {
      const key   = o.plan_id;
      const label = o.plan_label ?? o.plan_id;
      const ex    = map.get(key);
      if (ex) { ex.count++; ex.revenue += o.amount_usd ?? 0; }
      else      map.set(key, { label, count: 1, revenue: o.amount_usd ?? 0 });
    });
    return [...map.entries()]
      .map(([plan_id, d]) => ({
        plan_id, ...d,
        pct: totalRevenue ? Math.round(d.revenue / totalRevenue * 100) : 0,
      }))
      .sort((a, b) => b.revenue - a.revenue);
  }, [paid, totalRevenue]);

  // ── Monthly/weekly breakdown (last N buckets) ──────────────────────────────
  const timeline = useMemo(() => {
    if (paid.length === 0) return [];
    // Bucket by week if ≤ 30 d, by month otherwise
    const useWeeks = days > 0 && days <= 30;
    const buckets = new Map<string, number>();
    paid.forEach(o => {
      const d = new Date(o.created_at);
      let key: string;
      if (useWeeks) {
        // Week label: "May W2"
        const weekNum = Math.floor(d.getDate() / 7) + 1;
        key = `${d.toLocaleString("en-US", { month: "short" })} W${weekNum}`;
      } else {
        key = d.toLocaleString("en-US", { month: "short", year: "numeric" });
      }
      buckets.set(key, (buckets.get(key) ?? 0) + (o.amount_usd ?? 0));
    });
    const sorted = [...buckets.entries()].reverse();
    const maxVal = Math.max(...sorted.map(([, v]) => v), 1);
    return sorted.map(([label, value]) => ({ label, value, pct: Math.round(value / maxVal * 100) }));
  }, [paid, days]);

  return (
    <div className={styles.wrap}>

      {/* ── Period selector ─────────────────────────────────────────────────── */}
      <div className={styles.periodRow}>
        <span className={styles.periodLabel}>Period:</span>
        {PERIODS.map(p => (
          <button
            key={p.days}
            className={`${styles.periodBtn} ${days === p.days ? styles.periodActive : ""}`}
            onClick={() => setDays(p.days)}
          >
            {p.label}
          </button>
        ))}
        <span className={styles.hint}>{totalOrders} paid order{totalOrders !== 1 ? "s" : ""}</span>
      </div>

      {/* ── KPI cards ───────────────────────────────────────────────────────── */}
      <div className={styles.kpis}>
        <div className={`${styles.kpi} ${styles.kpiCyan}`}>
          <span className={styles.kpiNum}>${fmt(totalRevenue)}</span>
          <span className={styles.kpiLabel}>Total Revenue (USD)</span>
        </div>
        <div className={styles.kpi}>
          <span className={styles.kpiNum}>{totalOrders}</span>
          <span className={styles.kpiLabel}>Paid Orders</span>
        </div>
        <div className={styles.kpi}>
          <span className={styles.kpiNum}>${fmt(avgOrder)}</span>
          <span className={styles.kpiLabel}>Avg. Order Value</span>
        </div>
      </div>

      {totalOrders === 0 ? (
        <div className={styles.empty}>No paid orders in this period.</div>
      ) : (
        <>
          {/* ── Breakdown grid ────────────────────────────────────────────── */}
          <div className={styles.grid}>

            {/* By payment method */}
            <div className={styles.card}>
              <h3 className={styles.cardTitle}>By Payment Method</h3>
              {byMethod.length === 0 ? (
                <p className={styles.cardEmpty}>No data</p>
              ) : (
                <div className={styles.rows}>
                  {byMethod.map(({ method, revenue, count, pct }) => {
                    const meta      = METHOD_META[method] ?? { icon: "💰", label: method, color: "var(--cyan)" };
                    const isEnabled = enabledMethods.has(method);
                    return (
                      <div key={method} className={styles.row}>
                        <span className={styles.rowIcon}>{meta.icon}</span>
                        <div className={styles.rowMid}>
                          <div className={styles.rowName}>
                            {meta.label}
                            {!isEnabled && <span className={styles.offBadge}>off</span>}
                          </div>
                          <div className={styles.barTrack}>
                            <div className={styles.barFill} style={{ width: `${pct}%`, background: meta.color }} />
                          </div>
                        </div>
                        <div className={styles.rowRight}>
                          <span className={styles.rowAmt}>${fmt(revenue)}</span>
                          <span className={styles.rowSub}>{pct}% · {count} orders</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* By plan */}
            <div className={styles.card}>
              <h3 className={styles.cardTitle}>By Plan</h3>
              {byPlan.length === 0 ? (
                <p className={styles.cardEmpty}>No data</p>
              ) : (
                <div className={styles.rows}>
                  {byPlan.map(({ plan_id, label, revenue, count, pct }) => (
                    <div key={plan_id} className={styles.row}>
                      <span className={styles.rowIcon}>📦</span>
                      <div className={styles.rowMid}>
                        <div className={styles.rowName}>{label}</div>
                        <div className={styles.barTrack}>
                          <div className={styles.barFill} style={{ width: `${pct}%`, background: "var(--cyan)" }} />
                        </div>
                      </div>
                      <div className={styles.rowRight}>
                        <span className={styles.rowAmt}>${fmt(revenue)}</span>
                        <span className={styles.rowSub}>{pct}% · {count} orders</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ── Timeline bar chart ─────────────────────────────────────────── */}
          {timeline.length > 1 && (
            <div className={styles.card} style={{ marginTop: 20 }}>
              <h3 className={styles.cardTitle}>Revenue Over Time</h3>
              <div className={styles.timeline}>
                {timeline.map(({ label, value, pct }) => (
                  <div key={label} className={styles.tlCol}>
                    <span className={styles.tlAmt}>${value < 1000 ? value.toFixed(0) : (value / 1000).toFixed(1) + "k"}</span>
                    <div className={styles.tlBarWrap}>
                      <div className={styles.tlBar} style={{ height: `${Math.max(pct, 4)}%` }} />
                    </div>
                    <span className={styles.tlLabel}>{label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
