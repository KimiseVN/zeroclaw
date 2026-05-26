"use client";
import { useState } from "react";
import { useCart } from "@/lib/cart-context";
import { useGeneralSettings, useTrialSettings, usePricingPlans, fmtTrialLabel } from "@/lib/use-site-settings";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import type { Plan } from "@/lib/plans";
import styles from "./Pricing.module.css";

function fmtUsd(n: number) { return "$" + n.toFixed(2).replace(".00", ""); }
function fmtVnd(n: number) { return n.toLocaleString("vi-VN") + " ₫"; }

export default function Pricing() {
  const { addToCart } = useCart();
  const general = useGeneralSettings();
  const trial   = useTrialSettings();
  const PLANS   = usePricingPlans();
  const { lang } = useLanguage();
  const p = T.pricing;
  const discord = general.discord_url || "https://discord.gg/zeroclaw";
  const trialLabel = fmtTrialLabel(trial.days);
  const [noticePlan, setNoticePlan] = useState<Plan | null>(null);

  function proceed() {
    if (!noticePlan) return;
    addToCart(noticePlan);   // opens cart drawer automatically
    setNoticePlan(null);
  }

  return (
    <section id="pricing" className={styles.section}>
      <div className="container">
      <div className="section-label center">
        <p className="eyebrow"><span className="dot" /> {p.eyebrow[lang]}</p>
        <h2>{p.heading[lang]}</h2>
        <p className="section-lead" style={{ marginInline: "auto" }}>
          {lang === "vi"
            ? <>Dùng thử <strong>{trialLabel}</strong> miễn phí khi chạy lần đầu. Sau thử nghiệm, chọn gói để mở khóa toàn bộ tính năng.</>
            : <>Free <strong>{trialLabel}</strong> trial on first launch. After trial, choose a plan to unlock all features.</>}
        </p>
      </div>

      <div className={styles.grid}>
        {PLANS.map(plan => (
          <div key={plan.id} className={`${styles.card} ${plan.cls ? styles[plan.cls as keyof typeof styles] : ""}`}>
            {plan.badge && <div className={styles.badge}>{plan.badge[lang]}</div>}
            <div className={styles.duration}>{plan.label[lang]}</div>
            <div className={styles.price}>{fmtUsd(plan.usd)}</div>
            <div className={styles.priceVnd}>≈ {fmtVnd(plan.vnd)}</div>
            <ul className={styles.features}>
              {plan.features[lang].map(f => <li key={f}>{f}</li>)}
            </ul>
            <button className={styles.buyBtn} onClick={() => setNoticePlan(plan)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>
                <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
              </svg>
              {p.addToCart[lang]}
            </button>
          </div>
        ))}
      </div>

      <p className={styles.note}>
        {p.note[lang]}{" "}
        <a href={discord} target="_blank" rel="noreferrer">Discord</a>
        {lang === "vi" ? " để hỗ trợ" : " for support"}
      </p>
      </div>

      {/* ── Notice Modal ─────────────────────────────── */}
      {noticePlan && (
        <div className="modal-backdrop open" onClick={e => e.target === e.currentTarget && setNoticePlan(null)}>
          <div className="modal-card" style={{ maxWidth: 500, borderTop: "3px solid #FFB300" }}>
            <button className="modal-close" onClick={() => setNoticePlan(null)}>✕</button>
            <div style={{ textAlign: "center", marginBottom: 16 }}>
              <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#FFB300" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
            </div>
            <h3 style={{ fontFamily: "var(--font-head)", fontSize: 18, marginBottom: 8, textAlign: "center" }}>
              {p.modal.title[lang]} — {noticePlan.label[lang]}
            </h3>
            <p style={{ color: "var(--text-dim)", fontSize: 14, textAlign: "center", marginBottom: 8 }}>
              <strong style={{ color: "var(--cyan)" }}>{fmtUsd(noticePlan.usd)}</strong>
              {" "}· {fmtVnd(noticePlan.vnd)}
            </p>
            <p style={{ color: "var(--text-dim)", fontSize: 14, textAlign: "center", marginBottom: 20 }}>
              {p.modal.verify[lang]}
            </p>
            <ol style={{ display: "flex", flexDirection: "column", gap: 12, paddingLeft: 0, marginBottom: 24 }}>
              {p.modal.steps.map((step, i) => (
                <li key={i} style={{ display: "flex", gap: 12 }}>
                  <span style={{ width: 24, height: 24, borderRadius: "50%", background: "rgba(255,179,0,.15)", color: "#FFB300", fontWeight: 700, fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{i + 1}</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>{step.label[lang]}</div>
                    <div style={{ fontSize: 13, color: "var(--text-dim)" }}>{step.hint[lang]}</div>
                  </div>
                </li>
              ))}
            </ol>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn-primary btn-xl" style={{ flex: 1 }} onClick={proceed}>
                {p.modal.confirm[lang]}
              </button>
              <button className="btn btn-ghost" onClick={() => setNoticePlan(null)}>{p.modal.cancel[lang]}</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
