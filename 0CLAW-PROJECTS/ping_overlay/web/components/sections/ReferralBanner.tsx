"use client";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useReferralConfig } from "@/lib/use-site-settings";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import styles from "./ReferralBanner.module.css";

export default function ReferralBanner() {
  const refConfig = useReferralConfig();
  const { lang }  = useLanguage();
  const r         = T.ref;
  const dr        = T.dashboard.referral;
  const [code,      setCode]      = useState<string | null>(null);
  const [copied,    setCopied]    = useState<"code" | "link" | null>(null);
  const [points,    setPoints]    = useState(0);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && sessionStorage.getItem("ref_banner_dismissed")) {
      setDismissed(true);
    }
    const sb = createClient();
    sb.auth.getUser().then(async ({ data: { user } }) => {
      if (!user) return;
      const { data } = await sb.from("profiles")
        .select("referral_code, referral_points")
        .eq("id", user.id)
        .single();
      if (data?.referral_code) {
        setCode(data.referral_code);
        setPoints(data.referral_points ?? 0);
      }
    });
  }, []);

  if (!code || dismissed || !refConfig.enabled) return null;

  const siteUrl = typeof window !== "undefined" ? window.location.origin : "";
  const refLink = `${siteUrl}/ref?code=${code}`;

  const MSG_VI = `🎮 Đang chơi Where Winds Meet? Tải WWM Overlay – overlay tốt nhất!\n⚡ Ping, quest, events real-time chính xác.\n🔗 ${refLink}\n✨ Dùng mã ${code} để ủng hộ mình nhé!`;
  const MSG_EN = `🎮 Playing Where Winds Meet? Try WWM Overlay – the best in-game overlay!\n⚡ Real-time ping, quest tracker & event monitor. Free trial included.\n🔗 ${refLink}\n✨ Use code ${code} to support me!`;
  const shareMsg = lang === "en" ? MSG_EN : MSG_VI;

  function copy(text: string, type: "code" | "link") {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(type);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  function dismiss() {
    sessionStorage.setItem("ref_banner_dismissed", "1");
    setDismissed(true);
  }

  const threshold = refConfig.points_for_reward ?? 50;
  const pct = Math.min(100, Math.round((points / threshold) * 100));

  const subText = r.bannerSub[lang]
    .replace("{dl}",   String(refConfig.points_per_download))
    .replace("{pur}",  String(refConfig.points_per_purchase))
    .replace("{pts}",  String(threshold))
    .replace("{days}", String(refConfig.reward_days));

  return (
    <section className={styles.section}>
      <div className={styles.inner}>
        <div className={styles.left}>
          <p className={styles.eyebrow}>
            <span className="dot" /> {r.bannerEyebrow[lang]}
          </p>
          <h2 className={styles.title}>
            {r.bannerTitle[lang]}<span className={styles.accent}>{r.bannerAccent[lang]}</span>
          </h2>
          <p className={styles.sub}>{subText}</p>

          {/* Progress */}
          <div className={styles.progressWrap}>
            <div className={styles.progressBar}>
              <div className={styles.progressFill} style={{ width: `${pct}%` }} />
            </div>
            <span className={styles.progressLabel}>{points} / {threshold} {dr.pts[lang]}</span>
          </div>
        </div>

        <div className={styles.card}>
          <p className={styles.cardLabel}>{r.cardCodeLabel[lang]}</p>
          <div className={styles.codeRow}>
            <code className={styles.code}>{code}</code>
            <button
              className={styles.copyBtn}
              onClick={() => copy(code, "code")}
            >
              {copied === "code" ? dr.copied[lang] : dr.copyCode[lang]}
            </button>
          </div>

          <p className={styles.cardLabel} style={{ marginTop: 16 }}>{r.cardLinkLabel[lang]}</p>
          <div className={styles.linkRow}>
            <span className={styles.linkText}>{refLink}</span>
            <button
              className={`btn btn-primary ${styles.copyLinkBtn}`}
              onClick={() => copy(refLink, "link")}
            >
              {copied === "link" ? dr.copiedLink[lang] : dr.copyLink[lang]}
            </button>
          </div>

          <button
            className={styles.msgBtn}
            onClick={() => copy(shareMsg, "link")}
          >
            {copied === "link" ? dr.copiedMsg[lang] : dr.copyMsg[lang]}
          </button>
        </div>

        <button className={styles.dismiss} onClick={dismiss} title="Dismiss">✕</button>
      </div>
    </section>
  );
}
