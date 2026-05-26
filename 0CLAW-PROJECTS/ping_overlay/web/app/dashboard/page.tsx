"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import type { License, Notification, Order, Profile, ReferralEvent } from "@/lib/supabase/types";
import Header from "@/components/Header";
import DashboardClient from "./DashboardClient";

export default function DashboardPage() {
  const router = useRouter();
  const [ready,    setReady]    = useState(false);
  const [userId,   setUserId]   = useState("");
  const [email,    setEmail]    = useState("");
  const [licenses, setLicenses] = useState<License[]>([]);
  const [orders,   setOrders]   = useState<Order[]>([]);
  const [profile,       setProfile]       = useState<Pick<Profile, "full_name" | "avatar_url" | "referral_code" | "referral_points" | "created_at"> | null>(null);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [refEvents,     setRefEvents]     = useState<ReferralEvent[]>([]);

  useEffect(() => {
    const sb = createClient();

    sb.auth.getUser().then(async ({ data: { user } }) => {
      if (!user) { router.replace("/"); return; }

      setUserId(user.id);
      setEmail(user.email ?? "");

      const [{ data: lics }, { data: ords }, { data: prof }, { data: notifs }, { data: refs }] = await Promise.all([
        sb.from("licenses").select("*").eq("user_id", user.id).order("issued_at", { ascending: false }),
        sb.from("orders").select("*").eq("user_id", user.id).order("created_at", { ascending: false }),
        sb.from("profiles").select("full_name, avatar_url, referral_code, referral_points, created_at").eq("id", user.id).single(),
        sb.from("notifications").select("*").eq("user_id", user.id).order("created_at", { ascending: false }).limit(50),
        sb.from("referral_events").select("*").eq("referrer_id", user.id).order("created_at", { ascending: false }).limit(50),
      ]);

      // Backfill referral_code for users who logged in before the DB trigger existed.
      // Format: 8 uppercase alphanumeric chars (no dashes) — matches DB generate_referral_code().
      let finalProf = prof as any;
      if (finalProf && !finalProf.referral_code) {
        const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        const bytes = crypto.getRandomValues(new Uint8Array(8));
        let newCode = "";
        for (const b of bytes) newCode += chars[b % chars.length];
        await sb.from("profiles").update({ referral_code: newCode }).eq("id", user.id);
        finalProf = { ...finalProf, referral_code: newCode };
      }
      // Fix legacy codes that have the old XXXX-XXXX dashed format
      if (finalProf?.referral_code?.includes("-")) {
        const fixed = finalProf.referral_code.replace(/-/g, "").toUpperCase();
        await sb.from("profiles").update({ referral_code: fixed }).eq("id", user.id);
        finalProf = { ...finalProf, referral_code: fixed };
      }

      setLicenses((lics ?? []) as License[]);
      setOrders((ords ?? []) as Order[]);
      setProfile(finalProf as Pick<Profile, "full_name" | "avatar_url" | "referral_code" | "referral_points" | "created_at"> | null);
      setNotifications((notifs ?? []) as Notification[]);
      setRefEvents((refs ?? []) as ReferralEvent[]);
      setReady(true);
    });
  }, [router]);

  if (!ready) {
    return (
      <>
        <Header />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "calc(100vh - 60px)" }}>
          <div className="spinner" />
        </div>
      </>
    );
  }

  return (
    <>
      <Header />
      <DashboardClient
        user={{ id: userId, email }}
        licenses={licenses}
        orders={orders}
        profile={profile}
        notifications={notifications}
        refEvents={refEvents}
      />
    </>
  );
}
