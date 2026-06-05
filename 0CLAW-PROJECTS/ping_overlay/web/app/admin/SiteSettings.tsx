"use client";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { SiteSetting } from "@/lib/supabase/types";
import type { TimeSlot, SectionId } from "@/lib/use-site-settings";
import { ALL_SECTION_IDS } from "@/lib/use-site-settings";
import styles from "./admin.module.css";
import hoursStyles from "./hours-settings.module.css";
import AuthSettings from "./AuthSettings";

type Props = { settings: SiteSetting[] };

function pad2(n: number) { return String(n).padStart(2, "0"); }
function clamp(v: number, lo: number, hi: number) { return Math.min(hi, Math.max(lo, v)); }
function newId() { return Math.random().toString(36).slice(2, 10); }

async function saveSetting(key: string, value: Record<string, any>): Promise<string | null> {
  const { error } = await createClient().from("site_settings")
    .upsert({ key, value, updated_at: new Date().toISOString() }, { onConflict: "key" });
  return error ? error.message : null;
}

// ── General Card ─────────────────────────────────────────────────────────────
function GeneralCard({ initial }: { initial: Record<string, any> }) {
  const [discord,           setDiscord]           = useState<string> (initial.discord_url        ?? "https://discord.gg/zeroclaw");
  const [copyright,         setCopyright]         = useState<string> (initial.copyright          ?? "WWM Overlay. All rights reserved.");
  const [showVisitorStats,  setShowVisitorStats]  = useState<boolean>(initial.show_visitor_stats ?? true);
  const [busy, setBusy] = useState(false);
  const [msg,  setMsg]  = useState("");

  async function save() {
    setBusy(true); setMsg("");
    const err = await saveSetting("general", { discord_url: discord, copyright, show_visitor_stats: showVisitorStats });
    setBusy(false);
    if (err) { setMsg("Error: " + err); return; }
    setMsg("Saved!"); setTimeout(() => setMsg(""), 2000);
  }

  return (
    <div className={styles.settingCard}>
      <h3 className={styles.settingCardTitle}>General</h3>

      <div className={styles.formGroup}>
        <label className={styles.formLabel}>Discord Invite URL</label>
        <input className={styles.input} value={discord} onChange={e => setDiscord(e.target.value)} placeholder="https://discord.gg/..." />
        <p className={styles.inputHint}>Applied to all Discord links on the site (footer, download, pricing note, etc.)</p>
      </div>

      <div className={styles.formGroup}>
        <label className={styles.formLabel}>Copyright Text</label>
        <input className={styles.input} value={copyright} onChange={e => setCopyright(e.target.value)} placeholder="My Company. All rights reserved." />
        <p className={styles.inputHint}>Displayed as: © {new Date().getFullYear()} {copyright || "..."}</p>
      </div>

      {/* ── Visitor Stats toggle ──────────────────────────────────────────────── */}
      <div className={styles.formGroup}>
        <label className={styles.formLabel}>Visitor Stats (Homepage)</label>
        <label className={styles.toggleRow}>
          <div
            className={`${styles.toggle} ${showVisitorStats ? styles.toggleOn : ""}`}
            onClick={() => setShowVisitorStats(v => !v)}
            role="switch"
            aria-checked={showVisitorStats}
            tabIndex={0}
            onKeyDown={e => e.key === " " && setShowVisitorStats(v => !v)}
          >
            <div className={styles.toggleThumb} />
          </div>
          <span className={styles.toggleLabel}>
            {showVisitorStats ? "Visible" : "Hidden"} — "Players Around the World" section
          </span>
        </label>
        <p className={styles.inputHint}>Toggle the live visitor globe &amp; country stats block on the homepage.</p>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 4 }}>
        {msg && <span style={{ fontSize: 13, color: msg.startsWith("Error") ? "var(--red)" : "var(--green)" }}>{msg}</span>}
        <button className="btn btn-primary" style={{ marginLeft: "auto" }} onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
    </div>
  );
}

// ── Hours Card (multi-slot) ───────────────────────────────────────────────────
function parseSlots(raw: Record<string, any>): TimeSlot[] {
  if (Array.isArray(raw.slots) && raw.slots.length) return raw.slots as TimeSlot[];
  // migrate old single-slot
  if (raw.start_h !== undefined) {
    return [{ id: newId(), label: "", start_h: raw.start_h, start_m: raw.start_m, end_h: raw.end_h, end_m: raw.end_m }];
  }
  return [{ id: newId(), label: "", start_h: 2, start_m: 0, end_h: 17, end_m: 30 }];
}

function SlotRow({ slot, onChange, onDelete, canDelete }: {
  slot: TimeSlot;
  onChange: (s: TimeSlot) => void;
  onDelete: () => void;
  canDelete: boolean;
}) {
  const tStyle: React.CSSProperties = { width: 64, textAlign: "center", fontFamily: "monospace", fontSize: 15 };

  function setNum(field: keyof TimeSlot, max: number, v: string) {
    onChange({ ...slot, [field]: clamp(parseInt(v) || 0, 0, max) });
  }

  return (
    <div className={hoursStyles.slotRow}>
      {/* Label */}
      <input
        className={`${styles.input} ${hoursStyles.labelInput}`}
        value={slot.label}
        onChange={e => onChange({ ...slot, label: e.target.value })}
        placeholder="Label (e.g. Morning)"
      />
      {/* Start */}
      <div className={hoursStyles.timeGroup}>
        <input className={styles.input} type="number" min={0} max={23} value={pad2(slot.start_h)} style={tStyle}
          onChange={e => setNum("start_h", 23, e.target.value)} />
        <span className={hoursStyles.colon}>:</span>
        <input className={styles.input} type="number" min={0} max={59} value={pad2(slot.start_m)} style={tStyle}
          onChange={e => setNum("start_m", 59, e.target.value)} />
      </div>
      <span className={hoursStyles.dash}>–</span>
      {/* End */}
      <div className={hoursStyles.timeGroup}>
        <input className={styles.input} type="number" min={0} max={23} value={pad2(slot.end_h)} style={tStyle}
          onChange={e => setNum("end_h", 23, e.target.value)} />
        <span className={hoursStyles.colon}>:</span>
        <input className={styles.input} type="number" min={0} max={59} value={pad2(slot.end_m)} style={tStyle}
          onChange={e => setNum("end_m", 59, e.target.value)} />
      </div>
      <span className={hoursStyles.tzBadge}>VN</span>
      {/* Delete */}
      {canDelete && (
        <button className={hoursStyles.deleteBtn} onClick={onDelete} title="Remove slot">✕</button>
      )}
    </div>
  );
}

function HoursCard({ initial }: { initial: Record<string, any> }) {
  const [is24_7, setIs24_7] = useState<boolean>(initial.is_24_7 === true);
  const [slots,  setSlots]  = useState<TimeSlot[]>(parseSlots(initial));
  const [busy,   setBusy]   = useState(false);
  const [msg,    setMsg]    = useState("");

  async function save() {
    setBusy(true); setMsg("");
    const err = await saveSetting("business_hours", { is_24_7: is24_7, slots });
    setBusy(false);
    if (err) { setMsg("Error: " + err); return; }
    setMsg("Saved!"); setTimeout(() => setMsg(""), 2000);
  }

  function updateSlot(id: string, updated: TimeSlot) {
    setSlots(prev => prev.map(s => s.id === id ? updated : s));
  }
  function removeSlot(id: string) {
    setSlots(prev => prev.filter(s => s.id !== id));
  }
  function addSlot() {
    setSlots(prev => [...prev, { id: newId(), label: "", start_h: 8, start_m: 0, end_h: 17, end_m: 0 }]);
  }

  return (
    <div className={styles.settingCard}>
      <h3 className={styles.settingCardTitle}>
        Support Hours
        <span style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 400, marginLeft: 8 }}>Vietnam time (GMT+7) · Every day</span>
      </h3>

      {/* ── 24/7 toggle ────────────────────────────────────────────────────── */}
      <div className={styles.formGroup}>
        <label className={styles.formLabel}>24/7 Mode</label>
        <label className={styles.toggleRow}>
          <div
            className={`${styles.toggle} ${is24_7 ? styles.toggleOn : ""}`}
            onClick={() => setIs24_7(v => !v)}
            role="switch"
            aria-checked={is24_7}
            tabIndex={0}
            onKeyDown={e => e.key === " " && setIs24_7(v => !v)}
          >
            <div className={styles.toggleThumb} />
          </div>
          <span className={styles.toggleLabel}>
            {is24_7
              ? <><strong style={{ color: "var(--cyan)" }}>24/7 Active</strong> — always shown as online, time slots ignored</>
              : "Disabled — use custom time slots below"}
          </span>
        </label>
        <p className={styles.inputHint}>
          When enabled, the website shows "Always online · 24/7" and hides the time window display.
        </p>
      </div>

      {/* ── Time slots (shown only when not 24/7) ─────────────────────────── */}
      {!is24_7 && (
        <>
          <div className={hoursStyles.slotList}>
            {slots.map(s => (
              <SlotRow
                key={s.id}
                slot={s}
                onChange={updated => updateSlot(s.id, updated)}
                onDelete={() => removeSlot(s.id)}
                canDelete={slots.length > 1}
              />
            ))}
          </div>
          <button className={`btn btn-ghost ${hoursStyles.addBtn}`} onClick={addSlot}>+ Add Time Slot</button>
          <p className={styles.inputHint}>Multiple slots: user is shown "online" if current VN time is within any active slot.</p>
        </>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
        {msg && <span style={{ fontSize: 13, color: msg.startsWith("Error") ? "var(--red)" : "var(--green)" }}>{msg}</span>}
        <button className="btn btn-primary" style={{ marginLeft: "auto" }} onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
    </div>
  );
}

// ── Download Card ─────────────────────────────────────────────────────────────
function DownloadCard({ initial }: { initial: Record<string, any> }) {
  const [url,     setUrl]     = useState<string>(initial.url     ?? "");
  const [version, setVersion] = useState<string>(initial.version ?? "");
  const [busy, setBusy] = useState(false);
  const [msg,  setMsg]  = useState("");

  async function save() {
    setBusy(true); setMsg("");
    const err = await saveSetting("download", { url, version });
    setBusy(false);
    if (err) { setMsg("Error: " + err); return; }
    setMsg("Saved!"); setTimeout(() => setMsg(""), 2000);
  }

  return (
    <div className={styles.settingCard}>
      <h3 className={styles.settingCardTitle}>Download</h3>
      <div className={styles.formGroup}>
        <label className={styles.formLabel}>Latest Version</label>
        <input className={styles.input} value={version} onChange={e => setVersion(e.target.value)} placeholder="1.0.27" style={{ maxWidth: 200 }} />
      </div>
      <div className={styles.formGroup}>
        <label className={styles.formLabel}>Download URL</label>
        <input className={styles.input} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://drive.google.com/..." />
        <p className={styles.inputHint}>Direct download link or Google Drive folder URL.</p>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 4 }}>
        {msg && <span style={{ fontSize: 13, color: msg.startsWith("Error") ? "var(--red)" : "var(--green)" }}>{msg}</span>}
        <button className="btn btn-primary" style={{ marginLeft: "auto" }} onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
    </div>
  );
}

// ── Referral Card ─────────────────────────────────────────────────────────────
function ReferralCard({ initial }: { initial: Record<string, any> }) {
  const [enabled,    setEnabled]    = useState<boolean>(initial.enabled             ?? true);
  const [perDl,      setPerDl]      = useState<number> (initial.points_per_download ?? 1);
  const [perPurch,   setPerPurch]   = useState<number> (initial.points_per_purchase ?? 10);
  const [forReward,  setForReward]  = useState<number> (initial.points_for_reward   ?? 50);
  const [rewardDays, setRewardDays] = useState<number> (initial.reward_days         ?? 30);
  const [busy, setBusy] = useState(false);
  const [msg,  setMsg]  = useState("");

  async function save() {
    setBusy(true); setMsg("");
    const err = await saveSetting("referral_config", {
      enabled, points_per_download: perDl, points_per_purchase: perPurch,
      points_for_reward: forReward, reward_days: rewardDays,
    });
    setBusy(false);
    if (err) { setMsg("Error: " + err); return; }
    setMsg("Saved!"); setTimeout(() => setMsg(""), 2000);
  }

  return (
    <div className={styles.settingCard}>
      <h3 className={styles.settingCardTitle}>Referral System</h3>

      <div className={styles.formGroup}>
        <label className={styles.formLabel}>Enable Referrals</label>
        <label className={styles.toggleRow}>
          <div
            className={`${styles.toggle} ${enabled ? styles.toggleOn : ""}`}
            onClick={() => setEnabled(v => !v)}
            role="switch" aria-checked={enabled} tabIndex={0}
            onKeyDown={e => e.key === " " && setEnabled(v => !v)}
          >
            <div className={styles.toggleThumb} />
          </div>
          <span className={styles.toggleLabel}>{enabled ? "Active" : "Disabled"}</span>
        </label>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Points per Download</label>
          <input className={styles.input} type="number" min={0} max={100} value={perDl}
            onChange={e => setPerDl(Number(e.target.value))} style={{ maxWidth: 120 }} />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Points per Purchase</label>
          <input className={styles.input} type="number" min={0} max={100} value={perPurch}
            onChange={e => setPerPurch(Number(e.target.value))} style={{ maxWidth: 120 }} />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Points Threshold for Free License</label>
          <input className={styles.input} type="number" min={1} max={9999} value={forReward}
            onChange={e => setForReward(Number(e.target.value))} style={{ maxWidth: 120 }} />
          <p className={styles.inputHint}>Referrer earns a free license when they reach this threshold.</p>
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Reward License Days</label>
          <input className={styles.input} type="number" min={1} max={365} value={rewardDays}
            onChange={e => setRewardDays(Number(e.target.value))} style={{ maxWidth: 120 }} />
          <p className={styles.inputHint}>Duration of the auto-granted reward license.</p>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 4 }}>
        {msg && <span style={{ fontSize: 13, color: msg.startsWith("Error") ? "var(--red)" : "var(--green)" }}>{msg}</span>}
        <button className="btn btn-primary" style={{ marginLeft: "auto" }} onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
    </div>
  );
}

// ── Section Order Card ────────────────────────────────────────────────────────
const SECTION_META: Record<SectionId, { label: string; icon: string }> = {
  features:        { label: "Features",        icon: "✨" },
  demo:            { label: "Demo",            icon: "🎬" },
  reforge:         { label: "Reforge Tracker", icon: "⚔️" },
  pricing:         { label: "Pricing",         icon: "💰" },
  download:        { label: "Download",        icon: "⬇️" },
  referral_banner: { label: "Referral Banner", icon: "🎁" },
  visitor_stats:   { label: "Visitor Stats",   icon: "🌍" },
  faq:             { label: "FAQ",             icon: "❓" },
  support_hours:   { label: "Support Hours",   icon: "🕐" },
};

function SectionOrderCard({ initial }: { initial: Record<string, any> }) {
  const savedOrder  = Array.isArray(initial.order)  ? initial.order  as SectionId[] : ALL_SECTION_IDS;
  const savedHidden = Array.isArray(initial.hidden) ? initial.hidden as SectionId[] : [];
  const missing     = ALL_SECTION_IDS.filter(id => !savedOrder.includes(id));

  const [order,  setOrder]  = useState<SectionId[]>([...savedOrder, ...missing]);
  const [hidden, setHidden] = useState<SectionId[]>(savedHidden);
  const [busy,   setBusy]   = useState(false);
  const [msg,    setMsg]    = useState("");

  async function save() {
    setBusy(true); setMsg("");
    const err = await saveSetting("section_order", { order, hidden });
    setBusy(false);
    if (err) { setMsg("Error: " + err); return; }
    setMsg("Saved!"); setTimeout(() => setMsg(""), 2000);
  }

  function move(idx: number, dir: -1 | 1) {
    const next = idx + dir;
    if (next < 0 || next >= order.length) return;
    setOrder(prev => {
      const arr = [...prev];
      [arr[idx], arr[next]] = [arr[next], arr[idx]];
      return arr;
    });
  }

  function toggleHidden(id: SectionId) {
    setHidden(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  }

  const btnBase: React.CSSProperties = {
    background: "none", border: "1px solid var(--border-2)", borderRadius: 6,
    width: 28, height: 28, cursor: "pointer",
    color: "var(--text-dim)", fontSize: 12,
    display: "flex", alignItems: "center", justifyContent: "center",
    flexShrink: 0, transition: "color .12s, border-color .12s",
  };

  return (
    <div className={styles.settingCard}>
      <h3 className={styles.settingCardTitle}>Homepage Sections</h3>
      <p className={styles.inputHint} style={{ marginBottom: 16 }}>
        Reorder or hide sections on the homepage. <strong>Hero</strong> is always first and cannot be moved.
      </p>

      {/* Hero — fixed */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "10px 14px",
        background: "var(--bg-1)", border: "1px solid var(--border)",
        borderRadius: 10, marginBottom: 6, opacity: 0.45,
      }}>
        <span style={{ color: "var(--border-2)", fontSize: 14 }}>⠿</span>
        <span style={{ fontSize: 16 }}>🦸</span>
        <span style={{ fontSize: 14, fontWeight: 600, flex: 1, color: "var(--text-muted)" }}>Hero</span>
        <span style={{ fontSize: 11, color: "var(--text-muted)", padding: "2px 8px", border: "1px solid var(--border)", borderRadius: 20 }}>Fixed · Always first</span>
      </div>

      {order.map((id, idx) => {
        const meta     = SECTION_META[id];
        const isHidden = hidden.includes(id);

        return (
          <div key={id} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "10px 14px",
            background: isHidden ? "transparent" : "var(--surface)",
            border: `1px solid ${isHidden ? "var(--border)" : "var(--border-2)"}`,
            borderRadius: 10, marginBottom: 6,
            opacity: isHidden ? 0.45 : 1,
            transition: "opacity .15s, background .15s",
          }}>
            <span style={{ color: "var(--border-2)", fontSize: 14, userSelect: "none", flexShrink: 0 }}>⠿</span>
            <span style={{ fontSize: 16, flexShrink: 0 }}>{meta?.icon}</span>
            <span style={{
              fontSize: 14, fontWeight: 600, flex: 1,
              color: isHidden ? "var(--text-muted)" : "var(--text)",
              textDecoration: isHidden ? "line-through" : "none",
            }}>
              {meta?.label ?? id}
            </span>

            {/* Visibility toggle */}
            <button
              onClick={() => toggleHidden(id)}
              title={isHidden ? "Show" : "Hide"}
              style={{
                background: "none", border: "none", cursor: "pointer",
                fontSize: 13, padding: "3px 8px",
                color: isHidden ? "var(--text-muted)" : "var(--cyan)",
                borderRadius: 6, display: "flex", alignItems: "center", gap: 4,
              }}
            >
              {isHidden
                ? <><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19M1 1l22 22"/></svg> Hidden</>
                : <><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg> Visible</>
              }
            </button>

            {/* Up / Down */}
            <button
              onClick={() => move(idx, -1)}
              disabled={idx === 0}
              style={{ ...btnBase, opacity: idx === 0 ? 0.3 : 1, cursor: idx === 0 ? "not-allowed" : "pointer" }}
              title="Move up"
            >▲</button>
            <button
              onClick={() => move(idx, 1)}
              disabled={idx === order.length - 1}
              style={{ ...btnBase, opacity: idx === order.length - 1 ? 0.3 : 1, cursor: idx === order.length - 1 ? "not-allowed" : "pointer" }}
              title="Move down"
            >▼</button>
          </div>
        );
      })}

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
        {msg && <span style={{ fontSize: 13, color: msg.startsWith("Error") ? "var(--red)" : "var(--green)" }}>{msg}</span>}
        <button className="btn btn-ghost" style={{ fontSize: 13 }} onClick={() => { setOrder(ALL_SECTION_IDS); setHidden([]); }} disabled={busy}>Reset</button>
        <button className="btn btn-primary" style={{ marginLeft: "auto" }} onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function SiteSettings({ settings }: Props) {
  function getVal(key: string) {
    return settings.find(s => s.key === key)?.value ?? {};
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <GeneralCard       initial={getVal("general")} />
      <SectionOrderCard  initial={getVal("section_order")} />
      <HoursCard         initial={getVal("business_hours")} />
      <DownloadCard      initial={getVal("download")} />
      <AuthSettings      initial={getVal("auth_providers")} />
      <ReferralCard      initial={getVal("referral_config")} />
    </div>
  );
}
