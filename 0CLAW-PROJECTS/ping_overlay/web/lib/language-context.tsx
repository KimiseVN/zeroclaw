"use client";
import { createContext, useContext, useEffect, useState } from "react";

type Lang = "vi" | "en";

const LangCtx = createContext<{ lang: Lang; toggle: () => void }>({
  lang: "vi",
  toggle: () => {},
});

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = useState<Lang>("vi");

  useEffect(() => {
    const saved = localStorage.getItem("site_lang") as Lang | null;
    if (saved === "en" || saved === "vi") setLang(saved);
  }, []);

  function toggle() {
    setLang(prev => {
      const next: Lang = prev === "vi" ? "en" : "vi";
      localStorage.setItem("site_lang", next);
      return next;
    });
  }

  return <LangCtx.Provider value={{ lang, toggle }}>{children}</LangCtx.Provider>;
}

export function useLanguage() {
  return useContext(LangCtx);
}
