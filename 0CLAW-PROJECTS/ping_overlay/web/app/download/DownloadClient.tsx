"use client";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

async function trackDownload(refCode: string) {
  if (!refCode.trim()) return;
  try {
    // Normalize code: uppercase, alphanumeric only
    const cleanCode = refCode.trim().toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
    if (cleanCode.length < 4) return;
    // Use DB RPC (SECURITY DEFINER) — no edge function needed
    await createClient().rpc("track_referral_download", { p_code: cleanCode });
  } catch {
    // non-critical
  }
}

type Status = "loading" | "started" | "error";

export default function DownloadClient() {
  const [status,   setStatus]   = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    const params      = new URLSearchParams(window.location.search);
    const urlRef      = params.get("ref") ?? params.get("code") ?? "";
    const savedRef    = localStorage.getItem("ref_code") ?? "";
    const effectiveRef = urlRef || savedRef;

    if (urlRef) localStorage.setItem("ref_code", urlRef.toUpperCase());

    async function go() {
      try {
        const { data, error } = await createClient()
          .from("site_settings")
          .select("value")
          .eq("key", "download")
          .single();

        if (error) throw error;

        const url: string = (data?.value as Record<string, string> | null)?.url ?? "";
        if (!url) throw new Error("Download URL chưa được cấu hình.");

        if (effectiveRef) await trackDownload(effectiveRef);

        setStatus("started");
        window.location.href = url;
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        setErrorMsg(msg);
        setStatus("error");
      }
    }

    go();
  }, []);

  return (
    <>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        .dl-wrap {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 20px;
          background: #0d0d12;
          color: #e0e0e0;
          font-family: var(--font-body-var, system-ui, sans-serif);
          padding: 24px;
          text-align: center;
        }
        .dl-spinner {
          width: 40px;
          height: 40px;
          border: 3px solid #2a2a3a;
          border-top-color: #00d4ff;
          border-radius: 50%;
          animation: spin 0.75s linear infinite;
        }
        .dl-label {
          margin: 0;
          font-size: 16px;
          opacity: 0.75;
          max-width: 340px;
          line-height: 1.5;
        }
        .dl-back {
          margin-top: 8px;
          font-size: 14px;
          color: #00d4ff;
          text-decoration: none;
          opacity: 0.8;
        }
        .dl-back:hover { opacity: 1; }
        .dl-error { color: #ff6b6b; }
      `}</style>

      <div className="dl-wrap">
        {status === "loading" && (
          <>
            <div className="dl-spinner" />
            <p className="dl-label">Đang chuẩn bị tải xuống&hellip;</p>
          </>
        )}

        {status === "started" && (
          <>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none"
              stroke="#00d4ff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            <p className="dl-label">Tải xuống đã bắt đầu.<br />Nếu không tự động tải, hãy thử lại.</p>
            <a href="/" className="dl-back">← Quay lại trang chủ</a>
          </>
        )}

        {status === "error" && (
          <>
            <p className="dl-label dl-error">Lỗi: {errorMsg}</p>
            <a href="/" className="dl-back">← Quay lại trang chủ</a>
          </>
        )}
      </div>
    </>
  );
}
