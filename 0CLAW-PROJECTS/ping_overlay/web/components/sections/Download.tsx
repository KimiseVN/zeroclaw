"use client";
import { useEffect, useState } from "react";
import { useGeneralSettings, useDownloadSettings, useTrialSettings, fmtTrialLabel } from "@/lib/use-site-settings";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import styles from "./Download.module.css";

export default function Download() {
  const general    = useGeneralSettings();
  const dl         = useDownloadSettings();
  const trial      = useTrialSettings();
  const { lang }   = useLanguage();
  const d          = T.download;
  const discord    = general.discord_url || "https://discord.gg/akim.wwmoverlay";
  const version    = dl.version || "—";
  const trialLabel = fmtTrialLabel(trial.days);

  const [refCode, setRefCode] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlCode = params.get("ref") ?? params.get("code") ?? "";
    if (urlCode) {
      setRefCode(urlCode.toUpperCase());
      localStorage.setItem("ref_code", urlCode.toUpperCase());
    } else {
      const saved = localStorage.getItem("ref_code") ?? "";
      if (saved) setRefCode(saved);
    }
  }, []);

  // Build href that routes through /download so the real URL stays hidden.
  // The /download page picks up ?ref= and handles tracking + redirect.
  const dlHref = refCode.trim()
    ? `/download?ref=${encodeURIComponent(refCode.trim())}`
    : "/download";

  return (
    <section id="download" className={`section-pad ${styles.section}`}>
      <div className={styles.inner}>
        <div className={styles.copy}>
          <p className="eyebrow"><span className="dot" /> {d.eyebrow[lang]}</p>
          <h2>{d.heading[lang]}<br />{trialLabel} {lang === "vi" ? "dùng thử miễn phí." : "free trial."}</h2>
          <p className="section-lead">{d.lead[lang]}</p>
          <ul className={styles.reqs}>
            {d.reqs.map(r => (
              <li key={r.en}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                {r[lang]}
              </li>
            ))}
          </ul>
          <div className={styles.socials}>
            <a href={discord} target="_blank" rel="noreferrer" className={styles.socialBtn}>{d.discord[lang]}</a>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHead}>
            <div>
              <p className={styles.cardLabel}>{d.latest[lang]}</p>
              <h3>PingOverlay v{version}</h3>
            </div>
            <span className={styles.stableBadge}>{d.stable[lang]}</span>
          </div>

          <div className={styles.refRow}>
            <input
              className={styles.refInput}
              type="text"
              placeholder={d.refPlaceholder[lang]}
              value={refCode}
              onChange={e => setRefCode(e.target.value.toUpperCase())}
              maxLength={9}
              spellCheck={false}
            />
          </div>

          <a
            className={`btn btn-primary btn-xl ${styles.dlBtn}`}
            href={dlHref}
            target="_blank"
            rel="noreferrer"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            {d.dlBtn[lang]}
          </a>

          <a className={styles.support} href={discord} target="_blank" rel="noreferrer">
            {d.help[lang]}
          </a>
          <p className={styles.smartscreen}>
            {lang === "vi"
              ? <>Windows SmartScreen có thể cảnh báo — nhấn <strong>&ldquo;More info → Run anyway&rdquo;</strong> để tiếp tục.</>
              : <>Windows SmartScreen may warn — click <strong>&ldquo;More info → Run anyway&rdquo;</strong> to continue.</>}
          </p>
        </div>
      </div>
    </section>
  );
}
