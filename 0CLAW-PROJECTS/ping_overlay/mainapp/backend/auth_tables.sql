-- Auth tables for WWM Overlay API (run once on Neon)
-- These replace Supabase Auth

-- Email/password credentials (NULL hash = OAuth-only user)
CREATE TABLE IF NOT EXISTS public.user_auth (
  user_id       uuid PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
  password_hash text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- Refresh token store (rotating tokens)
CREATE TABLE IF NOT EXISTS public.refresh_tokens (
  token_hash  text        PRIMARY KEY,
  user_id     uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  expires_at  timestamptz NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON public.refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_exp  ON public.refresh_tokens (expires_at);

-- Auto-purge expired tokens (optional: run as a cron/scheduled job)
-- DELETE FROM public.refresh_tokens WHERE expires_at < now();

SELECT 'auth tables ready' AS status;
