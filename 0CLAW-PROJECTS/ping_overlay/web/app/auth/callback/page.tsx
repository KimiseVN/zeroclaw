"use client";
import { useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

function CallbackHandler() {
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    const code      = params.get("code");
    const next      = params.get("next") ?? "/dashboard";
    const error     = params.get("error");
    const errorDesc = params.get("error_description");

    if (error) {
      console.error("[auth/callback]", error, errorDesc);
      router.replace(`/?auth_error=${encodeURIComponent(errorDesc ?? error)}`);
      return;
    }

    if (code) {
      createClient()
        .auth.exchangeCodeForSession(code)
        .then(({ error: err }) => {
          if (err) {
            router.replace(`/?auth_error=${encodeURIComponent(err.message)}`);
          } else {
            router.replace(next);
          }
        });
      return;
    }

    router.replace("/");
  }, [params, router]);

  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      minHeight: "100vh", flexDirection: "column", gap: 16,
      background: "var(--bg)", color: "var(--text-dim)", fontSize: 14,
    }}>
      <div className="spinner" />
      <span>Signing you in…</span>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        minHeight: "100vh", background: "var(--bg)",
      }}>
        <div className="spinner" />
      </div>
    }>
      <CallbackHandler />
    </Suspense>
  );
}
