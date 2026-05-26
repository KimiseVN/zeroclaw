"use client";
import Link from "next/link";
import { useGeneralSettings } from "@/lib/use-site-settings";
import { useCookieConsent } from "@/lib/cookie-consent";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import styles from "./Footer.module.css";

export default function Footer() {
  const year    = new Date().getFullYear();
  const general = useGeneralSettings();
  const discord = general.discord_url || "https://discord.gg/zeroclaw";
  const { openSettings } = useCookieConsent();
  const { lang } = useLanguage();
  const f = T.footer;

  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <div className={styles.top}>
          {/* Brand */}
          <div className={styles.brandCol}>
            <Link href="/" className={styles.brand}>
              <img src="/assets/icon.png" alt="WWM Overlay" width={28} height={28} />
              WWM Overlay
            </Link>
            <p className={styles.tagline}>{f.tagline[lang]}</p>
            <div className={styles.socials}>
              <a href={discord} target="_blank" rel="noreferrer" className={styles.socialBtn}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20.317 4.37a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057c.002.022.015.043.033.055a19.93 19.93 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03z"/>
                </svg>
                Discord
              </a>
            </div>
          </div>

          {/* Link columns */}
          <div className={styles.cols}>
            <div className={styles.col}>
              <h4>{f.product[lang]}</h4>
              <Link href="/#features">{f.features[lang]}</Link>
              <Link href="/#demo">{f.demo[lang]}</Link>
              <Link href="/#pricing">{f.pricing[lang]}</Link>
              <Link href="/#download">{f.download[lang]}</Link>
            </div>

            <div className={styles.col}>
              <h4>{f.support[lang]}</h4>
              <Link href="/#faq">{f.faq[lang]}</Link>
              <Link href="/#hours">{f.hours[lang]}</Link>
              <a href={discord} target="_blank" rel="noreferrer">{f.discordServer[lang]}</a>
            </div>

            <div className={styles.col}>
              <h4>{f.account[lang]}</h4>
              <Link href="/dashboard">{f.myLicenses[lang]}</Link>
              <Link href="/dashboard">{f.orderHistory[lang]}</Link>
            </div>

            <div className={styles.col}>
              <h4>{f.legal[lang]}</h4>
              <Link href="/terms">{f.terms[lang]}</Link>
              <Link href="/privacy">{f.privacy[lang]}</Link>
              <button
                onClick={openSettings}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0, textAlign: "left", font: "inherit" }}
                className={styles.cookieBtn}
              >
                {f.cookieSettings[lang]}
              </button>
            </div>
          </div>
        </div>

        {/* Bottom bar */}
        <div className={styles.bottom}>
          <span>© {year} {general.copyright}</span>
          <div className={styles.bottomLinks}>
            <Link href="/terms">{f.termsShort[lang]}</Link>
            <Link href="/privacy">{f.privacyShort[lang]}</Link>
            <Link href="/#faq">FAQ</Link>
            <a href={discord} target="_blank" rel="noreferrer">Discord</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
