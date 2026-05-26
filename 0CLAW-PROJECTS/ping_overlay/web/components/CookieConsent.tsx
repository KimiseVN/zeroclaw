"use client";
import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { useCookieConsent } from "@/lib/cookie-consent";
import styles from "./CookieConsent.module.css";

export default function CookieConsent() {
  const { prefs, showBanner, acceptAll, rejectAll, saveCustom } = useCookieConsent();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [analytics,    setAnalytics]    = useState(false);
  const [preferences,  setPreferences]  = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  // Sync local state when prefs load
  useEffect(() => {
    setAnalytics(prefs.analytics);
    setPreferences(prefs.preferences);
  }, [prefs.analytics, prefs.preferences]);

  if (!mounted || !showBanner) return null;

  function openSettings() {
    setAnalytics(prefs.analytics);
    setPreferences(prefs.preferences);
    setSettingsOpen(true);
  }

  function handleSave() {
    saveCustom(analytics, preferences);
    setSettingsOpen(false);
  }

  function handleAcceptAll() {
    setSettingsOpen(false);
    acceptAll();
  }

  // ── Settings Modal ─────────────────────────────────────────────────────────
  const modal = settingsOpen && (
    <div className={styles.backdrop} onClick={e => { if (e.target === e.currentTarget) setSettingsOpen(false); }}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <div className={styles.modalTitle}>Cookie Settings</div>
          <p className={styles.modalSub}>
            Customise which cookies WWM Overlay may store. Essential cookies are always enabled as they are required for the site to function.
          </p>
        </div>

        <div className={styles.categories}>
          {/* Essential — always on */}
          <div className={`${styles.category} ${styles.active}`}>
            <div className={styles.catHeader}>
              <span className={styles.catIcon}>🔒</span>
              <div className={styles.catInfo}>
                <p className={styles.catName}>
                  Essential
                  <span className={styles.catBadge}>Always on</span>
                </p>
                <p className={styles.catDesc}>
                  Authentication session, security tokens, and cookie consent preference. Required for login, checkout, and all core site functions. Cannot be disabled.
                </p>
              </div>
              <button className={`${styles.toggle} ${styles.on} ${styles.disabled}`} disabled aria-checked={true} role="switch">
                <div className={styles.toggleThumb} />
              </button>
            </div>
            <div style={{ paddingLeft: 30, paddingTop: 4 }}>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Includes: Supabase auth session · CSRF token · consent record</span>
            </div>
          </div>

          {/* Analytics */}
          <div className={`${styles.category} ${analytics ? styles.active : ""}`}>
            <div className={styles.catHeader}>
              <span className={styles.catIcon}>📊</span>
              <div className={styles.catInfo}>
                <p className={styles.catName}>Analytics</p>
                <p className={styles.catDesc}>
                  Anonymous visit tracking: country, city, and approximate location. Powers the "Players Around the World" globe on the homepage. No personal data is stored beyond your approximate region.
                </p>
              </div>
              <button
                className={`${styles.toggle} ${analytics ? styles.on : ""}`}
                onClick={() => setAnalytics(v => !v)}
                role="switch"
                aria-checked={analytics}
              >
                <div className={styles.toggleThumb} />
              </button>
            </div>
            <div style={{ paddingLeft: 30, paddingTop: 4 }}>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Includes: visit session flag (sessionStorage) · IP geolocation (server-side, not stored)</span>
            </div>
          </div>

          {/* Preferences */}
          <div className={`${styles.category} ${preferences ? styles.active : ""}`}>
            <div className={styles.catHeader}>
              <span className={styles.catIcon}>⚙️</span>
              <div className={styles.catInfo}>
                <p className={styles.catName}>Preferences</p>
                <p className={styles.catDesc}>
                  Remembers your UI choices such as display preferences. Helps maintain a consistent experience across visits.
                </p>
              </div>
              <button
                className={`${styles.toggle} ${preferences ? styles.on : ""}`}
                onClick={() => setPreferences(v => !v)}
                role="switch"
                aria-checked={preferences}
              >
                <div className={styles.toggleThumb} />
              </button>
            </div>
            <div style={{ paddingLeft: 30, paddingTop: 4 }}>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Includes: UI settings stored in localStorage</span>
            </div>
          </div>
        </div>

        <div className={styles.modalActions}>
          <button className={styles.btnCustom} onClick={handleSave}>
            Save my choices
          </button>
          <button className={styles.btnAccept} onClick={handleAcceptAll}>
            Accept all
          </button>
        </div>

        <p style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center", marginTop: 14, marginBottom: 0, lineHeight: 1.6 }}>
          Read our <Link href="/privacy" style={{ color: "var(--cyan)" }}>Privacy Policy</Link> and{" "}
          <Link href="/terms" style={{ color: "var(--cyan)" }}>Terms of Service</Link> for full details.
        </p>
      </div>
    </div>
  );

  // ── Banner ─────────────────────────────────────────────────────────────────
  const banner = (
    <div className={styles.banner}>
      <span className={styles.bannerIcon}>🍪</span>
      <div className={styles.bannerContent}>
        <p className={styles.bannerTitle}>We use cookies</p>
        <p className={styles.bannerText}>
          We use essential cookies to keep the site running and optional analytics to understand how players find us. No ads, no tracking for profit.{" "}
          <Link href="/privacy">Privacy Policy</Link>
        </p>
      </div>
      <div className={styles.bannerActions}>
        <button className={styles.btnAccept} onClick={acceptAll}>Accept all</button>
        <button className={styles.btnCustom} onClick={openSettings}>Customise</button>
        <button className={styles.btnReject} onClick={rejectAll}>Essential only</button>
      </div>
    </div>
  );

  return createPortal(
    <>
      {banner}
      {modal}
    </>,
    document.body,
  );
}
