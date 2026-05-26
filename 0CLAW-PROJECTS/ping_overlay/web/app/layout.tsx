import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { CartProvider }            from "@/lib/cart-context";
import { TurnstileProvider }       from "@/lib/turnstile-context";
import { CookieConsentProvider }   from "@/lib/cookie-consent";
import { LanguageProvider }        from "@/lib/language-context";
import CartDrawer                  from "@/components/CartDrawer";
import VisitTracker                from "@/components/VisitTracker";
import TurnstileWidget             from "@/components/TurnstileWidget";
import CookieConsent               from "@/components/CookieConsent";
import BanGuard                   from "@/components/BanGuard";
import "./globals.css";

const inter = Inter({
  variable: "--font-body-var",
  subsets: ["latin"],
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-head-var",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

/* ─── Site-wide constants ────────────────────────────────────────────── */
const SITE_URL  = "https://wwmoverlay.com";
const SITE_NAME = "WWM Overlay";
const OG_TITLE  = "WWM Overlay — Ping, FPS & Events for Where Winds Meet";
const OG_DESC   =
  "Real-time Ping, FPS, Guild Events & Quest Helper overlay for Where Winds Meet. " +
  "Anti-cheat safe. Auto update. Free trial. — Overlay hiển thị Ping, FPS, sự kiện Guild và Quest Helper cho game Where Winds Meet.";

/* ─── Viewport ───────────────────────────────────────────────────────── */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0d0d12",
};

/* ─── Root metadata ──────────────────────────────────────────────────── */
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),

  title: {
    default:  OG_TITLE,
    template: "%s | WWM Overlay",
  },
  description: OG_DESC,
  keywords: [
    // English
    "WWM Overlay", "Where Winds Meet overlay", "ping overlay", "FPS overlay",
    "game overlay", "guild event overlay", "quest helper WWM",
    "WWM companion", "game performance monitor", "anti-cheat safe overlay",
    "where winds meet tool", "network monitor game", "frame rate overlay",
    // Vietnamese
    "overlay game", "theo dõi ping game", "overlay where winds meet",
    "công cụ hỗ trợ game WWM", "kiểm tra ping game", "hiển thị FPS game",
    "lịch sự kiện guild where winds meet", "overlay an toàn anti-cheat",
  ],
  authors:   [{ name: SITE_NAME, url: SITE_URL }],
  creator:   SITE_NAME,
  publisher: SITE_NAME,

  /* ── Canonical + hreflang ── */
  alternates: {
    canonical: SITE_URL,
    languages: {
      "en-US": SITE_URL,
      "vi-VN": SITE_URL,   // same URL, bilingual toggle via JS
    },
  },

  /* ── Robots ── */
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },

  /* ── Open Graph ── */
  openGraph: {
    type:            "website",
    locale:          "en_US",
    alternateLocale: ["vi_VN"],
    url:             SITE_URL,
    siteName:        SITE_NAME,
    title:           OG_TITLE,
    description:     OG_DESC,
    images: [
      {
        url:    "/og-image.png",
        width:  1200,
        height: 630,
        alt:    "WWM Overlay — Ping, FPS & Events for Where Winds Meet",
      },
    ],
  },

  /* ── Twitter / X card ── */
  twitter: {
    card:        "summary_large_image",
    title:       OG_TITLE,
    description: OG_DESC,
    images:      ["/og-image.png"],
  },

  /* ── Icons ── */
  icons: {
    icon:     "/assets/icon.png",
    shortcut: "/assets/icon.png",
    apple:    "/assets/icon.png",
  },
};

/* ─── JSON-LD structured data ────────────────────────────────────────── */
const jsonLd = [
  /* SoftwareApplication */
  {
    "@context":           "https://schema.org",
    "@type":              "SoftwareApplication",
    name:                 SITE_NAME,
    operatingSystem:      "Windows",
    applicationCategory:  "GameApplication",
    description:
      "Real-time Ping, FPS, Guild Events & Quest Helper overlay for Where Winds Meet. Anti-cheat safe.",
    url:         SITE_URL,
    downloadUrl: `${SITE_URL}/download`,
    screenshot:  `${SITE_URL}/og-image.png`,
    offers: {
      "@type":        "Offer",
      priceCurrency:  "USD",
      availability:   "https://schema.org/InStock",
    },
    author: {
      "@type": "Organization",
      name:    SITE_NAME,
      url:     SITE_URL,
    },
  },
  /* WebSite (enables Sitelinks Search Box eligibility) */
  {
    "@context": "https://schema.org",
    "@type":    "WebSite",
    name:       SITE_NAME,
    url:        SITE_URL,
  },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <head>
        {/* JSON-LD structured data — works in <head> and in <body> per Google spec */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body>
        {/*
          TurnstileProvider must wrap everything so any component
          can read the token via useTurnstile().

          Load order:
            1. TurnstileWidget  — injects Cloudflare script + invisible widget
                                  (afterInteractive, non-blocking)
            2. VisitTracker     — waits for Turnstile token before recording a visit
                                  (8 s fail-open if token never arrives)
        */}
        <LanguageProvider>
        <CookieConsentProvider>
          <TurnstileProvider>
            <CartProvider>
              <BanGuard>
                <TurnstileWidget />
                <VisitTracker />
                {children}
                <CartDrawer />
                <CookieConsent />
              </BanGuard>
            </CartProvider>
          </TurnstileProvider>
        </CookieConsentProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
