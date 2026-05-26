"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { logUnauthorizedAccess } from "@/lib/admin-guard";
import type { License } from "@/lib/supabase/types";
import Header from "@/components/Header";
import AccessDenied from "@/components/AccessDenied";
import AdminMfaGate from "@/components/AdminMfaGate";
import LicenseManager from "./LicenseManager";

// ── Status machine (same as /admin) ───────────────────────────────────────────
type Status = "loading" | "mfa_enroll" | "mfa_challenge" | "data_loading" | "allowed" | "denied" | "banned";

export default function AkimxiuPage() {
  const router = useRouter();
  const [status,   setStatus]   = useState<Status>("loading");
  const [licenses, setLicenses] = useState<License[]>([]);

  // ── Phase 2: load data (after MFA cleared) ─────────────────────────────────
  const loadData = useCallback(async () => {
    setStatus("data_loading");
    const sb = createClient();
    const { data: lics } = await sb
      .from("licenses")
      .select("*, profiles(email, full_name)")
      .order("issued_at", { ascending: false });
    setLicenses((lics ?? []) as License[]);
    setStatus("allowed");
  }, []);

  // ── Phase 1: auth + admin + MFA check ─────────────────────────────────────
  useEffect(() => {
    const sb = createClient();
    sb.auth.getUser().then(async ({ data: { user } }) => {
      // ── Not logged in ──────────────────────────────────────────────────────
      if (!user) {
        const result = await logUnauthorizedAccess(null, "/akimxiu");
        setStatus(result.banned ? "banned" : "denied");
        return;
      }

      // ── Check admin flag ───────────────────────────────────────────────────
      const { data: profile } = await sb
        .from("profiles").select("is_admin").eq("id", user.id).single();
      if (!profile?.is_admin) {
        const result = await logUnauthorizedAccess(user.id, "/akimxiu");
        setStatus(result.banned ? "banned" : "denied");
        return;
      }

      // ── Check MFA assurance level ──────────────────────────────────────────
      const { data: mfaData } = await sb.auth.mfa.getAuthenticatorAssuranceLevel();

      if (mfaData?.currentLevel === "aal2") {
        await loadData();
      } else if (mfaData?.nextLevel === "aal2") {
        setStatus("mfa_challenge");
      } else {
        setStatus("mfa_enroll");
      }
    });
  }, [router, loadData]);

  function handleMfaVerified() { loadData(); }

  // ── Render ─────────────────────────────────────────────────────────────────
  if (status === "denied")        return <AccessDenied />;
  if (status === "banned")        return <AccessDenied banned />;
  if (status === "mfa_enroll")    return <AdminMfaGate mode="enroll"    onVerified={handleMfaVerified} />;
  if (status === "mfa_challenge") return <AdminMfaGate mode="challenge" onVerified={handleMfaVerified} />;

  if (status === "loading" || status === "data_loading") return (
    <>
      <Header />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "calc(100vh - 60px)" }}>
        <div className="spinner" />
      </div>
    </>
  );

  return (
    <>
      <Header />
      <LicenseManager initialLicenses={licenses} onLicensesChange={setLicenses} />
    </>
  );
}
