import type { Metadata } from "next";
import DownloadClient from "./DownloadClient";

export const metadata: Metadata = {
  title:       "Download WWM Overlay",
  description:
    "Download WWM Overlay for Windows — real-time Ping, FPS, Guild Events & Quest Helper for Where Winds Meet. Free trial. Anti-cheat safe.",
  alternates:  { canonical: "https://wwmoverlay.com/download" },
  openGraph: {
    title:       "Download WWM Overlay",
    description: "Free trial available. Anti-cheat safe. Auto update.",
    url:         "https://wwmoverlay.com/download",
  },
  robots: { index: true, follow: true },
};

export default function DownloadPage() {
  return <DownloadClient />;
}
