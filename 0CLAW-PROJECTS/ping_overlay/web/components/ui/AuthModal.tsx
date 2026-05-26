"use client";
import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { createClient } from "@/lib/supabase/client";
import { useAuthProviders } from "@/lib/use-site-settings";
import { useTurnstile } from "@/lib/turnstile-context";
import type { AuthProviders } from "@/lib/supabase/types";
import type { Provider } from "@supabase/supabase-js";
import styles from "./AuthModal.module.css";

// ── SVG Icons ─────────────────────────────────────────────────────────────────
function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  );
}

function DiscordIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="#5865F2">
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057c.002.022.015.043.033.055a19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
    </svg>
  );
}

function TwitterIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
    </svg>
  );
}

function EmailIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="4" width="20" height="16" rx="3"/>
      <path d="m2 7 10 7 10-7"/>
    </svg>
  );
}

// ── Provider config ────────────────────────────────────────────────────────────
type OAuthProvider = "google" | "discord" | "github" | "twitter";

const PROVIDERS: {
  key: OAuthProvider;
  label: string;
  icon: React.ReactNode;
  supabaseId: Provider;
  colorClass: string;
}[] = [
  { key: "google",  label: "Continue with Google",  icon: <GoogleIcon />,  supabaseId: "google",  colorClass: styles.google },
  { key: "discord", label: "Continue with Discord", icon: <DiscordIcon />, supabaseId: "discord", colorClass: styles.discord },
  { key: "github",  label: "Continue with GitHub",  icon: <GitHubIcon />,  supabaseId: "github",  colorClass: styles.github },
  { key: "twitter", label: "Continue with Twitter / X", icon: <TwitterIcon />, supabaseId: "twitter", colorClass: styles.twitter },
];

// ── Anti-bot helpers ───────────────────────────────────────────────────────────
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

/** Call the validate-email-signup Edge Function (L4 domain check + L5 Turnstile verify).
 *  Fail-open: returns true on any network error so real users are never blocked. */
async function validateEmailSignup(email: string, turnstileToken: string | null): Promise<{ ok: boolean; reason?: string }> {
  try {
    const res = await fetch(`${SUPABASE_URL}/functions/v1/validate-email-signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, turnstile_token: turnstileToken ?? "bypass" }),
    });
    if (!res.ok) return { ok: true }; // fail-open on HTTP error
    return await res.json();
  } catch {
    return { ok: true }; // fail-open on network error
  }
}

// ── Main component ─────────────────────────────────────────────────────────────
type AuthMode   = "signin" | "signup";
type EmailMode  = "password" | "magic_link";

type Props = {
  isOpen:   boolean;
  onClose:  () => void;
  onSuccess?: () => void;
  /** Pre-select mode */
  defaultMode?: AuthMode;
  /** Redirect after OAuth. Defaults to current page. */
  redirectTo?: string;
};

export default function AuthModal({ isOpen, onClose, onSuccess, defaultMode = "signin", redirectTo }: Props) {
  const providers = useAuthProviders();
  const { verified: turnstileOk, token: turnstileToken } = useTurnstile(); // token = null (pending) | string (verified/bypass)
  const [mode,       setMode]      = useState<AuthMode>(defaultMode);
  const [emailMode,  setEmailMode] = useState<EmailMode>("password");
  const [email,      setEmail]     = useState("");
  const [fullName,   setFullName]  = useState("");
  const [password,   setPassword]  = useState("");
  const [busy,       setBusy]      = useState<string | null>(null); // which button is loading
  const [error,      setError]     = useState("");
  const [sent,       setSent]      = useState(false); // magic link / confirm email sent
  const [mounted,    setMounted]   = useState(false);
  // ── L3 honeypot — hidden field bots auto-fill; real users never see it ──────
  const [hp, setHp] = useState("");

  useEffect(() => { setMounted(true); }, []);

  // Reset state on open
  useEffect(() => {
    if (isOpen) {
      setMode(defaultMode);
      setEmail(""); setFullName(""); setPassword("");
      setError(""); setSent(false); setBusy(null); setHp("");
    }
  }, [isOpen, defaultMode]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    function handler(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  const redirect = redirectTo ?? (typeof window !== "undefined" ? `${window.location.origin}/auth/callback/` : "/auth/callback/");

  // ── OAuth ────────────────────────────────────────────────────────────────────
  async function handleOAuth(provider: Provider, btnKey: string) {
    setBusy(btnKey); setError("");
    const sb = createClient();
    const { error: err } = await sb.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: redirect,
        ...(provider === "google" ? { queryParams: { access_type: "offline", prompt: "consent" } } : {}),
      },
    });
    if (err) { setError(err.message); setBusy(null); }
    // On success Supabase redirects away — no need to clear busy
  }

  // ── Email / Password ─────────────────────────────────────────────────────────
  async function handleEmailPassword() {
    if (!email.trim() || !password) return;
    setBusy("email"); setError("");

    if (mode === "signup") {
      // L3: honeypot — if filled, bot detected → fake success silently
      if (hp) { setSent(true); setBusy(null); return; }

      // L4+L5: domain blocklist + server-side Turnstile verify (token captured at top level)
      const check = await validateEmailSignup(email.trim(), turnstileToken);
      if (!check.ok) {
        if (check.reason === "disposable_email") {
          setError("Please use a real email address — disposable/temporary emails are not allowed.");
        } else {
          setError("Bot verification failed. Please refresh and try again.");
        }
        setBusy(null); return;
      }
    }

    const sb = createClient();
    if (mode === "signup") {
      const { error: err } = await sb.auth.signUp({
        email: email.trim(),
        password,
        options: {
          emailRedirectTo: redirect,
          data: { full_name: fullName.trim() || null },
        },
      });
      if (err) { setError(err.message); setBusy(null); return; }
      setSent(true); setBusy(null);
    } else {
      const { error: err } = await sb.auth.signInWithPassword({ email: email.trim(), password });
      if (err) { setError(err.message); setBusy(null); return; }
      setBusy(null);
      onSuccess?.();
      onClose();
      window.location.href = "/dashboard";
    }
  }

  // ── Magic Link ───────────────────────────────────────────────────────────────
  async function handleMagicLink() {
    if (!email.trim()) return;
    setBusy("magic"); setError("");

    if (mode === "signup") {
      // L3: honeypot
      if (hp) { setSent(true); setBusy(null); return; }

      // L4+L5: domain blocklist + Turnstile verify
      const check = await validateEmailSignup(email.trim(), turnstileToken);
      if (!check.ok) {
        if (check.reason === "disposable_email") {
          setError("Please use a real email address — disposable/temporary emails are not allowed.");
        } else {
          setError("Bot verification failed. Please refresh and try again.");
        }
        setBusy(null); return;
      }
    }

    const sb = createClient();
    const { error: err } = await sb.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: redirect, shouldCreateUser: mode === "signup" },
    });
    if (err) { setError(err.message); setBusy(null); return; }
    setSent(true); setBusy(null);
  }

  // ── Forgot password ───────────────────────────────────────────────────────────
  async function handleForgotPassword() {
    if (!email.trim()) { setError("Enter your email first."); return; }
    setBusy("forgot"); setError("");
    const sb = createClient();
    const { error: err } = await sb.auth.resetPasswordForEmail(email.trim(), {
      redirectTo: `${typeof window !== "undefined" ? window.location.origin : ""}/reset-password`,
    });
    if (err) { setError(err.message); setBusy(null); return; }
    setSent(true); setBusy(null);
  }

  // ── Active OAuth providers ────────────────────────────────────────────────────
  const activeProviders = PROVIDERS.filter(p => providers[p.key as keyof AuthProviders]);
  const hasEmail   = providers.email_password || providers.magic_link;
  const hasOAuth   = activeProviders.length > 0;

  if (!mounted || !isOpen) return null;

  // ── Sent confirmation state ───────────────────────────────────────────────────
  const sentContent = (
    <div className={styles.successBox}>
      <div className={styles.successIcon}>📧</div>
      <div className={styles.successTitle}>Check your email</div>
      <div className={styles.successText}>
        We sent a link to <span className={styles.successEmail}>{email}</span>.<br />
        Click it to {mode === "signup" ? "confirm your account" : "sign in"}.
      </div>
      <button className={styles.submitBtn} style={{ marginTop: 8, maxWidth: 220 }} onClick={() => setSent(false)}>
        ← Back
      </button>
    </div>
  );

  const hasEmailPassword = providers.email_password;
  const hasMagicLink     = providers.magic_link;

  const modalContent = (
    <div className={styles.backdrop} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={styles.card}>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Close">×</button>

        {/* Header */}
        <div className={styles.header}>
          <div className={styles.logoWrap}>
            <div className={styles.logoIcon}>🎮</div>
            <span className={styles.logoName}>WWM Overlay</span>
          </div>
          <div className={styles.title}>
            {sent ? "Email sent!" : mode === "signin" ? "Welcome back" : "Create account"}
          </div>
          <div className={styles.subtitle}>
            {!sent && (mode === "signin" ? "Sign in to access your license & dashboard." : "Join WWM Overlay to manage your licenses.")}
          </div>
        </div>

        {/* Sent state */}
        {sent ? sentContent : (
          <>
            {/* Sign in / Sign up toggle — only if email enabled */}
            {hasEmail && (
              <div className={styles.modeToggle}>
                <button className={`${styles.modeBtn} ${mode === "signin" ? styles.modeBtnActive : ""}`} onClick={() => { setMode("signin"); setError(""); }}>
                  Sign in
                </button>
                <button className={`${styles.modeBtn} ${mode === "signup" ? styles.modeBtnActive : ""}`} onClick={() => { setMode("signup"); setError(""); }}>
                  Create account
                </button>
              </div>
            )}

            {/* Error */}
            {error && <div className={styles.error}>{error}</div>}

            {/* OAuth providers */}
            {hasOAuth && (
              <div className={styles.providers}>
                {activeProviders.map(p => (
                  <button
                    key={p.key}
                    className={`${styles.providerBtn} ${p.colorClass}`}
                    onClick={() => handleOAuth(p.supabaseId, p.key)}
                    disabled={!!busy}
                  >
                    <span className={styles.providerIcon}>{p.icon}</span>
                    <span className={styles.providerLabel}>{p.label}</span>
                    {busy === p.key ? <span className={styles.btnSpinner} /> : <span className={styles.providerArrow}>→</span>}
                  </button>
                ))}
              </div>
            )}

            {/* Divider */}
            {hasOAuth && hasEmail && <div className={styles.divider}>or continue with email</div>}

            {/* Email section */}
            {hasEmail && (
              <>
                {/* Tab: Password vs Magic Link (show only if both enabled) */}
                {hasEmailPassword && hasMagicLink && (
                  <div className={styles.emailTabs}>
                    <button
                      className={`${styles.emailTab} ${emailMode === "password" ? styles.emailTabActive : ""}`}
                      onClick={() => { setEmailMode("password"); setError(""); }}
                    >
                      Password
                    </button>
                    <button
                      className={`${styles.emailTab} ${emailMode === "magic_link" ? styles.emailTabActive : ""}`}
                      onClick={() => { setEmailMode("magic_link"); setError(""); }}
                    >
                      Magic link
                    </button>
                  </div>
                )}

                <div className={styles.form}>
                  {/* ── L3 honeypot — real users never see this; bots auto-fill it ── */}
                  <div aria-hidden="true" style={{ position: "absolute", left: "-9999px", top: "-9999px", width: 1, height: 1, overflow: "hidden", opacity: 0 }}>
                    <label htmlFor="auth-website">Website</label>
                    <input
                      id="auth-website"
                      name="website"
                      type="text"
                      value={hp}
                      onChange={e => setHp(e.target.value)}
                      tabIndex={-1}
                      autoComplete="off"
                    />
                  </div>

                  <div className={styles.field}>
                    <label className={styles.label}>Email address</label>
                    <input
                      className={styles.input}
                      type="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      disabled={!!busy}
                      autoComplete="email"
                      onKeyDown={e => {
                        if (e.key === "Enter") {
                          const em = emailMode === "magic_link" || !hasEmailPassword ? "magic" : undefined;
                          if (em) handleMagicLink();
                        }
                      }}
                    />
                  </div>

                  {/* Full name — only shown during email sign-up */}
                  {mode === "signup" && emailMode === "password" && hasEmailPassword && (
                    <div className={styles.field}>
                      <label className={styles.label}>
                        Full Name <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(optional)</span>
                      </label>
                      <input
                        className={styles.input}
                        type="text"
                        placeholder="Your name"
                        value={fullName}
                        onChange={e => setFullName(e.target.value)}
                        disabled={!!busy}
                        autoComplete="name"
                      />
                    </div>
                  )}

                  {/* Password field — only for password mode */}
                  {(emailMode === "password" && hasEmailPassword) && (
                    <div className={styles.field}>
                      <label className={styles.label}>Password</label>
                      <input
                        className={styles.input}
                        type="password"
                        placeholder={mode === "signup" ? "Create a strong password" : "Your password"}
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                        disabled={!!busy}
                        autoComplete={mode === "signup" ? "new-password" : "current-password"}
                        onKeyDown={e => { if (e.key === "Enter") handleEmailPassword(); }}
                      />
                    </div>
                  )}

                  {/* Submit */}
                  {/* Sign-up submissions are gated on Turnstile verification to block bots.
                      The invisible widget resolves in ~1 s for real users (zero friction).
                      On error/timeout it fail-opens ("bypass" token), so no one gets stuck. */}
                  {emailMode === "password" && hasEmailPassword ? (
                    <>
                      <button
                        className={styles.submitBtn}
                        onClick={handleEmailPassword}
                        disabled={!!busy || !email || !password || (mode === "signup" && !turnstileOk)}
                      >
                        {busy === "email"
                          ? <span className={styles.btnSpinner} style={{ borderColor: "rgba(0,0,0,.25)", borderTopColor: "#000" }} />
                          : mode === "signin" ? "Sign in" : "Create account"}
                      </button>
                      {mode === "signup" && !turnstileOk && (
                        <p className={styles.turnstileNote}>Verifying you&apos;re human…</p>
                      )}
                      <div className={styles.extras}>
                        <button className={styles.link} onClick={handleForgotPassword} disabled={!!busy}>
                          {busy === "forgot" ? "Sending…" : "Forgot password?"}
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <button
                        className={styles.submitBtn}
                        onClick={handleMagicLink}
                        disabled={!!busy || !email || (mode === "signup" && !turnstileOk)}
                      >
                        {busy === "magic"
                          ? <span className={styles.btnSpinner} style={{ borderColor: "rgba(0,0,0,.25)", borderTopColor: "#000" }} />
                          : "Send magic link →"}
                      </button>
                      {mode === "signup" && !turnstileOk && (
                        <p className={styles.turnstileNote}>Verifying you&apos;re human…</p>
                      )}
                    </>
                  )}
                </div>
              </>
            )}

            {/* Footer */}
            <p className={styles.footerNote}>
              By continuing you agree to our{" "}
              <a href="/terms" target="_blank" rel="noopener">Terms</a> and{" "}
              <a href="/privacy" target="_blank" rel="noopener">Privacy Policy</a>.
            </p>
          </>
        )}
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}
