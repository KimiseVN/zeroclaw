"use client";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useCart } from "@/lib/cart-context";
import type { PaymentConfig } from "@/lib/supabase/types";
import Header from "@/components/Header";
import styles from "./checkout.module.css";

// ── helpers ──────────────────────────────────────────────────────────────────
function vietQR(bankId: string, acNo: string, amount: number, info: string, holder: string) {
  const enc = encodeURIComponent;
  return `https://img.vietqr.io/image/${bankId}-${acNo}-compact2.png?amount=${amount}&addInfo=${enc(info)}&accountName=${enc(holder)}`;
}

function qrUrl(data: string) {
  return `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(data)}`;
}

type Method = "paypal" | "stripe" | "usdt" | "btc" | "eth" | "bank";

const METHOD_META: Record<Method, { icon: string; label: string; sub: string }> = {
  paypal: { icon: "💳", label: "PayPal",      sub: "Instant"      },
  stripe: { icon: "💎", label: "Stripe",      sub: "Card / Link"  },
  usdt:   { icon: "🪙", label: "USDT",        sub: "TRC20/ERC20"  },
  btc:    { icon: "₿",  label: "Bitcoin",     sub: "BTC"          },
  eth:    { icon: "⟠",  label: "Ethereum",    sub: "ETH"          },
  bank:   { icon: "🏦", label: "Bank VN",     sub: "Transfer"     },
};

// ── component ────────────────────────────────────────────────────────────────
export default function CheckoutPage() {
  const router  = useRouter();
  const { item, clearCart } = useCart();

  const [userId,   setUserId]   = useState<string | null>(null);
  const [email,    setEmail]    = useState("");
  const [configs,  setConfigs]  = useState<PaymentConfig[]>([]);
  const [method,   setMethod]   = useState<Method | null>(null);
  const [hwid,     setHwid]     = useState("");
  const [ref,      setRef]      = useState("");
  const [note,     setNote]     = useState("");
  const [busy,     setBusy]     = useState(false);
  const [err,      setErr]      = useState("");
  const [copied,   setCopied]   = useState(false);
  const [loading,  setLoading]  = useState(true);

  // Auth + payment configs
  useEffect(() => {
    const sb = createClient();
    Promise.all([
      sb.auth.getUser(),
      sb.from("payment_config").select("*").eq("enabled", true),
    ]).then(([{ data: { user } }, { data: cfg }]) => {
      setUserId(user?.id ?? null);
      setEmail(user?.email ?? "");
      const cfgs = (cfg ?? []) as PaymentConfig[];
      setConfigs(cfgs);
      // default to first available method
      const first = cfgs[0];
      if (first) setMethod(first.id as Method);
      setLoading(false);
    });
  }, []);

  const cfg = configs.find(c => c.id === method);

  // ── copy helper ────────────────────────────────────────────────────────────
  const copy = useCallback((text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, []);

  // ── place order ────────────────────────────────────────────────────────────
  async function placeOrder(overrideRef?: string) {
    if (!item || !method || !userId) return;
    setErr(""); setBusy(true);
    const sb = createClient();
    const plan = item.plan;
    const { data: order, error } = await sb.from("orders").insert({
      user_id:        userId,
      plan_id:        plan.id,
      plan_label:     plan.label.en,
      amount_usd:     plan.usd,
      amount_vnd:     plan.vnd,
      payment_method: method,
      payment_ref:    (overrideRef ?? ref) || null,
      hwid:           hwid || null,
      note:           note || null,
      status:         "pending",
    }).select("id").single();

    if (error) { setErr(error.message); setBusy(false); return; }
    clearCart();
    router.replace(`/thank-you/?order_id=${order.id}&method=${method}`);
  }

  // ── PayPal / Stripe redirect ───────────────────────────────────────────────
  async function handleExternalPay() {
    if (!item || !method || !cfg) return;

    let link: string | undefined;

    if (method === "paypal") {
      const username = (cfg.config?.me_username as string | undefined)?.trim();
      if (!username) { setErr("PayPal not configured. Contact admin."); return; }
      link = `https://www.paypal.me/${username}/${item.plan.usd}`;
    } else if (method === "stripe") {
      link = cfg.config?.plan_links?.[item.plan.id] as string | undefined;
      if (!link) { setErr("Stripe payment link not configured. Contact admin."); return; }
    }

    if (!link) { setErr("Payment link not configured. Contact admin."); return; }
    await placeOrder();
    window.open(link, "_blank");
  }

  // ── render ─────────────────────────────────────────────────────────────────
  if (loading) return (
    <>
      <Header />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "calc(100vh - 60px)" }}>
        <div className="spinner" />
      </div>
    </>
  );

  if (!userId) return (
    <>
      <Header />
      <main className={styles.main}>
        <div className={styles.container}>
          <div className={styles.loginPrompt}>
            <p style={{ marginBottom: 16 }}>Please sign in to checkout.</p>
            <a href="/" className="btn btn-primary">Sign in with Google</a>
          </div>
        </div>
      </main>
    </>
  );

  return (
    <>
      <Header />
      <main className={styles.main}>
        <div className={styles.container}>
          <h1 className={styles.pageTitle}>Checkout</h1>

          {!item ? (
            <div className={styles.emptyCart}>
              <p>Your cart is empty.</p>
              <a href="/#pricing" style={{ display: "inline-block", marginTop: 16 }} className="btn btn-primary">
                Browse Plans
              </a>
            </div>
          ) : (
            <div className={styles.grid}>
              {/* ── Left: Payment ── */}
              <div className={styles.payCard}>
                {/* Method selector */}
                <p className={styles.sectionTitle}>Payment Method</p>
                {configs.length === 0 ? (
                  <div className={styles.noMethods}>No payment methods configured yet. Contact admin.</div>
                ) : (
                  <div className={styles.methods}>
                    {configs.map(c => {
                      const meta = METHOD_META[c.id as Method] ?? { icon: "💰", label: c.id, sub: "" };
                      return (
                        <button
                          key={c.id}
                          className={`${styles.method} ${method === c.id ? styles.methodActive : ""}`}
                          onClick={() => { setMethod(c.id as Method); setErr(""); }}
                        >
                          <span className={styles.methodIcon}>{meta.icon}</span>
                          <span className={styles.methodLabel}>{meta.label}</span>
                          <span className={styles.methodSub}>{meta.sub}</span>
                        </button>
                      );
                    })}
                  </div>
                )}

                {/* Method details */}
                {cfg && (
                  <>
                    <p className={styles.sectionTitle}>Payment Details</p>
                    <div className={styles.payDetail}>
                      {/* PayPal */}
                      {method === "paypal" && (
                        <div style={{ textAlign: "center" }}>
                          {cfg.config.email && (
                            <p style={{ fontSize: 13, color: "var(--text-dim)", marginBottom: 16 }}>
                              Send to: <strong style={{ color: "var(--text)" }}>{cfg.config.email}</strong>
                            </p>
                          )}
                          <button className={`${styles.payLink} ${styles.paypalBtn}`} onClick={handleExternalPay} disabled={busy}>
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M7.076 21.337H2.47a.641.641 0 0 1-.633-.74L4.944.901C5.026.382 5.474 0 5.998 0h7.46c2.57 0 4.578.543 5.69 1.81 1.01 1.15 1.304 2.42 1.012 4.287-.023.143-.047.288-.077.437-.983 5.05-4.349 6.797-8.647 6.797h-2.19c-.524 0-.968.382-1.05.9l-1.12 7.106zm14.146-14.42a3.35 3.35 0 0 0-.607-.541c-.013.076-.026.175-.041.254-.59 3.025-2.566 6.082-8.558 6.082H9.825l-1.195 7.576H13.143c.457 0 .845-.332.917-.782l.038-.196.733-4.648.047-.254a.927.927 0 0 1 .916-.782h.577c3.736 0 6.659-1.517 7.514-5.905.358-1.83.173-3.357-.763-4.804z"/></svg>
                            Pay with PayPal
                          </button>
                        </div>
                      )}

                      {/* Stripe */}
                      {method === "stripe" && (
                        <div style={{ textAlign: "center" }}>
                          <button className={`${styles.payLink} ${styles.stripeBtn}`} onClick={handleExternalPay} disabled={busy}>
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M13.976 9.15c-2.172-.806-3.356-1.426-3.356-2.409 0-.831.683-1.305 1.901-1.305 2.227 0 4.515.858 6.09 1.631l.89-5.494C18.252.975 15.697 0 12.165 0 9.667 0 7.589.654 6.104 1.872 4.56 3.147 3.757 4.992 3.757 7.218c0 4.039 2.467 5.76 6.476 7.219 2.585.929 3.477 1.816 3.477 2.96 0 1.06-.△ skipping complex path... 0 0z"/></svg>
                            Pay with Stripe
                          </button>
                        </div>
                      )}

                      {/* Crypto: USDT / BTC / ETH */}
                      {(method === "usdt" || method === "btc" || method === "eth") && cfg.config.address && (
                        <>
                          <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 10 }}>
                            {method === "usdt" ? `Network: ${cfg.config.network}` : ""}
                            {method === "eth"  ? `Network: ${cfg.config.network}` : ""}
                          </p>
                          <img src={qrUrl(cfg.config.address)} alt="wallet QR" className={styles.qr} width={160} height={160} />
                          <div className={styles.payAddress}>
                            <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{cfg.config.address}</span>
                            <button className={styles.copyBtn} onClick={() => copy(cfg.config.address)}>
                              {copied ? "✓" : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>}
                            </button>
                          </div>
                          <p style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center" }}>
                            Send exactly <strong style={{ color: "var(--cyan)" }}>${item.plan.usd}</strong> worth
                          </p>
                        </>
                      )}

                      {/* Bank */}
                      {method === "bank" && (
                        <>
                          <img
                            src={vietQR(cfg.config.bank_id, cfg.config.account_no, item.plan.vnd,
                              `WWM ${item.plan.id}`, cfg.config.holder)}
                            alt="VietQR" className={styles.qr} width={180} height={200}
                          />
                          <div className={styles.bankRow}><span className={styles.bankKey}>Bank</span><span className={styles.bankVal}>{cfg.config.bank_label}</span></div>
                          <div className={styles.bankRow}><span className={styles.bankKey}>Account</span><span className={styles.bankVal}>{cfg.config.account_no}</span></div>
                          <div className={styles.bankRow}><span className={styles.bankKey}>Holder</span><span className={styles.bankVal}>{cfg.config.holder}</span></div>
                          <div className={styles.bankRow}><span className={styles.bankKey}>Amount</span><span className={styles.bankVal} style={{ color: "var(--cyan)" }}>{item.plan.vnd.toLocaleString("vi-VN")}đ</span></div>
                          <div className={styles.bankRow}><span className={styles.bankKey}>Description</span><span className={styles.bankVal}>WWM {item.plan.id} {email}</span></div>
                        </>
                      )}
                    </div>
                  </>
                )}

                <div className={styles.divider} />

                {/* HWID + ref inputs */}
                <div className={styles.formGroup}>
                  <label className={styles.label}>HWID (Hardware ID)</label>
                  <input className={styles.input} value={hwid} onChange={e => setHwid(e.target.value)}
                    placeholder="Optional — can fill later in dashboard" />
                  <p className={styles.inputHint}>Found in the app's Settings tab.</p>
                </div>

                {(method === "usdt" || method === "btc" || method === "eth") && (
                  <div className={styles.formGroup}>
                    <label className={styles.label}>Transaction Hash (TxID)</label>
                    <input className={styles.input} value={ref} onChange={e => setRef(e.target.value)}
                      placeholder="0x..." />
                  </div>
                )}

                {method === "bank" && (
                  <div className={styles.formGroup}>
                    <label className={styles.label}>Transfer Reference / Screenshot URL</label>
                    <input className={styles.input} value={ref} onChange={e => setRef(e.target.value)}
                      placeholder="Last 6 digits of transaction or screenshot link" />
                  </div>
                )}

                <div className={styles.formGroup}>
                  <label className={styles.label}>Note (optional)</label>
                  <input className={styles.input} value={note} onChange={e => setNote(e.target.value)}
                    placeholder="Anything to tell us" />
                </div>

                {err && <p className={styles.errMsg}>{err}</p>}

                {/* Submit — only for crypto/bank; PayPal/Stripe handled inline */}
                {(method === "usdt" || method === "btc" || method === "eth" || method === "bank") && (
                  <button
                    className={`btn btn-primary ${styles.submitBtn}`}
                    onClick={() => placeOrder()}
                    disabled={busy || !method}
                  >
                    {busy ? "Submitting…" : "Submit Order"}
                  </button>
                )}
              </div>

              {/* ── Right: Order summary ── */}
              <div className={styles.summary}>
                <p className={styles.sectionTitle}>Order Summary</p>
                <p className={styles.sumPlan}>{item.plan.label.en}</p>
                {item.plan.features.en.map(f => (
                  <p key={f} className={styles.sumFeature}>{f}</p>
                ))}
                <div className={styles.sumDivider} />
                <div className={styles.sumRow}>
                  <span className={styles.sumLabel}>USD</span>
                  <span className={styles.sumVal}>${item.plan.usd.toFixed(2)}</span>
                </div>
                <div className={styles.sumRow}>
                  <span className={styles.sumLabel}>VND</span>
                  <span className={styles.sumVal}>{item.plan.vnd.toLocaleString("vi-VN")}đ</span>
                </div>
                <div className={styles.sumDivider} />
                <div className={styles.sumRow}>
                  <span className={styles.sumLabel}>Total</span>
                  <span className={`${styles.sumVal} ${styles.sumTotal}`}>${item.plan.usd.toFixed(2)}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
