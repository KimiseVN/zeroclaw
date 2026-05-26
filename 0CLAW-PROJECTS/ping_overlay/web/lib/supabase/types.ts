export type AuthProviders = {
  email_password: boolean;
  magic_link:     boolean;
  google:         boolean;
  discord:        boolean;
  github:         boolean;
  twitter:        boolean;
};

export type SiteSetting = {
  key: string;
  value: Record<string, any>;
  updated_at: string;
};

export type FaqItem = {
  id: string;
  question:    string;       // EN
  question_vi: string | null; // VI
  answer:      string;       // EN
  answer_vi:   string | null; // VI
  order_index: number;
  enabled: boolean;
  created_at: string;
};

export type DemoImage = {
  id: string;
  url: string;
  caption: string;
  order_index: number;
  enabled: boolean;
};

export type PaymentConfig = {
  id:         string;
  enabled:    boolean;
  config:     Record<string, any>;
  updated_at: string;
};

export type Profile = {
  id: string;
  email: string | null;
  full_name: string | null;
  avatar_url: string | null;
  is_admin: boolean;
  referral_code: string | null;
  referral_points: number;
  created_at: string;
};

export type Notification = {
  id: string;
  user_id: string;
  type: "license" | "referral" | "system";
  title: string;
  body: string;
  read: boolean;
  created_at: string;
};

export type ReferralEvent = {
  id: string;
  referrer_id: string;
  referred_id: string | null;
  event_type: "download" | "purchase";
  points: number;
  order_id: string | null;
  meta: Record<string, any>;
  created_at: string;
};

export type Order = {
  id: string;
  user_id: string;
  plan_id: string;
  plan_label: string | null;
  amount_usd: number;
  amount_vnd: number;
  payment_method: "paypal" | "bank";
  payment_ref: string | null;
  hwid: string | null;
  note: string | null;
  status: "pending" | "paid" | "rejected";
  created_at: string;
  updated_at: string;
  // joined
  profiles?: Pick<Profile, "email" | "full_name" | "avatar_url">;
};

export type AppClient = {
  hwid:               string;
  last_seen:          string;
  app_version:        string | null;
  public_ip:          string | null;
  hostname:           string | null;
  licensed_local:     boolean;   // offline HMAC result the app reported
  license_error:      string | null;
  expires_at_local:   string | null;
  duration:           string | null;
  licensed_db:        boolean;   // active license found in licenses table
  license_db_expires: string | null;
  license_db_plan:    string | null;
  banned:             boolean;
  ban_reason:         string | null;
  force_update:       boolean;
  blocked_versions:   string[];
  trial_started_at:   string | null;
  trial_expires_at:   string | null;
  updated_at:         string;
};

export type BlacklistEntry = {
  id:           string;
  user_id:      string | null;
  ip:           string | null;
  route:        string;
  strike_count: number;
  is_banned:    boolean;
  notes:        string | null;
  created_at:   string;
  updated_at:   string;
  // joined
  profiles?: Pick<Profile, "email" | "full_name"> | null;
};

export type License = {
  id: string;
  order_id: string | null;
  user_id: string | null;          // null = floating (not yet claimed by a user)
  license_key: string;
  hwid: string | null;
  plan_id: string | null;
  plan_label: string | null;
  note: string | null;             // admin internal note
  issued_at: string;
  expires_at: string | null;
  status: "active" | "revoked" | "expired";
  // joined
  profiles?: Pick<Profile, "email" | "full_name">;
  orders?: Pick<Order, "plan_label" | "payment_method">;
};
