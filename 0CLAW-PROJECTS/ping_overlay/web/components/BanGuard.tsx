"use client";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { checkBan } from "@/lib/admin-guard";
import AccessDenied from "./AccessDenied";

const CACHE_KEY = "ban_check_v1";
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

export default function BanGuard({ children }: { children: React.ReactNode }) {
  const [banned, setBanned] = useState(false);

  useEffect(() => {
    async function check() {
      // Read sessionStorage cache
      try {
        const raw = sessionStorage.getItem(CACHE_KEY);
        if (raw) {
          const { result, ts } = JSON.parse(raw);
          if (Date.now() - ts < CACHE_TTL) {
            if (result) setBanned(true);
            return;
          }
        }
      } catch { /* ignore parse errors */ }

      const sb = createClient();
      const { data: { user } } = await sb.auth.getUser();

      // Admins are never banned — skip check entirely
      if (user) {
        const { data: prof } = await sb
          .from("profiles").select("is_admin").eq("id", user.id).single();
        if (prof?.is_admin) {
          sessionStorage.setItem(CACHE_KEY, JSON.stringify({ result: false, ts: Date.now() }));
          return;
        }
      }

      // Full check (includes IP lookup via edge function)
      const isBanned = await checkBan(user?.id ?? null);
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ result: isBanned, ts: Date.now() }));
      if (isBanned) setBanned(true);
    }

    check();
  }, []);

  return (
    <>
      {children}
      {banned && <AccessDenied banned />}
    </>
  );
}
