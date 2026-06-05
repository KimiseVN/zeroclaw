"use client";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import styles from "./ReforgeSection.module.css";

// ── Mock slot card ─────────────────────────────────────────────────────────
type SlotMockProps = {
  label: string;
  fails: number;
  state: "normal" | "hot" | "prime" | "locked" | "selected";
  badge: string;
};

function SlotMock({ label, fails, state, badge }: SlotMockProps) {
  return (
    <div className={`${styles.slot} ${styles[`slot_${state}`]}`}>
      <div className={styles.slotTop}>
        <span className={styles.slotLabel}>{label}</span>
        {state === "locked" && <span className={styles.lockIcon}>🔒</span>}
        {state === "selected" && <span className={styles.selDot}>●</span>}
      </div>
      <div className={styles.slotFails}>{fails}</div>
      <div className={`${styles.slotBadge} ${styles[`badge_${state}`]}`}>{badge}</div>
      <div className={styles.slotBtns}>
        <span>★</span><span>{state === "locked" ? "🔓" : "🔒"}</span><span>↺</span>
      </div>
    </div>
  );
}

// ── Log row mock ───────────────────────────────────────────────────────────
function LogRow({ msg, type }: { msg: string; type: "normal" | "prime" | "gold" | "hot" }) {
  const colors = {
    normal: "var(--text-dim)",
    prime:  "#3DD6A8",
    gold:   "#E8B04A",
    hot:    "#F08B5F",
  };
  return (
    <div className={styles.logRow}>
      <span className={styles.logTs}>12:34:01</span>
      <span style={{ color: colors[type], fontSize: 11 }}>{msg}</span>
    </div>
  );
}

// ── Tracker UI Mock ────────────────────────────────────────────────────────
function TrackerMock({ lang }: { lang: "en" | "vi" }) {
  const slots: SlotMockProps[] = [
    { label: "SLOT 1", fails: 8,  state: "selected", badge: lang === "vi" ? "✓ đang roll" : "✓ rolling" },
    { label: "SLOT 2", fails: 22, state: "hot",      badge: lang === "vi" ? "Nóng 🔥" : "Hot 🔥" },
    { label: "SLOT 3", fails: 31, state: "prime",    badge: "Prime 🎯" },
    { label: "SLOT 4", fails: 13, state: "locked",   badge: lang === "vi" ? "Khóa 🔒" : "Locked 🔒" },
  ];
  const rollLabel = lang === "vi"
    ? "🎲  Roll Slot Chọn (2)  🪨2/roll"
    : "🎲  Roll Selected (2)  🪨2/roll";

  return (
    <div className={styles.mockWindow}>
      {/* title bar */}
      <div className={styles.mockTitleBar}>
        <span>⚔&nbsp; Reforge Tracker</span>
        <span className={styles.mockClose}>✕</span>
      </div>

      {/* scheme tabs */}
      <div className={styles.mockTabs}>
        <span className={styles.mockTabActive}>BlazingSword&nbsp;✏&nbsp;×</span>
        <span className={styles.mockTab}>DragonStaff&nbsp;✏&nbsp;×</span>
        <span className={styles.mockTabAdd}>＋</span>
      </div>

      {/* tip bar */}
      <div className={styles.mockTip} style={{ color: "#3DD6A8" }}>
        {lang === "vi"
          ? "⚡ Slot 3 đang PRIME — chuyển tab để snipe!"
          : "⚡ Slot 3 is PRIME — switch tab to snipe!"}
      </div>

      {/* 4 slot cards */}
      <div className={styles.mockSlots}>
        {slots.map(s => <SlotMock key={s.label} {...s} />)}
      </div>

      {/* roll button */}
      <div className={styles.mockRollBtn}>{rollLabel}</div>

      {/* summary */}
      <div className={styles.mockSummary}>
        <div className={styles.mockMetric}>
          <div className={styles.mockMetricLabel}>{lang === "vi" ? "Tổng Roll" : "Total Rolls"}</div>
          <div className={styles.mockMetricVal}>47</div>
        </div>
        <div className={styles.mockMetric}>
          <div className={styles.mockMetricLabel}>{lang === "vi" ? "Gold Nhận" : "Golds Hit"}</div>
          <div className={styles.mockMetricVal}>3</div>
        </div>
        <div className={styles.mockMetric}>
          <div className={styles.mockMetricLabel}>{lang === "vi" ? "Đá Dùng" : "Stones Used"}</div>
          <div className={`${styles.mockMetricVal} ${styles.stoneVal}`}>61</div>
        </div>
        <div className={styles.mockMetric}>
          <div className={styles.mockMetricLabel}>Prime/Sel</div>
          <div className={styles.mockMetricVal}>1/2</div>
        </div>
      </div>

      {/* log rows */}
      <div className={styles.mockLog}>
        <LogRow msg="[BlazingSword] ×2  🪨2  |  8, 22, 31, 13" type="prime" />
        <LogRow msg="[BlazingSword] S3: ★ Gold! (29→0)  |  6, 20, 0, 13" type="gold" />
        <LogRow msg="[BlazingSword] ×2  🪨2  |  6, 20, 1, 13" type="normal" />
        <LogRow msg="[BlazingSword] S2: 🔥 Hot!  |  4, 20, 0, 11" type="hot" />
      </div>
    </div>
  );
}

// ── Main section ──────────────────────────────────────────────────────────
export default function ReforgeSection() {
  const { lang } = useLanguage();
  const r = T.reforge;

  return (
    <section id="reforge" className={`section-pad ${styles.section}`}>
      <div className="container">
        <div className={styles.layout}>

          {/* ── Left: info ────────────────────────────────────────── */}
          <div className={styles.info}>
            <p className="eyebrow"><span className="dot" /> {r.eyebrow[lang]}</p>
            <h2 className={styles.heading}>{r.heading[lang]}</h2>
            <p className={styles.lead}>{r.lead[lang]}</p>

            {/* Pseudo-RNG callout */}
            <div className={styles.callout}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                   stroke="#FFB300" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <span>{r.callout[lang]}</span>
            </div>

            {/* Feature bullets */}
            <ul className={styles.featureList}>
              {r.features.map((f, i) => (
                <li key={i} className={styles.featureItem}>
                  <span className={styles.featureIcon}>{f.icon}</span>
                  <div>
                    <div className={styles.featureTitle}>{f.title[lang]}</div>
                    <div className={styles.featureDesc}>{f.desc[lang]}</div>
                  </div>
                </li>
              ))}
            </ul>

            {/* Stone cost table */}
            <div className={styles.stoneTable}>
              <div className={styles.stoneTableTitle}>
                🪨 {lang === "vi" ? "Chi phí đá Reforge mỗi lần roll" : "Reforge stone cost per roll"}
              </div>
              <div className={styles.stoneRows}>
                {[
                  { lock: lang === "vi" ? "0 slot khóa" : "0 locked", cost: "1 🪨" },
                  { lock: lang === "vi" ? "1 slot khóa" : "1 locked", cost: "2 🪨" },
                  { lock: lang === "vi" ? "2 slot khóa" : "2 locked", cost: "5 🪨" },
                  { lock: lang === "vi" ? "3 slot khóa" : "3 locked", cost: "10 🪨" },
                ].map((row, i) => (
                  <div key={i} className={styles.stoneRow}>
                    <span>{row.lock}</span>
                    <span className={styles.stoneCost}>{row.cost}</span>
                  </div>
                ))}
              </div>
            </div>

            <p className={styles.howTo}>
              {r.howTo[lang]}
            </p>
          </div>

          {/* ── Right: tracker mock ───────────────────────────────── */}
          <div className={styles.mockWrap}>
            <TrackerMock lang={lang} />
          </div>

        </div>
      </div>
    </section>
  );
}
