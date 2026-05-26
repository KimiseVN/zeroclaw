"use client";
import { useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import Header from "@/components/Header";
import styles from "./admin-mfa-gate.module.css";

// ─────────────────────────────────────────────────────────────────────────────
// AdminMfaGate
//
// mode="enroll"    → first-time 2FA setup: shows QR code + secret, user scans
//                   with authenticator app, enters 6-digit code to activate.
// mode="challenge" → per-session TOTP verification: user already has TOTP
//                   enrolled, just needs to enter current code to reach aal2.
//
// onVerified() is called after successful verify; the parent page then loads
// its data and transitions to "allowed".
// ─────────────────────────────────────────────────────────────────────────────

type Mode = "enroll" | "challenge";
interface Props {
  mode: Mode;
  onVerified: () => void;
}

export default function AdminMfaGate({ mode, onVerified }: Props) {
  const [step,        setStep]        = useState<"loading" | "ready">("loading");
  const [qrSvg,       setQrSvg]       = useState("");
  const [secret,      setSecret]      = useState("");
  const [factorId,    setFactorId]    = useState("");
  const [challengeId, setChallengeId] = useState("");

  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err,  setErr]  = useState("");

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { initFlow(); }, []);          // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (step === "ready") inputRef.current?.focus(); }, [step]);

  async function initFlow() {
    const sb = createClient();
    try {
      if (mode === "enroll") {
        // Clean up unconfirmed factors before enrolling.
        // .totp only has VERIFIED factors; unverified ones are in .all.
        // Cast status to string — TS types it as the literal "verified".
        const { data: existing } = await sb.auth.mfa.listFactors();
        for (const f of existing?.all ?? []) {
          if (f.factor_type === "totp" && (f.status as string) !== "verified") {
            await sb.auth.mfa.unenroll({ factorId: f.id });
          }
        }

        // Create a new TOTP factor — Supabase returns QR SVG + secret
        const { data, error } = await sb.auth.mfa.enroll({
          factorType:   "totp",
          friendlyName: "Admin Authenticator",
        });
        if (error || !data) throw error ?? new Error("Enroll init failed");
        setQrSvg(data.totp.qr_code);   // SVG string
        setSecret(data.totp.secret);
        setFactorId(data.id);
      } else {
        // Challenge mode: list enrolled factors, start a challenge
        const { data: fData } = await sb.auth.mfa.listFactors();
        const totp = fData?.totp?.[0];
        if (!totp) throw new Error("No TOTP factor found — please re-enroll.");
        setFactorId(totp.id);
        const { data: ch, error: chErr } = await sb.auth.mfa.challenge({ factorId: totp.id });
        if (chErr || !ch) throw chErr ?? new Error("Challenge init failed");
        setChallengeId(ch.id);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to initialize 2FA";
      setErr(msg);
    } finally {
      setStep("ready");
    }
  }

  async function verify() {
    if (code.length < 6) return;
    setBusy(true); setErr("");
    const sb = createClient();
    try {
      let chId = challengeId;

      if (mode === "enroll") {
        // Enrollment: we need a fresh challenge to pair with the new factor
        const { data: ch, error: chErr } = await sb.auth.mfa.challenge({ factorId });
        if (chErr || !ch) throw chErr ?? new Error("Challenge failed");
        chId = ch.id;
      }

      const { error } = await sb.auth.mfa.verify({ factorId, challengeId: chId, code });
      if (error) throw error;

      // Supabase has now elevated the session to aal2 — hand control back
      onVerified();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Invalid code — try again";
      setErr(msg);
      setCode("");
      inputRef.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  const isEnroll    = mode === "enroll";
  const titleText   = isEnroll ? "Set up Two-Factor Authentication" : "Admin Verification Required";
  const subText     = isEnroll
    ? "Scan the QR code below with Google Authenticator, Authy, or any TOTP app. Then enter the 6-digit code to activate 2FA."
    : "Your admin session requires two-factor verification. Enter the 6-digit code from your authenticator app.";
  const btnLabel    = busy ? "Verifying…" : (isEnroll ? "Activate 2FA" : "Verify & Enter");

  return (
    <>
      <Header />
      <main className={styles.main}>
        <div className={styles.card}>
          <div className={styles.shield}>{isEnroll ? "🔐" : "🛡️"}</div>
          <h1 className={styles.title}>{titleText}</h1>
          <p  className={styles.sub}>{subText}</p>

          {step === "loading" && (
            <div className={styles.spinnerWrap}><div className="spinner" /></div>
          )}

          {step === "ready" && (
            <>
              {/* QR code — only for enrollment */}
              {isEnroll && qrSvg && (
                <div className={styles.qrSection}>
                  {/* qrSvg is a complete data: URI from Supabase — use directly as img src */}
                  <div className={styles.qrWrap}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={qrSvg} alt="2FA QR Code" className={styles.qrImg} />
                  </div>
                  {secret && (
                    <details className={styles.secretDetails}>
                      <summary className={styles.secretSummary}>Can&apos;t scan? Enter key manually</summary>
                      <code className={styles.secret}>{secret}</code>
                    </details>
                  )}
                </div>
              )}

              {/* Code input */}
              <div className={styles.inputSection}>
                <label className={styles.inputLabel}>
                  {isEnroll ? "Step 2 — Enter the code from your app" : "6-digit authenticator code"}
                </label>
                <input
                  ref={inputRef}
                  className={styles.codeInput}
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  placeholder="000000"
                  value={code}
                  onChange={e => setCode(e.target.value.replace(/\D/g, ""))}
                  onKeyDown={e => { if (e.key === "Enter") verify(); }}
                  disabled={busy}
                  autoComplete="one-time-code"
                />
              </div>

              {err && <p className={styles.err}>{err}</p>}

              <button
                className={`btn btn-primary ${styles.verifyBtn}`}
                onClick={verify}
                disabled={busy || code.length < 6}
              >
                {btnLabel}
              </button>

              <p className={styles.hint}>
                {isEnroll
                  ? "Supported apps: Google Authenticator, Authy, Microsoft Authenticator, 1Password."
                  : "Open your authenticator app and enter the current 6-digit code for \"Admin Authenticator\"."}
              </p>
            </>
          )}
        </div>
      </main>
    </>
  );
}
