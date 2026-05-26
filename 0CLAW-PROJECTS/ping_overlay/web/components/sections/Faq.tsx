"use client";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useLanguage } from "@/lib/language-context";
import type { FaqItem } from "@/lib/supabase/types";
import styles from "./Faq.module.css";

const FALLBACK: FaqItem[] = [
  {
    id: "1",
    question:    "Does the app inject into the game?",
    question_vi: "App có inject vào game không?",
    answer:      "No. The app reads system and network process stats via a separate overlay window. No DLL injection — safe with anti-cheat (KingSoft, Easy Anti-Cheat, etc.).",
    answer_vi:   "Không. App đọc thống kê hệ thống và tiến trình mạng qua cửa sổ overlay riêng biệt. Không có DLL injection — an toàn với anti-cheat (KingSoft, Easy Anti-Cheat, v.v.).",
    order_index: 0, enabled: true, created_at: "",
  },
  {
    id: "2",
    question:    "How do licenses and trials work?",
    question_vi: "Giấy phép và bản dùng thử hoạt động như thế nào?",
    answer:      "Free 3-Days trial based on HWID. After the trial, you need a license key. Licenses are verified via HWID and heartbeat backend. Contact Discord to purchase.",
    answer_vi:   "Dùng thử miễn phí 3 ngày dựa trên HWID. Sau thời gian thử, bạn cần license key. Giấy phép được xác minh qua HWID và heartbeat backend. Liên hệ Discord để mua.",
    order_index: 1, enabled: true, created_at: "",
  },
];

export default function Faq() {
  const { lang } = useLanguage();
  const [faqs, setFaqs] = useState<FaqItem[]>([]);

  useEffect(() => {
    createClient()
      .from("faq")
      .select("*")
      .eq("enabled", true)
      .order("order_index")
      .then(({ data }) => setFaqs((data as FaqItem[]) ?? FALLBACK));
  }, []);

  const list = faqs.length ? faqs : FALLBACK;

  return (
    <section id="faq" className={`section-pad ${styles.section}`}>
      <div className="container">
        <div className="section-label center">
          <p className="eyebrow"><span className="dot" /> FAQ</p>
          <h2>{lang === "vi" ? "Câu hỏi thường gặp." : "Frequently Asked Questions."}</h2>
        </div>
        <div className={styles.list}>
          {list.map(item => {
            const q = (lang === "vi" && item.question_vi) ? item.question_vi : item.question;
            const a = (lang === "vi" && item.answer_vi)   ? item.answer_vi   : item.answer;
            return (
              <details key={item.id} className={styles.item}>
                <summary className={styles.q}>{q}</summary>
                <p className={styles.a}>{a}</p>
              </details>
            );
          })}
        </div>
      </div>
    </section>
  );
}
