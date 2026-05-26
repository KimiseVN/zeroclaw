"use client";
import React, { useState, useTransition } from "react";
import { createClient } from "@/lib/supabase/client";
import type { Order, License, PaymentConfig, Profile, SiteSetting, FaqItem, DemoImage, ReferralEvent, BlacklistEntry } from "@/lib/supabase/types";
import PaymentSettings  from "./PaymentSettings";
import PricingSettings  from "./PricingSettings";
import SiteSettings     from "./SiteSettings";
import FaqSettings      from "./FaqSettings";
import DemoSettings     from "./DemoSettings";
import Analytics        from "./Analytics";
import RevenueStats     from "./RevenueStats";
import type { VisitRow } from "./Analytics";
import styles from "./admin.module.css";

type Stats = { pending: number; paid: number; active: number; totalOrders: number };
type Props = {
  orders: Order[]; licenses: License[];
  stats: Stats; paymentConfigs: PaymentConfig[];
  siteSettings: SiteSetting[]; faqs: FaqItem[]; demoImages: DemoImage[];
  visits: VisitRow[];
  users: Profile[];
  refEvents: ReferralEvent[];
  blacklist: BlacklistEntry[];
};

// ─── Plans for AssignModal (order-based, kept for backward-compat) ────────────
const PLANS: Record<string, { label: string; days: number }> = {
  "1d":  { label: "1 Day",    days: 1   },
  "7d":  { label: "7 Days",   days: 7   },
  "30d": { label: "30 Days",  days: 30  },
  "90d": { label: "90 Days",  days: 90  },
  "ltm": { label: "Lifetime", days: -1  },
};

// ─── PO1 license constants — must match license_lib.py / LicenseManager.tsx ──
const PO1_FORMAT = "PO1";
const PO1_SECRET = "PingOverlay-Kim-License-v1-2026-MAY-04-7G3Q9P";

const PO1_DURATIONS: Record<string, number> = {
  "1d": 1, "1w": 7, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "lt": 0,
};

const PO1_PLANS = [
  { id: "1d",  label: "1 Day"    },
  { id: "1w",  label: "1 Week"   },
  { id: "1mo", label: "1 Month"  },
  { id: "3mo", label: "3 Months" },
  { id: "6mo", label: "6 Months" },
  { id: "1y",  label: "1 Year"   },
  { id: "lt",  label: "Lifetime" },
];

function normalizeHwid(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 16);
}
function formatHwidDisplay(norm: string): string {
  if (norm.length !== 16) return norm;
  return [norm.slice(0, 4), norm.slice(4, 8), norm.slice(8, 12), norm.slice(12, 16)].join("-");
}
async function po1SignPayload(payload: string): Promise<string> {
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    "raw", enc.encode(PO1_SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sigBuf = await crypto.subtle.sign("HMAC", cryptoKey, enc.encode(payload));
  return Array.from(new Uint8Array(sigBuf))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("").toUpperCase().slice(0, 32);
}
async function issuePO1Key(hwid: string, durationCode: string): Promise<{
  key: string; expires_at_iso: string | null;
}> {
  const norm = normalizeHwid(hwid);
  if (norm.length !== 16) throw new Error("HWID phải đúng 16 ký tự alphanumeric (A–Z, 0–9)");
  const days = PO1_DURATIONS[durationCode];
  if (days === undefined) throw new Error(`Unknown duration: ${durationCode}`);
  let expiry_ts = 0;
  let expires_at_iso: string | null = null;
  if (days > 0) {
    const exp = new Date();
    exp.setDate(exp.getDate() + days);
    expiry_ts = Math.floor(exp.getTime() / 1000);
    expires_at_iso = exp.toISOString();
  }
  const payload = `${PO1_FORMAT}|${norm}|${durationCode.toLowerCase()}|${expiry_ts}`;
  const sig = await po1SignPayload(payload);
  return {
    key: `${PO1_FORMAT}-${norm}-${durationCode.toUpperCase()}-${expiry_ts}-${sig}`,
    expires_at_iso,
  };
}

const METHOD_LABEL: Record<string, string> = {
  paypal: "PayPal", stripe: "Stripe", usdt: "USDT",
  btc: "Bitcoin",   eth: "Ethereum",  bank: "Bank (VN)",
};

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}
function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}
function defaultExpiry(planId: string): string {
  const plan = PLANS[planId];
  if (!plan || plan.days < 0) return "";
  const d = new Date();
  d.setDate(d.getDate() + plan.days);
  return d.toISOString().slice(0, 10);
}
function genKey() {
  const seg = () => Math.random().toString(36).slice(2, 6).toUpperCase();
  return `WWM-${seg()}-${seg()}-${seg()}-${seg()}`;
}

// ─── Order Detail Modal ───────────────────────────────────────────────────────
function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className={styles.detailRow}>
      <span className={styles.detailLabel}>{label}</span>
      <span className={`${styles.detailValue} ${mono ? styles.detailMono : ""}`}>{value}</span>
    </div>
  );
}

function OrderDetailModal({
  order, onClose, onDeleted,
}: {
  order: Order;
  onClose: () => void;
  onDeleted: (id: string) => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [err,      setErr]      = useState("");

  async function handleDelete() {
    if (!confirm(
      `Delete order ${order.id.slice(0, 8)}…?\n\n` +
      `This cannot be undone. Any license issued for this order will remain active ` +
      `but lose its order reference.`,
    )) return;

    setDeleting(true); setErr("");
    try {
      const sb = createClient();
      // Unlink any associated license before deleting
      await sb.from("licenses").update({ order_id: null }).eq("order_id", order.id);
      const { error } = await sb.from("orders").delete().eq("id", order.id);
      if (error) throw error;
      onDeleted(order.id);
      onClose();
    } catch (e: any) {
      setErr(e.message ?? "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  const profile = order.profiles as any;

  return (
    <div className="modal-backdrop open" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card" style={{ maxWidth: 560 }}>
        <button className="modal-close" onClick={onClose}>✕</button>

        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20 }}>
          <div>
            <h3 style={{ fontFamily: "var(--font-head)", fontSize: 18, marginBottom: 4 }}>Order Details</h3>
            <code style={{ fontSize: 11, color: "var(--text-muted)" }}>{order.id}</code>
          </div>
          <span className={`badge badge-${order.status}`} style={{ marginTop: 2 }}>{order.status}</span>
        </div>

        <div className={styles.detailGrid}>
          <DetailRow label="User"      value={profile?.full_name ?? "—"} />
          <DetailRow label="Email"     value={profile?.email     ?? "—"} />
          <DetailRow label="Plan"      value={order.plan_label   ?? order.plan_id} />
          <DetailRow label="Amount"    value={
            `$${order.amount_usd.toFixed(2)} USD` +
            (order.amount_vnd ? ` · ${order.amount_vnd.toLocaleString()} VND` : "")
          } />
          <DetailRow label="Method"    value={METHOD_LABEL[order.payment_method] ?? order.payment_method} />
          <DetailRow label="Reference" value={order.payment_ref ?? "—"} mono />
          <DetailRow label="HWID"      value={order.hwid        ?? "—"} mono />
          {order.note && <DetailRow label="Note" value={order.note} />}
          <DetailRow label="Created"   value={`${fmtDate(order.created_at)} ${fmtTime(order.created_at)}`} />
          <DetailRow label="Updated"   value={`${fmtDate(order.updated_at)} ${fmtTime(order.updated_at)}`} />
        </div>

        {err && <p style={{ fontSize: 13, color: "var(--red)", marginTop: 12 }}>{err}</p>}

        <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
          <button className="btn btn-ghost" onClick={onClose} style={{ flex: 1 }} disabled={deleting}>
            Close
          </button>
          <button
            className={`btn ${styles.deleteOrderBtn}`}
            onClick={handleDelete}
            style={{ flex: 1 }}
            disabled={deleting}
          >
            {deleting ? "Deleting…" : "🗑 Delete Order"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Assign License Modal ────────────────────────────────────────────────────
function AssignModal({ order, onClose, onDone }: { order: Order; onClose: () => void; onDone: () => void }) {
  const [key,    setKey]    = useState(genKey());
  const [expiry, setExpiry] = useState(defaultExpiry(order.plan_id));
  const [busy,   setBusy]   = useState(false);
  const [err,    setErr]    = useState("");

  async function submit() {
    setBusy(true); setErr("");
    const sb = createClient();
    try {
      const { error: licErr } = await sb.from("licenses").insert({
        order_id: order.id, user_id: order.user_id, license_key: key,
        hwid: order.hwid ?? null, plan_id: order.plan_id, plan_label: order.plan_label,
        expires_at: expiry || null, status: "active",
      });
      if (licErr) throw licErr;
      const { error: ordErr } = await sb.from("orders").update({ status: "paid" }).eq("id", order.id);
      if (ordErr) throw ordErr;
      onDone(); onClose();
    } catch (e: any) { setErr(e.message ?? "Unknown error"); }
    finally { setBusy(false); }
  }

  return (
    <div className="modal-backdrop open" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card">
        <button className="modal-close" onClick={onClose}>✕</button>
        <h3 style={{ marginBottom: 6, fontFamily: "var(--font-head)", fontSize: 20 }}>Assign License</h3>
        <p style={{ fontSize: 13, color: "var(--text-dim)", marginBottom: 24 }}>
          Order <code style={{ color: "var(--cyan)" }}>{order.id.slice(0, 8)}</code> · {order.plan_label ?? order.plan_id}
        </p>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>License Key</label>
          <div className={styles.keyInputRow}>
            <input className={styles.input} value={key} onChange={e => setKey(e.target.value)} spellCheck={false} />
            <button className={`btn btn-ghost ${styles.regenBtn}`} onClick={() => setKey(genKey())}>↺</button>
          </div>
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Expires (leave blank = Lifetime)</label>
          <input type="date" className={styles.input} value={expiry} onChange={e => setExpiry(e.target.value)} />
        </div>
        {err && <p className={styles.errMsg}>{err}</p>}
        <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
          <button className="btn btn-ghost" onClick={onClose} style={{ flex: 1 }} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" onClick={submit} style={{ flex: 1 }} disabled={busy}>
            {busy ? "Saving…" : "Assign & Approve"}
          </button>
        </div>
      </div>
    </div>
  );
}

async function rejectOrder(id: string) {
  await createClient().from("orders").update({ status: "rejected" }).eq("id", id);
}
async function revokeLicense(id: string) {
  await createClient().from("licenses").update({ status: "revoked" }).eq("id", id);
}

// ─── User Edit Modal ─────────────────────────────────────────────────────────
function UserEditModal({
  user,
  onClose,
  onUpdated,
  onDeleted,
}: {
  user: Profile;
  onClose: () => void;
  onUpdated: (u: Profile) => void;
  onDeleted: (id: string) => void;
}) {
  const [fullName,  setFullName]  = useState(user.full_name ?? "");
  const [refPoints, setRefPoints] = useState(String(user.referral_points ?? 0));
  const [isAdmin,   setIsAdmin]   = useState(user.is_admin);
  const [busy,      setBusy]      = useState(false);
  const [err,       setErr]       = useState("");
  const [ok,        setOk]        = useState("");

  function flash(msg: string) { setOk(msg); setTimeout(() => setOk(""), 2500); }

  async function save() {
    const pts = parseInt(refPoints, 10);
    if (isNaN(pts) || pts < 0) { setErr("Points must be a non-negative number."); return; }
    setBusy(true); setErr("");
    const { error } = await createClient()
      .from("profiles")
      .update({ full_name: fullName.trim() || null, referral_points: pts, is_admin: isAdmin })
      .eq("id", user.id);
    setBusy(false);
    if (error) { setErr(error.message); return; }
    onUpdated({ ...user, full_name: fullName.trim() || null, referral_points: pts, is_admin: isAdmin });
    flash("Saved!");
  }

  async function deleteUser() {
    if (!confirm(
      `Delete profile for ${user.email ?? user.full_name}?\n\n` +
      `This removes profile data (name, ref code, points). The auth account may remain until next sign-in.`
    )) return;
    setBusy(true); setErr("");
    const { error } = await createClient().from("profiles").delete().eq("id", user.id);
    setBusy(false);
    if (error) { setErr(error.message); return; }
    onDeleted(user.id);
    onClose();
  }

  return (
    <div className="modal-backdrop open" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card" style={{ maxWidth: 480 }}>
        <button className="modal-close" onClick={onClose}>✕</button>
        <h3 style={{ fontFamily: "var(--font-head)", fontSize: 18, marginBottom: 4 }}>Edit User</h3>
        <code style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 20 }}>{user.id}</code>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label className={styles.formLabel}>Email</label>
            <input className={styles.input} value={user.email ?? ""} readOnly style={{ opacity: .55, cursor: "default" }} />
          </div>
          <div>
            <label className={styles.formLabel}>Full Name</label>
            <input className={styles.input} value={fullName} onChange={e => setFullName(e.target.value)} placeholder="—" disabled={busy} />
          </div>
          <div>
            <label className={styles.formLabel}>Referral Code</label>
            <input className={styles.input} value={user.referral_code ?? ""} readOnly style={{ opacity: .55, cursor: "default" }} />
          </div>
          <div>
            <label className={styles.formLabel}>Referral Points</label>
            <input className={styles.input} type="number" min={0} value={refPoints} onChange={e => setRefPoints(e.target.value)} disabled={busy} />
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <label className={styles.formLabel} style={{ margin: 0 }}>Admin</label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={isAdmin}
                onChange={e => setIsAdmin(e.target.checked)}
                disabled={busy}
                style={{ width: 16, height: 16, accentColor: "var(--cyan)" }}
              />
              <span className={`badge badge-${isAdmin ? "paid" : "pending"}`}>{isAdmin ? "Admin" : "User"}</span>
            </label>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Joined: {fmtDate(user.created_at)}
          </div>
        </div>

        {err && <p style={{ fontSize: 13, color: "var(--red, #ff4466)", marginTop: 12 }}>{err}</p>}
        {ok  && <p style={{ fontSize: 13, color: "var(--green, #00ff88)", marginTop: 12 }}>{ok}</p>}

        <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy} style={{ flex: 1 }}>Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={busy} style={{ flex: 1 }}>
            {busy ? "Saving…" : "Save Changes"}
          </button>
        </div>
        <div style={{ marginTop: 10 }}>
          <button
            className={`btn ${styles.deleteOrderBtn}`}
            onClick={deleteUser}
            disabled={busy}
            style={{ width: "100%" }}
          >
            🗑 Delete User
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── UserLicensePanel (expand row in Users tab) ───────────────────────────────
function UserLicensePanel({
  user,
  licenses,
  loading,
  onLicenseAdded,
}: {
  user: Profile;
  licenses: License[] | undefined;
  loading: boolean;
  onLicenseAdded: (lic: License) => void;
}) {
  const existingHwid = licenses?.find(l => l.hwid)?.hwid ?? "";
  const [hwid,    setHwid]    = useState(existingHwid);
  const [planId,  setPlanId]  = useState("1mo");
  const [preview, setPreview] = useState("");
  const [busy,    setBusy]    = useState(false);
  const [err,     setErr]     = useState("");
  const [lastKey, setLastKey] = useState<string | null>(null);

  // Pre-fill HWID once licenses finish loading
  React.useEffect(() => {
    if (!hwid && existingHwid) setHwid(existingHwid);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingHwid]);

  // Live preview of the PO1 key as HWID / plan changes
  React.useEffect(() => {
    const norm = normalizeHwid(hwid);
    if (norm.length !== 16) { setPreview(""); return; }
    let cancelled = false;
    issuePO1Key(hwid, planId)
      .then(({ key }) => { if (!cancelled) setPreview(key); })
      .catch(() => { if (!cancelled) setPreview(""); });
    return () => { cancelled = true; };
  }, [hwid, planId]);

  async function generate() {
    setErr(""); setLastKey(null);
    const norm = normalizeHwid(hwid);
    if (norm.length !== 16) {
      setErr("HWID phải đúng 16 ký tự alphanumeric (A–Z, 0–9). Lấy từ PingOverlay → Setting → copy HWID.");
      return;
    }
    setBusy(true);
    try {
      const { key, expires_at_iso } = await issuePO1Key(hwid, planId);
      const plan = PO1_PLANS.find(p => p.id === planId)!;
      const { data, error } = await createClient()
        .from("licenses")
        .insert({
          user_id:     user.id,
          order_id:    null,
          license_key: key,
          hwid:        norm,
          plan_id:     planId,
          plan_label:  plan.label,
          expires_at:  expires_at_iso,
          note:        null,
          status:      "active" as const,
        })
        .select()
        .single();
      if (error) throw error;
      setLastKey(key);
      setHwid("");
      onLicenseAdded(data as License);
    } catch (e: any) {
      setErr(e.message ?? "Failed to generate license");
    } finally {
      setBusy(false);
    }
  }

  const hwidNorm  = normalizeHwid(hwid);
  const hwidValid = hwidNorm.length === 16;

  if (loading) {
    return (
      <div className={styles.userExpanded}>
        <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Loading…</span>
      </div>
    );
  }

  const hasActive = licenses?.some(
    l => l.status === "active" && (!l.expires_at || new Date(l.expires_at) > new Date())
  );

  return (
    <div className={styles.userExpanded}>
      {/* ── License list ── */}
      <div className={styles.expandSection}>
        <p className={styles.expandLabel}>Licenses ({licenses?.length ?? 0})</p>
        {!licenses || licenses.length === 0 ? (
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>No licenses yet.</span>
        ) : (
          licenses.map(l => {
            const eff = l.status === "revoked" ? "revoked"
                      : (l.expires_at && new Date(l.expires_at) < new Date()) ? "expired"
                      : "active";
            return (
              <div key={l.id} className={styles.licenseItem}>
                <code className={styles.keyCode} style={{ fontSize: 10, wordBreak: "break-all" }}>
                  {l.license_key}
                </code>
                <span style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>
                  {l.plan_label ?? l.plan_id}
                </span>
                {l.hwid && (
                  <code style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "monospace", flexShrink: 0 }}>
                    {formatHwidDisplay(l.hwid)}
                  </code>
                )}
                <span style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>
                  {l.expires_at ? fmtDate(l.expires_at) : "Lifetime"}
                </span>
                <span
                  className={`badge badge-${eff === "active" ? "paid" : "rejected"}`}
                  style={{ flexShrink: 0 }}
                >
                  {eff}
                </span>
              </div>
            );
          })
        )}
      </div>

      {/* ── PO1 Generate form ── */}
      <div className={styles.expandSection} style={{ minWidth: 320 }}>
        <p className={styles.expandLabel}>{hasActive ? "Add License" : "Generate License"}</p>
        <div className={styles.genForm}>
          {/* HWID */}
          <div>
            <label className={styles.formLabel}>
              HWID <span style={{ color: "var(--red)", fontWeight: 700 }}>* required</span>
              <span style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 6, textTransform: "none" }}>
                — from PingOverlay → Setting → copy HWID
              </span>
            </label>
            <input
              className={styles.input}
              value={hwid}
              onChange={e => setHwid(e.target.value)}
              placeholder="XXXX-XXXX-XXXX-XXXX  or  XXXXXXXXXXXXXXXX"
              spellCheck={false}
              autoComplete="off"
              disabled={busy}
            />
            {hwid && !hwidValid && (
              <p style={{ fontSize: 11, color: "var(--yellow)", margin: "4px 0 0" }}>
                {hwidNorm.length} / 16 chars — need exactly 16 alphanumeric
              </p>
            )}
            {hwidValid && (
              <p style={{ fontSize: 11, color: "var(--green)", margin: "4px 0 0" }}>
                ✓ {formatHwidDisplay(hwidNorm)}
              </p>
            )}
          </div>

          {/* Plan pills */}
          <div>
            <label className={styles.formLabel}>Duration</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {PO1_PLANS.map(p => (
                <button
                  key={p.id}
                  onClick={() => setPlanId(p.id)}
                  disabled={busy}
                  style={{
                    padding: "5px 12px",
                    borderRadius: 20,
                    border: `1px solid ${planId === p.id ? "var(--cyan)" : "var(--border-2)"}`,
                    background: planId === p.id ? "rgba(0,229,255,.12)" : "transparent",
                    color: planId === p.id ? "var(--cyan)" : "var(--text-dim)",
                    fontSize: 12, fontWeight: 600, cursor: "pointer", transition: "all .12s",
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Preview key */}
          {preview && (
            <div style={{
              background: "var(--bg-2)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "10px 12px",
            }}>
              <p style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", margin: "0 0 4px" }}>
                Preview key (PO1)
              </p>
              <code style={{ fontSize: 11, color: "var(--cyan)", wordBreak: "break-all", lineHeight: 1.6 }}>{preview}</code>
            </div>
          )}

          {err && <p className={styles.errMsg}>{err}</p>}

          {/* Generate button */}
          <button
            className="btn btn-primary"
            onClick={generate}
            disabled={busy || !hwidValid}
            style={{ alignSelf: "flex-start" }}
          >
            {busy ? "Generating…" : "⚡ Generate & Save"}
          </button>

          {/* Success */}
          {lastKey && (
            <div style={{
              background: "rgba(0,255,136,.06)",
              border: "1px solid rgba(0,255,136,.25)",
              borderRadius: 8,
              padding: "10px 12px",
            }}>
              <p style={{ fontSize: 12, color: "var(--green)", margin: "0 0 6px", fontWeight: 700 }}>✓ License generated!</p>
              <code style={{ fontSize: 11, wordBreak: "break-all", color: "var(--cyan)", lineHeight: 1.6 }}>{lastKey}</code>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Main ────────────────────────────────────────────────────────────────────
type Tab = "orders" | "licenses" | "payments" | "pricing" | "settings" | "faq" | "demo" | "analytics" | "revenue" | "users" | "referrals" | "blacklist";

const NAV: { id: Tab; label: string; icon: string; dividerBefore?: boolean }[] = [
  { id: "orders",    label: "Orders",           icon: "🛒" },
  { id: "licenses",  label: "Licenses",         icon: "🔑" },
  { id: "users",     label: "Users",            icon: "👤" },
  { id: "referrals", label: "Referrals",        icon: "🎁" },
  { id: "blacklist", label: "Blacklist",        icon: "🚫" },
  { id: "payments",  label: "Payments",         icon: "💳" },
  { id: "pricing",   label: "Pricing Plans",    icon: "🏷️" },
  { id: "settings",  label: "Site Settings",    icon: "⚙️" },
  { id: "faq",       label: "FAQ",              icon: "❓" },
  { id: "demo",      label: "Demo Images",      icon: "🖼️" },
  { id: "revenue",   label: "Revenue",          icon: "💰", dividerBefore: true },
  { id: "analytics", label: "Analytics",        icon: "📊" },
];

export default function AdminClient({
  orders: initOrders, licenses: initLicenses, stats,
  paymentConfigs, siteSettings, faqs, demoImages, visits,
  users: initUsers, refEvents: initRefEvents, blacklist: initBlacklist,
}: Props) {
  const [tab,          setTab]          = useState<Tab>("orders");
  const [menuOpen,     setMenuOpen]     = useState(false);
  const [orders,       setOrders]       = useState(initOrders);
  const [licenses,     setLicenses]     = useState(initLicenses);
  const [assignOrder,  setAssignOrder]  = useState<Order | null>(null);
  const [viewOrder,    setViewOrder]    = useState<Order | null>(null);
  const [filter,       setFilter]       = useState<string>("all");
  const [users,        setUsers]        = useState<Profile[]>(initUsers);
  const [viewUser,     setViewUser]     = useState<Profile | null>(null);
  const [refEvents]                     = useState<ReferralEvent[]>(initRefEvents);
  const [blacklist,    setBlacklist]    = useState<BlacklistEntry[]>(initBlacklist);
  const [expandedUser, setExpandedUser] = useState<string | null>(null);
  const [userLicenses, setUserLicenses] = useState<Record<string, License[]>>({});
  const [licLoading,   setLicLoading]   = useState<Set<string>>(new Set());
  const [, startTransition] = useTransition();

  const filteredOrders = filter === "all" ? orders : orders.filter(o => o.status === filter);
  const activeLabel    = NAV.find(n => n.id === tab)?.label ?? "Admin";

  function navigate(id: Tab) { setTab(id); setMenuOpen(false); }

  async function toggleExpand(userId: string) {
    if (expandedUser === userId) { setExpandedUser(null); return; }
    setExpandedUser(userId);
    if (userLicenses[userId] !== undefined) return; // already cached
    setLicLoading(prev => new Set(prev).add(userId));
    const { data } = await createClient()
      .from("licenses")
      .select("*")
      .eq("user_id", userId)
      .order("issued_at", { ascending: false });
    setUserLicenses(prev => ({ ...prev, [userId]: (data ?? []) as License[] }));
    setLicLoading(prev => { const s = new Set(prev); s.delete(userId); return s; });
  }

  function handleLicenseAdded(userId: string, lic: License) {
    setUserLicenses(prev => ({ ...prev, [userId]: [lic, ...(prev[userId] ?? [])] }));
    setLicenses(prev => [lic, ...prev]);
  }

  return (
    <main className={styles.main}>
      <div className={styles.container}>

        {/* ── Mobile top bar ───────────────────────────────────────────── */}
        <div className={styles.mobileTopBar}>
          <button className={styles.hamburgerBtn} onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <span className={styles.hamburgerIcon}>
              <span /><span /><span />
            </span>
          </button>
          <span className={styles.mobilePageTitle}>{activeLabel}</span>
        </div>

        {/* ── Overlay (mobile) ─────────────────────────────────────────── */}
        {menuOpen && <div className={styles.overlay} onClick={() => setMenuOpen(false)} />}

        {/* ── Layout: sidebar + content ────────────────────────────────── */}
        <div className={styles.layout}>

          {/* Sidebar */}
          <aside className={`${styles.sidebar} ${menuOpen ? styles.sidebarOpen : ""}`}>
            <div className={styles.sidebarTop}>
              <span className={styles.sidebarTitle}>Admin Panel</span>
              <button className={styles.sidebarClose} onClick={() => setMenuOpen(false)} aria-label="Close">✕</button>
            </div>
            <nav className={styles.sidebarNav}>
              {NAV.map(n => (
                <React.Fragment key={n.id}>
                  {n.dividerBefore && <div className={styles.navDivider} />}
                  <button
                    className={`${styles.navItem} ${tab === n.id ? styles.navActive : ""}`}
                    onClick={() => navigate(n.id)}
                  >
                    <span className={styles.navIcon}>{n.icon}</span>
                    {n.label}
                  </button>
                </React.Fragment>
              ))}
              <div className={styles.navDivider} />
              <a
                href="/akimxiu"
                className={styles.navLink}
                target="_blank"
                rel="noreferrer"
              >
                <span className={styles.navIcon}>🔧</span>
                License Manager ↗
              </a>
            </nav>
          </aside>

          {/* Content */}
          <div className={styles.content}>
            {/* Page title (desktop only — mobile uses topbar) */}
            <div className={styles.pageHead}>
              <h1 className={styles.pageTitle}>{activeLabel}</h1>
            </div>

            {/* Stats */}
            <div className={styles.stats}>
              <div className={`${styles.stat} ${styles.statWarn}`}>
                <span className={styles.statNum}>{stats.pending}</span>
                <span className={styles.statLabel}>Pending Orders</span>
              </div>
              <div className={`${styles.stat} ${styles.statGreen}`}>
                <span className={styles.statNum}>{stats.paid}</span>
                <span className={styles.statLabel}>Paid Orders</span>
              </div>
              <div className={`${styles.stat} ${styles.statCyan}`}>
                <span className={styles.statNum}>{stats.active}</span>
                <span className={styles.statLabel}>Active Licenses</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statNum}>{stats.totalOrders}</span>
                <span className={styles.statLabel}>Total Orders</span>
              </div>
            </div>

        {/* ── Orders tab ──────────────────────────────────────────────────── */}
        {tab === "orders" && (
          <div className={styles.panel}>
            <div className={styles.filterRow}>
              {["all", "pending", "paid", "rejected"].map(f => (
                <button
                  key={f}
                  className={`${styles.filterBtn} ${filter === f ? styles.filterActive : ""}`}
                  onClick={() => setFilter(f)}
                >
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
            {filteredOrders.length === 0 ? (
              <div className={styles.empty}>No orders found.</div>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Date</th><th>User</th><th>Plan</th><th>Amount</th>
                      <th>Method</th><th>Ref / Note</th><th>Status</th><th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredOrders.map(o => (
                      <tr key={o.id} className={o.status === "pending" ? styles.rowPending : ""}>
                        <td>
                          <div>{fmtDate(o.created_at)}</div>
                          <div className={styles.tSub}>{fmtTime(o.created_at)}</div>
                        </td>
                        <td>
                          <div>{(o.profiles as any)?.full_name ?? "—"}</div>
                          <div className={styles.tSub}>{(o.profiles as any)?.email ?? "—"}</div>
                        </td>
                        <td>{o.plan_label ?? o.plan_id}</td>
                        <td>${o.amount_usd.toFixed(2)}</td>
                        <td className={styles.capitalize}>{METHOD_LABEL[o.payment_method] ?? o.payment_method}</td>
                        <td>
                          <div><code className={styles.refCode}>{o.payment_ref ?? "—"}</code></div>
                          {o.note && <div className={styles.tSub}>{o.note}</div>}
                        </td>
                        <td><span className={`badge badge-${o.status}`}>{o.status}</span></td>
                        <td>
                          <div className={styles.actionBtns}>
                            {/* View button — always visible */}
                            <button
                              className={`${styles.actionBtn} ${styles.viewBtn}`}
                              onClick={() => setViewOrder(o)}
                            >
                              View
                            </button>
                            {/* Approve / Reject — only for pending */}
                            {o.status === "pending" && <>
                              <button
                                className={`${styles.actionBtn} ${styles.approveBtn}`}
                                onClick={() => setAssignOrder(o)}
                              >
                                Approve
                              </button>
                              <button
                                className={`${styles.actionBtn} ${styles.rejectBtn}`}
                                onClick={async () => {
                                  if (!confirm("Reject this order?")) return;
                                  await rejectOrder(o.id);
                                  setOrders(prev => prev.map(x => x.id === o.id ? { ...x, status: "rejected" as const } : x));
                                }}
                              >
                                Reject
                              </button>
                            </>}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ── Licenses tab ────────────────────────────────────────────────── */}
        {tab === "licenses" && (
          <div className={styles.panel}>
            {licenses.length === 0 ? (
              <div className={styles.empty}>No licenses issued yet.</div>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr><th>Issued</th><th>User</th><th>Key</th><th>Plan</th><th>Expires</th><th>Status</th><th>Actions</th></tr>
                  </thead>
                  <tbody>
                    {licenses.map(lic => (
                      <tr key={lic.id}>
                        <td>{fmtDate(lic.issued_at)}</td>
                        <td>
                          <div>{(lic.profiles as any)?.full_name ?? "—"}</div>
                          <div className={styles.tSub}>{(lic.profiles as any)?.email ?? "—"}</div>
                        </td>
                        <td><code className={styles.keyCode}>{lic.license_key}</code></td>
                        <td>{lic.plan_label ?? lic.plan_id ?? "—"}</td>
                        <td>{lic.expires_at ? fmtDate(lic.expires_at) : "Lifetime"}</td>
                        <td>
                          <span className={`badge badge-${lic.status === "active" ? "paid" : "rejected"}`}>{lic.status}</span>
                        </td>
                        <td>
                          {lic.status === "active" && (
                            <button className={`${styles.actionBtn} ${styles.rejectBtn}`} onClick={async () => {
                              if (!confirm("Revoke this license?")) return;
                              await revokeLicense(lic.id);
                              setLicenses(prev => prev.map(x => x.id === lic.id ? { ...x, status: "revoked" as const } : x));
                            }}>Revoke</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

            {/* ── Payment Settings ─────────────────────────────────────── */}
            {tab === "payments" && (
              <div className={styles.panel}><PaymentSettings configs={paymentConfigs} /></div>
            )}

            {/* ── Pricing Plans ─────────────────────────────────────────── */}
            {tab === "pricing" && (
              <div className={styles.panel}>
                <PricingSettings
                  initial={siteSettings.find(s => s.key === "pricing_plans")?.value ?? {}}
                />
              </div>
            )}

            {/* ── Website Settings ─────────────────────────────────────── */}
            {tab === "settings" && (
              <div className={styles.panel}><SiteSettings settings={siteSettings} /></div>
            )}

            {/* ── FAQ ──────────────────────────────────────────────────── */}
            {tab === "faq" && (
              <div className={styles.panel}><FaqSettings faqs={faqs} /></div>
            )}

            {/* ── Demo Images ──────────────────────────────────────────── */}
            {tab === "demo" && (
              <div className={styles.panel}><DemoSettings images={demoImages} /></div>
            )}

            {/* ── Revenue Stats ────────────────────────────────────────── */}
            {tab === "revenue" && (
              <div className={styles.panel}><RevenueStats orders={orders} paymentConfigs={paymentConfigs} /></div>
            )}

            {/* ── Analytics ────────────────────────────────────────────── */}
            {tab === "analytics" && (
              <div className={styles.panel}><Analytics visits={visits} /></div>
            )}

            {/* ── Users ────────────────────────────────────────────────── */}
            {tab === "users" && (
              <div className={styles.panel}>
                {users.length === 0 ? (
                  <div className={styles.empty}>No users found.</div>
                ) : (
                  <div className={styles.tableWrap}>
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th style={{ width: 32 }}></th>
                          <th>Name</th><th>Email</th><th>Ref Code</th>
                          <th>Ref Pts</th><th>Role</th><th>Joined</th><th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {users.map(u => {
                          const isOpen      = expandedUser === u.id;
                          const isLicLoading = licLoading.has(u.id);
                          return (
                            <React.Fragment key={u.id}>
                              <tr style={isOpen ? { background: "rgba(0,229,255,.04)" } : undefined}>
                                <td style={{ width: 32, paddingRight: 0 }}>
                                  <button
                                    className={`${styles.expandBtn} ${isOpen ? styles.expandBtnOpen : ""}`}
                                    onClick={() => toggleExpand(u.id)}
                                    title={isOpen ? "Collapse" : "View licenses / generate"}
                                  >
                                    {isOpen ? "▾" : "▸"}
                                  </button>
                                </td>
                                <td>{u.full_name ?? <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                                <td><span style={{ fontSize: 13 }}>{u.email ?? "—"}</span></td>
                                <td>
                                  {u.referral_code
                                    ? <code className={styles.refCode}>{u.referral_code}</code>
                                    : <span style={{ color: "var(--text-muted)" }}>—</span>}
                                </td>
                                <td style={{ textAlign: "center" }}>{u.referral_points ?? 0}</td>
                                <td style={{ textAlign: "center" }}>
                                  <span className={`badge badge-${u.is_admin ? "paid" : "pending"}`}>
                                    {u.is_admin ? "Admin" : "User"}
                                  </span>
                                </td>
                                <td>{fmtDate(u.created_at)}</td>
                                <td>
                                  <button
                                    className={`${styles.actionBtn} ${styles.viewBtn}`}
                                    onClick={() => setViewUser(u)}
                                  >
                                    Edit
                                  </button>
                                </td>
                              </tr>
                              {isOpen && (
                                <tr>
                                  <td colSpan={8} className={styles.expandedCell}>
                                    <UserLicensePanel
                                      user={u}
                                      licenses={userLicenses[u.id]}
                                      loading={isLicLoading}
                                      onLicenseAdded={lic => handleLicenseAdded(u.id, lic)}
                                    />
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* ── Referrals ─────────────────────────────────────────────── */}
            {tab === "referrals" && (
              <div className={styles.panel}>
                {/* Summary stats */}
                <div className={styles.stats} style={{ marginBottom: 24 }}>
                  <div className={styles.stat}>
                    <span className={styles.statNum}>{refEvents.length}</span>
                    <span className={styles.statLabel}>Total Events</span>
                  </div>
                  <div className={`${styles.stat} ${styles.statCyan}`}>
                    <span className={styles.statNum}>{refEvents.filter(e => e.event_type === "download").length}</span>
                    <span className={styles.statLabel}>Downloads</span>
                  </div>
                  <div className={`${styles.stat} ${styles.statGreen}`}>
                    <span className={styles.statNum}>{refEvents.filter(e => e.event_type === "purchase").length}</span>
                    <span className={styles.statLabel}>Purchases</span>
                  </div>
                  <div className={styles.stat}>
                    <span className={styles.statNum}>{refEvents.reduce((s, e) => s + (e.points ?? 0), 0)}</span>
                    <span className={styles.statLabel}>Total Pts Awarded</span>
                  </div>
                </div>

                {refEvents.length === 0 ? (
                  <div className={styles.empty}>No referral events yet.</div>
                ) : (
                  <div className={styles.tableWrap}>
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th>Date</th><th>Referrer</th><th>Type</th>
                          <th>Code Used</th><th>Points</th>
                        </tr>
                      </thead>
                      <tbody>
                        {refEvents.map(e => {
                          const referrer = (e as any).referrer;
                          return (
                            <tr key={e.id}>
                              <td>
                                <div>{fmtDate(e.created_at)}</div>
                                <div className={styles.tSub}>{fmtTime(e.created_at)}</div>
                              </td>
                              <td>
                                <div>{referrer?.full_name ?? "—"}</div>
                                <div className={styles.tSub}>{referrer?.email ?? "—"}</div>
                              </td>
                              <td>
                                <span className={`badge badge-${e.event_type === "purchase" ? "paid" : "pending"}`}>
                                  {e.event_type === "purchase" ? "💳 Purchase" : "⬇️ Download"}
                                </span>
                              </td>
                              <td>
                                <code className={styles.refCode}>
                                  {(e.meta as any)?.referral_code ?? "—"}
                                </code>
                              </td>
                              <td style={{ fontWeight: 700, color: "var(--cyan)" }}>+{e.points}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
            {/* ── Blacklist ─────────────────────────────────────────────── */}
            {tab === "blacklist" && (
              <div className={styles.panel}>
                {/* Summary */}
                <div className={styles.stats} style={{ marginBottom: 24 }}>
                  <div className={`${styles.stat} ${styles.statWarn}`}>
                    <span className={styles.statNum}>{blacklist.length}</span>
                    <span className={styles.statLabel}>Total Entries</span>
                  </div>
                  <div className={`${styles.stat} ${styles.statCyan}`}>
                    <span className={styles.statNum}>{blacklist.filter(b => !b.is_banned).length}</span>
                    <span className={styles.statLabel}>Warned</span>
                  </div>
                  <div className={`${styles.stat}`} style={{ borderColor: "rgba(255,68,102,.3)" }}>
                    <span className={styles.statNum} style={{ color: "var(--red)" }}>{blacklist.filter(b => b.is_banned).length}</span>
                    <span className={styles.statLabel}>Banned</span>
                  </div>
                  <div className={styles.stat}>
                    <span className={styles.statNum}>{blacklist.filter(b => b.ip).length}</span>
                    <span className={styles.statLabel}>With IP</span>
                  </div>
                </div>

                {blacklist.length === 0 ? (
                  <div className={styles.empty}>No blacklist entries.</div>
                ) : (
                  <div className={styles.tableWrap}>
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th>User</th><th>IP</th><th>Route</th>
                          <th>Strikes</th><th>Status</th><th>Date</th><th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {blacklist.map(entry => {
                          const prof = entry.profiles as any;
                          return (
                            <tr key={entry.id} style={entry.is_banned ? { background: "rgba(255,68,102,.04)" } : undefined}>
                              <td>
                                <div>{prof?.full_name ?? <span style={{ color: "var(--text-muted)" }}>—</span>}</div>
                                <div className={styles.tSub}>{prof?.email ?? (entry.user_id ? entry.user_id.slice(0, 12) + "…" : "Anonymous")}</div>
                              </td>
                              <td>
                                {entry.ip
                                  ? <code className={styles.refCode}>{entry.ip}</code>
                                  : <span style={{ color: "var(--text-muted)" }}>—</span>}
                              </td>
                              <td>
                                <code style={{ fontSize: 12, color: "var(--text-dim)" }}>{entry.route || "—"}</code>
                              </td>
                              <td style={{ textAlign: "center" }}>
                                <span style={{
                                  fontWeight: 800, fontSize: 16,
                                  color: entry.strike_count >= 2 ? "var(--red)" : "var(--yellow)",
                                }}>{entry.strike_count}</span>
                              </td>
                              <td>
                                <span className={`badge badge-${entry.is_banned ? "rejected" : "pending"}`}>
                                  {entry.is_banned ? "🚫 Banned" : "⚠️ Warned"}
                                </span>
                              </td>
                              <td>
                                <div>{fmtDate(entry.created_at)}</div>
                                <div className={styles.tSub}>{fmtTime(entry.created_at)}</div>
                              </td>
                              <td>
                                <div className={styles.actionBtns}>
                                  {entry.is_banned && (
                                    <button
                                      className={`${styles.actionBtn} ${styles.approveBtn}`}
                                      onClick={async () => {
                                        if (!confirm(`Unban ${prof?.email ?? entry.ip ?? "this entry"}?`)) return;
                                        await createClient().from("blacklist")
                                          .update({ is_banned: false, strike_count: 1, updated_at: new Date().toISOString() })
                                          .eq("id", entry.id);
                                        setBlacklist(prev => prev.map(x => x.id === entry.id ? { ...x, is_banned: false, strike_count: 1 } : x));
                                      }}
                                    >
                                      Unban
                                    </button>
                                  )}
                                  <button
                                    className={`${styles.actionBtn} ${styles.rejectBtn}`}
                                    onClick={async () => {
                                      if (!confirm(`Delete blacklist entry for ${prof?.email ?? entry.ip ?? "this entry"}?`)) return;
                                      await createClient().from("blacklist").delete().eq("id", entry.id);
                                      setBlacklist(prev => prev.filter(x => x.id !== entry.id));
                                    }}
                                  >
                                    Delete
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

          </div>{/* end .content */}
        </div>{/* end .layout */}
      </div>{/* end .container */}

      {/* Modals */}
      {assignOrder && (
        <AssignModal
          order={assignOrder}
          onClose={() => setAssignOrder(null)}
          onDone={() => setOrders(prev => prev.map(x => x.id === assignOrder.id ? { ...x, status: "paid" as const } : x))}
        />
      )}

      {viewOrder && (
        <OrderDetailModal
          order={viewOrder}
          onClose={() => setViewOrder(null)}
          onDeleted={id => {
            setOrders(prev => prev.filter(x => x.id !== id));
            setViewOrder(null);
          }}
        />
      )}

      {viewUser && (
        <UserEditModal
          user={viewUser}
          onClose={() => setViewUser(null)}
          onUpdated={updated => {
            setUsers(prev => prev.map(x => x.id === updated.id ? updated : x));
            setViewUser(updated);
          }}
          onDeleted={id => {
            setUsers(prev => prev.filter(x => x.id !== id));
            setViewUser(null);
          }}
        />
      )}
    </main>
  );
}

