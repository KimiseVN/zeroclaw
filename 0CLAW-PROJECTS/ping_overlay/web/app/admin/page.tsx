"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { logUnauthorizedAccess } from "@/lib/admin-guard";
import type { Order, License, PaymentConfig, Profile, ReferralEvent, SiteSetting, FaqItem, DemoImage } from "@/lib/supabase/types";
import type { BlacklistEntry } from "@/lib/supabase/types";
import type { VisitRow } from "./Analytics";
import Header from "@/components/Header";
import AccessDenied from "@/components/AccessDenied";
import AdminMfaGate from "@/components/AdminMfaGate";
import AdminClient from "./AdminClient";

type Stats = { pending: number; paid: number; active: number; totalOrders: number };
// ── Status machine ─────────────────────────────────────────────────────────────
// loading      → checking auth + admin status + MFA level
// mfa_enroll   → admin confirmed, no TOTP factor enrolled → must set up 2FA
// mfa_challenge → admin confirmed, TOTP enrolled but session is aal1 → verify TOTP
// data_loading → MFA cleared, fetching admin data
// allowed      → fully authorised, data ready
// denied / banned → not admin (or blacklisted)
type Status = "loading" | "mfa_enroll" | "mfa_challenge" | "data_loading" | "allowed" | "denied" | "banned";

export default function AdminPage() {
  const router = useRouter();
  const [status,         setStatus]         = useState<Status>("loading");
  const [orders,         setOrders]         = useState<Order[]>([]);
  const [licenses,       setLicenses]       = useState<License[]>([]);
  const [paymentConfigs, setPaymentConfigs] = useState<PaymentConfig[]>([]);
  const [siteSettings,   setSiteSettings]   = useState<SiteSetting[]>([]);
  const [faqs,           setFaqs]           = useState<FaqItem[]>([]);
  const [demoImages,     setDemoImages]     = useState<DemoImage[]>([]);
  const [visits,         setVisits]         = useState<VisitRow[]>([]);
  const [users,          setUsers]          = useState<Profile[]>([]);
  const [refEvents,      setRefEvents]      = useState<ReferralEvent[]>([]);
  const [blacklist,      setBlacklist]      = useState<BlacklistEntry[]>([]);
  const [stats,          setStats]          = useState<Stats>({ pending: 0, paid: 0, active: 0, totalOrders: 0 });

  // ── Phase 2: load admin data (called after MFA is cleared) ─────────────────
  const loadData = useCallback(async () => {
    setStatus("data_loading");
    const sb = createClient();
    const [
      { data: ords },
      { data: lics },
      { data: pmtCfg },
      { data: siteCfg },
      { data: faqData },
      { data: demoData },
      { data: visitData },
      { data: usersData },
      { data: refData },
      { data: blData },
    ] = await Promise.all([
      sb.from("orders").select("*, profiles(email, full_name, avatar_url)").order("created_at", { ascending: false }),
      sb.from("licenses").select("*, profiles(email, full_name)").order("issued_at", { ascending: false }),
      sb.from("payment_config").select("*").order("id"),
      sb.from("site_settings").select("*").order("key"),
      sb.from("faq").select("*").order("order_index"),
      sb.from("demo_images").select("*").order("order_index"),
      sb.from("visits")
        .select("ip, country, country_code, city, lat, lng, visited_at")
        .gte("visited_at", new Date(Date.now() - 90 * 86400_000).toISOString())
        .order("visited_at", { ascending: false })
        .limit(5000),
      sb.from("profiles").select("*").order("created_at", { ascending: false }),
      sb.from("referral_events").select("*, referrer:profiles!referrer_id(email, full_name)").order("created_at", { ascending: false }).limit(500),
      sb.from("blacklist").select("*, profiles:user_id(email, full_name)").order("created_at", { ascending: false }),
    ]);

    const o = (ords ?? []) as Order[];
    const l = (lics ?? []) as License[];

    setOrders(o);
    setLicenses(l);
    setPaymentConfigs((pmtCfg ?? []) as PaymentConfig[]);
    setSiteSettings((siteCfg ?? []) as SiteSetting[]);
    setFaqs((faqData ?? []) as FaqItem[]);
    setDemoImages((demoData ?? []) as DemoImage[]);
    setVisits((visitData ?? []) as VisitRow[]);
    setUsers((usersData ?? []) as Profile[]);
    setRefEvents((refData ?? []) as ReferralEvent[]);
    setBlacklist((blData ?? []) as BlacklistEntry[]);
    setStats({
      pending:     o.filter(x => x.status === "pending").length,
      paid:        o.filter(x => x.status === "paid").length,
      active:      l.filter(x => x.status === "active").length,
      totalOrders: o.length,
    });
    setStatus("allowed");
  }, []);

  // ── Phase 1: auth + admin + MFA check ─────────────────────────────────────
  useEffect(() => {
    const sb = createClient();

    sb.auth.getUser().then(async ({ data: { user } }) => {
      // ── Not logged in ──────────────────────────────────────────────────────
      if (!user) {
        const result = await logUnauthorizedAccess(null, "/admin");
        setStatus(result.banned ? "banned" : "denied");
        return;
      }

      // ── Check admin flag ───────────────────────────────────────────────────
      const { data: profile } = await sb.from("profiles").select("is_admin").eq("id", user.id).single();
      if (!profile?.is_admin) {
        const result = await logUnauthorizedAccess(user.id, "/admin");
        setStatus(result.banned ? "banned" : "denied");
        return;
      }

      // ── Check MFA assurance level ──────────────────────────────────────────
      // currentLevel: level this session has achieved
      // nextLevel:    level achievable if all enrolled factors are verified
      const { data: mfaData } = await sb.auth.mfa.getAuthenticatorAssuranceLevel();

      if (mfaData?.currentLevel === "aal2") {
        // Already fully verified this session → load data immediately
        await loadData();
      } else if (mfaData?.nextLevel === "aal2") {
        // Has TOTP enrolled but hasn't verified this session → challenge
        setStatus("mfa_challenge");
      } else {
        // No TOTP factor enrolled → force enrollment before access
        setStatus("mfa_enroll");
      }
    });
  }, [router, loadData]);

  // ── MFA gate callback ──────────────────────────────────────────────────────
  // Called after AdminMfaGate successfully verifies (session is now aal2)
  function handleMfaVerified() { loadData(); }

  // ── Render ─────────────────────────────────────────────────────────────────
  if (status === "denied")       return <AccessDenied />;
  if (status === "banned")       return <AccessDenied banned />;
  if (status === "mfa_enroll")   return <AdminMfaGate mode="enroll"    onVerified={handleMfaVerified} />;
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
      <AdminClient
        orders={orders} licenses={licenses} stats={stats}
        paymentConfigs={paymentConfigs} siteSettings={siteSettings}
        faqs={faqs} demoImages={demoImages} visits={visits}
        users={users} refEvents={refEvents} blacklist={blacklist}
      />
    </>
  );
}
