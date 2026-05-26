"use client";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { PaymentConfig } from "@/lib/supabase/types";
import { PLANS } from "@/lib/plans";
import styles from "./payment-settings.module.css";

type Props = { configs: PaymentConfig[] };

const METHOD_META: Record<string, { icon: string; label: string }> = {
  paypal: { icon: "💳", label: "PayPal"    },
  stripe: { icon: "💎", label: "Stripe"    },
  usdt:   { icon: "🪙", label: "USDT"      },
  btc:    { icon: "₿",  label: "Bitcoin"   },
  eth:    { icon: "⟠",  label: "Ethereum"  },
  bank:   { icon: "🏦", label: "Bank (VN)" },
};

const BANKS = [
  { id: "MB",  label: "MB Bank"        },
  { id: "VCB", label: "Vietcombank"    },
  { id: "TCB", label: "Techcombank"    },
  { id: "ACB", label: "ACB"            },
  { id: "VPB", label: "VPBank"         },
  { id: "TPB", label: "TPBank"         },
  { id: "STB", label: "Sacombank"      },
  { id: "BID", label: "BIDV"           },
  { id: "VTB", label: "Vietinbank"     },
  { id: "AGR", label: "Agribank"       },
];

function PlanLinkTable({
  planLinks, onChange,
}: {
  planLinks: Record<string, string>;
  onChange: (links: Record<string, string>) => void;
}) {
  return (
    <div className={styles.planLinks}>
      {PLANS.map(p => (
        <div key={p.id} className={styles.planRow}>
          <span className={styles.planId}>{p.label.en}</span>
          <input
            className={styles.linkInput}
            value={planLinks[p.id] ?? ""}
            onChange={e => onChange({ ...planLinks, [p.id]: e.target.value })}
            placeholder="Payment link URL"
          />
        </div>
      ))}
    </div>
  );
}

function MethodCard({ cfg, onSaved }: { cfg: PaymentConfig; onSaved: (updated: PaymentConfig) => void }) {
  const meta    = METHOD_META[cfg.id] ?? { icon: "💰", label: cfg.id };
  const [enabled,  setEnabled]  = useState(cfg.enabled);
  const [config,   setConfig]   = useState<Record<string, any>>(cfg.config);
  const [busy,     setBusy]     = useState(false);
  const [msg,      setMsg]      = useState("");

  async function save() {
    setBusy(true); setMsg("");
    const sb = createClient();
    const { error } = await sb.from("payment_config")
      .update({ enabled, config, updated_at: new Date().toISOString() })
      .eq("id", cfg.id);
    setBusy(false);
    if (error) setMsg(`Error: ${error.message}`);
    else { setMsg("Saved!"); onSaved({ ...cfg, enabled, config }); setTimeout(() => setMsg(""), 2000); }
  }

  function setField(key: string, val: string) {
    setConfig(prev => ({ ...prev, [key]: val }));
  }

  function setPlanLink(links: Record<string, string>) {
    setConfig(prev => ({ ...prev, plan_links: links }));
  }

  return (
    <div className={`${styles.methodCard} ${enabled ? styles.methodEnabled : ""}`}>
      <div className={styles.methodHead}>
        <div className={styles.methodTitle}>
          <span className={styles.methodIcon}>{meta.icon}</span>
          <span>{meta.label}</span>
        </div>
        {/* Toggle */}
        <label className={styles.toggle}>
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
          <span className={styles.slider} />
          <span className={styles.toggleLabel}>{enabled ? "Enabled" : "Disabled"}</span>
        </label>
      </div>

      {enabled && (
        <div className={styles.fields}>
          {/* PayPal */}
          {cfg.id === "paypal" && <>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>PayPal.Me Username</label>
              <input className={styles.input} value={config.me_username ?? ""} onChange={e => setField("me_username", e.target.value)} placeholder="yourpaypalme" />
              <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 5 }}>
                Checkout redirects to: <code style={{ color: "var(--cyan)" }}>paypal.me/{config.me_username || "username"}/{"{"} amount {"}"}</code>
              </p>
            </div>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>PayPal Email (shown to buyer)</label>
              <input className={styles.input} value={config.email ?? ""} onChange={e => setField("email", e.target.value)} placeholder="your@paypal.com" />
            </div>
          </>}

          {/* Stripe */}
          {cfg.id === "stripe" && <>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Stripe Payment Links (per plan)</label>
              <PlanLinkTable planLinks={config.plan_links ?? {}} onChange={setPlanLink} />
            </div>
          </>}

          {/* USDT */}
          {cfg.id === "usdt" && <>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Network</label>
              <select className={styles.input} value={config.network ?? "TRC20"} onChange={e => setField("network", e.target.value)}>
                <option value="TRC20">TRC20 (Tron)</option>
                <option value="ERC20">ERC20 (Ethereum)</option>
                <option value="BEP20">BEP20 (BSC)</option>
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Wallet Address</label>
              <input className={styles.input} value={config.address ?? ""} onChange={e => setField("address", e.target.value)} placeholder="T..." />
            </div>
          </>}

          {/* BTC */}
          {cfg.id === "btc" && <>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Bitcoin Address</label>
              <input className={styles.input} value={config.address ?? ""} onChange={e => setField("address", e.target.value)} placeholder="1A... or bc1..." />
            </div>
          </>}

          {/* ETH */}
          {cfg.id === "eth" && <>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Network</label>
              <select className={styles.input} value={config.network ?? "ERC20"} onChange={e => setField("network", e.target.value)}>
                <option value="ERC20">ERC20 (Ethereum Mainnet)</option>
                <option value="BEP20">BEP20 (BSC)</option>
                <option value="MATIC">Polygon (MATIC)</option>
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Wallet Address</label>
              <input className={styles.input} value={config.address ?? ""} onChange={e => setField("address", e.target.value)} placeholder="0x..." />
            </div>
          </>}

          {/* Bank */}
          {cfg.id === "bank" && <>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Bank</label>
              <select className={styles.input} value={config.bank_id ?? "MB"} onChange={e => setField("bank_id", e.target.value)}>
                {BANKS.map(b => <option key={b.id} value={b.id}>{b.label}</option>)}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Account Number</label>
              <input className={styles.input} value={config.account_no ?? ""} onChange={e => setField("account_no", e.target.value)} placeholder="123456789" />
            </div>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Account Holder Name</label>
              <input className={styles.input} value={config.holder ?? ""} onChange={e => setField("holder", e.target.value)} placeholder="NGUYEN VAN A" />
            </div>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Bank Label (display name)</label>
              <input className={styles.input} value={config.bank_label ?? ""} onChange={e => setField("bank_label", e.target.value)} placeholder="MB Bank" />
            </div>
          </>}
        </div>
      )}

      <div className={styles.cardFoot}>
        {msg && <span className={msg.startsWith("Error") ? styles.msgErr : styles.msgOk}>{msg}</span>}
        <button className="btn btn-primary" onClick={save} disabled={busy} style={{ marginLeft: "auto" }}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

export default function PaymentSettings({ configs: initial }: Props) {
  const [configs, setConfigs] = useState(initial);

  function handleSaved(updated: PaymentConfig) {
    setConfigs(prev => prev.map(c => c.id === updated.id ? updated : c));
  }

  return (
    <div className={styles.wrap}>
      <p className={styles.hint}>
        Enable payment methods and fill in details. Users will see enabled methods at checkout.
      </p>
      {configs.map(cfg => (
        <MethodCard key={cfg.id} cfg={cfg} onSaved={handleSaved} />
      ))}
    </div>
  );
}
