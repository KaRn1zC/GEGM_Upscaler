import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";
import en from "@/i18n/en.json";
import fr from "@/i18n/fr.json";

/**
 * Init i18next — détection auto via :
 *   1. `localStorage.i18nextLng` (choix user persisté depuis Settings).
 *   2. `navigator.language` (première visite).
 *   3. Fallback `fr` (langue par défaut historique de l'outil).
 *
 * Les resources sont bundlées (pas de fetch async) — 2 langues seulement,
 * coût négligeable sur le bundle. Pour N > 4 langues on migrerait vers
 * `i18next-http-backend` avec chunks par langue.
 */
void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      fr: { translation: fr },
      en: { translation: en },
    },
    fallbackLng: "fr",
    supportedLngs: ["fr", "en"],
    interpolation: {
      escapeValue: false, // React échappe déjà
    },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: "i18nextLng",
    },
  });

export default i18n;
