"use client";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { FaqItem } from "@/lib/supabase/types";
import styles from "./admin.module.css";
import faqStyles from "./faq-settings.module.css";

type Lang = "en" | "vi";
type Props = { faqs: FaqItem[] };

function FaqCard({
  item, onUpdate, onDelete, onMove,
  isFirst, isLast,
}: {
  item: FaqItem;
  onUpdate: (updated: FaqItem) => void;
  onDelete: (id: string) => void;
  onMove: (id: string, dir: -1 | 1) => void;
  isFirst: boolean; isLast: boolean;
}) {
  const [lang,    setLang]    = useState<Lang>("en");
  const [qEn,     setQEn]     = useState(item.question    ?? "");
  const [aEn,     setAEn]     = useState(item.answer      ?? "");
  const [qVi,     setQVi]     = useState(item.question_vi ?? "");
  const [aVi,     setAVi]     = useState(item.answer_vi   ?? "");
  const [enabled, setEnabled] = useState(item.enabled);
  const [busy,    setBusy]    = useState(false);
  const [msg,     setMsg]     = useState("");
  const [open,    setOpen]    = useState(false);

  async function save() {
    setBusy(true); setMsg("");
    const { error } = await createClient().from("faq").update({
      question:    qEn.trim(),
      answer:      aEn.trim(),
      question_vi: qVi.trim() || null,
      answer_vi:   aVi.trim() || null,
      enabled,
    }).eq("id", item.id);
    setBusy(false);
    if (error) { setMsg("Error: " + error.message); return; }
    setMsg("Saved!"); setTimeout(() => setMsg(""), 2000);
    onUpdate({ ...item, question: qEn, answer: aEn, question_vi: qVi || null, answer_vi: aVi || null, enabled });
  }

  async function del() {
    if (!confirm("Delete this FAQ?")) return;
    await createClient().from("faq").delete().eq("id", item.id);
    onDelete(item.id);
  }

  async function toggle() {
    const next = !enabled;
    setEnabled(next);
    await createClient().from("faq").update({ enabled: next }).eq("id", item.id);
    onUpdate({ ...item, enabled: next });
  }

  const previewQ = lang === "vi" ? (qVi || qEn) : qEn;

  return (
    <div className={`${faqStyles.card} ${!enabled ? faqStyles.cardDisabled : ""}`}>
      {/* ── Header ── */}
      <div className={faqStyles.cardHead} onClick={() => setOpen(o => !o)}>
        <div className={faqStyles.orderBtns}>
          <button className={faqStyles.orderBtn} disabled={isFirst} onClick={e => { e.stopPropagation(); onMove(item.id, -1); }}>▲</button>
          <button className={faqStyles.orderBtn} disabled={isLast}  onClick={e => { e.stopPropagation(); onMove(item.id,  1); }}>▼</button>
        </div>
        <span className={faqStyles.preview}>
          {previewQ || <em style={{ color: "var(--text-muted)" }}>New question…</em>}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: "auto", flexShrink: 0 }}>
          <label className={faqStyles.toggle} onClick={e => e.stopPropagation()}>
            <input type="checkbox" checked={enabled} onChange={toggle} />
            <span className={faqStyles.slider} />
          </label>
          <button className={faqStyles.deleteBtn} onClick={e => { e.stopPropagation(); del(); }}>✕</button>
          <span className={faqStyles.chevron}>{open ? "▴" : "▾"}</span>
        </div>
      </div>

      {/* ── Body ── */}
      {open && (
        <div className={faqStyles.cardBody}>
          {/* Lang tabs */}
          <div className={faqStyles.langTabs}>
            <button
              className={`${faqStyles.langTab} ${lang === "en" ? faqStyles.langTabActive : ""}`}
              onClick={() => setLang("en")}
            >🇬🇧 English</button>
            <button
              className={`${faqStyles.langTab} ${lang === "vi" ? faqStyles.langTabActive : ""}`}
              onClick={() => setLang("vi")}
            >🇻🇳 Tiếng Việt</button>
          </div>

          {lang === "en" ? (
            <>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Question (EN)</label>
                <input
                  className={styles.input}
                  value={qEn}
                  onChange={e => setQEn(e.target.value)}
                  placeholder="Question in English…"
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Answer (EN)</label>
                <textarea
                  className={`${styles.input} ${faqStyles.textarea}`}
                  value={aEn}
                  onChange={e => setAEn(e.target.value)}
                  placeholder="Answer in English…"
                  rows={4}
                />
              </div>
            </>
          ) : (
            <>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Question (VI)</label>
                <input
                  className={styles.input}
                  value={qVi}
                  onChange={e => setQVi(e.target.value)}
                  placeholder="Câu hỏi bằng tiếng Việt…"
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Answer (VI)</label>
                <textarea
                  className={`${styles.input} ${faqStyles.textarea}`}
                  value={aVi}
                  onChange={e => setAVi(e.target.value)}
                  placeholder="Câu trả lời bằng tiếng Việt…"
                  rows={4}
                />
              </div>
            </>
          )}

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {msg && (
              <span style={{ fontSize: 13, color: msg.startsWith("Error") ? "var(--red)" : "var(--green)" }}>
                {msg}
              </span>
            )}
            <button className="btn btn-primary" style={{ marginLeft: "auto" }} onClick={save} disabled={busy}>
              {busy ? "Saving…" : "💾 Save"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main export ─────────────────────────────────────────────────────────────
export default function FaqSettings({ faqs: initial }: Props) {
  const [faqs,   setFaqs]   = useState<FaqItem[]>([...initial].sort((a, b) => a.order_index - b.order_index));
  const [adding, setAdding] = useState(false);

  function handleUpdate(updated: FaqItem) {
    setFaqs(prev => prev.map(f => f.id === updated.id ? updated : f));
  }

  function handleDelete(id: string) {
    setFaqs(prev => prev.filter(f => f.id !== id));
  }

  async function handleMove(id: string, dir: -1 | 1) {
    const idx = faqs.findIndex(f => f.id === id);
    if (idx < 0) return;
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= faqs.length) return;
    const next = [...faqs];
    [next[idx], next[newIdx]] = [next[newIdx], next[idx]];
    const sb = createClient();
    const updates = next.map((f, i) => ({ id: f.id, order_index: i }));
    for (const u of updates) {
      await sb.from("faq").update({ order_index: u.order_index }).eq("id", u.id);
    }
    setFaqs(next.map((f, i) => ({ ...f, order_index: i })));
  }

  async function addFaq() {
    setAdding(true);
    const maxOrder = faqs.length ? Math.max(...faqs.map(f => f.order_index)) + 1 : 0;
    const { data, error } = await createClient().from("faq")
      .insert({ question: "", answer: "", question_vi: null, answer_vi: null, order_index: maxOrder, enabled: true })
      .select().single();
    setAdding(false);
    if (!error && data) setFaqs(prev => [...prev, data as FaqItem]);
  }

  return (
    <div>
      {/* Header bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {faqs.length} question{faqs.length !== 1 ? "s" : ""} · Bilingual EN / VI · Reorder with ▲▼
        </p>
        <button className="btn btn-primary" onClick={addFaq} disabled={adding}>
          {adding ? "Adding…" : "+ Add Question"}
        </button>
      </div>

      {/* Hint banner */}
      <div style={{
        background: "rgba(0,229,255,.06)", border: "1px solid rgba(0,229,255,.18)",
        borderRadius: 10, padding: "10px 14px", fontSize: 13, color: "var(--text-dim)",
        marginBottom: 16, lineHeight: 1.6,
      }}>
        <strong style={{ color: "var(--cyan)" }}>Tip:</strong> Expand a card and switch between{" "}
        <strong>🇬🇧 English</strong> / <strong>🇻🇳 Tiếng Việt</strong> tabs to edit each language separately.
        If Vietnamese is left blank, the website falls back to English automatically.
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {faqs.map((f, i) => (
          <FaqCard
            key={f.id} item={f}
            onUpdate={handleUpdate}
            onDelete={handleDelete}
            onMove={handleMove}
            isFirst={i === 0}
            isLast={i === faqs.length - 1}
          />
        ))}
        {faqs.length === 0 && (
          <div className={styles.empty}>No FAQs yet. Click "+ Add Question" to create the first one.</div>
        )}
      </div>
    </div>
  );
}
