"use client";
import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Header from "@/components/Header";

function ResetPasswordForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [password,  setPassword]  = useState("");
  const [confirm,   setConfirm]   = useState("");
  const [busy,      setBusy]      = useState(false);
  const [error,     setError]     = useState("");
  const [success,   setSuccess]   = useState(false);
  const [validating, setValidating] = useState(true);
  const [sessionOk,  setSessionOk]  = useState(false);

  // Supabase sends ?code= for PKCE or handles session automatically via hash
  useEffect(() => {
    const code = params.get("code");
    const sb = createClient();

    if (code) {
      sb.auth.exchangeCodeForSession(code).then(({ data, error: err }) => {
        if (err || !data.session) {
          setError("This reset link is invalid or has expired. Please request a new one.");
        } else {
          setSessionOk(true);
        }
        setValidating(false);
      });
    } else {
      // Check if already has session (hash-based flow)
      sb.auth.getSession().then(({ data: { session } }) => {
        if (session) {
          setSessionOk(true);
        } else {
          setError("This reset link is invalid or has expired. Please request a new one.");
        }
        setValidating(false);
      });
    }
  }, [params]);

  async function submit() {
    if (!password) return;
    if (password !== confirm) { setError("Passwords do not match."); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }

    setBusy(true); setError("");
    const sb = createClient();
    const { error: err } = await sb.auth.updateUser({ password });
    if (err) { setError(err.message); setBusy(false); return; }
    setSuccess(true);
    setTimeout(() => router.replace("/dashboard"), 3000);
  }

  return (
    <>
      <Header />
      <main style={{
        minHeight: "calc(100vh - 72px)", display: "flex",
        alignItems: "center", justifyContent: "center",
        background: "var(--bg)", padding: "24px 16px",
      }}>
        <div style={{
          width: "100%", maxWidth: 400,
          background: "var(--surface)", border: "1px solid var(--border-2)",
          borderRadius: 18, padding: "32px 28px",
          boxShadow: "0 16px 48px rgba(0,0,0,.4)",
        }}>
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>🔐</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: "var(--text)" }}>Set new password</div>
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
              Create a new secure password for your account.
            </div>
          </div>

          {validating ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "24px 0" }}>
              <div className="spinner" />
            </div>
          ) : success ? (
            <div style={{ textAlign: "center", padding: "16px 0" }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>✅</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text)", marginBottom: 8 }}>Password updated!</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Redirecting to your dashboard…</div>
            </div>
          ) : !sessionOk ? (
            <div>
              {error && (
                <div style={{
                  padding: "10px 14px", borderRadius: 8, marginBottom: 16,
                  background: "rgba(255,59,48,.12)", border: "1px solid rgba(255,59,48,.3)",
                  color: "var(--red)", fontSize: 13,
                }}>
                  {error}
                </div>
              )}
              <button
                className="btn btn-primary"
                style={{ width: "100%" }}
                onClick={() => router.replace("/")}
              >
                ← Back to home
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {error && (
                <div style={{
                  padding: "10px 14px", borderRadius: 8,
                  background: "rgba(255,59,48,.12)", border: "1px solid rgba(255,59,48,.3)",
                  color: "var(--red)", fontSize: 13,
                }}>
                  {error}
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>
                  New password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Min. 8 characters"
                  disabled={busy}
                  style={{
                    padding: "11px 14px", borderRadius: 10,
                    background: "var(--bg-1)", border: "1px solid var(--border-2)",
                    color: "var(--text)", fontSize: 14, outline: "none",
                    boxSizing: "border-box", width: "100%",
                  }}
                  onKeyDown={e => { if (e.key === "Enter") submit(); }}
                />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>
                  Confirm password
                </label>
                <input
                  type="password"
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  placeholder="Repeat new password"
                  disabled={busy}
                  style={{
                    padding: "11px 14px", borderRadius: 10,
                    background: "var(--bg-1)", border: "1px solid var(--border-2)",
                    color: "var(--text)", fontSize: 14, outline: "none",
                    boxSizing: "border-box", width: "100%",
                  }}
                  onKeyDown={e => { if (e.key === "Enter") submit(); }}
                />
              </div>
              <button
                className="btn btn-primary"
                style={{ width: "100%", marginTop: 4 }}
                onClick={submit}
                disabled={busy || !password || !confirm}
              >
                {busy ? "Updating…" : "Update password"}
              </button>
            </div>
          )}
        </div>
      </main>
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", background: "var(--bg)" }}>
        <div className="spinner" />
      </div>
    }>
      <ResetPasswordForm />
    </Suspense>
  );
}
