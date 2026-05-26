export type Plan = {
  id: string;
  days: number;
  label: { en: string; vi: string };
  usd: number;
  vnd: number;
  badge?: { en: string; vi: string };
  cls?: string;
  paypalUrl: string;
  features: { en: string[]; vi: string[] };
};

export const PLANS: Plan[] = [
  {
    id: "1d", days: 1,
    label:   { en: "1 Day",    vi: "1 Ngày"    },
    usd: 0.50, vnd: 12_000, badge: undefined,
    paypalUrl: "https://www.paypal.com/ncp/payment/RHPYMYJ4EV64J",
    features: {
      en: ["Good trial option", "Full overlay", "Network + FPS"],
      vi: ["Trial tốt để thử", "Full overlay", "Network + FPS"],
    },
  },
  {
    id: "7d", days: 7,
    label:   { en: "7 Days",   vi: "7 Ngày"    },
    usd: 3.00, vnd: 75_000, badge: undefined,
    paypalUrl: "https://www.paypal.com/ncp/payment/ULAP5WQBLDY4E",
    features: {
      en: ["1 week of use", "Full overlay", "Quest Helper", "Game Tweaks"],
      vi: ["1 tuần sử dụng", "Full overlay", "Quest Helper", "Game Tweaks"],
    },
  },
  {
    id: "30d", days: 30,
    label:   { en: "30 Days",  vi: "30 Ngày"   },
    usd: 10.00, vnd: 250_000,
    badge: { en: "Most Popular", vi: "Phổ biến nhất" }, cls: "popular",
    paypalUrl: "https://www.paypal.com/ncp/payment/753UMNZUD3MVS",
    features: {
      en: ["1 month of use", "All features", "Quest + Encounter", "Game Tweaks", "Auto update"],
      vi: ["1 tháng sử dụng", "Full tính năng", "Quest + Encounter", "Game Tweaks", "Auto update"],
    },
  },
  {
    id: "90d", days: 90,
    label:   { en: "90 Days",  vi: "90 Ngày"   },
    usd: 25.00, vnd: 625_000, badge: undefined,
    paypalUrl: "https://www.paypal.com/ncp/payment/YS9HS96XSK3T4",
    features: {
      en: ["3 months of use", "All features", "Quest + Encounter", "Game Tweaks", "Auto update"],
      vi: ["3 tháng sử dụng", "Full tính năng", "Quest + Encounter", "Game Tweaks", "Auto update"],
    },
  },
  {
    id: "ltm", days: -1,
    label:   { en: "Lifetime", vi: "Lifetime"  },
    usd: 50.00, vnd: 1_250_000,
    badge: { en: "Best Value", vi: "Tốt nhất" }, cls: "best",
    paypalUrl: "https://www.paypal.com/ncp/payment/TBZRBXLBT2DB8",
    features: {
      en: ["Use forever", "All features", "Quest + Encounter", "Game Tweaks", "All future updates"],
      vi: ["Dùng mãi mãi", "Full tính năng", "Quest + Encounter", "Game Tweaks", "Tất cả update sau này"],
    },
  },
];

// Fallback values only — the live site reads download URL + version from
// Supabase site_settings (key = "download") via useDownloadSettings().
// Update these only as a last-resort static fallback.
export const RELEASE = {
  version:     "1.0.28",
  downloadUrl: "https://github.com/KimiseVN/wwm-overlay/releases/latest",
};

export const BANK = {
  bankId:    "MB",
  account:   "338141286",
  holder:    "KIM THUY TONG",
  bankLabel: "MB Bank",
};
