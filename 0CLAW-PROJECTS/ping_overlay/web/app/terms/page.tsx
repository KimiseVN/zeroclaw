import Link from "next/link";
import Header from "@/components/Header";
import styles from "@/app/legal/legal.module.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — WWM Overlay",
  description: "Terms and conditions for using WWM Overlay software and services.",
};

const LAST_UPDATED = "May 13, 2025";

const TOC = [
  { id: "acceptance",  label: "Acceptance of Terms" },
  { id: "license",     label: "Software License" },
  { id: "account",     label: "Account & Registration" },
  { id: "hwid",        label: "Hardware ID Binding" },
  { id: "prohibited",  label: "Prohibited Conduct" },
  { id: "payment",     label: "Payment & Refunds" },
  { id: "updates",     label: "Updates & Availability" },
  { id: "liability",   label: "Limitation of Liability" },
  { id: "termination", label: "Termination" },
  { id: "governing",   label: "Governing Law" },
  { id: "contact",     label: "Contact" },
];

export default function TermsPage() {
  return (
    <>
      <Header />
      <main className={styles.page}>
        {/* Hero */}
        <div className={styles.hero}>
          <div className={styles.heroIcon}>📄</div>
          <div className={styles.heroLabel}>Legal</div>
          <h1 className={styles.heroTitle}>Terms of Service</h1>
          <p className={styles.heroMeta}>Last updated: {LAST_UPDATED} · Effective immediately upon account creation</p>
        </div>

        <div className={styles.container}>
          {/* Intro */}
          <div className={styles.infoBox} style={{ marginBottom: 36 }}>
            By downloading, installing, or using <strong>WWM Overlay</strong> ("the Software") or accessing our website and services, you agree to be bound by these Terms of Service. If you do not agree, do not use the Software or services.
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

          {/* 1. Acceptance */}
          <div className={styles.section} id="acceptance">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>1</span>
              <h2 className={styles.sectionTitle}>Acceptance of Terms</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>These Terms of Service ("Terms") constitute a legally binding agreement between you ("User") and WWM Overlay ("we", "our", "us") governing your use of the WWM Overlay software, website, and related services (collectively the "Service").</p>
              <p>You must be at least 13 years of age to use this Service. By using the Service you represent that you meet this requirement. Users under 18 must have parental or guardian consent.</p>
              <p>We reserve the right to update these Terms at any time. Continued use of the Service after changes constitutes acceptance of the revised Terms. Material changes will be announced via our Discord server.</p>
            </div>
          </div>

          {/* 2. License */}
          <div className={styles.section} id="license">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>2</span>
              <h2 className={styles.sectionTitle}>Software License</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>Subject to your compliance with these Terms, we grant you a limited, non-exclusive, non-transferable, revocable license to:</p>
              <ul>
                <li>Download and install one copy of WWM Overlay on one computer that you own or control.</li>
                <li>Use WWM Overlay solely for your personal, non-commercial gaming purposes with <em>Wild West Mania</em>.</li>
              </ul>
              <p>This license does <strong>not</strong> grant you the right to:</p>
              <ul>
                <li>Copy, modify, adapt, translate, or create derivative works of the Software.</li>
                <li>Reverse-engineer, decompile, disassemble, or attempt to discover the source code.</li>
                <li>Sell, resell, sublicense, rent, lend, or transfer the Software or your license to any third party.</li>
                <li>Remove, alter, or obscure any proprietary notices or labels on the Software.</li>
                <li>Use the Software in any way not expressly permitted by these Terms.</li>
              </ul>
              <p>All rights not expressly granted are reserved by us. The Software is licensed, not sold.</p>
            </div>
          </div>

          {/* 3. Account */}
          <div className={styles.section} id="account">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>3</span>
              <h2 className={styles.sectionTitle}>Account & Registration</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>To access certain features (license management, order history, dashboard) you must create an account. You agree to:</p>
              <ul>
                <li>Provide accurate and complete registration information.</li>
                <li>Keep your account credentials confidential and not share them with others.</li>
                <li>Notify us immediately of any unauthorised access to your account.</li>
                <li>Accept full responsibility for all activity that occurs under your account.</li>
              </ul>
              <p>We support sign-in via email/password, magic link, Google, Discord, and GitHub. Third-party OAuth providers are subject to their own terms of service.</p>
              <p>We reserve the right to suspend or terminate accounts that violate these Terms or that we believe have been compromised.</p>
            </div>
          </div>

          {/* 4. HWID */}
          <div className={styles.section} id="hwid">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>4</span>
              <h2 className={styles.sectionTitle}>Hardware ID (HWID) Binding</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>Each license is bound to a single Hardware ID (HWID) — a unique identifier derived from your computer's hardware configuration. This is necessary to prevent license sharing and protect license integrity.</p>
              <div className={styles.warnBox}>
                <strong>⚠️ Important:</strong> A license may only be active on <strong>one device at a time</strong>. Installing on additional devices requires purchasing additional licenses.
              </div>
              <p>If you change significant hardware components your HWID may change and your license may need to be reset. Contact us on Discord for HWID reset requests — we allow one free reset per license per 90 days in reasonable circumstances (hardware upgrade, OS reinstall).</p>
              <p>Attempts to spoof, manipulate, or bypass the HWID system are a material breach of these Terms and will result in immediate license revocation without refund.</p>
            </div>
          </div>

          {/* 5. Prohibited */}
          <div className={styles.section} id="prohibited">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>5</span>
              <h2 className={styles.sectionTitle}>Prohibited Conduct</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>You agree not to:</p>
              <ul>
                <li>Use the Software to gain an unfair competitive advantage beyond its documented overlay features.</li>
                <li>Share, sell, or distribute your license key to others.</li>
                <li>Attempt to bypass, circumvent, or interfere with any security, anti-cheat, or licensing mechanisms.</li>
                <li>Use the Software in conjunction with any cheating software, aimbots, macros, or exploits.</li>
                <li>Impersonate any person or entity, or misrepresent your affiliation with any person or entity.</li>
                <li>Upload or transmit any malicious code, viruses, or other harmful software.</li>
                <li>Attempt to access any non-public areas of our systems or infrastructure.</li>
                <li>Use automated bots or scripts to interact with our website or services.</li>
                <li>Use the Service for any unlawful purpose or in violation of any applicable laws.</li>
              </ul>
              <p>We reserve the right to determine what constitutes a violation at our sole discretion. Violations may result in immediate license revocation and account termination without refund.</p>
            </div>
          </div>

          {/* 6. Payment */}
          <div className={styles.section} id="payment">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>6</span>
              <h2 className={styles.sectionTitle}>Payment & Refunds</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>All purchases are processed manually. Payment methods accepted include PayPal and bank transfer. Prices are displayed in USD and VND and are subject to change without notice.</p>
              <p><strong>License activation:</strong> Your license is activated by an administrator after payment is verified. This may take up to 24 hours during business hours (Vietnam time).</p>
              <p><strong>Free trial:</strong> We offer a limited-time free trial so you can evaluate the Software before purchasing. Trial features and duration are at our discretion.</p>
              <div className={styles.warnBox}>
                <strong>Refund policy:</strong> Due to the digital nature of the Software, all sales are <strong>final</strong>. We do not offer refunds once a license key has been activated and bound to a HWID. If you experience a technical issue preventing use of the Software, contact us within 7 days of purchase and we will make reasonable efforts to resolve it.
              </div>
              <p>Chargebacks or payment disputes filed without first contacting us will result in immediate account termination and may be reported to payment processors.</p>
            </div>
          </div>

          {/* 7. Updates */}
          <div className={styles.section} id="updates">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>7</span>
              <h2 className={styles.sectionTitle}>Updates & Availability</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>We may release updates, patches, or new versions of the Software at any time. The Software may require you to install updates in order to continue using it. We are not obligated to provide updates.</p>
              <p>We may modify, suspend, or discontinue the Service (or any part thereof) at any time with or without notice. We are not liable to you or any third party for any such modification, suspension, or discontinuation.</p>
              <p>Service availability is provided on an "as-is" basis. We do not guarantee uninterrupted access. Scheduled maintenance will be announced on Discord where possible.</p>
            </div>
          </div>

          {/* 8. Liability */}
          <div className={styles.section} id="liability">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>8</span>
              <h2 className={styles.sectionTitle}>Limitation of Liability</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>The Software is provided "AS IS" without warranty of any kind. To the maximum extent permitted by applicable law, we disclaim all warranties, express or implied, including but not limited to warranties of merchantability, fitness for a particular purpose, and non-infringement.</p>
              <p>We are not responsible for any game account actions (bans, suspensions, penalties) that may result from using third-party software including WWM Overlay. Use is at your own risk. While we design the Software to be safe, we make no guarantees regarding interactions with game anti-cheat systems.</p>
              <p>In no event shall we be liable for any indirect, incidental, special, consequential, or punitive damages, including loss of profits, data, or goodwill, arising out of or in connection with your use of the Service, even if advised of the possibility of such damages.</p>
              <p>Our total liability to you for any claims arising under these Terms shall not exceed the amount you paid for the Service in the 12 months preceding the claim.</p>
            </div>
          </div>

          {/* 9. Termination */}
          <div className={styles.section} id="termination">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>9</span>
              <h2 className={styles.sectionTitle}>Termination</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>You may stop using the Service at any time. Deleting your account is available from your dashboard settings.</p>
              <p>We may terminate or suspend your account and license at our sole discretion, without prior notice or liability, for any reason, including but not limited to: violation of these Terms, fraudulent activity, or requests from law enforcement.</p>
              <p>Upon termination, your license is revoked, your right to use the Software ceases immediately, and we may delete your account data subject to our Privacy Policy and applicable law.</p>
              <p>Sections that by their nature should survive termination (Limitation of Liability, Governing Law, and any payment obligations) shall survive.</p>
            </div>
          </div>

          {/* 10. Governing law */}
          <div className={styles.section} id="governing">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>10</span>
              <h2 className={styles.sectionTitle}>Governing Law</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>These Terms shall be governed by and construed in accordance with the laws of the Socialist Republic of Vietnam. Any disputes arising under these Terms shall be subject to the exclusive jurisdiction of the competent courts of Vietnam.</p>
              <p>If any provision of these Terms is found to be unenforceable, the remaining provisions will remain in full force and effect.</p>
              <p>These Terms constitute the entire agreement between you and us with respect to the Service and supersede all prior agreements.</p>
            </div>
          </div>

          {/* 11. Contact */}
          <div className={styles.section} id="contact">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>11</span>
              <h2 className={styles.sectionTitle}>Contact</h2>
            </div>
            <div className={styles.sectionBody}>
              <p>If you have any questions about these Terms, please contact us:</p>
              <div className={styles.contactCard}>
                <span className={styles.contactIcon}>💬</span>
                <div className={styles.contactInfo}>
                  <h4>WWM Overlay Support</h4>
                  <p>
                    Discord (preferred): <a href="https://discord.com/users/1382397076889145444" target="_blank" rel="noopener">ミ★ ムKim</a><br/>
                    For urgent legal matters, contact us through Discord and we will provide a direct email address.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom nav */}
        <div className={styles.bottomNav}>
          <span>© {new Date().getFullYear()} WWM Overlay. All rights reserved.</span>
          <Link href="/privacy">Privacy Policy →</Link>
        </div>
      </main>
    </>
  );
}
