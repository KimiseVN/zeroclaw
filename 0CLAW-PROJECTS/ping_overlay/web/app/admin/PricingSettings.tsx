"use client";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { PLANS } from "@/lib/plans";
import styles from "./admin.module.css";

// ─── helpers ─────────────────────────────────────────────────────────────────
function fmtUsd(n: number) { return "$" + Number(n).toFixed(2).replace(/\.00$/, ""); }
function fmtVnd(n: number) { return Math.round(n).toLocaleString("vi-VN") + " ₫"; }

// ─── types ────────────────────────────────────────────────────────────────────
type PlanRow = {
  id:          string;
  usd:         string; // string for <input> binding
  vnd:         string;
  paypalUrl:   string;
  badge_en:    string;
  badge_vi:    string;
  cls:         string;   // "" | "popular" | "best"
  features_en: string;   // newline-separated
  features_vi: string;
};

// ─── merge saved DB data onto static plan base ────────────────────────────────
function initRow(staticPlan: typeof PLANS[0], saved?: Record<string, any>): PlanRow {
  const s        = saved ?? {};
  const badge    = s.badge    ?? staticPlan.badge;
  const features = s.features ?? staticPlan.features;
  return {
    id:          staticPlan.id,
    usd:         String(s.usd         ?? staticPlan.usd),
    vnd:         String(s.vnd         ?? staticPlan.vnd),
    paypalUrl:   String(s.paypalUrl   ?? staticPlan.paypalUrl),
    badge_en:    badge?.en ?? "",
    badge_vi:    badge?.vi ?? "",
    cls:         s.cls      ?? staticPlan.cls ?? "",
    features_en: ((features?.en ?? []) as string[]).join("\n"),
    features_vi: ((features?.vi ?? []) as string[]).join("\n"),
  };
}

// ─── single plan card ─────────────────────────────────────────────────────────
function PlanCard({
  row,
  onChange,
}: {
  row: PlanRow;
  onChange: (field: keyof PlanRow, val: string) => void;
}) {
  const staticPlan = PLANS.find(p => p.id === row.id)!;
  const usdNum     = parseFloat(row.usd)  || 0;
  const vndNum     = parseFloat(row.vnd)  || 0;

  return (
    <div className={styles.settingCard}>
      {/* header */}
      <h3 className={styles.settingCardTitle}>
        {staticPlan.label.en}
        <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400, marginLeft: 10, fontFamily: "monospace" }}>
          id: {row.id} · {staticPlan.days > 0 ? `${staticPlan.days}d` : "Lifetime"}
        </span>
      </h3>

      {/* ── Prices ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Price (USD)</label>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: "var(--text-muted)", fontSize: 15, flexShrink: 0 }}>$</span>
            <input
              className={styles.input}
              type="number" min={0} step={0.01}
              value={row.usd}
              onChange={e => onChange("usd", e.target.value)}
              style={{ maxWidth: 110, fontFamily: "monospace" }}
            />
            <span style={{ fontSize: 12, color: "var(--cyan)", flexShrink: 0 }}>{fmtUsd(usdNum)}</span>
          </div>
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Price (VND)</label>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              className={styles.input}
              type="number" min={0} step={1000}
              value={row.vnd}
              onChange={e => onChange("vnd", e.target.value)}
              style={{ maxWidth: 160, fontFamily: "monospace" }}
            />
            <span style={{ fontSize: 12, color: "var(--cyan)", flexShrink: 0 }}>{fmtVnd(vndNum)}</span>
          </div>
        </div>
      </div>

      {/* ── PayPal ── */}
      <div className={styles.formGroup}>
        <label className={styles.formLabel}>PayPal Payment URL</label>
        <input
          className={styles.input}
          type="url"
          value={row.paypalUrl}
          onChange={e => onChange("paypalUrl", e.target.value)}
          placeholder="https://www.paypal.com/ncp/payment/..."
          spellCheck={false}
        />
        <p className={styles.inputHint}>
          PayPal.me, Buy Now, or ncp/payment links. Leave blank to hide PayPal for this plan.
        </p>
      </div>

      {/* ── Badge / style ── */}
      <div style={{ display: "grid", gridTemplateColumns: "140px 1fr 1fr", gap: 12, alignItems: "start" }}>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Card Style</label>
          <select
            className={styles.input}
            value={row.cls}
            onChange={e => onChange("cls", e.target.value)}
          >
            <option value="">Normal</option>
            <option value="popular">Popular</option>
            <option value="best">Best Value</option>
          </select>
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Badge (EN)</label>
          <input
            className={styles.input}
            value={row.badge_en}
            onChange={e => onChange("badge_en", e.target.value)}
            placeholder="Most Popular"
          />
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Badge (VI)</label>
          <input
            className={styles.input}
            value={row.badge_vi}
            onChange={e => onChange("badge_vi", e.target.value)}
            placeholder="Phổ biến nhất"
          />
        </div>
      </div>

      {/* ── Features ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Features (EN) — one per line</label>
          <textarea
            className={styles.input}
            rows={4}
            value={row.features_en}
            onChange={e => onChange("features_en", e.target.value)}
            style={{ resize: "vertical", fontSize: 13, lineHeight: 1.5 }}
            placeholder={"Full overlay\nNetwork + FPS\nAuto update"}
          />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Features (VI) — mỗi dòng 1 tính năng</label>
          <textarea
            className={styles.input}
            rows={4}
            value={row.features_vi}
            onChange={e => onChange("features_vi", e.target.value)}
            style={{ resize: "vertical", fontSize: 13, lineHeight: 1.5 }}
            placeholder={"Full overlay\nNetwork + FPS\nAuto update"}
          />
        </div>
      </div>
    </div>
  );
}

// ─── main export ──────────────────────────────────────────────────────────────
export default function PricingSettings({ initial }: { initial: Record<string, any> }) {
  // Merge DB overrides onto static plan definitions
  const savedPlans = Array.isArray(initial.plans) ? (initial.plans as any[]) : [];

  const [rows, setRows] = useState<PlanRow[]>(
    PLANS.map(plan => {
      const saved = savedPlans.find((s: any) => s.id === plan.id);
      return initRow(plan, saved);
    }),
  );

  const [busy, setBusy] = useState(false);
  const [msg,  setMsg]  = useState("");

  function change(id: string, field: keyof PlanRow, val: string) {
    setRows(prev => prev.map(r => r.id === id ? { ...r, [field]: val } : r));
  }

  async function save() {
    setBusy(true); setMsg("");

    const planData = rows.map(r => ({
      id:       r.id,
      usd:      Math.max(0, parseFloat(r.usd)  || 0),
      vnd:      Math.max(0, Math.round(parseFloat(r.vnd) || 0)),
      paypalUrl: r.paypalUrl.trim(),
      badge:    (r.badge_en.trim() || r.badge_vi.trim())
        ? { en: r.badge_en.trim(), vi: r.badge_vi.trim() }
        : null,
      cls:      r.cls || null,
      features: {
        en: r.features_en.split("\n").map(l => l.trim()).filter(Boolean),
        vi: r.features_vi.split("\n").map(l => l.trim()).filter(Boolean),
      },
    }));

    const { error } = await createClient()
      .from("site_settings")
      .upsert(
        { key: "pricing_plans", value: { plans: planData }, updated_at: new Date().toISOString() },
        { onConflict: "key" },
      );

    setBusy(false);
    if (error) { setMsg("Error: " + error.message); return; }
    setMsg("Saved!"); setTimeout(() => setMsg(""), 2500);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

      {/* Intro */}
      <div style={{
        background: "rgba(0,229,255,.06)", border: "1px solid rgba(0,229,255,.18)",
        borderRadius: 10, padding: "12px 16px", fontSize: 13, color: "var(--text-dim)",
        lineHeight: 1.6,
      }}>
        <strong style={{ color: "var(--cyan)" }}>Pricing Plans</strong> — changes are reflected live on the website Pricing section.
        Plan IDs and durations are fixed (they map to license codes). Edit prices, PayPal links, badges, and feature bullets below.
      </div>

      {rows.map(row => (
        <PlanCard
          key={row.id}
          row={row}
          onChange={(field, val) => change(row.id, field, val)}
        />
      ))}

      {/* Save bar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "12px 20px",
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 12, position: "sticky", bottom: 16,
      }}>
        {msg && (
          <span style={{ fontSize: 13, color: msg.startsWith("Error") ? "var(--red)" : "var(--green)" }}>
            {msg}
          </span>
        )}
        <button
          className="btn btn-primary"
          style={{ marginLeft: "auto" }}
          onClick={save}
          disabled={busy}
        >
          {busy ? "Saving…" : "💾 Save All Plans"}
        </button>
      </div>
    </div>
  );
}
