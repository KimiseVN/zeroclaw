"use client";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCart } from "@/lib/cart-context";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import type { User } from "@supabase/supabase-js";
import AuthButton from "./ui/AuthButton";
import NotificationBell from "./ui/NotificationBell";
import Link from "next/link";
import styles from "./Header.module.css";

type Profile = { full_name: string | null; avatar_url: string | null; is_admin: boolean };

export default function Header() {
  const [user,    setUser]    = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const { item, setCartOpen } = useCart();
  const { lang, toggle }      = useLanguage();

  useEffect(() => {
    const sb = createClient();

    async function load(u: User | null) {
      setUser(u);
      if (!u) { setProfile(null); return; }
      const { data } = await sb
        .from("profiles")
        .select("full_name, avatar_url, is_admin")
        .eq("id", u.id)
        .single();
      setProfile(data ?? null);
    }

    sb.auth.getUser().then(({ data: { user: u } }) => load(u));

    const { data: { subscription } } = sb.auth.onAuthStateChange((_evt, session) => {
      load(session?.user ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link href="/" className={styles.brand}>
          <img src="/assets/icon.png" alt="" width={32} height={32} />
          <span>WWM Overlay</span>
        </Link>

        <nav className={styles.nav}>
          <Link href="/#features">{T.nav.features[lang]}</Link>
          <Link href="/#demo">{T.nav.demo[lang]}</Link>
          <Link href="/#reforge">{T.nav.reforge[lang]}</Link>
          <Link href="/#pricing">{T.nav.pricing[lang]}</Link>
          <Link href="/#download">{T.nav.download[lang]}</Link>
          <Link href="/#faq">{T.nav.faq[lang]}</Link>
          <Link href="/#hours">{T.nav.hours[lang]}</Link>
        </nav>

        <div className={styles.actions}>
          {/* Language toggle */}
          <div className={styles.langToggle} role="group" aria-label="Language">
            <button
              className={`${styles.langBtn} ${lang === "en" ? styles.langActive : ""}`}
              onClick={() => lang !== "en" && toggle()}
            >EN</button>
            <button
              className={`${styles.langBtn} ${lang === "vi" ? styles.langActive : ""}`}
              onClick={() => lang !== "vi" && toggle()}
            >VI</button>
          </div>

          {/* Notification bell — logged-in users only */}
          {user && <NotificationBell userId={user.id} />}

          {/* Cart button */}
          <button
            className={styles.cartBtn}
            onClick={() => setCartOpen(true)}
            aria-label="Cart"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="9"  cy="21" r="1"/><circle cx="20" cy="21" r="1"/>
              <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
            </svg>
            {item && <span className={styles.cartBadge}>1</span>}
          </button>

          <AuthButton user={user} profile={profile} />
          <Link href="/#pricing" className="btn btn-primary">{T.nav.buyNow[lang]}</Link>
        </div>
      </div>
    </header>
  );
}
