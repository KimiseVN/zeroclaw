"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useDownloadSettings, useTrialSettings, fmtTrialLabel, useReferralConfig } from "@/lib/use-site-settings";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import Header from "@/components/Header";
import styles from "./ref.module.css";

function RefContent() {
  const searchParams = useSearchParams();
  const code         = (searchParams.get("code") ?? "").toUpperCase();
  const dl           = useDownloadSettings();
  const trial        = useTrialSettings();
  const refConfig    = useReferralConfig();
  const trialLabel   = fmtTrialLabel(trial.days);
  const { lang }     = useLanguage();
  const r            = T.ref;

  const [copied,  setCopied]  = useState(false);
  const [tracked, setTracked] = useState(false);

  useEffect(() => {
    if (!code) return;
    localStorage.setItem("ref_code", code);
  }, [code]);

  async function handleDownload() {
    if (tracked || !code) return;
    setTracked(true);
    try {
      // Log pending download via DB RPC (SECURITY DEFINER) — no edge function needed.
      // Points are awarded only when the app first launches and claims the referral.
      const cleanCode = code.replace(/[^A-Z0-9]/g, "").slice(0, 8);
      if (cleanCode.length >= 4) {
        await createClient().rpc("track_referral_download", { p_code: cleanCode });
      }
    } catch { /* non-critical */ }
  }

  const dlUrl = dl.url || "#";

  return (
    <main className={styles.main}>
      {/* Hero */}
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.inviteBadge}>{r.inviteBadge[lang]}</div>
          <h1 className={styles.heroTitle}>
            WWM Overlay — <span className={styles.accent}>{r.heroAccent[lang]}</span><br />
            {r.heroSuffix[lang]}
          </h1>
          <p className={styles.heroSub}>
            {r.heroSub[lang].replace("{trial}", trialLabel)}
          </p>

          {code && (
            <div className={styles.codeCard}>
              <p className={styles.codeLabel}>{r.codeLabel[lang]}</p>
              <code className={styles.code}>{code}</code>
              <button
                className={styles.copyBtn}
                onClick={() => { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
              >
                {copied ? r.copied[lang] : r.copyCode[lang]}
              </button>
            </div>
          )}

          <a
            className={styles.dlBtn}
            href={dlUrl}
            target="_blank"
            rel="noreferrer"
            onClick={handleDownload}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            {r.dlBtn[lang]}
          </a>
          <p className={styles.smartscreen}>
            {r.smartscreen[lang].split('"More info → Run anyway"')[0]}
            <strong>&ldquo;More info → Run anyway&rdquo;</strong>
          </p>
        </div>
      </section>

      {/* Features */}
      <section className={styles.features}>
        <div className={styles.featuresInner}>
          {r.features.map(f => (
            <div key={f.title.en} className={styles.featureCard}>
              <div className={styles.featureIcon}>{f.icon}</div>
              <h3>{f.title[lang]}</h3>
              <p>{f.desc[lang]}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Referral reward info */}
      {refConfig.enabled && (
        <section className={styles.rewardSection}>
          <div className={styles.rewardInner}>
            <h2>{r.howTitle[lang]}</h2>
            <div className={styles.steps}>
              <div className={styles.step}>
                <div className={styles.stepNum}>1</div>
                <p>{r.step1[lang]}</p>
              </div>
              <div className={styles.step}>
                <div className={styles.stepNum}>2</div>
                <p dangerouslySetInnerHTML={{ __html: r.step2[lang].replace("{n}", `<strong>+${refConfig.points_per_download}</strong>`) }} />
              </div>
              <div className={styles.step}>
                <div className={styles.stepNum}>3</div>
                <p dangerouslySetInnerHTML={{ __html: r.step3[lang].replace("{n}", `<strong>+${refConfig.points_per_purchase}</strong>`) }} />
              </div>
              <div className={styles.step}>
                <div className={styles.stepNum}>4</div>
                <p dangerouslySetInnerHTML={{ __html: r.step4[lang]
                  .replace("{pts}",  `<strong>${refConfig.points_for_reward}</strong>`)
                  .replace("{days}", `<strong>${refConfig.reward_days}</strong>`)
                }} />
              </div>
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className={styles.ctaSection}>
        <div className={styles.ctaInner}>
          <h2>{r.ctaTitle[lang]}</h2>
          <p>{r.ctaSub[lang].replace("{trial}", trialLabel)}</p>
          <a className={styles.dlBtn} href={dlUrl} target="_blank" rel="noreferrer" onClick={handleDownload}>
            {r.ctaBtn[lang]}
          </a>
        </div>
      </section>
    </main>
  );
}

export default function RefPage() {
  return (
    <>
      <Header />
      <Suspense fallback={<main className={styles.main} />}>
        <RefContent />
      </Suspense>
    </>
  );
}
