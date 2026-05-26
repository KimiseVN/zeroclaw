"use client";
import { useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { DemoImage } from "@/lib/supabase/types";
import styles from "./Demo.module.css";

export default function Demo() {
  const [images, setImages] = useState<DemoImage[]>([]);
  const [active, setActive] = useState(0);
  const trackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    createClient()
      .from("demo_images")
      .select("*")
      .eq("enabled", true)
      .order("order_index")
      .then(({ data }) => { if (data?.length) setImages(data as DemoImage[]); });
  }, []);

  function scrollTo(idx: number) {
    setActive(idx);
    const track = trackRef.current;
    if (!track) return;
    const child = track.children[idx] as HTMLElement;
    if (child) child.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }

  return (
    <section id="demo" className={`section-pad ${styles.section}`}>
      <div className="container">
      <div className="section-label center">
        <p className="eyebrow"><span className="dot" /> Control Panel</p>
        <h2>Simple management interface.</h2>
        <p className="section-lead" style={{ marginInline: "auto" }}>All features toggled in one compact window.</p>
      </div>

      {images.length === 0 ? (
        <div className={styles.placeholder}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--border-2)" strokeWidth="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/>
            <polyline points="21 15 16 10 5 21"/>
          </svg>
          <p>Screenshots coming soon.</p>
        </div>
      ) : (
        <div className={styles.carousel}>
          <div className={styles.track} ref={trackRef}>
            {images.map((img, i) => (
              <div key={img.id} className={`${styles.slide} ${i === active ? styles.slideActive : ""}`} onClick={() => scrollTo(i)}>
                <img src={img.url} alt={img.caption || `Demo ${i + 1}`} className={styles.img} />
                {img.caption && <p className={styles.caption}>{img.caption}</p>}
              </div>
            ))}
          </div>
          {images.length > 1 && (
            <div className={styles.dots}>
              {images.map((_, i) => (
                <button key={i} className={`${styles.dot} ${i === active ? styles.dotActive : ""}`} onClick={() => scrollTo(i)} />
              ))}
            </div>
          )}
        </div>
      )}
      </div>
    </section>
  );
}
