-- ============================================================
--  WWM Overlay — Full database migration: Supabase → Neon
--  Generated: 2026-05-25
--  Tables: profiles, orders, licenses, payment_config,
--          site_settings, faq, demo_images, visits, clients,
--          notifications, referral_events, blacklist,
--          pending_referrals
-- ============================================================

-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Helper function: current_user_id() ───────────────────────────────────────
-- Equivalent of auth.uid() from Supabase; reads from app.user_id session var.
-- NOTE: defined BEFORE is_admin() which depends on profiles table.
CREATE OR REPLACE FUNCTION current_user_id() RETURNS uuid
  LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.user_id', true), '')::uuid;
$$;

-- ══════════════════════════════════════════════════════════════
--  TABLES
-- ══════════════════════════════════════════════════════════════

-- ── profiles ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.profiles (
  id              uuid PRIMARY KEY,
  email           text,
  full_name       text,
  avatar_url      text,
  is_admin        boolean      NOT NULL DEFAULT false,
  created_at      timestamptz           DEFAULT now(),
  referral_code   text         UNIQUE,
  referral_points integer      NOT NULL DEFAULT 0
);

-- ── Helper function: is_admin() ───────────────────────────────────────────────
-- Defined AFTER profiles table so PostgreSQL can validate the reference.
-- On Neon (no Supabase auth), reads app.user_id custom setting set by middleware.
CREATE OR REPLACE FUNCTION is_admin() RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT EXISTS (
      SELECT 1 FROM public.profiles
      WHERE id = NULLIF(current_setting('app.user_id', true), '')::uuid
        AND is_admin = true
    );
$$;

-- ── orders ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.orders (
  id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid        NOT NULL REFERENCES public.profiles(id),
  plan_id        text        NOT NULL,
  plan_label     text,
  amount_usd     numeric,
  amount_vnd     integer,
  payment_method text                 DEFAULT 'paypal',
  payment_ref    text,
  hwid           text,
  note           text,
  status         text        NOT NULL DEFAULT 'pending',
  created_at     timestamptz          DEFAULT now(),
  updated_at     timestamptz          DEFAULT now(),
  referral_code  text
);

-- ── licenses ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.licenses (
  id          uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id    uuid  REFERENCES public.orders(id),
  user_id     uuid  REFERENCES public.profiles(id),
  license_key text  NOT NULL UNIQUE,
  hwid        text,
  plan_id     text,
  plan_label  text,
  issued_at   timestamptz DEFAULT now(),
  expires_at  timestamptz,
  status      text        NOT NULL DEFAULT 'active',
  note        text
);

-- ── payment_config ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.payment_config (
  id         text  PRIMARY KEY,
  enabled    boolean NOT NULL DEFAULT false,
  config     jsonb   NOT NULL DEFAULT '{}',
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── site_settings ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.site_settings (
  key        text  PRIMARY KEY,
  value      jsonb NOT NULL DEFAULT '{}',
  updated_at timestamptz DEFAULT now()
);

-- ── faq ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.faq (
  id          uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
  question    text    NOT NULL,
  answer      text    NOT NULL,
  order_index integer NOT NULL DEFAULT 0,
  enabled     boolean NOT NULL DEFAULT true,
  created_at  timestamptz DEFAULT now()
);

-- ── demo_images ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.demo_images (
  id          uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
  url         text    NOT NULL,
  caption     text             DEFAULT '',
  order_index integer NOT NULL DEFAULT 0,
  enabled     boolean NOT NULL DEFAULT true
);

-- ── visits ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.visits (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ip           text,
  country      text,
  country_code text,
  city         text,
  lat          double precision,
  lng          double precision,
  page         text,
  visited_at   timestamptz DEFAULT now()
);

-- ── clients ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.clients (
  hwid              text        PRIMARY KEY,
  last_seen         timestamptz NOT NULL DEFAULT now(),
  app_version       text,
  public_ip         text,
  hostname          text,
  licensed_local    boolean     NOT NULL DEFAULT false,
  license_error     text,
  expires_at_local  text,
  duration          text,
  licensed_db       boolean     NOT NULL DEFAULT false,
  license_db_expires text,
  license_db_plan   text,
  banned            boolean     NOT NULL DEFAULT false,
  ban_reason        text,
  force_update      boolean     NOT NULL DEFAULT false,
  blocked_versions  text[]      NOT NULL DEFAULT '{}',
  trial_started_at  timestamptz,
  trial_expires_at  timestamptz,
  updated_at        timestamptz NOT NULL DEFAULT now()
);

-- ── notifications ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.notifications (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL REFERENCES public.profiles(id),
  type       text NOT NULL DEFAULT 'system',
  title      text NOT NULL,
  body       text NOT NULL,
  read       boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── referral_events ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.referral_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  referrer_id uuid NOT NULL REFERENCES public.profiles(id),
  referred_id uuid          REFERENCES public.profiles(id),
  event_type  text NOT NULL CHECK (event_type IN ('download', 'purchase')),
  points      integer NOT NULL DEFAULT 0,
  order_id    uuid          REFERENCES public.orders(id),
  meta        jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ── blacklist ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.blacklist (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid REFERENCES public.profiles(id),
  ip           text,
  route        text NOT NULL DEFAULT '',
  strike_count integer NOT NULL DEFAULT 1,
  is_banned    boolean NOT NULL DEFAULT false,
  notes        text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

-- ── pending_referrals ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.pending_referrals (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  referrer_id   uuid REFERENCES public.profiles(id),
  referral_code text NOT NULL,
  client_ip     text,
  claimed       boolean NOT NULL DEFAULT false,
  claimed_hwid  text,
  claimed_at    timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);


-- ══════════════════════════════════════════════════════════════
--  INDEXES
-- ══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_clients_last_seen          ON public.clients (last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_licenses_hwid_active       ON public.licenses (hwid, status, expires_at) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS notifications_user_created     ON public.notifications (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS referral_events_referrer       ON public.referral_events (referrer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS referral_events_order_id_idx   ON public.referral_events (order_id) WHERE order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS referral_events_download_ip_idx ON public.referral_events (referrer_id, event_type, (meta->>'ip')) WHERE event_type = 'download';
CREATE INDEX IF NOT EXISTS referral_events_referred_purchase_idx ON public.referral_events (referrer_id, referred_id, event_type) WHERE event_type = 'purchase';
CREATE INDEX IF NOT EXISTS blacklist_banned_idx            ON public.blacklist (is_banned) WHERE is_banned = true;
CREATE INDEX IF NOT EXISTS blacklist_ip_idx               ON public.blacklist (ip) WHERE ip IS NOT NULL;
CREATE INDEX IF NOT EXISTS blacklist_user_id_idx          ON public.blacklist (user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS visits_visited_at_idx          ON public.visits (visited_at DESC);
CREATE INDEX IF NOT EXISTS visits_country_code_idx        ON public.visits (country_code);
CREATE INDEX IF NOT EXISTS idx_pending_referrals_ip       ON public.pending_referrals (client_ip) WHERE NOT claimed;
CREATE INDEX IF NOT EXISTS idx_pending_referrals_hwid     ON public.pending_referrals (claimed_hwid) WHERE claimed_hwid IS NOT NULL;


-- ══════════════════════════════════════════════════════════════
--  ROW LEVEL SECURITY
--  Uses current_user_id() instead of auth.uid()
--  and is_admin() helper defined above.
--  Your API middleware must set:  SET LOCAL app.user_id = '<uuid>';
-- ══════════════════════════════════════════════════════════════

ALTER TABLE public.profiles         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.licenses         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payment_config   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_settings    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.faq              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.demo_images      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visits           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clients          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.referral_events  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.blacklist        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pending_referrals ENABLE ROW LEVEL SECURITY;

-- profiles
CREATE POLICY profiles_select ON public.profiles FOR SELECT USING (current_user_id() = id OR is_admin());
CREATE POLICY profiles_update ON public.profiles FOR UPDATE USING (current_user_id() = id);
CREATE POLICY profiles_admin  ON public.profiles FOR ALL    USING (is_admin());

-- orders
CREATE POLICY orders_select ON public.orders FOR SELECT USING (current_user_id() = user_id OR is_admin());
CREATE POLICY orders_insert ON public.orders FOR INSERT WITH CHECK (current_user_id() = user_id);
CREATE POLICY orders_admin  ON public.orders FOR ALL    USING (is_admin());

-- licenses
CREATE POLICY licenses_select ON public.licenses FOR SELECT USING (current_user_id() = user_id OR is_admin());
CREATE POLICY licenses_admin  ON public.licenses FOR ALL    USING (is_admin());

-- payment_config
CREATE POLICY payment_config_read  ON public.payment_config FOR SELECT USING (true);
CREATE POLICY payment_config_admin ON public.payment_config FOR ALL    USING (is_admin()) WITH CHECK (is_admin());

-- site_settings
CREATE POLICY site_settings_read  ON public.site_settings FOR SELECT USING (true);
CREATE POLICY site_settings_admin ON public.site_settings FOR ALL    USING (is_admin()) WITH CHECK (is_admin());

-- faq
CREATE POLICY faq_read  ON public.faq FOR SELECT USING (enabled = true);
CREATE POLICY faq_admin ON public.faq FOR ALL    USING (is_admin()) WITH CHECK (is_admin());

-- demo_images
CREATE POLICY demo_images_read  ON public.demo_images FOR SELECT USING (enabled = true);
CREATE POLICY demo_images_admin ON public.demo_images FOR ALL    USING (is_admin()) WITH CHECK (is_admin());

-- visits
CREATE POLICY visits_insert ON public.visits FOR INSERT WITH CHECK (true);
CREATE POLICY visits_read   ON public.visits FOR SELECT USING (is_admin());
CREATE POLICY visits_delete ON public.visits FOR DELETE USING (is_admin());

-- clients
CREATE POLICY clients_admin ON public.clients FOR ALL USING (is_admin()) WITH CHECK (is_admin());

-- notifications
CREATE POLICY notif_select_own   ON public.notifications FOR SELECT USING (current_user_id() = user_id);
CREATE POLICY notif_update_own   ON public.notifications FOR UPDATE USING (current_user_id() = user_id);
CREATE POLICY notif_insert_service ON public.notifications FOR INSERT WITH CHECK (true);

-- referral_events
CREATE POLICY ref_events_select_own     ON public.referral_events FOR SELECT USING (current_user_id() = referrer_id OR current_user_id() = referred_id);
CREATE POLICY ref_events_insert_service ON public.referral_events FOR INSERT WITH CHECK (true);

-- blacklist
CREATE POLICY blacklist_read_admin   ON public.blacklist FOR SELECT USING (is_admin());
CREATE POLICY blacklist_update_admin ON public.blacklist FOR UPDATE USING (is_admin());
CREATE POLICY blacklist_delete_admin ON public.blacklist FOR DELETE USING (is_admin());
CREATE POLICY blacklist_read_own     ON public.blacklist FOR SELECT USING (current_user_id() = user_id);

-- pending_referrals
-- (service-role only, no user-facing policy needed)


-- ══════════════════════════════════════════════════════════════
--  DATA — profiles (insert before other tables due to FKs)
-- ══════════════════════════════════════════════════════════════

INSERT INTO public.profiles (id, email, full_name, avatar_url, is_admin, created_at, referral_code, referral_points) VALUES
  ('6b146b33-74a2-4cd9-9122-1ed216b8c994', 'thuytk.cod@gmail.com',        'Kim Thuy Tong (Kimise)', 'https://lh3.googleusercontent.com/a/ACg8ocJi8Q5ZKviEZOQUTZyRrHFVwjjoqmSVLxmS5Z1AcDFQrB1PbRU=s96-c', true,  '2026-05-11T20:19:37.479288+00:00', 'NFDZ-ZJUG', 5),
  ('1c8a05fd-3fbb-43bd-bf0f-28c97b3a8002', 'lotusnguyen2691999@gmail.com', 'Cái Lùm Mía',           'https://cdn.discordapp.com/avatars/223155198145593344/a_0b3d3d307e60eee3a1f100f5a7ff5bd0.gif',  false, '2026-05-13T19:13:23.986880+00:00', '27Z2-THL5', 0),
  ('5265a30d-5184-4727-a007-6c59ee8005eb', 'dangtrinh.nguyen93@gmail.com', 'umbalala',               'https://cdn.discordapp.com/avatars/450417337946865685/0c2b6fa676cfcde131cfa376f49f5e69.png',   false, '2026-05-14T19:56:14.006902+00:00', NULL,        0),
  ('1f2ef061-13e2-4104-af25-5359f55286ad', 'datpro1236@gmail.com',         'cha_neo',                'https://cdn.discordapp.com/avatars/472690249458384907/ac60e3922ca214aa058b08c8f2cfa404.png',   false, '2026-05-15T20:18:02.699752+00:00', NULL,        0),
  ('68826473-e42d-45b7-9ccc-ad8832028dc2', 'tr.trung.le@gmail.com',        'murasame7680',           'https://cdn.discordapp.com/avatars/700041007374401626/64bf1fd18e09f6e63d629e35b1dfce82.png',   false, '2026-05-15T20:21:36.993065+00:00', NULL,        0),
  ('086eb405-49b1-4f0c-83c0-19d7d71984b2', 'kinmaters2019@gmail.com',      'lightiii_',              'https://cdn.discordapp.com/avatars/1211486459576721438/cb44f2b367343acbcdecb28dfc8a1e5a.png',  false, '2026-05-19T17:57:28.220142+00:00', NULL,        0)
ON CONFLICT (id) DO NOTHING;

-- ── licenses ─────────────────────────────────────────────────
INSERT INTO public.licenses (id, order_id, user_id, license_key, hwid, plan_id, plan_label, issued_at, expires_at, status, note) VALUES
  ('0cc940a2-49da-4ecd-8a94-456e95606478', NULL, '1c8a05fd-3fbb-43bd-bf0f-28c97b3a8002', 'PO1-H3OXEFDP2MVLOHUR-LT-0-076F961DF6201F9F1A71C1D21E4B6DAC',        'H3OXEFDP2MVLOHUR', 'lt',   'Lifetime', '2026-05-14T20:37:34.329141+00:00', NULL,                           'active', 'Gift'),
  ('183249cb-65ef-4401-951d-16fd3a1184cf', NULL, '1c8a05fd-3fbb-43bd-bf0f-28c97b3a8002', 'PO1-NCOQSRCYCA3WBOIH-LT-0-519C5B4B225999C66C9B82787A2A5ACA',        'NCOQSRCYCA3WBOIH', 'lt',   'Lifetime', '2026-05-14T20:38:50.317303+00:00', NULL,                           'active', 'Gift'),
  ('b8336e21-6047-4763-b9af-c6c756c5946f', NULL, '1f2ef061-13e2-4104-af25-5359f55286ad', 'PO1-626KK6RNCZH5PSBD-LT-0-734A0568621294B2011FC4EB8A944216',         '626KK6RNCZH5PSBD', 'lt',   'Lifetime', '2026-05-15T20:19:23.287742+00:00', NULL,                           'active', NULL),
  ('305b38ec-e893-4948-a983-d534d12b9d7d', NULL, '68826473-e42d-45b7-9ccc-ad8832028dc2', 'PO1-CH7UN3H4ECP7LZUP-LT-0-D43B7EED1A6621B8E18697C6CE360306',         'CH7UN3H4ECP7LZUP', 'lt',   'Lifetime', '2026-05-15T20:22:19.205690+00:00', NULL,                           'active', NULL),
  ('0e8809d9-4a32-4e6b-a60d-550b7ae252c8', NULL, '086eb405-49b1-4f0c-83c0-19d7d71984b2', 'PO1-UM3UDHJSYQ2Y7CW3-1MO-1781806092-2168F4BC75BE72E2C12D9AED168F4449', 'UM3UDHJSYQ2Y7CW3', '1mo', '1 Month',  '2026-05-19T18:08:13.406969+00:00', '2026-06-18T18:08:12.970+00:00', 'active', NULL),
  ('72a61b75-72f3-4c14-b769-e2e4807f6813', NULL, '6b146b33-74a2-4cd9-9122-1ed216b8c994', 'PO1-P4YBFTQACUSIJ2RZ-LT-0-9DECEEEA0322EE37CCE2D1F993A1E587',          'P4YBFTQACUSIJ2RZ', 'lt',   'Lifetime', '2026-05-23T09:11:50.308555+00:00', NULL,                           'active', NULL),
  ('220113e2-cf95-4d2f-923a-3815fe6723bb', NULL, '5265a30d-5184-4727-a007-6c59ee8005eb', 'PO1-JA2NXLCKQWAL7UMU-LT-0-E70954919FAD618B2FA50BFCDF336A6D',          'JA2NXLCKQWAL7UMU', 'lt',   'Lifetime', '2026-05-23T13:51:50.723720+00:00', NULL,                           'active', NULL)
ON CONFLICT (id) DO NOTHING;

-- ── payment_config ───────────────────────────────────────────
INSERT INTO public.payment_config (id, enabled, config, updated_at) VALUES
  ('stripe',  false, '{"plan_links":{"1d":"","7d":"","30d":"","90d":"","ltm":""}}',         '2026-05-11T22:30:23.959947+00:00'),
  ('usdt',    false, '{"address":"","network":"TRC20"}',                                    '2026-05-11T22:30:23.959947+00:00'),
  ('btc',     false, '{"address":""}',                                                      '2026-05-11T22:30:23.959947+00:00'),
  ('eth',     false, '{"address":"","network":"ERC20"}',                                    '2026-05-11T22:30:23.959947+00:00'),
  ('bank',    true,  '{"holder":"KIM THUY TONG","bank_id":"MB","account_no":"338141286","bank_label":"MB Bank"}', '2026-05-11T22:30:23.959947+00:00'),
  ('paypal',  true,  '{"email":"thuytk.cod@gmail.com","me_username":"wwmoverlay"}',          '2026-05-11T23:34:34.889+00:00')
ON CONFLICT (id) DO NOTHING;

-- ── site_settings ────────────────────────────────────────────
INSERT INTO public.site_settings (key, value, updated_at) VALUES
  ('trial',           '{"days":3}',                                                                                                              '2026-05-13T01:01:37.473+00:00'),
  ('auth_providers',  '{"github":false,"google":true,"discord":true,"twitter":false,"magic_link":true,"email_password":true}',                    '2026-05-13T13:45:30.415+00:00'),
  ('general',         '{"copyright":"WWM Overlay · ムKim - ぶMiêuGiaぶ Guild WWM Global. All rights reserved.","discord_url":"https://discord.com/users/1382397076889145444","show_visitor_stats":true}', '2026-05-13T14:56:40.352+00:00'),
  ('section_order',   '{"order":["referral_banner","features","demo","pricing","download","visitor_stats","faq","support_hours"],"hidden":[]}',    '2026-05-13T23:04:00.297+00:00'),
  ('referral_config', '{"enabled":true,"reward_days":7,"points_for_reward":10,"points_per_download":1,"points_per_purchase":2}',                  '2026-05-14T04:00:22.766+00:00'),
  ('business_hours',  '{"slots":[{"id":"wsluws8x","end_h":23,"end_m":59,"label":"","start_h":0,"start_m":0}],"is_24_7":true}',                    '2026-05-15T20:07:17.446+00:00'),
  ('download',        '{"url":"https://drive.google.com/drive/folders/1siTr6hr04bRWVX8ytYc8bCsPzZTlHvB_?usp=sharing","version":"1.0.86"}',        '2026-05-23T09:14:43.476+00:00')
ON CONFLICT (key) DO NOTHING;

-- ── faq ──────────────────────────────────────────────────────
INSERT INTO public.faq (id, question, answer, order_index, enabled, created_at) VALUES
  ('736d4e03-e00e-4b6a-8175-5bd530e7519c', 'Does the app inject into the game?',        'No. The app reads system and network process stats via a separate overlay window. No DLL injection — safe with anti-cheat (KingSoft, Easy Anti-Cheat, etc.).', 0, true, '2026-05-12T00:45:36.158398+00:00'),
  ('df5f13c1-0759-46b7-8a28-ad54a48359c0', 'How do licenses and trials work?',           'Free 24-hour trial based on HWID. After the trial, you need a license key. Licenses are verified via HWID and heartbeat backend. Contact Discord to purchase.', 1, true, '2026-05-12T00:45:36.158398+00:00'),
  ('9e96b26f-fd5a-4cda-ac26-9f6ac51819a0', 'What does Quest Helper need to work?',      'Quest Helper uses OCR to read the quest name from the screen. Press the hotkey (default Ctrl+F1) while the quest name is visible. The app auto-matches with its database and shows the walkthrough.', 2, true, '2026-05-12T00:45:36.158398+00:00'),
  ('854e1a4e-dff3-4e15-aa8e-23d85b227590', 'Does the overlay affect FPS?',              'Very little. The app uses a Tkinter window overlay with ~1s refresh and only renders on value changes. Real-world CPU overhead is under 0.5% on an average machine.', 3, true, '2026-05-12T00:45:36.158398+00:00'),
  ('a9e4e1a8-6598-40ec-b432-26151b8f5a40', 'Why does SmartScreen warn about it?',       'The app does not have a commercial code-signing certificate. SmartScreen warns about new unsigned executables — click "More info → Run anyway" to continue.', 4, true, '2026-05-12T00:45:36.158398+00:00'),
  ('46ab886d-7955-458e-88fe-9d8c87ae3a52', 'Does it work on low-RAM machines?',         'The app uses around 50–80 MB RAM when fully running. On 8 GB+ machines it won''t impact gameplay. You can disable individual metrics to reduce overhead.', 5, true, '2026-05-12T00:45:36.158398+00:00')
ON CONFLICT (id) DO NOTHING;

-- ── demo_images ──────────────────────────────────────────────
INSERT INTO public.demo_images (id, url, caption, order_index, enabled) VALUES
  ('8b59625e-6546-4c58-9403-6634e8f602bd', 'https://laglyewqpxefwpfhryso.supabase.co/storage/v1/object/public/demo-images/1778548558546-3kgkrdbaqcu.png', '', 0, true),
  ('0d48a591-e49f-45d2-85b9-3c46d2910b7b', 'https://laglyewqpxefwpfhryso.supabase.co/storage/v1/object/public/demo-images/1778548565683-xkwckbuwpn.png', '', 1, true),
  ('3d03809b-85b5-4706-8a14-1d881c7361bd', 'https://laglyewqpxefwpfhryso.supabase.co/storage/v1/object/public/demo-images/1778548572066-5xl8kjtx6bd.png', '', 2, true)
ON CONFLICT (id) DO NOTHING;

-- ── clients ──────────────────────────────────────────────────
INSERT INTO public.clients (hwid, last_seen, app_version, public_ip, hostname, licensed_local, license_error, expires_at_local, duration, licensed_db, license_db_expires, license_db_plan, banned, ban_reason, force_update, blocked_versions, trial_started_at, trial_expires_at, updated_at) VALUES
  ('H3OXEFDP2MVLOHUR', '2026-05-23T00:06:34.930+00:00', '1.0.75', '95.91.249.34',    'meomeo',         true,  NULL, 'lifetime', 'lt',   true,  NULL,                           'lt',   false, NULL, false, '{}', NULL, NULL, '2026-05-23T00:06:36.802284+00:00'),
  ('NCOQSRCYCA3WBOIH', '2026-05-23T22:31:28.317+00:00', '1.0.88', '145.224.83.207',  'TuanPC',         true,  NULL, 'lifetime', 'lt',   true,  NULL,                           'lt',   false, NULL, false, '{}', NULL, NULL, '2026-05-23T22:31:29.824228+00:00'),
  ('JA2NXLCKQWAL7UMU', '2026-05-23T22:26:58.468+00:00', '1.0.86', '79.161.233.211',  'Potato',         true,  NULL, 'lifetime', 'lt',   true,  NULL,                           'lt',   false, NULL, false, '{}', NULL, NULL, '2026-05-23T22:26:58.875882+00:00'),
  ('P4YBFTQACUSIJ2RZ', '2026-05-23T15:36:53.535+00:00', '1.0.88', '31.18.8.130',     'Kim-AI',         true,  NULL, 'lifetime', 'lt',   true,  NULL,                           'lt',   false, NULL, false, '{}', NULL, NULL, '2026-05-23T15:36:53.967669+00:00'),
  ('CH7UN3H4ECP7LZUP', '2026-05-15T22:41:41.995+00:00', '1.0.52', '176.135.44.134',  'Trung',          true,  NULL, 'lifetime', 'lt',   true,  NULL,                           'lt',   false, NULL, false, '{}', NULL, NULL, '2026-05-15T22:41:43.198422+00:00'),
  ('626KK6RNCZH5PSBD', '2026-05-19T22:04:46.578+00:00', '1.0.55', '79.214.246.164',  'thu-ha',         true,  NULL, 'lifetime', 'lt',   true,  NULL,                           'lt',   false, NULL, false, '{}', NULL, NULL, '2026-05-19T22:04:47.567900+00:00'),
  ('UM3UDHJSYQ2Y7CW3', '2026-05-23T22:33:07.105+00:00', '1.0.88', '92.208.164.203',  'Minh',           false, NULL, NULL,       NULL,   true,  '2026-06-18T18:08:12.97+00:00', '1mo', false, NULL, false, '{}', NULL, NULL, '2026-05-23T22:33:08.658793+00:00'),
  ('6MHYWQGRVMD7UCKP', '2026-05-20T22:23:55.099+00:00', '1.0.63', '79.161.233.211',  'Potato',         true,  NULL, 'lifetime', 'lt',   true,  NULL,                           'lt',   false, NULL, false, '{}', NULL, NULL, '2026-05-21T15:21:06.955665+00:00'),
  ('4MPHXGYIUAHGBQZL', '2026-05-21T16:29:53.052+00:00', '1.0.76', '1.55.210.223',    'DESKTOP-SG0GLNK', false, NULL, NULL,       NULL,   false, NULL,                           NULL,   false, NULL, false, '{}', NULL, NULL, '2026-05-21T16:29:54.057640+00:00'),
  ('G76BGEVD6UDJXPOX', '2026-05-20T22:15:46.758+00:00', '1.0.76', '92.208.164.231',  'Minh',           false, NULL, NULL,       NULL,   false, NULL,                           NULL,   false, NULL, false, '{}', NULL, NULL, '2026-05-20T22:15:47.870422+00:00'),
  ('AFUQP66OHI4KKWFT', '2026-05-16T08:49:28.297+00:00', '1.0.52', '178.76.242.166',  'DESKTOP-D3HEHFV', false, NULL, NULL,       NULL,   false, NULL,                           NULL,   false, NULL, false, '{}', NULL, NULL, '2026-05-16T08:49:29.785299+00:00'),
  ('HE2INAXSYQPA3E4Q', '2026-05-13T07:01:27.142+00:00', '1.0.31', '118.71.64.249',   'NgoThien',       false, NULL, NULL,       NULL,   false, NULL,                           NULL,   false, NULL, false, '{}', NULL, NULL, '2026-05-13T07:01:28.479285+00:00'),
  ('YFL3RPIJXFTCKHLI', '2026-05-13T14:55:06.540+00:00', '1.0.31', '115.74.131.57',   'ADMIN-PC',       false, NULL, NULL,       NULL,   false, NULL,                           NULL,   false, NULL, false, '{}', NULL, NULL, '2026-05-13T14:55:06.916517+00:00'),
  ('O7MELNYR7XOCF2XW', '2026-05-13T23:20:20.395+00:00', '1.0.31', '79.214.246.164',  'thu-ha',         false, NULL, NULL,       NULL,   false, NULL,                           NULL,   false, NULL, false, '{}', NULL, NULL, '2026-05-13T23:20:21.530444+00:00')
ON CONFLICT (hwid) DO NOTHING;

-- ── notifications ────────────────────────────────────────────
INSERT INTO public.notifications (id, user_id, type, title, body, read, created_at) VALUES
  ('d9703a5b-a4e9-41f5-9229-2a64b97240fb', '6b146b33-74a2-4cd9-9122-1ed216b8c994', 'referral', '⬇️ New referral download',            'Someone downloaded the app using your referral code. +1 point. (1/50)', true, '2026-05-13T21:03:35.895560+00:00'),
  ('11dfb76d-ca42-470a-a7ae-2fe1a3906b83', '6b146b33-74a2-4cd9-9122-1ed216b8c994', 'referral', '⬇️ New referral download',            'Someone downloaded the app using your referral code. +1 point. (2/50)', true, '2026-05-13T21:06:34.731693+00:00'),
  ('027150a4-2bd5-4f40-af2a-a91326dbe850', '6b146b33-74a2-4cd9-9122-1ed216b8c994', 'referral', '⬇️ New referral download',            'Someone downloaded the app using your referral code. +1 pt. (3/50)',   true, '2026-05-13T21:19:21.138398+00:00'),
  ('c2d33f63-fd52-47b4-9239-d928dc3a7f10', '6b146b33-74a2-4cd9-9122-1ed216b8c994', 'referral', '⬇️ New referral download',            'Someone downloaded the app using your referral code. +1 pt. (4/10)',   true, '2026-05-16T18:19:41.942872+00:00'),
  ('bd9d93f2-5d8a-4862-9fa3-37b7f41dc543', '6b146b33-74a2-4cd9-9122-1ed216b8c994', 'referral', '⬇️ Referral app launch confirmed',    'Someone launched the app via your referral link. +1 pt. (5/10)',       true, '2026-05-18T19:17:09.560076+00:00')
ON CONFLICT (id) DO NOTHING;

-- ── referral_events ──────────────────────────────────────────
INSERT INTO public.referral_events (id, referrer_id, referred_id, event_type, points, order_id, meta, created_at) VALUES
  ('8d9497af-d71e-4e6c-b7cb-99a454e822da', '6b146b33-74a2-4cd9-9122-1ed216b8c994', NULL, 'download', 1, NULL, '{"referral_code":"NFDZ-ZJUG"}',                        '2026-05-13T21:03:35.218647+00:00'),
  ('ac4a1d3c-d647-4eae-b764-febb454e3314', '6b146b33-74a2-4cd9-9122-1ed216b8c994', NULL, 'download', 1, NULL, '{"referral_code":"NFDZ-ZJUG"}',                        '2026-05-13T21:06:34.347364+00:00'),
  ('2acc2fe7-0e46-4cd3-a56c-edd567344b8f', '6b146b33-74a2-4cd9-9122-1ed216b8c994', NULL, 'download', 1, NULL, '{"ip":"31.18.8.130","referral_code":"NFDZ-ZJUG"}',      '2026-05-13T21:19:20.768580+00:00'),
  ('97e04c5f-b430-4002-b2ba-73e64a05d9ad', '6b146b33-74a2-4cd9-9122-1ed216b8c994', NULL, 'download', 1, NULL, '{"ip":"62.26.157.34","referral_code":"NFDZ-ZJUG"}',     '2026-05-16T18:19:41.575836+00:00')
ON CONFLICT (id) DO NOTHING;

-- ── blacklist ────────────────────────────────────────────────
INSERT INTO public.blacklist (id, user_id, ip, route, strike_count, is_banned, notes, created_at, updated_at) VALUES
  ('1eb0792e-b6d4-4187-b623-3f5a306a9df7', NULL, '31.18.8.130', '/akimxiu', 1, false, NULL, '2026-05-23T16:17:27.107043+00:00', '2026-05-23T16:17:27.107043+00:00')
ON CONFLICT (id) DO NOTHING;

-- ── pending_referrals ────────────────────────────────────────
INSERT INTO public.pending_referrals (id, referrer_id, referral_code, client_ip, claimed, claimed_hwid, claimed_at, created_at) VALUES
  ('7bfdd7f1-8f21-4ac2-b3b2-867888f5018b', '6b146b33-74a2-4cd9-9122-1ed216b8c994', 'NFDZ-ZJUG', '31.18.8.130', true,  'P4YBFTQACUSIJ2RZ', '2026-05-18T19:17:08.869+00:00', '2026-05-17T02:49:38.582220+00:00'),
  ('11db9e04-86be-4c21-9e5d-3b7d20a891d4', '6b146b33-74a2-4cd9-9122-1ed216b8c994', 'NFDZ-ZJUG', '31.18.8.130', false, NULL,               NULL,                           '2026-05-19T03:39:03.242854+00:00'),
  ('651ecbf7-a714-450e-b311-58ffae32e122', '6b146b33-74a2-4cd9-9122-1ed216b8c994', 'NFDZ-ZJUG', '31.18.8.130', false, NULL,               NULL,                           '2026-05-20T22:04:57.393800+00:00'),
  ('f799cf11-770a-4f2c-b056-d27e1fbafa09', '6b146b33-74a2-4cd9-9122-1ed216b8c994', 'NFDZ-ZJUG', '31.18.8.130', false, NULL,               NULL,                           '2026-05-23T09:16:58.357923+00:00')
ON CONFLICT (id) DO NOTHING;

-- ── visits: too many to inline — skip historical data ────────
-- visits table (234 rows) is analytics-only. It will auto-populate
-- as real users visit the site on Neon. Historical data is not critical.
-- To migrate if needed: pg_dump -t visits from Supabase → psql Neon.

-- ══════════════════════════════════════════════════════════════
--  VERIFY ROW COUNTS
-- ══════════════════════════════════════════════════════════════
SELECT 'profiles'         AS tbl, COUNT(*) FROM public.profiles         UNION ALL
SELECT 'licenses',               COUNT(*) FROM public.licenses          UNION ALL
SELECT 'clients',                COUNT(*) FROM public.clients           UNION ALL
SELECT 'payment_config',         COUNT(*) FROM public.payment_config    UNION ALL
SELECT 'site_settings',          COUNT(*) FROM public.site_settings     UNION ALL
SELECT 'faq',                    COUNT(*) FROM public.faq               UNION ALL
SELECT 'demo_images',            COUNT(*) FROM public.demo_images       UNION ALL
SELECT 'notifications',          COUNT(*) FROM public.notifications     UNION ALL
SELECT 'referral_events',        COUNT(*) FROM public.referral_events   UNION ALL
SELECT 'blacklist',              COUNT(*) FROM public.blacklist         UNION ALL
SELECT 'pending_referrals',      COUNT(*) FROM public.pending_referrals
ORDER BY 1;
