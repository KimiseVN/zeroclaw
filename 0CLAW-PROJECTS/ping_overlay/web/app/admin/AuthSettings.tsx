"use client";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { AuthProviders } from "@/lib/supabase/types";
import styles from "./admin.module.css";

type Props = { initial: Record<string, any> };

const DEFAULT: AuthProviders = {
  email_password: true,
  magic_link:     true,
  google:         true,
  discord:        false,
  github:         false,
  twitter:        false,
};

type ProviderMeta = {
  key: keyof AuthProviders;
  label: string;
  description: string;
  icon: string;
  category: "email" | "oauth";
  supabaseDoc?: string;
};

const PROVIDER_LIST: ProviderMeta[] = [
  {
    key: "email_password",
    label: "Email / Password",
    description: "Classic email + password sign-up and sign-in. Requires Supabase email auth enabled.",
    icon: "✉️",
    category: "email",
  },
  {
    key: "magic_link",
    label: "Magic Link (Passwordless)",
    description: "Send a one-time login link to user's email. No password required.",
    icon: "🔗",
    category: "email",
  },
  {
    key: "google",
    label: "Google",
    description: "OAuth 2.0 via Google. Requires Google OAuth app in Supabase dashboard.",
    icon: "🔵",
    category: "oauth",
    supabaseDoc: "https://supabase.com/docs/guides/auth/social-login/auth-google",
  },
  {
    key: "discord",
    label: "Discord",
    description: "OAuth via Discord. Requires Discord app in Supabase dashboard.",
    icon: "🟣",
    category: "oauth",
    supabaseDoc: "https://supabase.com/docs/guides/auth/social-login/auth-discord",
  },
  {
    key: "github",
    label: "GitHub",
    description: "OAuth via GitHub. Requires GitHub OAuth app in Supabase dashboard.",
    icon: "⚫",
    category: "oauth",
    supabaseDoc: "https://supabase.com/docs/guides/auth/social-login/auth-github",
  },
  {
    key: "twitter",
    label: "Twitter / X",
    description: "OAuth via Twitter/X. Requires Twitter app credentials in Supabase dashboard.",
    icon: "🐦",
    category: "oauth",
    supabaseDoc: "https://supabase.com/docs/guides/auth/social-login/auth-twitter",
  },
];

async function saveProviders(val: AuthProviders) {
  await createClient().from("site_settings")
    .upsert({ key: "auth_providers", value: val, updated_at: new Date().toISOString() }, { onConflict: "key" });
}

export default function AuthSettings({ initial }: Props) {
  const merged = { ...DEFAULT, ...initial } as AuthProviders;
  const [providers, setProviders] = useState<AuthProviders>(merged);
  const [busy, setBusy] = useState(false);
  const [msg,  setMsg]  = useState("");

  function toggle(key: keyof AuthProviders) {
    setProviders(prev => ({ ...prev, [key]: !prev[key] }));
  }

  async function save() {
    setBusy(true); setMsg("");
    await saveProviders(providers);
    setBusy(false); setMsg("Saved!"); setTimeout(() => setMsg(""), 2000);
  }

  const emailProviders = PROVIDER_LIST.filter(p => p.category === "email");
  const oauthProviders = PROVIDER_LIST.filter(p => p.category === "oauth");

  return (
    <div className={styles.settingCard}>
      <h3 className={styles.settingCardTitle}>Auth Providers</h3>
      <p className={styles.inputHint} style={{ marginBottom: 20 }}>
        Controls which sign-in methods appear on the site. OAuth providers must also be configured in your{" "}
        <a href="https://supabase.com/dashboard/project/_/auth/providers" target="_blank" rel="noopener" style={{ color: "var(--cyan)" }}>
          Supabase dashboard
        </a>.
      </p>

      {/* Email methods */}
      <div className={styles.formGroup}>
        <label className={styles.formLabel} style={{ marginBottom: 10 }}>Email Methods</label>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {emailProviders.map(p => (
            <ProviderRow key={p.key} meta={p} enabled={providers[p.key]} onToggle={() => toggle(p.key)} />
          ))}
        </div>
      </div>

      {/* OAuth providers */}
      <div className={styles.formGroup}>
        <label className={styles.formLabel} style={{ marginBottom: 10 }}>OAuth Providers</label>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {oauthProviders.map(p => (
            <ProviderRow key={p.key} meta={p} enabled={providers[p.key]} onToggle={() => toggle(p.key)} />
          ))}
        </div>
      </div>

      {/* Note about email templates */}
      <div style={{
        padding: "12px 14px", borderRadius: 8,
        background: "rgba(0,229,255,.06)", border: "1px solid rgba(0,229,255,.15)",
        fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6, marginTop: 4,
      }}>
        <strong style={{ color: "var(--cyan)" }}>💡 Email templates</strong> — Customize confirmation, magic link, and password reset emails in{" "}
        <a href="https://supabase.com/dashboard/project/_/auth/templates" target="_blank" rel="noopener" style={{ color: "var(--cyan)" }}>
          Supabase → Auth → Email Templates
        </a>.
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16 }}>
        {msg && <span style={{ fontSize: 13, color: msg.startsWith("Error") ? "var(--red)" : "var(--green)" }}>{msg}</span>}
        <button className="btn btn-primary" style={{ marginLeft: "auto" }} onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

function ProviderRow({ meta, enabled, onToggle }: {
  meta: ProviderMeta;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 12,
      padding: "12px 14px", borderRadius: 10,
      background: "var(--bg-1)", border: `1px solid ${enabled ? "rgba(0,229,255,.2)" : "var(--border)"}`,
      transition: "border-color .15s",
    }}>
      <span style={{ fontSize: 20, lineHeight: 1, marginTop: 1 }}>{meta.icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text)" }}>{meta.label}</span>
          {meta.supabaseDoc && (
            <a href={meta.supabaseDoc} target="_blank" rel="noopener"
              style={{ fontSize: 11, color: "var(--text-muted)", textDecoration: "none" }}
              title="Setup docs"
            >
              docs ↗
            </a>
          )}
        </div>
        <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "3px 0 0", lineHeight: 1.5 }}>{meta.description}</p>
      </div>
      {/* Toggle */}
      <label style={{ display: "flex", alignItems: "center", cursor: "pointer", flexShrink: 0, marginTop: 2 }}>
        <div
          style={{
            width: 38, height: 22, borderRadius: 11, position: "relative",
            background: enabled ? "var(--cyan)" : "var(--border-2)",
            transition: "background .2s", cursor: "pointer",
            border: "none", flexShrink: 0,
          }}
          onClick={onToggle}
          role="switch"
          aria-checked={enabled}
          tabIndex={0}
          onKeyDown={e => e.key === " " && onToggle()}
        >
          <div style={{
            width: 16, height: 16, borderRadius: "50%",
            background: "#fff",
            position: "absolute", top: 3,
            left: enabled ? 19 : 3,
            transition: "left .2s",
            boxShadow: "0 1px 3px rgba(0,0,0,.3)",
          }} />
        </div>
      </label>
    </div>
  );
}
