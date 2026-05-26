import Link from "next/link";
import Header from "@/components/Header";
import styles from "@/app/legal/legal.module.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Installer Exit Codes — WWM Overlay",
  description:
    "Reference for WWM Overlay installer (Inno Setup) EXE return codes — exit code values for each installation scenario.",
  robots: { index: true, follow: true },
};

const CODES = [
  {
    code: 8,
    title: "Application already installed (upgrade / reinstall)",
    badge: "Custom",
    badgeColor: "#8b5cf6",
    icon: "🔄",
    description:
      "The installer detected an existing installation of WWM Overlay on this device before setup began. The installation completed successfully as an upgrade or reinstall. This custom exit code is returned instead of 0 to allow deployment systems (Intune, WinGet) to distinguish an upgrade from a fresh install.",
    causes: [
      "WWM Overlay was previously installed on this device.",
      "User is reinstalling the same or a newer version over an existing install.",
      "Deployment system is pushing an update to an already-managed device.",
    ],
    resolution:
      "No action needed — the upgrade completed successfully. The application is up to date. This code is informational only.",
    scenarios: ["Application already exists"],
  },
  {
    code: 1,
    title: "Setup failed to initialize",
    badge: "Fatal",
    badgeColor: "#ef4444",
    icon: "💥",
    description:
      "The installer process could not start. This typically means the installer executable is corrupted, a required DLL is missing, or the system environment prevented the process from launching (e.g. out of memory, corrupted temp directory).",
    causes: [
      "Downloaded installer file is incomplete or corrupted (hash mismatch).",
      "Antivirus or security software blocked the process before it could start.",
      "Insufficient memory or resources to start the installer.",
      "Corrupted %TEMP% directory or missing Windows runtime components.",
    ],
    resolution:
      "Re-download the installer from the official release page and verify the SHA-256 hash before running. Add a Windows Defender exclusion for the file if AV is blocking it.",
    scenarios: [],
  },
  {
    code: 2,
    title: "User cancelled before installation began",
    badge: "Cancelled",
    badgeColor: "#f59e0b",
    icon: "🚫",
    description:
      'The wizard launched successfully but the user clicked "Cancel" or "No" before any files were copied — typically on the welcome screen, the license agreement screen, or the initial confirmation prompt. No changes were made to the system.',
    causes: [
      'User dismissed the installer on the "This will install…" confirmation.',
      'User declined the license agreement (clicked "I do not accept").',
      'User clicked "Cancel" on the wizard welcome page.',
      "Silent install received a termination signal before setup phases began.",
    ],
    resolution:
      "No action needed — the system is unchanged. Re-run the installer if the cancellation was unintentional. For silent/automated deployments, ensure the correct switches are passed (/VERYSILENT /SUPPRESSMSGBOXES /NORESTART).",
    scenarios: ["Installation cancelled by user"],
  },
  {
    code: 3,
    title: "Fatal error preparing installation",
    badge: "Fatal",
    badgeColor: "#ef4444",
    icon: "⚠️",
    description:
      "A fatal error occurred while the installer was preparing to transition to the actual file-copy phase. Setup has already validated prerequisites but failed before writing any files. System state may be partially modified (e.g. temp extraction started).",
    causes: [
      "Insufficient disk space detected during pre-install check.",
      "Target install directory is locked or inaccessible (permissions issue).",
      "A required pre-install script or custom action threw an unhandled exception.",
      "UAC elevation was denied or timed out mid-preparation.",
    ],
    resolution:
      "Check available disk space on the target drive (minimum ~200 MB required). Ensure you are running the installer as Administrator. If using a managed deployment, verify the deployment account has write access to %ProgramFiles(x86)%.",
    scenarios: ["Disk space is full", "Installation already in progress"],
  },
  {
    code: 4,
    title: "Fatal error during installation",
    badge: "Fatal",
    badgeColor: "#ef4444",
    icon: "❌",
    description:
      "A fatal error occurred while files were actively being copied or registered. The installation is incomplete — some files may have been written. Inno Setup will attempt to roll back any changes it can, but a partial install state is possible.",
    causes: [
      "Disk became full while copying files.",
      "A file being replaced was locked by another process (e.g. PingOverlay.exe still running).",
      "Write access denied to %ProgramFiles(x86)%\\PingOverlay\\.",
      "Antivirus quarantined or deleted a file during the copy operation.",
      "Security policy on the device blocked execution of the installer payload.",
    ],
    resolution:
      "Free disk space and re-run the installer. Ensure PingOverlay.exe is not running before installing (the installer auto-kills it via taskkill, but security software may block this). Add an AV exclusion for the install directory. For managed deployments, verify no group policy restricts writes to Program Files.",
    scenarios: [
      "Disk space is full",
      "Network failure",
      "Package rejected during installation",
    ],
  },
  {
    code: 5,
    title: "User cancelled during installation",
    badge: "Cancelled",
    badgeColor: "#f59e0b",
    icon: "⛔",
    description:
      'The user clicked Cancel or chose Abort in an Abort-Retry-Ignore dialog while files were actively being copied. The installation is incomplete. Inno Setup will attempt to roll back written files, but the system may be left in a partially installed state.',
    causes: [
      'User clicked Cancel on the progress screen mid-copy.',
      'User chose Abort when prompted on a file-write error.',
      "Process was forcefully terminated by an external tool during file copy.",
    ],
    resolution:
      "Run the installer again from the beginning. If the app appears partially installed (visible in Add/Remove Programs), uninstall it first via Control Panel before re-installing. For automated deployments use /VERYSILENT to prevent any Cancel UI from appearing.",
    scenarios: ["Installation cancelled by user"],
  },
];

export default function InstallerExitCodesPage() {
  return (
    <>
      <Header />
      <main className={styles.page}>
        {/* Hero */}
        <div className={styles.hero}>
          <div className={styles.heroIcon}>🛠️</div>
          <div className={styles.heroLabel}>Developer Reference</div>
          <h1 className={styles.heroTitle}>Installer Exit Codes</h1>
          <p className={styles.heroMeta}>
            WWM Overlay Setup (Inno Setup) · EXE return code reference for
            deployment and enterprise management systems
          </p>
        </div>

        <div className={styles.container}>
          {/* Intro */}
          <div className={styles.infoBox} style={{ marginBottom: 36 }}>
            <strong>Installer technology:</strong> Inno Setup 6 &nbsp;·&nbsp;
            <strong>Silent switch:</strong>{" "}
            <code
              style={{
                background: "rgba(0,229,255,.08)",
                padding: "2px 7px",
                borderRadius: 5,
                fontFamily: "monospace",
                fontSize: 12,
              }}
            >
              /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
            </code>
            &nbsp;·&nbsp;
            <strong>Default install dir:</strong>{" "}
            <code
              style={{
                background: "rgba(0,229,255,.08)",
                padding: "2px 7px",
                borderRadius: 5,
                fontFamily: "monospace",
                fontSize: 12,
              }}
            >
              C:\Program Files (x86)\PingOverlay\
            </code>
          </div>

          {/* Code table summary */}
          <table className={styles.cookieTable} style={{ marginBottom: 44 }}>
            <thead>
              <tr>
                <th>Exit Code</th>
                <th>Meaning</th>
                <th>System changed?</th>
              </tr>
            </thead>
            <tbody>
              {CODES.map((c) => (
                <tr key={c.code}>
                  <td>
                    <a href={`#code-${c.code}`}>{c.code}</a>
                  </td>
                  <td style={{ color: "var(--text-muted)" }}>{c.title}</td>
                  <td
                    style={{
                      color:
                        c.code === 2 || c.code === 8
                          ? "#22c55e"
                          : c.code === 5
                          ? "#f59e0b"
                          : "#ef4444",
                    }}
                  >
                    {c.code === 2
                      ? "No"
                      : c.code === 8
                      ? "Yes (upgrade success)"
                      : c.code === 5
                      ? "Partial (rollback attempted)"
                      : c.code === 1
                      ? "No"
                      : c.code === 3
                      ? "Partial"
                      : "Partial (rollback attempted)"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Individual code sections */}
          {CODES.map((c) => (
            <div className={styles.section} id={`code-${c.code}`} key={c.code}>
              <div className={styles.sectionHeader}>
                <span className={styles.sectionNum}>{c.code}</span>
                <h2 className={styles.sectionTitle}>
                  {c.icon} {c.title}
                </h2>
                <span
                  style={{
                    marginLeft: "auto",
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: ".06em",
                    textTransform: "uppercase",
                    padding: "3px 10px",
                    borderRadius: 100,
                    background: `${c.badgeColor}18`,
                    color: c.badgeColor,
                    border: `1px solid ${c.badgeColor}40`,
                    flexShrink: 0,
                  }}
                >
                  {c.badge}
                </span>
              </div>

              <div className={styles.sectionBody}>
                <p>{c.description}</p>

                <p style={{ fontWeight: 600, color: "var(--text-dim)" }}>
                  Common causes:
                </p>
                <ul>
                  {c.causes.map((cause, i) => (
                    <li key={i}>{cause}</li>
                  ))}
                </ul>

                {c.scenarios.length > 0 && (
                  <>
                    <p style={{ fontWeight: 600, color: "var(--text-dim)" }}>
                      Maps to install scenario(s):
                    </p>
                    <ul>
                      {c.scenarios.map((s, i) => (
                        <li key={i}>
                          <em>{s}</em>
                        </li>
                      ))}
                    </ul>
                  </>
                )}

                <div className={styles.infoBox}>
                  <strong>Resolution:</strong> {c.resolution}
                </div>
              </div>
            </div>
          ))}

          {/* Silent install reference */}
          <div className={styles.section} id="silent-install">
            <div className={styles.sectionHeader}>
              <span className={styles.sectionNum}>⚙</span>
              <h2 className={styles.sectionTitle}>Silent Install Reference</h2>
            </div>
            <div className={styles.sectionBody}>
              <table className={styles.cookieTable}>
                <thead>
                  <tr>
                    <th>Switch</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>/VERYSILENT</td>
                    <td>Suppress all UI — no wizard window, no progress dialog.</td>
                  </tr>
                  <tr>
                    <td>/SILENT</td>
                    <td>Show only the progress bar (no wizard pages).</td>
                  </tr>
                  <tr>
                    <td>/SUPPRESSMSGBOXES</td>
                    <td>Suppress all message box popups (error dialogs, confirmations).</td>
                  </tr>
                  <tr>
                    <td>/NORESTART</td>
                    <td>Prevent automatic restart even if setup requests one.</td>
                  </tr>
                  <tr>
                    <td>/DIR="path"</td>
                    <td>Override the default installation directory.</td>
                  </tr>
                  <tr>
                    <td>/TASKS="desktopicon"</td>
                    <td>Enable desktop shortcut (unchecked by default).</td>
                  </tr>
                  <tr>
                    <td>/SP-</td>
                    <td>Disable the "This will install…" confirmation prompt.</td>
                  </tr>
                </tbody>
              </table>

              <div className={styles.warnBox}>
                <strong>⚠️ Admin required:</strong> WWM Overlay requires
                administrator privileges at runtime (raw socket ping + Intel
                PresentMon ETW for FPS monitoring). The installer itself also
                runs as admin (<code>PrivilegesRequired=admin</code>). Ensure
                your deployment system runs the installer in an elevated
                context.
              </div>
            </div>
          </div>
        </div>

        {/* Bottom nav */}
        <div className={styles.bottomNav}>
          <span>© {new Date().getFullYear()} WWM Overlay. All rights reserved.</span>
          <Link href="/download">Download →</Link>
        </div>
      </main>
    </>
  );
}
