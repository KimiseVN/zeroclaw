"use client";
import { useState, useRef, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import type { User } from "@supabase/supabase-js";
import Link from "next/link";
import AuthModal from "./AuthModal";
import styles from "./AuthButton.module.css";

type Props = {
  user: User | null;
  profile: { full_name: string | null; avatar_url: string | null; is_admin: boolean } | null;
};

export default function AuthButton({ user, profile }: Props) {
  const [open,      setOpen]      = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  async function signOut() {
    const sb = createClient();
    await sb.auth.signOut();
    window.location.href = "/";
  }

  // ── Not logged in → show Sign in button + modal ──────────────────────────
  if (!user) {
    return (
      <>
        <button className={styles.loginBtn} onClick={() => setModalOpen(true)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
            <polyline points="10 17 15 12 10 7"/>
            <line x1="15" y1="12" x2="3" y2="12"/>
          </svg>
          Sign in
        </button>
        <AuthModal isOpen={modalOpen} onClose={() => setModalOpen(false)} />
      </>
    );
  }

  // ── Logged in → avatar chip + dropdown ──────────────────────────────────
  const name     = profile?.full_name || user.email?.split("@")[0] || "User";
  const initials = name.split(" ").map((w: string) => w[0]).join("").slice(0, 2).toUpperCase();

  return (
    <div className={styles.wrap} ref={ref}>
      <button className={styles.chip} onClick={() => setOpen(o => !o)}>
        {profile?.avatar_url
          ? <img src={profile.avatar_url} className={styles.avatar} alt="" width={26} height={26} />
          : <span className={styles.initials}>{initials}</span>}
        <span className={styles.chipName}>{name.split(" ")[0]}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>

      {open && (
        <div className={styles.dropdown}>
          <Link href="/dashboard" className={styles.dropItem} onClick={() => setOpen(false)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
              <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
            </svg>
            My Account
          </Link>
          {profile?.is_admin && (
            <Link href="/admin" className={`${styles.dropItem} ${styles.adminLink}`} onClick={() => setOpen(false)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
              Admin Panel
            </Link>
          )}
          <div className={styles.sep} />
          <button className={`${styles.dropItem} ${styles.logout}`} onClick={signOut}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
