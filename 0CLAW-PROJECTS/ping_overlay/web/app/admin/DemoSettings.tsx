"use client";
import { useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { DemoImage } from "@/lib/supabase/types";
import styles from "./admin.module.css";
import demoStyles from "./demo-settings.module.css";

type Props = { images: DemoImage[] };

function ImageCard({
  img, onUpdate, onDelete, onMove, isFirst, isLast,
}: {
  img: DemoImage;
  onUpdate: (u: DemoImage) => void;
  onDelete: (id: string) => void;
  onMove: (id: string, dir: -1 | 1) => void;
  isFirst: boolean; isLast: boolean;
}) {
  const [url,     setUrl]     = useState(img.url);
  const [caption, setCaption] = useState(img.caption ?? "");
  const [enabled, setEnabled] = useState(img.enabled);
  const [busy,    setBusy]    = useState(false);
  const [msg,     setMsg]     = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function save() {
    setBusy(true); setMsg("");
    const sb = createClient();
    const { error } = await sb.from("demo_images").update({ url, caption, enabled }).eq("id", img.id);
    setBusy(false);
    if (error) { setMsg("Error: " + error.message); return; }
    setMsg("Saved!"); setTimeout(() => setMsg(""), 2000);
    onUpdate({ ...img, url, caption, enabled });
  }

  async function toggleEnabled() {
    const next = !enabled;
    setEnabled(next);
    await createClient().from("demo_images").update({ enabled: next }).eq("id", img.id);
    onUpdate({ ...img, enabled: next });
  }

  async function del() {
    if (!confirm("Remove this image?")) return;
    await createClient().from("demo_images").delete().eq("id", img.id);
    onDelete(img.id);
  }

  async function uploadFile(file: File) {
    setUploading(true); setMsg("");
    try {
      const sb   = createClient();
      const ext  = file.name.split(".").pop() ?? "jpg";
      const path = `demo/${Date.now()}.${ext}`;
      const { error: upErr } = await sb.storage.from("demo-images").upload(path, file, { upsert: true });
      if (upErr) { setMsg("Upload error: " + upErr.message); return; }
      const { data: { publicUrl } } = sb.storage.from("demo-images").getPublicUrl(path);
      setUrl(publicUrl);
    } catch (e) {
      setMsg("Upload error: " + String(e));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className={`${demoStyles.card} ${!enabled ? demoStyles.cardDisabled : ""}`}>
      {/* Image preview */}
      <div className={demoStyles.preview}>
        {url ? (
          <img src={url} alt={caption || "demo"} className={demoStyles.thumb} />
        ) : (
          <div className={demoStyles.thumbPlaceholder}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--border-2)" strokeWidth="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <polyline points="21 15 16 10 5 21"/>
            </svg>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className={demoStyles.body}>
        <div className={styles.formGroup} style={{ marginBottom: 8 }}>
          <label className={styles.formLabel}>Image URL</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input className={styles.input} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://..." style={{ flex: 1 }} />
            <button className="btn btn-ghost" onClick={() => fileRef.current?.click()} disabled={uploading} title="Upload image">
              {uploading ? "…" : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
              )}
            </button>
            <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }}
              onChange={e => { const f = e.target.files?.[0]; if (f) uploadFile(f); e.target.value = ""; }} />
          </div>
        </div>

        <div className={styles.formGroup} style={{ marginBottom: 8 }}>
          <label className={styles.formLabel}>Caption (optional)</label>
          <input className={styles.input} value={caption} onChange={e => setCaption(e.target.value)} placeholder="Description for this image..." />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {/* order */}
          <button className="btn btn-ghost" style={{ padding: "6px 10px", fontSize: 12 }} disabled={isFirst} onClick={() => onMove(img.id, -1)}>▲</button>
          <button className="btn btn-ghost" style={{ padding: "6px 10px", fontSize: 12 }} disabled={isLast}  onClick={() => onMove(img.id,  1)}>▼</button>
          {/* toggle */}
          <label className={demoStyles.toggle}>
            <input type="checkbox" checked={enabled} onChange={toggleEnabled} />
            <span className={demoStyles.slider} />
            <span style={{ fontSize: 12, color: enabled ? "var(--cyan)" : "var(--text-muted)" }}>{enabled ? "Visible" : "Hidden"}</span>
          </label>
          {/* msg */}
          {msg && <span style={{ fontSize: 12, color: msg.startsWith("Error") ? "var(--red)" : "var(--green)" }}>{msg}</span>}
          {/* actions */}
          <button className="btn btn-ghost" style={{ marginLeft: "auto", color: "var(--red)", fontSize: 12 }} onClick={del}>Delete</button>
          <button className="btn btn-primary" style={{ fontSize: 13 }} onClick={save} disabled={busy || uploading}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </div>
  );
}

export default function DemoSettings({ images: initial }: Props) {
  const [images, setImages] = useState<DemoImage[]>([...initial].sort((a, b) => a.order_index - b.order_index));
  const [adding, setAdding] = useState(false);

  function handleUpdate(u: DemoImage) {
    setImages(prev => prev.map(i => i.id === u.id ? u : i));
  }
  function handleDelete(id: string) {
    setImages(prev => prev.filter(i => i.id !== id));
  }

  async function handleMove(id: string, dir: -1 | 1) {
    const idx = images.findIndex(i => i.id === id);
    if (idx < 0) return;
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= images.length) return;
    const next = [...images];
    [next[idx], next[newIdx]] = [next[newIdx], next[idx]];
    const sb = createClient();
    for (let i = 0; i < next.length; i++) {
      await sb.from("demo_images").update({ order_index: i }).eq("id", next[i].id);
    }
    setImages(next.map((img, i) => ({ ...img, order_index: i })));
  }

  async function addImage() {
    setAdding(true);
    const maxOrder = images.length ? Math.max(...images.map(i => i.order_index)) + 1 : 0;
    const { data, error } = await createClient().from("demo_images")
      .insert({ url: "", caption: "", order_index: maxOrder, enabled: true })
      .select().single();
    setAdding(false);
    if (!error && data) setImages(prev => [...prev, data as DemoImage]);
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {images.length} image{images.length !== 1 ? "s" : ""} · Upload or paste URL · Reorder with ▲▼
        </p>
        <button className="btn btn-primary" onClick={addImage} disabled={adding}>
          {adding ? "Adding…" : "+ Add Image"}
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {images.map((img, i) => (
          <ImageCard
            key={img.id} img={img}
            onUpdate={handleUpdate}
            onDelete={handleDelete}
            onMove={handleMove}
            isFirst={i === 0}
            isLast={i === images.length - 1}
          />
        ))}
        {images.length === 0 && (
          <div className={styles.empty}>No images yet. Click "+ Add Image" to upload or add a URL.</div>
        )}
      </div>
    </div>
  );
}
