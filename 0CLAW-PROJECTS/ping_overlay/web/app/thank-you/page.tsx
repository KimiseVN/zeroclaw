"use client";
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useGeneralSettings } from "@/lib/use-site-settings";
import type { Order } from "@/lib/supabase/types";
import Link from "next/link";
import styles from "./thank-you.module.css";

const METHOD_LABELS: Record<string, string> = {
  paypal: "PayPal", stripe: "Stripe",
  usdt: "USDT", btc: "Bitcoin", eth: "Ethereum",
  bank: "Bank Transfer",
};

const STEPS: Record<string, { icon: string; steps: string[] }> = {
  paypal: { icon: "💳", steps: [
    "Complete the payment on <strong>PayPal</strong> if you haven't already.",
    "Admin will verify your payment and issue your license key.",
    "You'll receive the key — check <strong>My Dashboard</strong>.",
  ]},
  stripe: { icon: "💎", steps: [
    "Complete the payment on <strong>Stripe</strong> if you haven't already.",
    "Admin will verify and issue your license key.",
    "Check <strong>My Dashboard</strong> for your key.",
  ]},
  usdt:  { icon: "🪙", steps: [
    "Send the exact USDT amount to the wallet shown on the previous page.",
    "Paste the <strong>TxID (transaction hash)</strong> in your order note if you haven't.",
    "Admin verifies on-chain and issues your license key.",
  ]},
  btc:   { icon: "₿", steps: [
    "Send the exact BTC amount to the wallet shown on the previous page.",
    "Share the <strong>transaction hash</strong> via Discord or order note.",
    "Admin confirms and issues your license key (may take 1-3 confirms).",
  ]},
  eth:   { icon: "⟠", steps: [
    "Send the exact ETH amount to the wallet address.",
    "Share the <strong>TxID</strong> via Discord or order note.",
    "Admin verifies on-chain and issues your license key.",
  ]},
  bank:  { icon: "🏦", steps: [
    "Complete the bank transfer with the exact amount and correct description.",
    "Admin checks the transaction and issues your license key.",
    "Check <strong>My Dashboard</strong> — usually done within business hours.",
  ]},
};

function ThankYouContent() {
  const params   = useSearchParams();
  const orderId  = params.get("order_id") ?? "";
  const method   = (params.get("method") ?? "bank") as string;

  const general  = useGeneralSettings();
  const discord  = general.discord_url || "https://discord.gg/zeroclaw";

  const [order,  setOrder]  = useState<Order | null>(null);
  const [hwid,   setHwid]   = useState("");
  const [saving, setSaving] = useState(false);
  const [saved,  setSaved]  = useState(false);

  useEffect(() => {
    if (!orderId) return;
    const sb = createClient();
    sb.from("orders").select("*").eq("id", orderId).single()
      .then(({ data }) => { if (data) setOrder(data as Order); });
  }, [orderId]);

  async function saveHwid() {
    if (!hwid.trim() || !orderId) return;
    setSaving(true);
    const sb = createClient();
    await sb.from("orders").update({ hwid }).eq("id", orderId);
    setSaved(true); setSaving(false);
  }

  const meta  = STEPS[method] ?? STEPS.bank;
  const label = METHOD_LABELS[method] ?? method;

  return (
    <main className={styles.main}>
      <div className={styles.card}>
        <div className={styles.icon}>{meta.icon}</div>
        <h1 className={styles.title}>Order Received!</h1>
        <p className={styles.sub}>
          Thank you for your purchase. Your order is <strong style={{ color: "var(--yellow)" }}>pending verification</strong>.
        </p>

        {/* Order box */}
        {order && (
          <div className={styles.orderBox}>
            <div className={styles.orderRow}>
              <span className={styles.orderKey}>Order ID</span>
              <span className={styles.orderVal} style={{ fontFamily: "monospace", fontSize: 12 }}>{order.id.slice(0, 16)}…</span>
            </div>
            <div className={styles.orderRow}>
              <span className={styles.orderKey}>Plan</span>
              <span className={styles.orderVal}>{order.plan_label ?? order.plan_id}</span>
            </div>
            <div className={styles.orderRow}>
              <span className={styles.orderKey}>Amount</span>
              <span className={styles.orderVal}>${order.amount_usd.toFixed(2)}</span>
            </div>
            <div className={styles.orderRow}>
              <span className={styles.orderKey}>Payment</span>
              <span className={styles.orderVal}>{label}</span>
            </div>
            <div className={styles.orderRow}>
              <span className={styles.orderKey}>Status</span>
              <span className="badge badge-pending">pending</span>
            </div>
          </div>
        )}

        {/* Steps */}
        <div className={styles.steps}>
          {meta.steps.map((step, i) => (
            <div key={i} className={styles.step}>
              <div className={styles.stepNum}>{i + 1}</div>
              <p className={styles.stepText} dangerouslySetInnerHTML={{ __html: step }} />
            </div>
          ))}
        </div>

        {/* HWID input if not filled */}
        {order && !order.hwid && (
          <div className={styles.hwidForm}>
            <label className={styles.label}>Add your HWID (optional)</label>
            <input
              className={styles.input}
              value={hwid}
              onChange={e => setHwid(e.target.value)}
              placeholder="Found in the app Settings tab"
            />
            {saved ? (
              <p style={{ fontSize: 13, color: "var(--green)" }}>✓ HWID saved!</p>
            ) : (
              <button className="btn btn-ghost" onClick={saveHwid} disabled={saving || !hwid.trim()}>
                {saving ? "Saving…" : "Save HWID"}
              </button>
            )}
          </div>
        )}

        {/* Actions */}
        <div className={styles.actions}>
          <Link href="/dashboard/" className="btn btn-primary">My Dashboard</Link>
          <a href={discord} target="_blank" rel="noreferrer" className="btn btn-ghost">
            Discord Support
          </a>
        </div>
      </div>
    </main>
  );
}

export default function ThankYouPage() {
  return (
    <Suspense fallback={
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <div className="spinner" />
      </div>
    }>
      <ThankYouContent />
    </Suspense>
  );
}
