"use client";
import { useEffect, useState } from "react";
import { useBusinessHours, type TimeSlot } from "@/lib/use-site-settings";
import { useLanguage } from "@/lib/language-context";
import { T } from "@/lib/translations";
import styles from "./SupportHours.module.css";

const VN_TZ = "Asia/Ho_Chi_Minh";
const DE_TZ = "Europe/Berlin";

function clockStr(date: Date, tz: string) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(date);
}

function vnMinutes(date: Date) {
  const p = new Intl.DateTimeFormat("en-GB", {
    timeZone: VN_TZ, hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(date);
  return parseInt(p.find(x => x.type === "hour")!.value, 10) * 60
       + parseInt(p.find(x => x.type === "minute")!.value, 10);
}

function pad2(n: number) { return String(n).padStart(2, "0"); }

function slotStr(s: TimeSlot) {
  return `${pad2(s.start_h)}:${pad2(s.start_m)} – ${pad2(s.end_h)}:${pad2(s.end_m)}`;
}

function isInSlot(cur: number, s: TimeSlot) {
  const start = s.start_h * 60 + s.start_m;
  const end   = s.end_h   * 60 + s.end_m;
  return cur >= start && cur <= end;
}

function deSlotStr(date: Date, s: TimeSlot) {
  const vnDate = new Intl.DateTimeFormat("en-CA", {
    timeZone: VN_TZ, year: "numeric", month: "2-digit", day: "2-digit",
  }).format(date);
  const toDE = (h: number, m: number) => {
    const utc = new Date(`${vnDate}T${pad2(h)}:${pad2(m)}:00+07:00`);
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: DE_TZ, hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(utc);
  };
  return `${toDE(s.start_h, s.start_m)} – ${toDE(s.end_h, s.end_m)}`;
}

export default function SupportHours() {
  const { slots, is_24_7 } = useBusinessHours();
  const { lang }           = useLanguage();
  const s = T.supportHours;

  const [vnClock,    setVnClock]    = useState("--:--:--");
  const [deClock,    setDeClock]    = useState("--:--:--");
  const [deSlots,    setDeSlots]    = useState<string[]>([]);
  const [online,     setOnline]     = useState(false);
  const [activeSlot, setActiveSlot] = useState<TimeSlot | null>(null);

  useEffect(() => {
    // Always tick for clocks; skip slot logic when 24/7
    function tick() {
      const now = new Date();
      setVnClock(clockStr(now, VN_TZ));
      setDeClock(clockStr(now, DE_TZ));
      if (!is_24_7) {
        setDeSlots(slots.map(sl => deSlotStr(now, sl)));
        const cur = vnMinutes(now);
        const hit = slots.find(sl => isInSlot(cur, sl)) ?? null;
        setOnline(!!hit);
        setActiveSlot(hit);
      }
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [slots, is_24_7]);

  const displayOnline = is_24_7 ? true : online;

  return (
    <section id="hours" className={`section-pad ${styles.section}`}>
      <div className="container">
        <div className="section-label center">
          <p className="eyebrow"><span className="dot" /> {s.eyebrow[lang]}</p>
          <h2>{s.heading[lang]}</h2>
          <p className="section-lead" style={{ marginInline: "auto" }}>
            {is_24_7 ? s.lead247[lang] : s.lead[lang]}
          </p>
        </div>

        <div className={styles.grid}>
          {/* VN card */}
          <div className={styles.card}>
            <div className={styles.cardHead}>
              <span className={styles.flag}>🇻🇳</span>
              <div>
                <div className={styles.zone}>Việt Nam</div>
                <div className={styles.tz}>Asia/Ho Chi Minh · GMT+7</div>
              </div>
            </div>
            {is_24_7 ? (
              <div className={`${styles.window} ${styles.windowActive}`}>
                {s.window247[lang]}
              </div>
            ) : (
              slots.map(sl => (
                <div key={sl.id} className={`${styles.window} ${online && activeSlot?.id === sl.id ? styles.windowActive : ""}`}>
                  {sl.label && <span className={styles.slotLabel}>{sl.label}</span>}
                  {slotStr(sl)}
                </div>
              ))
            )}
            <div className={styles.daily}>{is_24_7 ? s.daily247[lang] : s.every[lang]}</div>
            <div className={styles.liveRow}><span>{s.now[lang]}</span><span className={styles.clock}>{vnClock}</span></div>
          </div>

          {/* Status center */}
          <div className={styles.statusCenter}>
            <div className={styles.pulseWrap}>
              <span className={`${styles.pulse} ${displayOnline ? styles.pulseOnline : ""}`} />
              <span className={`${styles.dot2} ${displayOnline ? styles.dotOnline : styles.dotOffline}`} />
            </div>
            <div className={`${styles.statusLabel} ${displayOnline ? styles.statusOnline : ""}`}>
              {is_24_7 ? s.alwaysOnline[lang] : (online ? s.online[lang] : s.offline[lang])}
            </div>
            {!is_24_7 && online && activeSlot?.label && (
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{activeSlot.label}</div>
            )}
          </div>

          {/* DE card */}
          <div className={styles.card}>
            <div className={styles.cardHead}>
              <span className={styles.flag}>🇩🇪</span>
              <div>
                <div className={styles.zone}>Europe (Berlin)</div>
                <div className={styles.tz}>Europe/Berlin · CET/CEST</div>
              </div>
            </div>
            {is_24_7 ? (
              <div className={`${styles.window} ${styles.windowActive}`}>
                {s.window247[lang]}
              </div>
            ) : (
              deSlots.map((ds, i) => (
                <div key={slots[i]?.id ?? i} className={`${styles.window} ${online && activeSlot?.id === slots[i]?.id ? styles.windowActive : ""}`}>
                  {slots[i]?.label && <span className={styles.slotLabel}>{slots[i].label}</span>}
                  {ds}
                </div>
              ))
            )}
            <div className={styles.daily}>{is_24_7 ? s.daily247[lang] : s.every[lang]}</div>
            <div className={styles.liveRow}><span>{s.now[lang]}</span><span className={styles.clock}>{deClock}</span></div>
          </div>
        </div>
      </div>
    </section>
  );
}
