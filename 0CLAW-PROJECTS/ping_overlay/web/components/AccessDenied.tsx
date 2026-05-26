"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Props = {
  banned?: boolean;
};

export default function AccessDenied({ banned = false }: Props) {
  const router = useRouter();
  const [countdown, setCountdown] = useState(3);

  useEffect(() => {
    if (banned) return;
    const id = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { clearInterval(id); router.replace("/"); return 0; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [banned, router]);

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9999,
      background: "rgba(8,12,20,.98)",
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      gap: 20, padding: 24,
    }}>
      <div style={{ fontSize: 64, lineHeight: 1 }}>{banned ? "🚫" : "⛔"}</div>

      <h1 style={{
        fontFamily: "var(--font-head)", fontSize: 26,
        color: banned ? "var(--red)" : "var(--yellow)",
        textAlign: "center", margin: 0,
      }}>
        {banned ? "Tài khoản bị chặn" : "Không có quyền truy cập"}
      </h1>

      {banned ? (
        <>
          <p style={{
            color: "var(--text-dim)", fontSize: 15, textAlign: "center",
            maxWidth: 480, lineHeight: 1.6, margin: 0,
          }}>
            Tài khoản hoặc địa chỉ IP của bạn đã bị <strong style={{ color: "var(--red)" }}>cấm</strong>{" "}
            do nhiều lần cố gắng truy cập vào trang bị hạn chế.
          </p>
          <p style={{ color: "var(--text-muted)", fontSize: 13, margin: 0 }}>
            Liên hệ Admin qua Discord để được hỗ trợ kháng cáo.
          </p>
          <div style={{
            marginTop: 8, padding: "10px 20px",
            background: "rgba(255,68,102,.08)",
            border: "1px solid rgba(255,68,102,.25)",
            borderRadius: 10, color: "var(--red)",
            fontSize: 12, fontFamily: "monospace",
          }}>
            ACCESS PERMANENTLY DENIED
          </div>
        </>
      ) : (
        <>
          <p style={{ color: "var(--text-dim)", fontSize: 15, textAlign: "center", margin: 0 }}>
            Bạn không có quyền truy cập trang này.
          </p>
          <p style={{
            color: "var(--text-muted)", fontSize: 13, textAlign: "center",
            maxWidth: 400, lineHeight: 1.6, margin: 0,
          }}>
            Hành động này đã được ghi lại. Cố gắng truy cập lại sẽ dẫn đến <strong style={{ color: "var(--red)" }}>cấm vĩnh viễn</strong>.
          </p>
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "10px 20px",
            background: "rgba(255,221,0,.06)",
            border: "1px solid rgba(255,221,0,.2)",
            borderRadius: 10,
          }}>
            <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
              Tự động chuyển về trang chủ sau
            </span>
            <span style={{
              color: "var(--cyan)", fontSize: 20, fontWeight: 800,
              fontFamily: "var(--font-head)", minWidth: 24, textAlign: "center",
            }}>
              {countdown}
            </span>
            <span style={{ color: "var(--text-muted)", fontSize: 13 }}>giây</span>
          </div>
        </>
      )}
    </div>
  );
}
