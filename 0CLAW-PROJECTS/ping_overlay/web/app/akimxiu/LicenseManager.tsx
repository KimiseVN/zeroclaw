"use client";
import React, { useState, useMemo, useCallback, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import type { License, AppClient } from "@/lib/supabase/types";
import styles from "./license-manager.module.css";

// ─── License constants (must match license_lib.py exactly) ────────────────────
const LICENSE_FORMAT  = "PO1";
const LICENSE_SECRET  = "PingOverlay-Kim-License-v1-2026-MAY-04-7G3Q9P";

// duration code → days (0 = lifetime), mirrors DURATIONS in license_lib.py
const DURATIONS: Record<string, number> = {
  "1d":  1,
  "1w":  7,
  "1mo": 30,
  "3mo": 90,
  "6mo": 180,
  "1y":  365,
  "lt":  0,
};

const PLANS = [
  { id: "1d",  label: "1 Day"    },
  { id: "1w",  label: "1 Week"   },
  { id: "1mo", label: "1 Month"  },
  { id: "3mo", label: "3 Months" },
  { id: "6mo", label: "6 Months" },
  { id: "1y",  label: "1 Year"   },
  { id: "lt",  label: "Lifetime" },
];

// ─── HWID helpers ─────────────────────────────────────────────────────────────
function normalizeHwid(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 16);
}

function formatHwidDisplay(norm: string): string {
  if (norm.length !== 16) return norm;
  return [norm.slice(0, 4), norm.slice(4, 8), norm.slice(8, 12), norm.slice(12, 16)].join("-");
}

// ─── HMAC-SHA256 signing (Web Crypto API, mirrors _sign() in license_lib.py) ─
async function signPayload(payload: string): Promise<string> {
  const enc      = new TextEncoder();
  const keyData  = enc.encode(LICENSE_SECRET);
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sigBuf = await crypto.subtle.sign("HMAC", cryptoKey, enc.encode(payload));
  const hex = Array.from(new Uint8Array(sigBuf))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
  return hex.slice(0, 32);
}

// ─── Issue a real PO1 license key ─────────────────────────────────────────────
async function issueLicenseKey(hwid: string, durationCode: string): Promise<{
  key: string;
  expiry_ts: number;
  expires_at_iso: string | null;
}> {
  const hwid_norm = normalizeHwid(hwid);
  if (hwid_norm.length !== 16) throw new Error("HWID must be exactly 16 alphanumeric characters");
  const days = DURATIONS[durationCode];
  if (days === undefined) throw new Error(`Unknown duration code: ${durationCode}`);

  let expiry_ts = 0;
  let expires_at_iso: string | null = null;
  if (days > 0) {
    const exp = new Date();
    exp.setDate(exp.getDate() + days);
    expiry_ts = Math.floor(exp.getTime() / 1000);
    expires_at_iso = exp.toISOString();
  }

  const payload = `${LICENSE_FORMAT}|${hwid_norm}|${durationCode.toLowerCase()}|${expiry_ts}`;
  const sig = await signPayload(payload);
  const key = `${LICENSE_FORMAT}-${hwid_norm}-${durationCode.toUpperCase()}-${expiry_ts}-${sig}`;
  return { key, expiry_ts, expires_at_iso };
}

// ─── Misc helpers ─────────────────────────────────────────────────────────────
function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function isExpired(lic: License) {
  if (!lic.expires_at) return false;
  return new Date(lic.expires_at) < new Date();
}

function effectiveStatus(lic: License): "active" | "revoked" | "expired" {
  if (lic.status === "revoked") return "revoked";
  if (isExpired(lic))           return "expired";
  return "active";
}

// ─── Copy-to-clipboard hook ───────────────────────────────────────────────────
function useCopy() {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = useCallback((text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(id);
      setTimeout(() => setCopied(null), 1500);
    });
  }, []);
  return { copied, copy };
}

// ─── Supabase site_settings helper ───────────────────────────────────────────
async function saveSetting(key: string, value: Record<string, any>) {
  await createClient().from("site_settings")
    .upsert({ key, value, updated_at: new Date().toISOString() }, { onConflict: "key" });
}

// ─── Edit Expiry Modal ────────────────────────────────────────────────────────
function EditExpiryModal({
  lic, onClose, onSaved,
}: {
  lic: License;
  onClose: () => void;
  onSaved: (updated: License) => void;
}) {
  const [expiry, setExpiry] = useState(lic.expires_at ? lic.expires_at.slice(0, 10) : "");
  const [busy,   setBusy]   = useState(false);
  const [err,    setErr]    = useState("");

  async function save() {
    setBusy(true); setErr("");
    const sb = createClient();
    const { error } = await sb
      .from("licenses")
      .update({ expires_at: expiry || null })
      .eq("id", lic.id);
    setBusy(false);
    if (error) { setErr(error.message); return; }
    onSaved({ ...lic, expires_at: expiry || null });
    onClose();
  }

  return (
    <div className="modal-backdrop open" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card" style={{ maxWidth: 380 }}>
        <button className="modal-close" onClick={onClose}>✕</button>
        <h3 style={{ fontFamily: "var(--font-head)", fontSize: 18, marginBottom: 18 }}>Edit Expiry</h3>
        <code style={{ fontSize: 12, color: "var(--cyan)", display: "block", marginBottom: 16 }}>{lic.license_key}</code>
        <label style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-muted)", display: "block", marginBottom: 8 }}>
          Expiry Date (blank = Lifetime)
        </label>
        <input
          type="date"
          className={styles.input}
          value={expiry}
          onChange={e => setExpiry(e.target.value)}
          style={{ marginBottom: 16 }}
        />
        {err && <p style={{ fontSize: 13, color: "var(--red)", marginBottom: 10 }}>{err}</p>}
        <div style={{ display: "flex", gap: 10 }}>
          <button className="btn btn-ghost" onClick={onClose} style={{ flex: 1 }} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" onClick={save}  style={{ flex: 1 }} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </div>
  );
}

// ─── Generate Form ─────────────────────────────────────────────────────────────
function GenerateForm({ onGenerated }: { onGenerated: (lic: License) => void }) {
  const [planId,  setPlanId]  = useState("1mo");
  const [hwid,    setHwid]    = useState("");
  const [email,   setEmail]   = useState("");
  const [note,    setNote]    = useState("");
  const [busy,    setBusy]    = useState(false);
  const [err,     setErr]     = useState("");
  const [lastKey, setLastKey] = useState<string | null>(null);
  const { copied, copy }      = useCopy();

  const [preview, setPreview] = useState("");
  useEffect(() => {
    const norm = normalizeHwid(hwid);
    if (norm.length !== 16) { setPreview(""); return; }
    let cancelled = false;
    issueLicenseKey(hwid, planId).then(({ key }) => {
      if (!cancelled) setPreview(key);
    }).catch(() => { if (!cancelled) setPreview(""); });
    return () => { cancelled = true; };
  }, [hwid, planId]);

  async function generate() {
    setErr(""); setLastKey(null);
    const norm = normalizeHwid(hwid);
    if (norm.length !== 16) {
      setErr("HWID phải đúng 16 ký tự alphanumeric (A–Z, 0–9). Lấy từ app PingOverlay → Setting.");
      return;
    }
    setBusy(true);
    try {
      const sb = createClient();
      const { key, expires_at_iso } = await issueLicenseKey(hwid, planId);

      let userId: string | null = null;
      if (email.trim()) {
        const { data: prof } = await sb
          .from("profiles")
          .select("id")
          .eq("email", email.trim())
          .maybeSingle();
        userId = prof?.id ?? null;
      }

      const plan = PLANS.find(p => p.id === planId)!;
      const payload = {
        user_id:     userId,
        order_id:    null,
        license_key: key,
        hwid:        norm,
        plan_id:     planId,
        plan_label:  plan.label,
        expires_at:  expires_at_iso,
        note:        note.trim() || (email.trim() && !userId ? `for: ${email.trim()}` : null),
        status:      "active" as const,
      };

      const { data: inserted, error } = await sb
        .from("licenses")
        .insert(payload)
        .select("*, profiles(email, full_name)")
        .single();

      if (error) throw error;

      onGenerated(inserted as License);
      setLastKey(key);
      setHwid(""); setEmail(""); setNote("");
    } catch (e: any) {
      setErr(e.message ?? "Failed to generate license");
    } finally {
      setBusy(false);
    }
  }

  const hwidNorm  = normalizeHwid(hwid);
  const hwidValid = hwidNorm.length === 16;

  return (
    <div className={styles.generateCard}>
      <h2 className={styles.cardTitle}>
        <span className={styles.cardTitleIcon}>🔑</span> Generate License
      </h2>

      <div className={styles.fieldGroup}>
        <label className={styles.label}>
          HWID của khách <span className={styles.required}>* bắt buộc</span>
          <span className={styles.optional}> — lấy từ PingOverlay → Setting → copy HWID</span>
        </label>
        <input
          className={`${styles.input} ${styles.keyInput} ${hwid && !hwidValid ? styles.inputErr : ""}`}
          value={hwid}
          onChange={e => setHwid(e.target.value)}
          placeholder="XXXX-XXXX-XXXX-XXXX  hoặc  XXXXXXXXXXXXXXXX"
          spellCheck={false}
          autoComplete="off"
        />
        {hwid && !hwidValid && (
          <p className={styles.hwidHint}>{hwidNorm.length} / 16 ký tự — cần đúng 16 ký tự (chữ + số)</p>
        )}
        {hwidValid && (
          <p className={styles.hwidOk}>✓ {formatHwidDisplay(hwidNorm)}</p>
        )}
      </div>

      <div className={styles.fieldGroup}>
        <label className={styles.label}>Thời hạn / Duration</label>
        <div className={styles.planPills}>
          {PLANS.map(p => (
            <button
              key={p.id}
              className={`${styles.pill} ${planId === p.id ? styles.pillActive : ""}`}
              onClick={() => setPlanId(p.id)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {preview && (
        <div className={styles.previewBox}>
          <span className={styles.previewLabel}>Preview key</span>
          <code className={styles.previewKey}>{preview}</code>
        </div>
      )}

      <div className={styles.row2}>
        <div className={styles.fieldGroup}>
          <label className={styles.label}>Email user <span className={styles.optional}>(optional)</span></label>
          <input
            type="email"
            className={styles.input}
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="user@example.com"
          />
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.label}>Ghi chú <span className={styles.optional}>(admin internal)</span></label>
          <input
            className={styles.input}
            value={note}
            onChange={e => setNote(e.target.value)}
            placeholder="Reseller, gift, etc."
          />
        </div>
      </div>

      {err && <p className={styles.errMsg}>{err}</p>}

      <button
        className={`btn btn-primary ${styles.generateBtn}`}
        onClick={generate}
        disabled={busy || !hwidValid}
      >
        {busy ? "Đang tạo…" : "⚡ Generate & Save"}
      </button>

      {lastKey && (
        <div className={styles.successBox}>
          <p className={styles.successLabel}>✓ License đã tạo thành công</p>
          <div className={styles.successKey}>
            <code className={styles.bigKey}>{lastKey}</code>
            <button
              className={`btn btn-ghost ${styles.copyBtnLg}`}
              onClick={() => copy(lastKey, "gen")}
            >
              {copied === "gen" ? "✓ Copied!" : "Copy"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── License Table ────────────────────────────────────────────────────────────
function LicenseTable({
  licenses,
  onUpdate,
  onDelete,
}: {
  licenses: License[];
  onUpdate: (updated: License) => void;
  onDelete: (id: string) => void;
}) {
  const [search,    setSearch]    = useState("");
  const [statusTab, setStatusTab] = useState<"all" | "active" | "revoked" | "expired">("all");
  const [planTab,   setPlanTab]   = useState("all");
  const [editLic,   setEditLic]   = useState<License | null>(null);
  const [busy,      setBusy]      = useState<string | null>(null);
  const [expanded,  setExpanded]  = useState<string | null>(null);
  const { copied,   copy }        = useCopy();

  const planOptions = useMemo(() => {
    const ids = [...new Set(licenses.map(l => l.plan_id).filter(Boolean))];
    return ids as string[];
  }, [licenses]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return licenses.filter(l => {
      const eff = effectiveStatus(l);
      if (statusTab !== "all" && eff !== statusTab) return false;
      if (planTab   !== "all" && l.plan_id !== planTab) return false;
      if (q) {
        const em = (l.profiles as any)?.email ?? "";
        const nm = (l.profiles as any)?.full_name ?? "";
        if (
          !l.license_key.toLowerCase().includes(q) &&
          !em.toLowerCase().includes(q) &&
          !nm.toLowerCase().includes(q) &&
          !(l.hwid ?? "").toLowerCase().includes(q) &&
          !(l.note ?? "").toLowerCase().includes(q)
        ) return false;
      }
      return true;
    });
  }, [licenses, search, statusTab, planTab]);

  async function toggleStatus(lic: License) {
    const newStatus = lic.status === "active" ? "revoked" : "active";
    setBusy(lic.id);
    const sb = createClient();
    const { error } = await sb.from("licenses").update({ status: newStatus }).eq("id", lic.id);
    setBusy(null);
    if (!error) onUpdate({ ...lic, status: newStatus });
  }

  async function deleteLicense(lic: License) {
    if (!confirm(`Xóa license:\n${lic.license_key}\n\nThao tác không thể hoàn tác.`)) return;
    setBusy(lic.id);
    const sb = createClient();
    await sb.from("licenses").delete().eq("id", lic.id);
    setBusy(null);
    onDelete(lic.id);
  }

  const STATUS_TABS = ["all", "active", "revoked", "expired"] as const;
  const counts = useMemo(() => {
    const c = { all: licenses.length, active: 0, revoked: 0, expired: 0 };
    licenses.forEach(l => { c[effectiveStatus(l)]++; });
    return c;
  }, [licenses]);

  return (
    <div className={styles.tableCard}>
      <div className={styles.tableHead}>
        <h2 className={styles.cardTitle}>
          <span className={styles.cardTitleIcon}>📋</span>
          All Licenses <span className={styles.countBadge}>{licenses.length}</span>
        </h2>
        <input
          className={`${styles.input} ${styles.searchInput}`}
          placeholder="Search key, HWID, email, note…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <div className={styles.filterRow}>
        <div className={styles.filterGroup}>
          {STATUS_TABS.map(s => (
            <button
              key={s}
              className={`${styles.filterBtn} ${statusTab === s ? styles.filterActive : ""}`}
              onClick={() => setStatusTab(s)}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}{" "}
              <span className={styles.filterCount}>{counts[s]}</span>
            </button>
          ))}
        </div>
        {planOptions.length > 0 && (
          <div className={styles.filterGroup}>
            <button className={`${styles.filterBtn} ${planTab === "all" ? styles.filterActive : ""}`} onClick={() => setPlanTab("all")}>
              All Plans
            </button>
            {planOptions.map(id => {
              const p = PLANS.find(x => x.id === id);
              return (
                <button key={id} className={`${styles.filterBtn} ${planTab === id ? styles.filterActive : ""}`} onClick={() => setPlanTab(id)}>
                  {p?.label ?? id}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {filtered.length === 0 ? (
        <div className={styles.empty}>Không có license nào phù hợp bộ lọc.</div>
      ) : (
        <>
          {/* ── Mobile accordion (≤700px) ────────────────────────────────── */}
          <div className={styles.licenseList}>
            {filtered.map(lic => {
              const eff     = effectiveStatus(lic);
              const profile = (lic.profiles as any);
              const isBusy  = busy === lic.id;
              const isOpen  = expanded === lic.id;

              const dotClass = eff === "active"  ? styles.licenseActive
                             : eff === "revoked" ? styles.licenseRevoked
                             :                    styles.licenseExpired;

              return (
                <div key={lic.id} className={styles.clientItem}>
                  {/* Header: status dot · plan badge · HWID · chevron */}
                  <button
                    className={styles.clientItemHead}
                    onClick={() => setExpanded(isOpen ? null : lic.id)}
                  >
                    <span className={`${styles.clientStatusDot} ${dotClass}`} />
                    <span className={styles.planBadge}>{lic.plan_label ?? lic.plan_id ?? "—"}</span>
                    <code className={styles.clientHwid} style={{ fontSize: 11 }}>
                      {lic.hwid ? formatHwidDisplay(lic.hwid) : "floating"}
                    </code>
                    <span className={`${styles.clientChevron} ${isOpen ? styles.clientChevronOpen : ""}`}>▾</span>
                  </button>

                  {/* Expanded detail rows */}
                  {isOpen && (
                    <div className={styles.clientItemBody}>
                      {/* License key with copy */}
                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>Key</span>
                        <button
                          className={styles.keyCell}
                          onClick={() => copy(lic.license_key, lic.id + "_m")}
                          title="Tap to copy"
                          style={{ flex: 1 }}
                        >
                          <code style={{ fontSize: 10, wordBreak: "break-all", lineHeight: 1.5, color: "var(--cyan)" }}>
                            {lic.license_key}
                          </code>
                          <span className={styles.copyHint}>{copied === lic.id + "_m" ? "✓" : "⎘"}</span>
                        </button>
                      </div>

                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>HWID</span>
                        <span className={styles.clientInfoValue}>
                          {lic.hwid
                            ? <code style={{ fontFamily: "monospace", fontSize: 12, color: "var(--text-dim)", letterSpacing: ".04em" }}>{formatHwidDisplay(lic.hwid)}</code>
                            : <span className={styles.muted}>—</span>
                          }
                        </span>
                      </div>

                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>User</span>
                        <span className={styles.clientInfoValue}>
                          {profile ? (
                            <span>
                              {profile.full_name && <span style={{ fontWeight: 600, marginRight: 4 }}>{profile.full_name}</span>}
                              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{profile.email}</span>
                            </span>
                          ) : (
                            <span className={styles.floating}>floating</span>
                          )}
                        </span>
                      </div>

                      {lic.note && (
                        <div className={styles.clientInfoRow}>
                          <span className={styles.clientInfoLabel}>Note</span>
                          <span className={styles.clientInfoValue} style={{ fontSize: 12 }}>📝 {lic.note}</span>
                        </div>
                      )}

                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>Expires</span>
                        <span className={styles.clientInfoValue}>
                          {lic.expires_at
                            ? <span className={eff === "expired" ? styles.expiredDate : ""}>{fmtDate(lic.expires_at)}</span>
                            : <span className={styles.lifetime}>Lifetime ∞</span>
                          }
                        </span>
                      </div>

                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>Status</span>
                        <span className={`${styles.clientInfoValue} ${styles[`status_${eff}`]}`}>
                          <span className={`${styles.statusDot} ${styles[`dot_${eff}`]}`} />
                          {eff}
                        </span>
                      </div>

                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>Issued</span>
                        <span className={styles.clientInfoValue}>{fmtDate(lic.issued_at)}</span>
                      </div>

                      {/* Actions */}
                      <div className={styles.clientItemActions}>
                        <button
                          className={`${styles.clientActionBtn} ${styles.copyBtn}`}
                          onClick={() => copy(lic.license_key, lic.id + "_act")}
                        >
                          {copied === lic.id + "_act" ? "✓ Copied" : "⎘ Copy Key"}
                        </button>
                        <button
                          className={`${styles.clientActionBtn} ${styles.editBtn}`}
                          onClick={() => setEditLic(lic)}
                          disabled={isBusy}
                        >
                          ✏ Edit Expiry
                        </button>
                        <button
                          className={`${styles.clientActionBtn} ${lic.status === "active" ? styles.revokeBtn : styles.activateBtn}`}
                          onClick={() => toggleStatus(lic)}
                          disabled={isBusy}
                        >
                          {isBusy ? "…" : lic.status === "active" ? "⛔ Revoke" : "✅ Activate"}
                        </button>
                        <button
                          className={`${styles.clientActionBtn} ${styles.deleteBtn}`}
                          onClick={() => deleteLicense(lic)}
                          disabled={isBusy}
                        >
                          🗑 Delete
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* ── Desktop table (>700px) ────────────────────────────────────── */}
          <div className={`${styles.tableWrap} ${styles.licensesDesktopOnly}`}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>License Key (PO1)</th>
                  <th>HWID</th>
                  <th>Plan</th>
                  <th>User / Note</th>
                  <th>Expires</th>
                  <th>Status</th>
                  <th>Issued</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(lic => {
                  const eff     = effectiveStatus(lic);
                  const profile = (lic.profiles as any);
                  const isBusy  = busy === lic.id;

                  return (
                    <tr key={lic.id} className={styles[`row_${eff}`]}>
                      <td>
                        <button
                          className={styles.keyCell}
                          onClick={() => copy(lic.license_key, lic.id)}
                          title="Click to copy"
                        >
                          <code>{lic.license_key}</code>
                          <span className={styles.copyHint}>{copied === lic.id ? "✓" : "⎘"}</span>
                        </button>
                      </td>
                      <td>
                        {lic.hwid
                          ? <code className={styles.hwidCode}>{formatHwidDisplay(lic.hwid)}</code>
                          : <span className={styles.muted}>—</span>
                        }
                      </td>
                      <td>
                        <span className={styles.planBadge}>{lic.plan_label ?? lic.plan_id ?? "—"}</span>
                      </td>
                      <td>
                        {profile ? (
                          <>
                            <div className={styles.userName}>{profile.full_name ?? "—"}</div>
                            <div className={styles.userEmail}>{profile.email}</div>
                          </>
                        ) : (
                          <span className={styles.floating}>floating</span>
                        )}
                        {lic.note && <div className={styles.note} title={lic.note}>📝 {lic.note}</div>}
                      </td>
                      <td>
                        {lic.expires_at
                          ? <span className={eff === "expired" ? styles.expiredDate : ""}>{fmtDate(lic.expires_at)}</span>
                          : <span className={styles.lifetime}>Lifetime</span>
                        }
                      </td>
                      <td>
                        <span className={`${styles.statusDot} ${styles[`dot_${eff}`]}`} />
                        <span className={styles[`status_${eff}`]}>{eff}</span>
                      </td>
                      <td className={styles.muted}>{fmtDate(lic.issued_at)}</td>
                      <td>
                        <div className={styles.actions}>
                          <button
                            className={`${styles.actionBtn} ${styles.copyBtn}`}
                            onClick={() => copy(lic.license_key, lic.id + "_act")}
                            title="Copy key"
                          >
                            {copied === lic.id + "_act" ? "✓" : "⎘"}
                          </button>
                          <button
                            className={`${styles.actionBtn} ${styles.editBtn}`}
                            onClick={() => setEditLic(lic)}
                            title="Edit expiry"
                            disabled={isBusy}
                          >
                            ✏
                          </button>
                          <button
                            className={`${styles.actionBtn} ${lic.status === "active" ? styles.revokeBtn : styles.activateBtn}`}
                            onClick={() => toggleStatus(lic)}
                            title={lic.status === "active" ? "Revoke" : "Reactivate"}
                            disabled={isBusy}
                          >
                            {isBusy ? "…" : lic.status === "active" ? "⛔" : "✅"}
                          </button>
                          <button
                            className={`${styles.actionBtn} ${styles.deleteBtn}`}
                            onClick={() => deleteLicense(lic)}
                            title="Delete"
                            disabled={isBusy}
                          >
                            🗑
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {editLic && (
        <EditExpiryModal
          lic={editLic}
          onClose={() => setEditLic(null)}
          onSaved={updated => { onUpdate(updated); setEditLic(null); }}
        />
      )}
    </div>
  );
}

// ─── Active Clients Tab ───────────────────────────────────────────────────────
function ClientsTab() {
  const [clients,  setClients]  = useState<AppClient[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [busy,     setBusy]     = useState<string | null>(null);
  const [err,      setErr]      = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const { copied,  copy }       = useCopy();

  async function load() {
    setLoading(true); setErr("");
    const sb = createClient();
    const { data, error } = await sb
      .from("clients")
      .select("*")
      .order("last_seen", { ascending: false });
    setLoading(false);
    if (error) { setErr(error.message); return; }
    setClients((data ?? []) as AppClient[]);
  }

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function toggleBan(c: AppClient) {
    const newBanned = !c.banned;
    const reason = newBanned ? (prompt("Lý do ban (có thể để trống):") ?? "") : "";
    setBusy(c.hwid);
    const sb = createClient();
    const { error } = await sb
      .from("clients")
      .update({ banned: newBanned, ban_reason: newBanned ? reason : "" })
      .eq("hwid", c.hwid);
    setBusy(null);
    if (error) { alert(error.message); return; }
    setClients(prev => prev.map(x => x.hwid === c.hwid
      ? { ...x, banned: newBanned, ban_reason: newBanned ? reason : "" }
      : x
    ));
  }

  async function toggleForceUpdate(c: AppClient) {
    const newVal = !c.force_update;
    setBusy(c.hwid + "_fu");
    const sb = createClient();
    const { error } = await sb
      .from("clients")
      .update({ force_update: newVal })
      .eq("hwid", c.hwid);
    setBusy(null);
    if (error) { alert(error.message); return; }
    setClients(prev => prev.map(x => x.hwid === c.hwid ? { ...x, force_update: newVal } : x));
  }

  function fmtAgo(iso: string) {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1)  return "now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  const online   = clients.filter(c => Date.now() - new Date(c.last_seen).getTime() < 20 * 60 * 1000).length;
  const banned   = clients.filter(c => c.banned).length;
  const licensed = clients.filter(c => c.licensed_db || c.licensed_local).length;

  return (
    <div className={styles.tableCard}>
      <div className={styles.tableHead}>
        <h2 className={styles.cardTitle}>
          <span className={styles.cardTitleIcon}>📡</span>
          Active Clients
          <span className={styles.countBadge}>{clients.length}</span>
          <span className={styles.onlineDot} title={`${online} online (seen <20m)`}>{online} online</span>
        </h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button className={`btn btn-ghost ${styles.refreshBtn}`} onClick={load} disabled={loading}>
            {loading ? "Loading…" : "↺ Refresh"}
          </button>
        </div>
      </div>

      <div className={styles.clientStats}>
        <span className={styles.cStat}><span className={styles.cStatNum} style={{ color: "var(--green)" }}>{licensed}</span> licensed</span>
        <span className={styles.cStat}><span className={styles.cStatNum} style={{ color: "var(--red)" }}>{banned}</span> banned</span>
        <span className={styles.cStat}><span className={styles.cStatNum}>{clients.length}</span> total</span>
      </div>

      {err && <p className={styles.errMsg}>{err}</p>}

      {clients.length === 0 && !loading ? (
        <div className={styles.empty}>
          Chưa có heartbeat nào. App PingOverlay cần được build với endpoint mới và chạy ít nhất 1 lần.
        </div>
      ) : (
        <>
          {/* ── Mobile accordion (≤700px) ────────────────────────────────── */}
          <div className={styles.clientList}>
            {clients.map(c => {
              const isOpen     = expanded === c.hwid;
              const isBusy     = busy === c.hwid || busy === c.hwid + "_fu";
              const isOnline   = Date.now() - new Date(c.last_seen).getTime() < 20 * 60 * 1000;
              const hwidDisplay = [c.hwid.slice(0,4), c.hwid.slice(4,8), c.hwid.slice(8,12), c.hwid.slice(12,16)].join("-");
              const ago         = fmtAgo(c.last_seen);

              return (
                <div
                  key={c.hwid}
                  className={`${styles.clientItem} ${c.banned ? styles.clientBanned : ""}`}
                >
                  {/* Header row — HWID + chevron */}
                  <button
                    className={styles.clientItemHead}
                    onClick={() => setExpanded(isOpen ? null : c.hwid)}
                  >
                    <span className={`${styles.clientStatusDot} ${isOnline ? styles.clientStatusOnline : ""}`} />
                    <code className={styles.clientHwid}>{hwidDisplay}</code>
                    <span className={`${styles.clientChevron} ${isOpen ? styles.clientChevronOpen : ""}`}>▾</span>
                  </button>

                  {/* Expanded detail rows */}
                  {isOpen && (
                    <div className={styles.clientItemBody}>
                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>Last Seen</span>
                        <span className={styles.clientInfoValue} style={{ color: isOnline ? "var(--green)" : undefined }}>
                          {isOnline ? "🟢 " : ""}{ago}
                        </span>
                      </div>
                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>Version</span>
                        <span className={styles.clientInfoValue}>{c.app_version ?? "—"}</span>
                      </div>
                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>IP</span>
                        <span className={styles.clientInfoValue} style={{ fontFamily: "monospace", fontSize: 12 }}>
                          {c.public_ip ?? "—"}
                        </span>
                      </div>
                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>License</span>
                        <span className={`${styles.clientInfoValue} ${(c.licensed_db || c.licensed_local) ? styles.status_active : styles.status_expired}`}>
                          {(c.licensed_db || c.licensed_local) ? `✓ ${c.license_db_plan ?? "active"}` : "✗ none"}
                        </span>
                      </div>
                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>Local Key</span>
                        <span className={`${styles.clientInfoValue} ${c.licensed_local ? styles.status_active : ""}`}>
                          {c.licensed_local ? "✓ yes" : <span className={styles.muted}>—</span>}
                        </span>
                      </div>
                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>Banned</span>
                        <span className={styles.clientInfoValue}>
                          {c.banned
                            ? <span className={styles.status_revoked}>⛔ {c.ban_reason || "banned"}</span>
                            : <span className={styles.muted}>—</span>
                          }
                        </span>
                      </div>
                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>Force Upd</span>
                        <span className={styles.clientInfoValue}>
                          {c.force_update
                            ? <span style={{ color: "var(--yellow)" }}>⚠ forced</span>
                            : <span className={styles.muted}>—</span>
                          }
                        </span>
                      </div>
                      <div className={styles.clientInfoRow}>
                        <span className={styles.clientInfoLabel}>HWID (raw)</span>
                        <button
                          className={styles.keyCell}
                          onClick={() => copy(c.hwid, c.hwid + "_m")}
                          title="Tap to copy"
                        >
                          <code style={{ fontSize: 11, color: "var(--cyan)" }}>{hwidDisplay}</code>
                          <span className={styles.copyHint}>{copied === c.hwid + "_m" ? "✓" : "⎘"}</span>
                        </button>
                      </div>

                      {/* Action buttons */}
                      <div className={styles.clientItemActions}>
                        <button
                          className={`${styles.clientActionBtn} ${c.banned ? styles.activateBtn : styles.revokeBtn}`}
                          onClick={() => toggleBan(c)}
                          disabled={isBusy}
                        >
                          {isBusy && busy === c.hwid ? "…" : c.banned ? "✅ Unban" : "⛔ Ban"}
                        </button>
                        <button
                          className={`${styles.clientActionBtn} ${c.force_update ? styles.activateBtn : styles.editBtn}`}
                          onClick={() => toggleForceUpdate(c)}
                          disabled={isBusy}
                        >
                          {isBusy && busy === c.hwid + "_fu" ? "…" : c.force_update ? "✅ Remove Force" : "⬆ Force Update"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* ── Desktop table (>700px) ────────────────────────────────────── */}
          <div className={`${styles.tableWrap} ${styles.clientsDesktopOnly}`}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>HWID</th>
                  <th>Last Seen</th>
                  <th>Version</th>
                  <th>IP</th>
                  <th>License (DB)</th>
                  <th>Local</th>
                  <th>Banned</th>
                  <th>Force Upd</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {clients.map(c => {
                  const isBusy      = busy === c.hwid || busy === c.hwid + "_fu";
                  const ago         = fmtAgo(c.last_seen);
                  const isOnline    = Date.now() - new Date(c.last_seen).getTime() < 20 * 60 * 1000;
                  const hwidDisplay = [c.hwid.slice(0,4), c.hwid.slice(4,8), c.hwid.slice(8,12), c.hwid.slice(12,16)].join("-");

                  return (
                    <tr key={c.hwid} className={c.banned ? styles.row_revoked : ""}>
                      <td>
                        <button
                          className={styles.keyCell}
                          onClick={() => copy(c.hwid, c.hwid)}
                          title="Click to copy raw HWID"
                        >
                          <code style={{ fontSize: 11 }}>{hwidDisplay}</code>
                          <span className={styles.copyHint}>{copied === c.hwid ? "✓" : "⎘"}</span>
                        </button>
                      </td>
                      <td>
                        <span style={{ fontSize: 12, color: isOnline ? "var(--green)" : "var(--text-muted)" }}>
                          {isOnline ? "🟢 " : ""}{ago}
                        </span>
                      </td>
                      <td><span className={styles.muted}>{c.app_version ?? "—"}</span></td>
                      <td><span className={styles.muted} style={{ fontSize: 11 }}>{c.public_ip ?? "—"}</span></td>
                      <td>
                        {(c.licensed_db || c.licensed_local) ? (
                          <span className={styles.status_active}>✓ {c.license_db_plan ?? "active"}</span>
                        ) : (
                          <span className={styles.status_expired}>✗ none</span>
                        )}
                      </td>
                      <td>
                        {c.licensed_local
                          ? <span className={styles.status_active}>✓</span>
                          : <span className={styles.muted}>—</span>
                        }
                      </td>
                      <td>
                        {c.banned
                          ? <span className={styles.status_revoked} title={c.ban_reason ?? ""}>⛔ banned</span>
                          : <span className={styles.muted}>—</span>
                        }
                      </td>
                      <td>
                        {c.force_update
                          ? <span style={{ color: "var(--yellow)", fontSize: 12 }}>⚠ forced</span>
                          : <span className={styles.muted}>—</span>
                        }
                      </td>
                      <td>
                        <div className={styles.actions}>
                          <button
                            className={`${styles.actionBtn} ${c.banned ? styles.activateBtn : styles.revokeBtn}`}
                            onClick={() => toggleBan(c)}
                            title={c.banned ? "Unban" : "Ban"}
                            disabled={isBusy}
                          >
                            {isBusy && busy === c.hwid ? "…" : c.banned ? "✅" : "⛔"}
                          </button>
                          <button
                            className={`${styles.actionBtn} ${c.force_update ? styles.activateBtn : styles.editBtn}`}
                            onClick={() => toggleForceUpdate(c)}
                            title={c.force_update ? "Remove force update" : "Force update"}
                            disabled={isBusy}
                          >
                            {isBusy && busy === c.hwid + "_fu" ? "…" : "⬆"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

// ─── Trial Settings Card ──────────────────────────────────────────────────────
function TrialCard() {
  const [days,   setDays]   = useState<number>(1);
  const [loaded, setLoaded] = useState(false);
  const [busy,   setBusy]   = useState(false);
  const [msg,    setMsg]    = useState("");

  useEffect(() => {
    createClient()
      .from("site_settings")
      .select("value")
      .eq("key", "trial")
      .single()
      .then(({ data }) => {
        if (data?.value) {
          const d = (data.value as any).days;
          if (typeof d === "number" && d >= 1) setDays(Math.round(d));
        }
        setLoaded(true);
      });
  }, []);

  async function save() {
    const d = Math.max(1, Math.min(365, Math.round(days) || 1));
    setDays(d);
    setBusy(true); setMsg("");
    await saveSetting("trial", { days: d });
    setBusy(false); setMsg("Saved!"); setTimeout(() => setMsg(""), 2500);
  }

  const label = days === 1 ? "24-hour trial (1 day)" : `${days}-day trial`;

  return (
    <div className={styles.settingCard}>
      <h2 className={styles.cardTitle}>
        <span className={styles.cardTitleIcon}>⏱</span> Free Trial Settings
      </h2>

      {!loaded ? (
        <p className={styles.muted}>Loading…</p>
      ) : (
        <>
          <div className={styles.fieldGroup}>
            <label className={styles.label}>Trial Duration (days)</label>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <input
                className={styles.input}
                type="number"
                min={1}
                max={365}
                value={days}
                onChange={e => setDays(Math.max(1, Math.min(365, parseInt(e.target.value) || 1)))}
                style={{ maxWidth: 100, fontFamily: "monospace" }}
              />
              <span style={{ fontSize: 13, color: "var(--text-dim)" }}>
                → <strong style={{ color: "var(--cyan)" }}>{label}</strong>
              </span>
            </div>
            <p className={styles.inputHint}>
              Number of free trial days granted when a new user runs the app for the first time.<br />
              Displayed on the website (Download &amp; Pricing sections) and read by the app at startup via Supabase.<br />
              <strong>Note:</strong> changing this only affects new trials — existing trial windows are not extended.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 8 }}>
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
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ─── Nav definition ───────────────────────────────────────────────────────────
type Tab = "generate" | "licenses" | "clients" | "trial";

const NAV: { id: Tab; icon: string; label: string; dividerBefore?: boolean }[] = [
  { id: "generate", icon: "🔑", label: "Generate"       },
  { id: "licenses", icon: "📋", label: "Licenses"       },
  { id: "clients",  icon: "📡", label: "Active Clients" },
  { id: "trial",    icon: "⏱",  label: "Trial Settings", dividerBefore: true },
];

// ─── Main Export ──────────────────────────────────────────────────────────────
export default function LicenseManager({
  initialLicenses,
  onLicensesChange,
}: {
  initialLicenses: License[];
  onLicensesChange: (lics: License[]) => void;
}) {
  const [licenses, setLicenses] = useState(initialLicenses);
  const [tab,      setTab]      = useState<Tab>("generate");
  const [menuOpen, setMenuOpen] = useState(false);

  function update(l: License[]) { setLicenses(l); onLicensesChange(l); }

  function navigate(t: Tab) {
    setTab(t);
    setMenuOpen(false);
  }

  const handleGenerated = useCallback((lic: License) => {
    update([lic, ...licenses]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [licenses]);

  const handleUpdate = useCallback((updated: License) => {
    update(licenses.map(l => l.id === updated.id ? updated : l));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [licenses]);

  const handleDelete = useCallback((id: string) => {
    update(licenses.filter(l => l.id !== id));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [licenses]);

  const stats = useMemo(() => {
    const active   = licenses.filter(l => l.status === "active" && !isExpired(l)).length;
    const revoked  = licenses.filter(l => l.status === "revoked").length;
    const expired  = licenses.filter(l => l.status === "active" && isExpired(l)).length;
    const floating = licenses.filter(l => !l.user_id).length;
    return { active, revoked, expired, floating };
  }, [licenses]);

  const activeLabel = NAV.find(n => n.id === tab)?.label ?? "License Manager";

  return (
    <main className={styles.main}>
      <div className={styles.container}>

        {/* ── Mobile top bar ──────────────────────────────────────────────── */}
        <div className={styles.mobileTopBar}>
          <button
            className={styles.hamburgerBtn}
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
          >
            <div className={styles.hamburgerIcon}>
              <span /><span /><span />
            </div>
          </button>
          <span className={styles.mobilePageTitle}>{activeLabel}</span>
        </div>

        {/* ── Sidebar overlay ─────────────────────────────────────────────── */}
        {menuOpen && (
          <div className={styles.overlay} onClick={() => setMenuOpen(false)} />
        )}

        {/* ── Layout ──────────────────────────────────────────────────────── */}
        <div className={styles.layout}>

          {/* Sidebar */}
          <aside className={`${styles.sidebar} ${menuOpen ? styles.sidebarOpen : ""}`}>
            <div className={styles.sidebarTop}>
              <span className={styles.sidebarTitle}>License Manager</span>
              <button
                className={styles.sidebarClose}
                onClick={() => setMenuOpen(false)}
                aria-label="Close menu"
              >
                ✕
              </button>
            </div>

            {/* Mini stats */}
            <div className={styles.sidebarStats}>
              <div className={styles.ssItem}>
                <span className={styles.ssNum}>{stats.active}</span>
                <span className={styles.ssLabel}>Active</span>
              </div>
              <div className={styles.ssItem}>
                <span className={`${styles.ssNum} ${styles.ssRed}`}>{stats.revoked}</span>
                <span className={styles.ssLabel}>Revoked</span>
              </div>
              <div className={styles.ssItem}>
                <span className={`${styles.ssNum} ${styles.ssYellow}`}>{stats.expired}</span>
                <span className={styles.ssLabel}>Expired</span>
              </div>
              <div className={styles.ssItem}>
                <span className={`${styles.ssNum} ${styles.ssMuted}`}>{stats.floating}</span>
                <span className={styles.ssLabel}>Float</span>
              </div>
            </div>

            {/* Nav */}
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
                    {n.id === "licenses" && (
                      <span className={styles.navBadge}>{licenses.length}</span>
                    )}
                  </button>
                </React.Fragment>
              ))}
            </nav>
          </aside>

          {/* Content */}
          <div className={styles.content}>
            {/* Page header (desktop only) */}
            <div className={styles.pageHead}>
              <div>
                <h1 className={styles.pageTitle}>{activeLabel}</h1>
                <p className={styles.pageRoute}>/akimxiu — PO1 · HMAC-SHA256 · Supabase</p>
              </div>
            </div>

            {tab === "generate" && (
              <GenerateForm
                onGenerated={lic => { handleGenerated(lic); navigate("licenses"); }}
              />
            )}
            {tab === "licenses" && (
              <LicenseTable
                licenses={licenses}
                onUpdate={handleUpdate}
                onDelete={handleDelete}
              />
            )}
            {tab === "clients" && <ClientsTab />}
            {tab === "trial"   && <TrialCard />}
          </div>
        </div>
      </div>
    </main>
  );
}
