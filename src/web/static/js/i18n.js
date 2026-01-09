/**
 * Frontend internationalization (i18n) module for CharTii-i18n.
 *
 * This module provides translation functionality for JavaScript code.
 * It loads translations from the server and provides a simple t() function
 * for retrieving translated strings.
 */

(function () {
  "use strict";

  // i18n namespace
  const i18n = {
    translations: {},
    currentLang: window.currentLang || "en",
    isLoaded: false,
    loadPromise: null,
  };

  /**
   * Load translations for the current language.
   * @returns {Promise} Resolves when translations are loaded
   */
  i18n.load = function () {
    if (i18n.loadPromise) {
      return i18n.loadPromise;
    }

    i18n.loadPromise = fetch(`/api/settings/translations?lang=${i18n.currentLang}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Failed to load translations: ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        i18n.translations = data.translations || {};
        i18n.isLoaded = true;
        return i18n.translations;
      })
      .catch((error) => {
        console.warn("Failed to load translations, using keys as fallback:", error);
        i18n.translations = {};
        i18n.isLoaded = true;
        return i18n.translations;
      });

    return i18n.loadPromise;
  };

  /**
   * Get a nested value from an object using dot notation.
   * @param {Object} obj - The object to search
   * @param {string} path - Dot-separated path (e.g., 'nav.home')
   * @returns {string|undefined} The value if found
   */
  function getNestedValue(obj, path) {
    const keys = path.split(".");
    let current = obj;

    for (const key of keys) {
      if (current && typeof current === "object" && key in current) {
        current = current[key];
      } else {
        return undefined;
      }
    }

    return typeof current === "string" ? current : undefined;
  }

  /**
   * Get a translated string.
   * @param {string} key - The translation key (dot notation, e.g., 'nav.home')
   * @param {Object} params - Optional parameters for string interpolation
   * @returns {string} The translated string or the key if not found
   */
  i18n.t = function (key, params = {}) {
    let value = getNestedValue(i18n.translations, key);

    // If not found, return the key
    if (value === undefined) {
      console.debug(`Translation not found: ${key}`);
      return key;
    }

    // Apply string interpolation if params provided
    if (params && typeof params === "object") {
      Object.keys(params).forEach((paramKey) => {
        const regex = new RegExp(`\\{${paramKey}\\}`, "g");
        value = value.replace(regex, params[paramKey]);
      });
    }

    return value;
  };

  /**
   * Shorthand for i18n.t()
   */
  window.t = function (key, params) {
    return i18n.t(key, params);
  };

  /**
   * Get current language code.
   * @returns {string} Current language code
   */
  i18n.getCurrentLang = function () {
    return i18n.currentLang;
  };

  /**
   * Check if translations are loaded.
   * @returns {boolean} True if loaded
   */
  i18n.isReady = function () {
    return i18n.isLoaded;
  };

  /**
   * Wait for translations to be loaded.
   * @returns {Promise} Resolves when translations are ready
   */
  i18n.ready = function () {
    if (i18n.isLoaded) {
      return Promise.resolve(i18n.translations);
    }
    return i18n.load();
  };

  // Expose i18n to global scope
  window.i18n = i18n;

  // Auto-load translations on DOMContentLoaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      i18n.load();
    });
  } else {
    // DOM already loaded
    i18n.load();
  }
})();
