"use client";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import styles from "./Features.module.css";

export default function Features() {
  const { lang } = useLanguage();
  const f = T.features;

  return (
    <section id="features" className={`section-pad ${styles.section}`}>
      <div className="container">
      <div className="section-label">
        <p className="eyebrow"><span className="dot" /> {f.eyebrow[lang]}</p>
        <h2>{lang === "vi" ? <>Mọi thứ bạn cần,<br />ngay trên màn hình.</> : <>Everything you need,<br />right on screen.</>}</h2>
        <p className="section-lead">{f.lead[lang]}</p>
      </div>
      <div className={styles.grid}>
        {f.cards.map(card => (
          <article key={card.title.en} className={styles.card}>
            <h3 className={styles.cardTitle}>{card.title[lang]}</h3>
            <p className={styles.cardDesc}>{card.desc[lang]}</p>
            <div className={styles.tags}>{card.tags.map(tag => <span key={tag}>{tag}</span>)}</div>
          </article>
        ))}
      </div>
      </div>
    </section>
  );
}
