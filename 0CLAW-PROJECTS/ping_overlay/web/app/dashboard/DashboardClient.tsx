"use client";
import { useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import { useReferralConfig } from "@/lib/use-site-settings";
import type { License, Notification, Order, Profile, ReferralEvent } from "@/lib/supabase/types";
import styles from "./dashboard.module.css";

type Props = {
  user: { email: string; id: string };
  licenses: License[];
  orders: Order[];
  profile: Pick<Profile, "full_name" | "avatar_url" | "referral_code" | "referral_points" | "created_at"> | null;
  notifications: Notification[];
  refEvents: ReferralEvent[];
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

type Lang = "en" | "vi";

function timeAgo(iso: string, lang: Lang): string {
  const d = T.dashboard.timeAgo;
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60)    return d.justNow[lang];
  if (diff < 3600)  return `${Math.floor(diff / 60)} ${d.mAgo[lang]}`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ${d.hAgo[lang]}`;
  return `${Math.floor(diff / 86400)} ${d.dAgo[lang]}`;
}

function licenseStatus(lic: License, lang: Lang) {
  const ls = T.dashboard.licenses;
  if (lic.status === "revoked") return { label: ls.statusRevoked[lang], cls: styles.statusRevoked };
  if (lic.expires_at && new Date(lic.expires_at) < new Date()) return { label: ls.statusExpired[lang], cls: styles.statusExpired };
  if (lic.status === "active") return { label: ls.statusActive[lang], cls: styles.statusActive };
  return { label: lic.status, cls: "" };
}

function daysLeft(expires_at: string | null, lang: Lang) {
  const ls = T.dashboard.licenses;
  if (!expires_at) return ls.lifetime[lang];
  const diff = Math.ceil((new Date(expires_at).getTime() - Date.now()) / 86_400_000);
  if (diff <= 0) return ls.expired[lang];
  return `${diff} ${ls.daysLeft[lang]}`;
}

function copyText(text: string, setCopied: (v: boolean) => void) {
  navigator.clipboard.writeText(text).then(() => {
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  });
}

// ── Avatar ────────────────────────────────────────────────────────────────────
function Avatar({ url, name, size = 64 }: { url: string | null; name: string | null; size?: number }) {
  const initials = (name ?? "?").split(" ").map(w => w[0] ?? "").join("").slice(0, 2).toUpperCase();
  if (url) return <img src={url} alt={name ?? "avatar"} className={styles.avatarImg} style={{ width: size, height: size }} />;
  return <div className={styles.avatarInitials} style={{ width: size, height: size, fontSize: size * 0.38 }}>{initials}</div>;
}

// ── Inbox tab ─────────────────────────────────────────────────────────────────
const TYPE_ICON: Record<string, string> = { license: "🔑", referral: "🎁", system: "📢" };

function InboxTab({ userId, initial }: { userId: string; initial: Notification[] }) {
  const { lang } = useLanguage();
  const ib = T.dashboard.inbox;
  const [notifs, setNotifs] = useState<Notification[]>(initial);

  async function markRead(id: string) {
    setNotifs(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
    await createClient().from("notifications").update({ read: true }).eq("id", id);
  }

  async function markAllRead() {
    setNotifs(prev => prev.map(n => ({ ...n, read: true })));
    const ids = notifs.filter(n => !n.read).map(n => n.id);
    if (ids.length) await createClient().from("notifications").update({ read: true }).in("id", ids);
  }

  const unread = notifs.filter(n => !n.read).length;
  const countLabel = notifs.length === 1 ? ib.notification[lang] : ib.notifications[lang];

  return (
    <div className={styles.panel}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <span style={{ fontSize: 14, color: "var(--text-muted)" }}>
          {notifs.length} {countLabel}{unread > 0 ? ` · ${unread} ${ib.unread[lang]}` : ""}
        </span>
        {unread > 0 && (
          <button className="btn btn-ghost" style={{ fontSize: 13 }} onClick={markAllRead}>{ib.markAllRead[lang]}</button>
        )}
      </div>

      {notifs.length === 0 ? (
        <div className={styles.empty}><p>{ib.empty[lang]}</p></div>
      ) : (
        <div className={styles.notifList}>
          {notifs.map(n => (
            <div
              key={n.id}
              className={`${styles.notifItem} ${!n.read ? styles.notifUnread : ""}`}
              onClick={() => markRead(n.id)}
            >
              <span className={styles.notifIcon}>{TYPE_ICON[n.type] ?? "📢"}</span>
              <div className={styles.notifBody}>
                <div className={styles.notifTitle}>{n.title}</div>
                <div className={styles.notifText}>{n.body}</div>
                <div className={styles.notifTime}>{timeAgo(n.created_at, lang)}</div>
              </div>
              {!n.read && <span className={styles.notifDot} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Referral tab ──────────────────────────────────────────────────────────────
function ReferralTab({ profile, refEvents }: {
  profile: Pick<Profile, "referral_code" | "referral_points"> | null;
  refEvents: ReferralEvent[];
}) {
  const { lang }    = useLanguage();
  const refConfig   = useReferralConfig();
  const forReward   = refConfig.points_for_reward;
  const rewardDays  = refConfig.reward_days;
  const r = T.dashboard.referral;
  const [copiedCode, setCopiedCode] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedMsg,  setCopiedMsg]  = useState(false);

  const code    = profile?.referral_code ?? null;
  const points  = profile?.referral_points ?? 0;
  const siteUrl = typeof window !== "undefined" ? window.location.origin : "https://zeroclaw.com";
  const refLink = code ? `${siteUrl}/ref?code=${code}` : null;

  const downloadEvents = refEvents.filter(e => e.event_type === "download").length;
  const purchaseEvents = refEvents.filter(e => e.event_type === "purchase").length;

  const MSG_VI = `🎮 Đang chơi Where Winds Meet? Tải WWM Overlay – overlay tốt nhất!\n⚡ Ping, quest, events real-time chính xác.\n🔗 ${refLink}\n✨ Dùng mã ${code} để ủng hộ mình nhé!`;
  const MSG_EN = `🎮 Playing Where Winds Meet? Try WWM Overlay – the best in-game overlay!\n⚡ Real-time ping, quest tracker & event monitor. Free trial included.\n🔗 ${refLink}\n✨ Use code ${code} to support me!`;
  const shareMsg = lang === "en" ? MSG_EN : MSG_VI;

  return (
    <div className={styles.accountWrap}>
      {/* Referral code card */}
      <div className={styles.accountCard}>
        <h3 className={styles.accountCardTitle}>{r.codeTitle[lang]}</h3>
        <p className={styles.accountCardSub}>{r.codeSub[lang]}</p>

        {code ? (
          <>
            <div className={styles.refCodeBox}>
              <code className={styles.refCode}>{code}</code>
              <button
                className={`btn btn-ghost ${styles.copyCodeBtn}`}
                onClick={() => copyText(code, setCopiedCode)}
                title={r.copyCode[lang]}
              >
                {copiedCode ? r.copied[lang] : r.copyCode[lang]}
              </button>
            </div>

            <div className={styles.accountField} style={{ marginTop: 16 }}>
              <label className={styles.accountLabel}>{r.linkLabel[lang]}</label>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  className={`${styles.accountInput} ${styles.accountInputReadonly}`}
                  value={refLink ?? ""}
                  readOnly
                  style={{ flex: 1 }}
                />
                <button
                  className="btn btn-primary"
                  style={{ flexShrink: 0 }}
                  onClick={() => copyText(refLink ?? "", setCopiedLink)}
                >
                  {copiedLink ? r.copiedLink[lang] : r.copyLink[lang]}
                </button>
              </div>
            </div>

            <div className={styles.accountField} style={{ marginTop: 8 }}>
              <label className={styles.accountLabel}>{r.msgLabel[lang]}</label>
              <textarea
                className={styles.msgTextarea}
                readOnly
                value={shareMsg}
              />
              <button
                className={styles.msgCopyBtn}
                onClick={() => copyText(shareMsg, setCopiedMsg)}
              >
                {copiedMsg ? r.copiedMsg[lang] : r.copyMsg[lang]}
              </button>
            </div>
          </>
        ) : (
          <div className={styles.empty} style={{ padding: "24px 0" }}>
            <p>{r.generating[lang]}</p>
          </div>
        )}
      </div>

      {/* Points card */}
      <div className={styles.accountCard}>
        <h3 className={styles.accountCardTitle}>{r.pointsTitle[lang]}</h3>

        <div className={styles.refStatsRow}>
          <div className={styles.refStat}>
            <span className={styles.refStatNum}>{points}</span>
            <span className={styles.refStatLabel}>{r.totalPoints[lang]}</span>
          </div>
          <div className={styles.refStat}>
            <span className={styles.refStatNum}>{downloadEvents}</span>
            <span className={styles.refStatLabel}>{r.downloads[lang]}</span>
          </div>
          <div className={styles.refStat}>
            <span className={styles.refStatNum}>{purchaseEvents}</span>
            <span className={styles.refStatLabel}>{r.purchases[lang]}</span>
          </div>
        </div>

        <div className={styles.refProgress}>
          <div className={styles.refProgressBar}>
            <div
              className={styles.refProgressFill}
              style={{ width: `${Math.min(100, (points / forReward) * 100)}%` }}
            />
          </div>
          <span className={styles.refProgressLabel}>{points} / {forReward} {r.progressLabel[lang]} {rewardDays}{r.progressDay[lang]}</span>
        </div>

        {refEvents.length > 0 && (
          <div style={{ marginTop: 20 }}>
            <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-dim)", marginBottom: 10 }}>{r.recentActivity[lang]}</p>
            <div className={styles.refEventList}>
              {refEvents.slice(0, 10).map(e => (
                <div key={e.id} className={styles.refEventRow}>
                  <span className={styles.refEventIcon}>{e.event_type === "purchase" ? "💳" : "⬇️"}</span>
                  <span className={styles.refEventLabel}>
                    {e.event_type === "purchase" ? r.purchaseRef[lang] : r.downloadRef[lang]}
                  </span>
                  <span className={styles.refEventPts}>+{e.points} {r.pts[lang]}</span>
                  <span className={styles.refEventTime}>{timeAgo(e.created_at, lang)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Two-Factor Authentication card ───────────────────────────────────────────
// Self-contained: lists factors, handles enroll + unenroll inline.
// Available to all users; required for admin access.
function TwoFactorCard() {
  type CardState = "loading" | "idle_off" | "idle_on" | "enrolling" | "confirming";
  const [cardState,  setCardState]  = useState<CardState>("loading");
  const [factors,    setFactors]    = useState<{ id: string; friendly_name: string }[]>([]);
  const [qrSvg,      setQrSvg]      = useState("");
  const [secret,     setSecret]     = useState("");
  const [factorId,   setFactorId]   = useState("");
  const [code,       setCode]       = useState("");
  const [busy,       setBusy]       = useState(false);
  const [msg,        setMsg]        = useState<{ text: string; ok: boolean } | null>(null);
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => { loadFactors(); }, []);
  useEffect(() => { if (cardState === "confirming") codeRef.current?.focus(); }, [cardState]);

  async function loadFactors() {
    const sb = createClient();
    const { data } = await sb.auth.mfa.listFactors();
    const totp = (data?.totp ?? []) as { id: string; friendly_name: string }[];
    setFactors(totp);
    setCardState(totp.length > 0 ? "idle_on" : "idle_off");
  }

  async function startEnroll() {
    setCardState("enrolling"); setBusy(true); setMsg(null);
    const sb = createClient();
    try {
      // Clean up unconfirmed factors before enrolling.
      // NOTE: listFactors().totp only returns VERIFIED factors;
      //       unverified/pending factors are in .all — use that instead.
      //       Cast status to string because TS types it as the literal "verified".
      const { data: existing } = await sb.auth.mfa.listFactors();
      for (const f of existing?.all ?? []) {
        if (f.factor_type === "totp" && (f.status as string) !== "verified") {
          await sb.auth.mfa.unenroll({ factorId: f.id });
        }
      }

      const { data, error } = await sb.auth.mfa.enroll({
        factorType: "totp",
        friendlyName: "Authenticator",
      });
      if (error || !data) throw error ?? new Error("Enrollment failed");

      // Set all state atomically — avoids intermediate render where QR is missing
      setQrSvg(data.totp.qr_code);
      setSecret(data.totp.secret);
      setFactorId(data.id);
      setCode("");
      setCardState("confirming"); // triggers focus effect on code input
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to start enrollment";
      setMsg({ text: msg, ok: false });
      setCardState("idle_off");
    } finally {
      setBusy(false); // always last — avoids spinner disappearing before QR mounts
    }
  }

  async function confirmEnroll() {
    if (code.length < 6) return;
    setBusy(true); setMsg(null);
    const sb = createClient();
    const { data: ch, error: chErr } = await sb.auth.mfa.challenge({ factorId });
    if (chErr || !ch) { setMsg({ text: chErr?.message ?? "Challenge failed", ok: false }); setBusy(false); return; }
    const { error } = await sb.auth.mfa.verify({ factorId, challengeId: ch.id, code });
    if (error) { setMsg({ text: error.message, ok: false }); setBusy(false); setCode(""); codeRef.current?.focus(); return; }
    setMsg({ text: "✓ 2FA activated successfully!", ok: true });
    await loadFactors();
    setBusy(false);
  }

  async function cancelEnroll() {
    // Unenroll the pending (unconfirmed) factor
    if (factorId) await createClient().auth.mfa.unenroll({ factorId });
    setQrSvg(""); setSecret(""); setFactorId(""); setCode("");
    setCardState("idle_off"); setMsg(null);
  }

  async function unenroll(id: string) {
    if (!confirm("Remove 2FA? You will need to re-enroll the next time you access admin.")) return;
    setBusy(true);
    await createClient().auth.mfa.unenroll({ factorId: id });
    setMsg({ text: "2FA removed.", ok: true });
    await loadFactors();
    setBusy(false);
  }

  return (
    <div className={styles.accountCard}>
      <h3 className={styles.accountCardTitle}>🔐 Two-Factor Authentication (2FA)</h3>
      <p className={styles.accountCardSub}>
        {cardState === "idle_on"
          ? "2FA is active. Admin panel access requires TOTP verification each session."
          : cardState === "loading"
          ? "Loading security status…"
          : "Add an extra layer of protection. Required for admin panel access."}
      </p>

      {/* Status badge */}
      {(cardState === "idle_on" || cardState === "idle_off") && (
        <div className={styles.twoFaStatus}>
          <span className={cardState === "idle_on" ? styles.twoFaBadgeOn : styles.twoFaBadgeOff}>
            {cardState === "idle_on" ? "✓ Enabled" : "○ Not enabled"}
          </span>
        </div>
      )}

      {/* Enrolled factors list */}
      {cardState === "idle_on" && factors.map(f => (
        <div key={f.id} className={styles.twoFaFactor}>
          <span className={styles.twoFaFactorName}>🔑 {f.friendly_name || "Authenticator"}</span>
          <button
            className={styles.twoFaRemoveBtn}
            onClick={() => unenroll(f.id)}
            disabled={busy}
          >
            Remove
          </button>
        </div>
      ))}

      {/* QR + confirm step */}
      {(cardState === "enrolling" || cardState === "confirming") && (
        <div className={styles.twoFaSetup}>
          {busy && cardState === "enrolling" && (
            <div style={{ textAlign: "center", padding: "20px 0" }}><div className="spinner" /></div>
          )}
          {cardState === "confirming" && (
            <>
              <p className={styles.twoFaStep}><strong>Step 1.</strong> Scan this QR code with your authenticator app.</p>
              {qrSvg && (
                /* qrSvg from Supabase is already a complete data: URI — use as img src directly */
                <div className={styles.twoFaQrWrap}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={qrSvg} alt="2FA QR Code" className={styles.twoFaQrImg} />
                </div>
              )}
              {secret && (
                <details style={{ marginBottom: 16 }}>
                  <summary style={{ fontSize: 12, color: "var(--cyan)", cursor: "pointer", userSelect: "none" }}>
                    Can&apos;t scan? Enter manually
                  </summary>
                  <code style={{ display: "block", marginTop: 6, fontSize: 12, wordBreak: "break-all", background: "var(--bg-2)", padding: "8px 10px", borderRadius: 6, letterSpacing: ".05em" }}>{secret}</code>
                </details>
              )}
              <p className={styles.twoFaStep}><strong>Step 2.</strong> Enter the 6-digit code from your app.</p>
              <input
                ref={codeRef}
                className={styles.twoFaCodeInput}
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                placeholder="000000"
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, ""))}
                onKeyDown={e => { if (e.key === "Enter") confirmEnroll(); }}
                disabled={busy}
                autoComplete="one-time-code"
              />
              <div className={styles.twoFaActions}>
                <button className="btn btn-primary" onClick={confirmEnroll} disabled={busy || code.length < 6}>
                  {busy ? "Activating…" : "Activate 2FA"}
                </button>
                <button className="btn btn-ghost" onClick={cancelEnroll} disabled={busy}>Cancel</button>
              </div>
            </>
          )}
        </div>
      )}

      {msg && (
        <p className={msg.ok ? styles.msgOk : styles.msgError} style={{ marginTop: 12 }}>{msg.text}</p>
      )}

      {/* CTA buttons for idle states */}
      {cardState === "idle_off" && (
        <div className={styles.accountActions} style={{ marginTop: 16 }}>
          <button className="btn btn-primary" onClick={startEnroll}>Set up 2FA</button>
        </div>
      )}

      {cardState === "loading" && (
        <div style={{ paddingTop: 16 }}><div className="spinner" /></div>
      )}
    </div>
  );
}

// ── My Account tab ────────────────────────────────────────────────────────────
function AccountTab({ user, profile }: {
  user: { email: string; id: string };
  profile: Pick<Profile, "full_name" | "avatar_url" | "created_at"> | null;
}) {
  const { lang } = useLanguage();
  const ac = T.dashboard.account;

  const [fullName,    setFullName]    = useState(profile?.full_name ?? "");
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileMsg,  setProfileMsg]  = useState("");

  const [newPass,   setNewPass]   = useState("");
  const [confPass,  setConfPass]  = useState("");
  const [passBusy,  setPassBusy]  = useState(false);
  const [passMsg,   setPassMsg]   = useState("");
  const [passIsErr, setPassIsErr] = useState(false);

  async function saveProfile() {
    setProfileBusy(true); setProfileMsg("");
    const { error } = await createClient().from("profiles").update({ full_name: fullName.trim() || null }).eq("id", user.id);
    setProfileBusy(false);
    if (error) { setProfileMsg("Error: " + error.message); return; }
    setProfileMsg(ac.saved[lang]); setTimeout(() => setProfileMsg(""), 2500);
  }

  function passError(msg: string) { setPassMsg(msg); setPassIsErr(true); }
  function passOk(msg: string)    { setPassMsg(msg); setPassIsErr(false); }

  async function changePassword() {
    if (!newPass) { passError(ac.errEmpty[lang]); return; }
    if (newPass.length < 8) { passError(ac.errShort[lang]); return; }
    if (newPass !== confPass) { passError(ac.errMatch[lang]); return; }
    setPassBusy(true); setPassMsg("");
    const { error } = await createClient().auth.updateUser({ password: newPass });
    setPassBusy(false);
    if (error) { passError(error.message); return; }
    setNewPass(""); setConfPass("");
    passOk(ac.passUpdated[lang]); setTimeout(() => setPassMsg(""), 2500);
  }

  return (
    <div className={styles.accountWrap}>
      <div className={styles.accountCard}>
        <h3 className={styles.accountCardTitle}>{ac.profileTitle[lang]}</h3>
        <div className={styles.profileRow}>
          <Avatar url={profile?.avatar_url ?? null} name={fullName || user.email} size={72} />
          <div className={styles.profileMeta}>
            <span className={styles.profileEmail}>{user.email}</span>
            {profile?.created_at && <span className={styles.profileJoined}>{ac.memberSince[lang]} {fmtDate(profile.created_at)}</span>}
          </div>
        </div>
        <div className={styles.accountField}>
          <label className={styles.accountLabel}>{ac.fullName[lang]}</label>
          <input className={styles.accountInput} type="text" placeholder={ac.namePlaceholder[lang]} value={fullName} onChange={e => setFullName(e.target.value)} disabled={profileBusy} autoComplete="name" />
        </div>
        <div className={styles.accountField}>
          <label className={styles.accountLabel}>{ac.emailLabel[lang]}</label>
          <input className={`${styles.accountInput} ${styles.accountInputReadonly}`} type="email" value={user.email} readOnly tabIndex={-1} />
          <p className={styles.accountHint}>{ac.emailHint[lang]}</p>
        </div>
        <div className={styles.accountActions}>
          {profileMsg && <span className={profileMsg.startsWith("Error") ? styles.msgError : styles.msgOk}>{profileMsg}</span>}
          <button className="btn btn-primary" onClick={saveProfile} disabled={profileBusy}>{profileBusy ? ac.saving[lang] : ac.saveChanges[lang]}</button>
        </div>
      </div>

      <div className={styles.accountCard}>
        <h3 className={styles.accountCardTitle}>{ac.passwordTitle[lang]}</h3>
        <p className={styles.accountCardSub}>{ac.passwordSub[lang]}</p>
        <div className={styles.accountField}>
          <label className={styles.accountLabel}>{ac.newPassword[lang]}</label>
          <input className={styles.accountInput} type="password" placeholder={ac.passPlaceholder[lang]} value={newPass} onChange={e => setNewPass(e.target.value)} disabled={passBusy} autoComplete="new-password" />
        </div>
        <div className={styles.accountField}>
          <label className={styles.accountLabel}>{ac.confirmPassword[lang]}</label>
          <input className={styles.accountInput} type="password" placeholder={ac.confirmPlaceholder[lang]} value={confPass} onChange={e => setConfPass(e.target.value)} disabled={passBusy} autoComplete="new-password" onKeyDown={e => { if (e.key === "Enter") changePassword(); }} />
        </div>
        <div className={styles.accountActions}>
          {passMsg && <span className={passIsErr ? styles.msgError : styles.msgOk}>{passMsg}</span>}
          <button className="btn btn-primary" onClick={changePassword} disabled={passBusy}>{passBusy ? ac.updating[lang] : ac.updatePassword[lang]}</button>
        </div>
      </div>

      {/* 2FA card — always shown, self-contained */}
      <TwoFactorCard />
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function DashboardClient({ user, licenses, orders, profile, notifications, refEvents }: Props) {
  const { lang } = useLanguage();
  const db = T.dashboard;

  const [tab,    setTab]    = useState<"licenses" | "orders" | "inbox" | "referral" | "account">("licenses");
  const [copied, setCopied] = useState("");

  const unread = notifications.filter(n => !n.read).length;

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        {/* Page header */}
        <div className={styles.pageHead}>
          <div>
            <h1 className={styles.pageTitle}>{db.title[lang]}</h1>
            <p className={styles.pageEmail}>{user.email}</p>
          </div>
          <a href="/#pricing" className="btn btn-primary">{db.buyLicense[lang]}</a>
        </div>

        {/* Stats row */}
        <div className={styles.stats}>
          <div className={styles.stat}>
            <span className={styles.statNum}>{licenses.filter(l => l.status === "active").length}</span>
            <span className={styles.statLabel}>{db.stats.activeLicenses[lang]}</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statNum}>{licenses.length}</span>
            <span className={styles.statLabel}>{db.stats.totalLicenses[lang]}</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statNum}>{profile?.referral_points ?? 0}</span>
            <span className={styles.statLabel}>{db.stats.referralPoints[lang]}</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statNum}>{orders.length}</span>
            <span className={styles.statLabel}>{db.stats.totalOrders[lang]}</span>
          </div>
        </div>

        {/* Tabs */}
        <div className={styles.tabs}>
          <button className={`${styles.tab} ${tab === "licenses" ? styles.tabActive : ""}`} onClick={() => setTab("licenses")}>{db.tabs.licenses[lang]}</button>
          <button className={`${styles.tab} ${tab === "orders"   ? styles.tabActive : ""}`} onClick={() => setTab("orders")}>{db.tabs.orders[lang]}</button>
          <button className={`${styles.tab} ${tab === "inbox"    ? styles.tabActive : ""}`} onClick={() => setTab("inbox")}>
            {db.tabs.inbox[lang]} {unread > 0 && <span className={styles.tabBadge}>{unread}</span>}
          </button>
          <button className={`${styles.tab} ${tab === "referral" ? styles.tabActive : ""}`} onClick={() => setTab("referral")}>{db.tabs.referral[lang]}</button>
          <button className={`${styles.tab} ${tab === "account"  ? styles.tabActive : ""}`} onClick={() => setTab("account")}>{db.tabs.account[lang]}</button>
        </div>

        {/* Licenses panel */}
        {tab === "licenses" && (
          <div className={styles.panel}>
            {licenses.length === 0 ? (
              <div className={styles.empty}><p>{db.licenses.empty[lang]}</p><a href="/#pricing" className="btn btn-primary" style={{ marginTop: 16 }}>{db.licenses.get[lang]}</a></div>
            ) : (
              <div className={styles.licenseGrid}>
                {licenses.map(lic => {
                  const { label, cls } = licenseStatus(lic, lang);
                  const isCopied = copied === lic.license_key;
                  return (
                    <div key={lic.id} className={styles.licenseCard}>
                      <div className={styles.licenseHead}>
                        <span className={styles.planLabel}>{lic.plan_label ?? lic.plan_id ?? "License"}</span>
                        <span className={`${styles.statusBadge} ${cls}`}>{label}</span>
                      </div>
                      <div className={styles.keyRow}>
                        <code className={styles.keyCode}>{lic.license_key}</code>
                        <button className={styles.copyBtn} onClick={() => { navigator.clipboard.writeText(lic.license_key).then(() => { setCopied(lic.license_key); setTimeout(() => setCopied(""), 2000); }); }} title="Copy key">
                          {isCopied
                            ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                            : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                          }
                        </button>
                      </div>
                      <div className={styles.licenseMeta}><span>{db.licenses.issued[lang]} {fmtDate(lic.issued_at)}</span><span>{daysLeft(lic.expires_at, lang)}</span></div>
                      {lic.hwid && <div className={styles.hwidRow}><span className={styles.hwidLabel}>HWID</span><code className={styles.hwidCode}>{lic.hwid.slice(0, 16)}…</code></div>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Orders panel */}
        {tab === "orders" && (
          <div className={styles.panel}>
            {orders.length === 0 ? (
              <div className={styles.empty}><p>{db.orders.empty[lang]}</p></div>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead><tr>
                    <th>{db.orders.date[lang]}</th>
                    <th>{db.orders.plan[lang]}</th>
                    <th>{db.orders.amount[lang]}</th>
                    <th>{db.orders.method[lang]}</th>
                    <th>{db.orders.ref[lang]}</th>
                    <th>{db.orders.status[lang]}</th>
                  </tr></thead>
                  <tbody>
                    {orders.map(o => (
                      <tr key={o.id}>
                        <td>{fmtDate(o.created_at)}</td>
                        <td>{o.plan_label ?? o.plan_id}</td>
                        <td>${o.amount_usd.toFixed(2)}</td>
                        <td className={styles.capitalize}>{o.payment_method}</td>
                        <td><code className={styles.refCode}>{o.payment_ref ? o.payment_ref.slice(0, 12) + (o.payment_ref.length > 12 ? "…" : "") : "—"}</code></td>
                        <td><span className={`badge badge-${o.status}`}>{o.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Inbox panel */}
        {tab === "inbox" && <InboxTab userId={user.id} initial={notifications} />}

        {/* Referral panel */}
        {tab === "referral" && <ReferralTab profile={profile} refEvents={refEvents} />}

        {/* My Account panel */}
        {tab === "account" && <AccountTab user={user} profile={profile} />}
      </div>
    </main>
  );
}
