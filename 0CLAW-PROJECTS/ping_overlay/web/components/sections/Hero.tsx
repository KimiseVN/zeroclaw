"use client";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import styles from "./Hero.module.css";
import HeroCta from "./HeroCta";

export default function Hero() {
  const { lang } = useLanguage();
  const h = T.hero;

  return (
    <section className={styles.hero}>
      <div className="container">
      <div className={`${styles.inner} ${styles.copy}`}>
        <div className="eyebrow"><span className="dot" /> {h.eyebrow[lang]}</div>
        <h1 className={styles.h1}>
          {lang === "vi" ? <>Ping. FPS. Sự kiện.<br /><span className={styles.glow}>Tất cả trong một.</span></> : <>Ping. FPS. Events.<br /><span className={styles.glow}>All in one.</span></>}
        </h1>
        <p className={styles.lead}>{h.lead[lang]}</p>
        <HeroCta />
        <div className={styles.trust}>
          <div className={styles.trustItem}>
            <span className={styles.trustIcon}>🛡️</span>
            <div><strong>{h.trust.antiCheat.title[lang]}</strong><small>{h.trust.antiCheat.sub[lang]}</small></div>
          </div>
          <div className={styles.trustItem}>
            <span className={styles.trustIcon}>🔄</span>
            <div><strong>{h.trust.autoUpdate.title[lang]}</strong><small>{h.trust.autoUpdate.sub[lang]}</small></div>
          </div>
          <div className={styles.trustItem}>
            <span className={styles.trustIcon}>🌐</span>
            <div><strong>{h.trust.lang.title[lang]}</strong><small>{h.trust.lang.sub[lang]}</small></div>
          </div>
        </div>
      </div>
      </div>
    </section>
  );
}
