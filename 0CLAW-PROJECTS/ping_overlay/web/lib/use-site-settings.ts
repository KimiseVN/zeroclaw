"use client";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { AuthProviders } from "@/lib/supabase/types";
import { PLANS, type Plan } from "@/lib/plans";

export type GeneralSettings = {
  discord_url:          string;
  copyright:            string;
  show_visitor_stats:   boolean; // toggle "Players Around the World" section on homepage
};

export type TimeSlot = {
  id: string;          // uuid for stable key
  label: string;       // e.g. "Morning", "Afternoon" — optional display label
  start_h: number;
  start_m: number;
  end_h: number;
  end_m: number;
};

export type BusinessHours = {
  is_24_7: boolean;
  slots:   TimeSlot[];
};

export type DownloadSettings = {
  url: string;
  version: string;
};

export type TrialSettings = {
  /** Number of free trial days granted on first launch (default 1). */
  days: number;
};

export type { AuthProviders };

const DEFAULT_SLOT: TimeSlot = { id: "default", label: "", start_h: 2, start_m: 0, end_h: 17, end_m: 30 };

const DEFAULT_AUTH_PROVIDERS: AuthProviders = {
  email_password: true,
  magic_link:     true,
  google:         true,
  discord:        false,
  github:         false,
  twitter:        false,
};

const DEFAULTS = {
  general:        { discord_url: "https://discord.gg/zeroclaw", copyright: "WWM Overlay. All rights reserved.", show_visitor_stats: true } as GeneralSettings,
  business_hours: { is_24_7: false, slots: [DEFAULT_SLOT] } as BusinessHours,
  download:       { url: "", version: "" } as DownloadSettings,
  trial:          { days: 1 } as TrialSettings,
  auth_providers: DEFAULT_AUTH_PROVIDERS,
};

export function useGeneralSettings() {
  const [val, setVal] = useState<GeneralSettings>(DEFAULTS.general);
  useEffect(() => {
    createClient().from("site_settings").select("value").eq("key", "general").single()
      .then(({ data }) => { if (data?.value) setVal(data.value as GeneralSettings); });
  }, []);
  return val;
}

export function useBusinessHours() {
  const [val, setVal] = useState<BusinessHours>(DEFAULTS.business_hours);
  useEffect(() => {
    createClient().from("site_settings").select("value").eq("key", "business_hours").single()
      .then(({ data }) => {
        if (!data?.value) return;
        const raw = data.value as Record<string, any>;
        // Migrate old single-slot format → new multi-slot format
        const is24 = raw.is_24_7 === true;
        if (Array.isArray(raw.slots)) {
          setVal({ is_24_7: is24, slots: raw.slots as TimeSlot[] });
        } else if (raw.start_h !== undefined) {
          setVal({ is_24_7: is24, slots: [{ id: "migrated", label: "", start_h: raw.start_h, start_m: raw.start_m, end_h: raw.end_h, end_m: raw.end_m }] });
        } else {
          setVal(prev => ({ ...prev, is_24_7: is24 }));
        }
      });
  }, []);
  return val;
}

export function useDownloadSettings() {
  const [val, setVal] = useState<DownloadSettings>(DEFAULTS.download);
  useEffect(() => {
    createClient().from("site_settings").select("value").eq("key", "download").single()
      .then(({ data }) => { if (data?.value) setVal(data.value as DownloadSettings); });
  }, []);
  return val;
}

export function useTrialSettings() {
  const [val, setVal] = useState<TrialSettings>(DEFAULTS.trial);
  useEffect(() => {
    createClient().from("site_settings").select("value").eq("key", "trial").single()
      .then(({ data }) => {
        if (!data?.value) return;
        const days = (data.value as any).days;
        if (typeof days === "number" && days >= 1) setVal({ days: Math.round(days) });
      });
  }, []);
  return val;
}

export function useAuthProviders() {
  const [val, setVal] = useState<AuthProviders>(DEFAULT_AUTH_PROVIDERS);
  useEffect(() => {
    createClient().from("site_settings").select("value").eq("key", "auth_providers").single()
      .then(({ data }) => {
        if (data?.value) setVal({ ...DEFAULT_AUTH_PROVIDERS, ...(data.value as Partial<AuthProviders>) });
      });
  }, []);
  return val;
}

export type ReferralConfig = {
  enabled:              boolean;
  points_per_download:  number;
  points_per_purchase:  number;
  points_for_reward:    number;
  reward_days:          number;
};

const DEFAULT_REFERRAL: ReferralConfig = {
  enabled:             true,
  points_per_download: 1,
  points_per_purchase: 10,
  points_for_reward:   50,
  reward_days:         30,
};

export function useReferralConfig() {
  const [val, setVal] = useState<ReferralConfig>(DEFAULT_REFERRAL);
  useEffect(() => {
    createClient().from("site_settings").select("value").eq("key", "referral_config").single()
      .then(({ data }) => {
        if (data?.value) setVal({ ...DEFAULT_REFERRAL, ...(data.value as Partial<ReferralConfig>) });
      });
  }, []);
  return val;
}

export type SectionId =
  | "features" | "demo" | "pricing" | "download"
  | "referral_banner" | "visitor_stats" | "faq" | "support_hours";

export type SectionOrderConfig = {
  order:  SectionId[];
  hidden: SectionId[];
};

export const ALL_SECTION_IDS: SectionId[] = [
  "features", "demo", "pricing", "download",
  "referral_banner", "visitor_stats", "faq", "support_hours",
];

const DEFAULT_SECTION_ORDER: SectionOrderConfig = {
  order:  ALL_SECTION_IDS,
  hidden: [],
};

export function useSectionOrder() {
  const [val, setVal] = useState<SectionOrderConfig>(DEFAULT_SECTION_ORDER);
  useEffect(() => {
    createClient().from("site_settings").select("value").eq("key", "section_order").single()
      .then(({ data }) => {
        if (!data?.value) return;
        const raw = data.value as Partial<SectionOrderConfig>;
        // Merge with defaults: keep any new sections not yet in saved order
        const savedOrder  = Array.isArray(raw.order)  ? (raw.order  as SectionId[]) : ALL_SECTION_IDS;
        const savedHidden = Array.isArray(raw.hidden) ? (raw.hidden as SectionId[]) : [];
        // Append any new sections (added after last save) at the end
        const missing = ALL_SECTION_IDS.filter(id => !savedOrder.includes(id));
        setVal({ order: [...savedOrder, ...missing], hidden: savedHidden });
      });
  }, []);
  return val;
}

/** Format trial days as human-readable label, e.g. 1 → "24h", 3 → "3-day", 7 → "7-day" */
export function fmtTrialLabel(days: number): string {
  if (days === 1) return "24h";
  return `${days}-day`;
}

/**
 * Returns the live pricing plans from site_settings (key "pricing_plans").
 * Falls back to the static PLANS constant when no DB override exists.
 * The hook merges saved overrides onto static plan defaults field-by-field,
 * so partial saves still work correctly.
 */
export function usePricingPlans(): Plan[] {
  const [plans, setPlans] = useState<Plan[]>(PLANS);

  useEffect(() => {
    createClient()
      .from("site_settings")
      .select("value")
      .eq("key", "pricing_plans")
      .maybeSingle()
      .then(({ data }) => {
        if (!data?.value) return;
        const saved = (data.value as any).plans;
        if (!Array.isArray(saved)) return;

        setPlans(
          PLANS.map(staticPlan => {
            const override = (saved as any[]).find((s: any) => s.id === staticPlan.id);
            if (!override) return staticPlan;
            return {
              ...staticPlan,
              usd:      typeof override.usd      === "number" ? override.usd      : staticPlan.usd,
              vnd:      typeof override.vnd      === "number" ? override.vnd      : staticPlan.vnd,
              paypalUrl: typeof override.paypalUrl === "string" ? override.paypalUrl : staticPlan.paypalUrl,
              badge:    override.badge  ?? staticPlan.badge,
              cls:      override.cls   ?? staticPlan.cls,
              features: (override.features?.en?.length || override.features?.vi?.length)
                ? override.features as Plan["features"]
                : staticPlan.features,
            };
          }),
        );
      });
  }, []);

  return plans;
}
