"use client";
import { createContext, useContext, useEffect, useState, useCallback } from "react";

export type CookiePrefs = {
  essential:   true;          // always on, cannot be toggled
  analytics:   boolean;       // visit tracking (IP/country for globe)
  preferences: boolean;       // UI preferences (future use)
  decided:     boolean;       // user has made a choice
  timestamp:   string;        // ISO date of decision
};

const DEFAULT_PREFS: CookiePrefs = {
  essential:   true,
  analytics:   false,
  preferences: false,
  decided:     false,
  timestamp:   "",
};

const STORAGE_KEY = "wwm_cookie_consent";

type Ctx = {
  prefs:      CookiePrefs;
  showBanner: boolean;
  openSettings: () => void;
  acceptAll:  () => void;
  rejectAll:  () => void;
  saveCustom: (analytics: boolean, preferences: boolean) => void;
};

const CookieContext = createContext<Ctx>({
  prefs:        DEFAULT_PREFS,
  showBanner:   false,
  openSettings: () => {},
  acceptAll:    () => {},
  rejectAll:    () => {},
  saveCustom:   () => {},
});

export function CookieConsentProvider({ children }: { children: React.ReactNode }) {
  const [prefs,       setPrefs]       = useState<CookiePrefs>(DEFAULT_PREFS);
  const [showBanner,  setShowBanner]  = useState(false);
  const [_settingsOpen, _setSettingsOpen] = useState(false); // internal — banner manages this

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as CookiePrefs;
        setPrefs({ ...DEFAULT_PREFS, ...saved, essential: true });
        setShowBanner(false);
      } else {
        // First visit — show banner after short delay
        const t = setTimeout(() => setShowBanner(true), 1200);
        return () => clearTimeout(t);
      }
    } catch {
      setShowBanner(true);
    }
  }, []);

  function persist(next: CookiePrefs) {
    setPrefs(next);
    setShowBanner(false);
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch {}
  }

  const acceptAll = useCallback(() => {
    persist({ essential: true, analytics: true, preferences: true, decided: true, timestamp: new Date().toISOString() });
  }, []);

  const rejectAll = useCallback(() => {
    persist({ essential: true, analytics: false, preferences: false, decided: true, timestamp: new Date().toISOString() });
  }, []);

  const saveCustom = useCallback((analytics: boolean, preferences: boolean) => {
    persist({ essential: true, analytics, preferences, decided: true, timestamp: new Date().toISOString() });
  }, []);

  const openSettings = useCallback(() => {
    setShowBanner(true);
  }, []);

  return (
    <CookieContext.Provider value={{ prefs, showBanner, openSettings, acceptAll, rejectAll, saveCustom }}>
      {children}
    </CookieContext.Provider>
  );
}

export function useCookieConsent() {
  return useContext(CookieContext);
}
