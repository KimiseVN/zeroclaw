"use client";
import Link from "next/link";
import { useDownloadSettings } from "@/lib/use-site-settings";
import styles from "./Hero.module.css";

/**
 * Client-only CTA buttons for the Hero section.
 * Reads version from Supabase site_settings so admin changes take effect
 * without a redeploy. Download is routed through /download to hide the
 * real URL and handle ref tracking there.
 */
export default function HeroCta() {
  const dl      = useDownloadSettings();
  const version = dl.version || "—";

  return (
    <div className={styles.actions}>
      <Link
        className="btn btn-primary btn-large"
        href="/download"
        target="_blank"
        rel="noreferrer"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        {version && version !== "—" ? `Download v${version}` : "Download"}
      </Link>
      <Link className="btn btn-ghost btn-large" href="/#features">See features</Link>
    </div>
  );
}
