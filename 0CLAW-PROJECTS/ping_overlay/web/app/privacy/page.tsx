import Link from "next/link";
import Header from "@/components/Header";
import styles from "@/app/legal/legal.module.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — WWM Overlay",
  description: "How WWM Overlay collects, uses, and protects your personal data.",
};

const LAST_UPDATED = "May 13, 2025";

const TOC = [
  { id: "controller",  label: "Data Controller" },
  { id: "collected",   label: "Data We Collect" },
  { id: "purpose",     label: "How We Use Your Data" },
  { id: "cookies",     label: "Cookies & Local Storage" },
  { id: "third-party", label: "Third-Party Services" },
  { id: "retention",   label: "Data Retention" },
  { id: "rights",      label: "Your Rights" },
  { id: "children",    label: "Children's Privacy" },
  { id: "changes",     label: "Changes to This Policy" },
  { id: "contact",     label: "Contact" },
];

export default function PrivacyPage() {
  return (
    <>
      <Header />
      <main className={styles.page}>
        {/* Hero */}
        <div className={styles.hero}>
          <div className={styles.heroIcon}>🔒</div>
          <div className={styles.heroLabel}>Legal</div>
          <h1 className={styles.heroTitle}>Privacy Policy</h1>
          <p className={styles.heroMeta}>Last updated: {LAST_UPDATED} · We collect only what we need.</p>
        </div>

        <div className={styles.container}>
          {/* Intro */}
          <div className={styles.infoBox} style={{ marginBottom: 36 }}>
            This Privacy Policy explains how <strong>WWM Overlay</strong> ("we", "our", "us") collects, uses, and protects information about you when you use our website (<em>this site</em>) and the WWM Overlay desktop software. We are committed to minimal data collection and transparency.
          </div>

          {/* TOC */}
          <div className={styles.toc}>
            <p className={styles.tocTitle}>Table of Contents</p>
            <ol className={styles.tocList}>
              {TOC.map((item, i) => (
                <li key={item.id}><a href={`#${item.id}`}>{i + 1}. {item.label}</a></li>
              ))}
            </ol>
          </div>

          {/* 1. Controller */}
          <div className={styles.section} id="controller">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>1</span>
              <h2 className={styles.sectionTitle}>Data Controller</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>WWM Overlay is the data controller responsible for your personal data. Contact details are provided in Section 10.</p>
              <p>This policy applies to data processed through our website and desktop application. It does not apply to third-party services that have their own privacy policies (see Section 5).</p>
            </div>
          </div>

          {/* 2. Collected */}
          <div className={styles.section} id="collected">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>2</span>
              <h2 className={styles.sectionTitle}>Data We Collect</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>We collect different types of data depending on how you interact with us:</p>

              <p><strong>Account data</strong> — When you create an account:</p>
              <ul>
                <li>Email address (required for email/password or magic-link sign-in)</li>
                <li>Full name and profile picture (from OAuth providers, if you sign in via Google, Discord, or GitHub — only if your provider shares them)</li>
              </ul>

              <p><strong>License & order data</strong> — When you purchase a license:</p>
              <ul>
                <li>Order details (plan, amount, payment method reference)</li>
                <li>License key and activation status</li>
                <li>Hardware ID (HWID) — a hash derived from your computer's hardware, used to bind your license to one device</li>
              </ul>

              <p><strong>App telemetry</strong> — When the desktop app runs:</p>
              <ul>
                <li>HWID (for license validation)</li>
                <li>App version</li>
                <li>Public IP address (for license heartbeat — not stored permanently)</li>
                <li>Hostname (for display in admin panel only, not shared)</li>
                <li>License validity status and expiry</li>
              </ul>

              <p><strong>Analytics data</strong> (only with your consent):</p>
              <ul>
                <li>Approximate geographic location: country, city, latitude/longitude (derived server-side from your IP — your raw IP is not stored)</li>
                <li>Page visited</li>
                <li>Visit timestamp</li>
              </ul>

              <p><strong>Technical data</strong> — automatically collected for security:</p>
              <ul>
                <li>Browser user-agent string (to filter bots)</li>
                <li>Cloudflare Turnstile challenge result (to verify you are human — no biometrics, no CAPTCHA image stored)</li>
              </ul>

              <div className={styles.infoBox}>
                <strong>We do not collect:</strong> payment card numbers, bank account details, game account credentials, gameplay data, microphone/camera input, screen captures, or any data beyond what is described above.
              </div>
            </div>
          </div>

          {/* 3. Purpose */}
          <div className={styles.section} id="purpose">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>3</span>
              <h2 className={styles.sectionTitle}>How We Use Your Data</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>We use your data only for the following purposes:</p>
              <ul>
                <li><strong>Authentication & account management</strong> — To create and maintain your account, enable secure sign-in, and manage session tokens.</li>
                <li><strong>License management</strong> — To issue, validate, and renew software licenses. HWID is used exclusively to bind and verify license ownership.</li>
                <li><strong>Order processing</strong> — To record purchases, track payment status, and deliver license keys.</li>
                <li><strong>Software updates & heartbeat</strong> — The desktop app periodically contacts our server to verify license validity and check for updates. This contact sends HWID and version — no other data.</li>
                <li><strong>Analytics</strong> (consent required) — To display the "Players Around the World" globe on our homepage showing approximate geographic distribution of users. Data is aggregated and not linked to individual accounts.</li>
                <li><strong>Security & anti-abuse</strong> — To detect and prevent bot traffic, license fraud, and abuse of our systems.</li>
                <li><strong>Support</strong> — To assist you when you contact us with questions or issues.</li>
                <li><strong>Transactional email</strong> — To send account-related emails: welcome on signup, magic-link sign-in, password reset. We do not send marketing emails without explicit opt-in.</li>
              </ul>
              <p>We do not use your data for advertising, profiling, behavioural tracking, or sale to third parties.</p>
            </div>
          </div>

          {/* 4. Cookies */}
          <div className={styles.section} id="cookies">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>4</span>
              <h2 className={styles.sectionTitle}>Cookies & Local Storage</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>We use a minimal set of cookies and browser storage. You can manage your preferences via the cookie banner or at any time through the cookie settings link in the footer.</p>

              <table className={styles.cookieTable}>
                <thead>
                  <tr>
                    <th>Name / Key</th>
                    <th>Type</th>
                    <th>Purpose</th>
                    <th>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>sb-*-auth-token</td>
                    <td><span className={`${styles.badge} ${styles.badgeEssential}`}>Essential</span></td>
                    <td>Supabase authentication session. Keeps you signed in.</td>
                    <td>Session / 1 week</td>
                  </tr>
                  <tr>
                    <td>wwm_cookie_consent</td>
                    <td><span className={`${styles.badge} ${styles.badgeEssential}`}>Essential</span></td>
                    <td>Stores your cookie preference decision (localStorage). Required to remember your choice.</td>
                    <td>Permanent (localStorage)</td>
                  </tr>
                  <tr>
                    <td>wwm_tracked</td>
                    <td><span className={`${styles.badge} ${styles.badgeAnalytics}`}>Analytics</span></td>
                    <td>Prevents duplicate visit tracking within one browser session (sessionStorage). Set only if analytics cookies are accepted.</td>
                    <td>Browser session</td>
                  </tr>
                  <tr>
                    <td>cf-* (Cloudflare)</td>
                    <td><span className={`${styles.badge} ${styles.badgeEssential}`}>Essential</span></td>
                    <td>Cloudflare Turnstile bot-protection challenge token. Used to distinguish humans from automated bots.</td>
                    <td>Session</td>
                  </tr>
                </tbody>
              </table>

              <p style={{ marginTop: 16 }}>We do not use advertising cookies, social media tracking pixels, or any cookies that follow you across other websites.</p>

              <div className={styles.infoBox}>
                You can withdraw your analytics consent at any time by clicking <strong>"Cookie Settings"</strong> in the footer. Essential cookies cannot be disabled as the site cannot function without them.
              </div>
            </div>
          </div>

          {/* 5. Third-party */}
          <div className={styles.section} id="third-party">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>5</span>
              <h2 className={styles.sectionTitle}>Third-Party Services</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>We use the following third-party services, each of which has its own privacy policy:</p>
              <ul>
                <li>
                  <strong>Supabase</strong> — Our backend infrastructure (database, authentication, edge functions). Data is stored on Supabase servers in the <strong>ap-southeast-1</strong> (Singapore) region. <a href="https://supabase.com/privacy" target="_blank" rel="noopener">Supabase Privacy Policy</a>
                </li>
                <li>
                  <strong>Cloudflare Turnstile</strong> — Bot detection on our website. Cloudflare processes your browser's challenge response but does not store your IP address on our behalf. <a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noopener">Cloudflare Privacy Policy</a>
                </li>
                <li>
                  <strong>Google OAuth</strong> — If you choose to sign in with Google, Google shares your email, name, and profile picture with us per your Google account settings. <a href="https://policies.google.com/privacy" target="_blank" rel="noopener">Google Privacy Policy</a>
                </li>
                <li>
                  <strong>Discord OAuth</strong> — If you choose to sign in with Discord, Discord shares your username and email. <a href="https://discord.com/privacy" target="_blank" rel="noopener">Discord Privacy Policy</a>
                </li>
                <li>
                  <strong>GitHub OAuth</strong> — If you choose to sign in with GitHub, GitHub shares your email and username. <a href="https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement" target="_blank" rel="noopener">GitHub Privacy Policy</a>
                </li>
                <li>
                  <strong>Hostinger (email delivery)</strong> — We use Hostinger's SMTP service to send transactional emails (welcome, password reset, magic link). Only your email address and name are transmitted. <a href="https://www.hostinger.com/privacy-policy" target="_blank" rel="noopener">Hostinger Privacy Policy</a>
                </li>
              </ul>
              <p>We do not use Google Analytics, Meta Pixel, or any advertising networks.</p>
            </div>
          </div>

          {/* 6. Retention */}
          <div className={styles.section} id="retention">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>6</span>
              <h2 className={styles.sectionTitle}>Data Retention</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>We retain your data only as long as necessary:</p>
              <ul>
                <li><strong>Account data</strong> — Retained while your account is active. Deleted within 30 days of account deletion request.</li>
                <li><strong>License & order data</strong> — Retained for 5 years for financial record-keeping compliance, then deleted.</li>
                <li><strong>App heartbeat data</strong> — The last-seen timestamp and version are updated each heartbeat. Historical heartbeat data is not retained beyond 90 days.</li>
                <li><strong>Analytics visit data</strong> — Retained for 90 days, then automatically deleted.</li>
                <li><strong>Auth logs</strong> — Managed by Supabase. Retained per their policy.</li>
              </ul>
              <p>When you delete your account, we delete your profile, login credentials, and associated personal data. License records may be retained for financial compliance purposes with personal identifiers removed.</p>
            </div>
          </div>

          {/* 7. Rights */}
          <div className={styles.section} id="rights">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>7</span>
              <h2 className={styles.sectionTitle}>Your Rights</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>Depending on your location, you may have the following rights regarding your personal data:</p>
              <ul>
                <li><strong>Access</strong> — Request a copy of the personal data we hold about you.</li>
                <li><strong>Correction</strong> — Request correction of inaccurate or incomplete data. You can update your name in your dashboard.</li>
                <li><strong>Deletion</strong> — Request deletion of your account and associated personal data ("right to be forgotten").</li>
                <li><strong>Portability</strong> — Request your data in a machine-readable format.</li>
                <li><strong>Objection</strong> — Object to processing of your data where we rely on legitimate interests.</li>
                <li><strong>Withdraw consent</strong> — Withdraw analytics consent at any time via Cookie Settings in the footer. This does not affect the lawfulness of processing before withdrawal.</li>
              </ul>
              <p>To exercise any of these rights, contact us via Discord (see Section 10). We will respond within 30 days. We may need to verify your identity before processing your request.</p>
              <p>If you are located in the EU/EEA, you have the right to lodge a complaint with your local data protection authority.</p>
            </div>
          </div>

          {/* 8. Children */}
          <div className={styles.section} id="children">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>8</span>
              <h2 className={styles.sectionTitle}>Children's Privacy</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>Our Service is not directed to children under the age of 13. We do not knowingly collect personal information from children under 13. If you are a parent or guardian and believe your child has provided us with personal information, please contact us and we will delete it promptly.</p>
              <p>Users between 13 and 18 must have parental consent to use the Service.</p>
            </div>
          </div>

          {/* 9. Changes */}
          <div className={styles.section} id="changes">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>9</span>
              <h2 className={styles.sectionTitle}>Changes to This Policy</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>We may update this Privacy Policy from time to time. When we make material changes, we will update the "Last updated" date at the top of this page and announce the change on our Discord server.</p>
              <p>We encourage you to review this Policy periodically. Your continued use of the Service after changes are posted constitutes your acceptance of the updated Policy.</p>
            </div>
          </div>

          {/* 10. Contact */}
          <div className={styles.section} id="contact">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>10</span>
              <h2 className={styles.sectionTitle}>Contact</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>For privacy-related requests, questions, or concerns:</p>
              <div className={styles.contactCard}>
                <span className={styles.contactIcon}>🔒</span>
                <div className={styles.contactInfo}>
                  <h4>WWM Overlay — Data Privacy</h4>
                  <p>
                    Discord (preferred): <a href="https://discord.com/users/1382397076889145444" target="_blank" rel="noopener">ミ★ ムKim</a><br/>
                    Please include "Privacy Request" in your message subject. We aim to respond within 30 days.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom nav */}
        <div className={styles.bottomNav}>
          <span>© {new Date().getFullYear()} WWM Overlay. All rights reserved.</span>
          <Link href="/terms">Terms of Service →</Link>
        </div>
      </main>
    </>
  );
}
