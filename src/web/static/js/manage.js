// Create LPM namespace for module communication
window.LPM = window.LPM || {};

(function () {
  const metadataSection = document.getElementById("project-metadata");
  if (!metadataSection) {
    console.warn(
      "Project metadata element not found; management page scripts disabled."
    );
    return;
  }

  const projectId = metadataSection.dataset.projectId;
  if (!projectId) {
    console.warn(
      "Project ID missing in metadata; management page not initialised."
    );
    return;
  }

  const API_BASE = `/api/projects/${projectId}`;

  // Expose API_BASE to modules
  window.LPM.API_BASE = API_BASE;

  const selectors = {
    projectTitle: document.getElementById("project-title"),
    projectSubtitle: document.getElementById("project-subtitle"),
    sourceLanguageValue: document.getElementById("source-language-value"),
    sourceKeysCount: document.getElementById("source-keys-count"),
    pageCount: document.getElementById("page-count"),
    targetLanguageCount: document.getElementById("target-language-count"),
    targetLanguageSummary: document.getElementById("target-language-summary"),
    languageProgressTable: document.getElementById("language-progress-table"),
    pagesTable: document.getElementById("pages-table"),
    startTranslateBtn: document.getElementById("start-translate-btn"),
    syncStatusContainer: document.getElementById("project-sync-status"),
    syncSpinner: document.getElementById("sync-spinner"),
    syncStatusText: document.getElementById("sync-status-text"),
    lastSyncedTime: document.getElementById("last-synced-time"),
    reloadSourceLink: document.getElementById("reload-source-link"),
    protectedTermsBtn: document.getElementById("protected-terms-btn"),
    manualTranslateBtn: document.getElementById("manual-translate-btn"),
    manualPageSelect: document.getElementById("manual-page-select"),
    manualSearchInput: document.getElementById("manual-search-input"),
    manualSearchBtn: document.getElementById("manual-search-btn"),
    manualKeyResultsTable: document.getElementById("manual-key-results-table"),
    manualWorklistTable: document.getElementById("manual-worklist-table"),
    manualWorklistSort: document.getElementById("manual-worklist-sort"),
    manualWorklistSelectAll: document.getElementById(
      "manual-worklist-select-all"
    ),
    manualSaveSelectedBtn: document.getElementById("manual-save-selected-btn"),
    manualUnlockSelectedBtn: document.getElementById(
      "manual-unlock-selected-btn"
    ),
    manualLanguageModal: document.getElementById("manualLanguageModal"),
    manualLanguageList: document.getElementById("manual-language-list"),
    manualLanguageConfirmBtn: document.getElementById(
      "manual-language-confirm-btn"
    ),
    protectedEnableSwitch: document.getElementById("protected-terms-enabled"),
    protectedTermInput: document.getElementById("protected-term-input"),
    protectedRegexCheckbox: document.getElementById("protected-regex-checkbox"),
    protectedAddBtn: document.getElementById("protected-add-btn"),
    protectedAnalyzeBtn: document.getElementById("protected-analyze-btn"),
    protectedFilterCategory: document.getElementById(
      "protected-filter-category"
    ),
    protectedSortOrder: document.getElementById("protected-sort-order"),
    protectedTermsTable: document.getElementById("protected-terms-table"),
    suggestionsModal: document.getElementById("protectedSuggestionsModal"),
    suggestionsSelectAll: document.getElementById(
      "protected-suggestions-select-all"
    ),
    suggestionsApplyBtn: document.getElementById(
      "protected-suggestions-apply-btn"
    ),
    suggestionsTable: document.getElementById("protected-suggestions-table"),
    // Translate tab selectors
    translateProvider: document.getElementById("translate-provider"),
    translateProviderError: document.getElementById("translate-provider-error"),
    translateSelectAll: document.getElementById("translate-select-all"),
    translateLanguagesTbody: document.getElementById(
      "translate-languages-tbody"
    ),
    translateStrategyMissing: document.getElementById(
      "translate-strategy-missing"
    ),
    translateStrategyAi: document.getElementById("translate-strategy-ai"),
    translateStrategyFull: document.getElementById("translate-strategy-full"),
    translateStrategyValidate: document.getElementById(
      "translate-strategy-validate"
    ),
    translateFullWarning: document.getElementById("translate-full-warning"),
    translateIncludeLocked: document.getElementById("translate-include-locked"),
    translateConfirmUnderstand: document.getElementById(
      "translate-confirm-understand"
    ),
    translateGenerateFiles: document.getElementById("translate-generate-files"),
    translateStartBtn: document.getElementById("translate-start-btn"),
    translateConfigSection: document.getElementById("translate-config-section"),
    translateProgressSection: document.getElementById(
      "translate-progress-section"
    ),
    translateProgressStatus: document.getElementById(
      "translate-progress-status"
    ),
    translateProgressPercent: document.getElementById(
      "translate-progress-percent"
    ),
    translateProgressBar: document.getElementById("translate-progress-bar"),
    translateBriefingLog: document.getElementById("translate-briefing-log"),
    translateSummaryTranslated: document.getElementById(
      "translate-summary-translated"
    ),
    translateSummarySucceeded: document.getElementById(
      "translate-summary-succeeded"
    ),
    translateSummaryFailed: document.getElementById("translate-summary-failed"),
    translateSummaryFailedLabel: document.getElementById(
      "translate-summary-failed-label"
    ),
    translateSummaryTokenInput: document.getElementById(
      "translate-summary-token-input"
    ),
    translateSummaryTokenOutput: document.getElementById(
      "translate-summary-token-output"
    ),
    translateCancelBtn: document.getElementById("translate-cancel-btn"),
    translateCompletionActions: document.getElementById(
      "translate-completion-actions"
    ),
    translateBackBtn: document.getElementById("translate-back-btn"),
    translateAgainBtn: document.getElementById("translate-again-btn"),
  };

  const state = {
    project: null,
    stats: null,
    languages: [],
    pages: [],
    manual: {
      keyResults: [],
      worklist: [],
      worklistSelected: new Set(),
      selectedRows: new Set(),
      translations: [],
      currentKey: null,
      pendingAddKey: null,
      pendingAddSourceText: null,
      lockedLoaded: false,
      translationCache: new Map(),
    },
    protectedTerms: [],
    protectedTermsDirty: false,
    protectedSuggestions: [],
    autoSyncInProgress: false,
    // Translate tab state
    translate: {
      availableProviders: [],
      selectedProvider: null,
      selectedLanguages: [],
      mode: "missing_only",
      includeLocked: false,
      generateFiles: true,
      jobId: null,
      isRunning: false,
      pollInterval: null,
      currentLanguageIndex: -1,
      // Batch tracking fields
      currentBatch: 0,
      currentPhase: "",
      lastLanguage: "",
      lastTotalBatches: 0,
      lastCompletedLanguage: "", // Track which language's summary was last shown
      lastCompletedStats: {}, // Track completion stats per language to detect updates: {langCode: {successCount, failureCount}}
      processedProgressItems: new Set(), // Track processed progress items by ID to avoid duplicates and support updates
      totalTokenUsage: { prompt_tokens: 0, completion_tokens: 0 }, // Accumulated token usage across all languages
      lastProgressPercent: 0, // Store last valid progress percentage to maintain during retry/saving phases
      // Key count tracking for accurate progress calculation
      languageKeyCounts: {}, // Track key count for each language: {langCode: keyCount}
      completedKeysByLanguage: {}, // Track completed keys for each language: {langCode: completedKeys}
      totalKeysAcrossAllLanguages: 0, // Total keys across all languages
      completedBatchKeys: {}, // Track completed batch keys to avoid double-counting: {batchKey: keyCount}
    },
  };

  // Expose selectors and state to modules
  window.LPM.selectors = selectors;
  window.LPM.state = state;

  function showToast(message, variant = "info") {
    const toastContainer = document.getElementById("toast-stack");
    if (!toastContainer) {
      console.warn("Toast container not found; message was:", message);
      return;
    }

    const variantMap = {
      info: "info",
      success: "success",
      warning: "warning",
      danger: "danger",
    };
    const color = variantMap[variant] || "info";

    const toast = document.createElement("div");
    toast.className = `toast align-items-center text-bg-${color} border-0 shadow`;
    toast.setAttribute("role", "alert");
    toast.setAttribute("aria-live", "assertive");
    toast.setAttribute("aria-atomic", "true");
    toast.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    `;

    toastContainer.appendChild(toast);
    const delay = variant === "danger" ? 9000 : 5000;
    const toastInstance = new bootstrap.Toast(toast, { delay });
    toastInstance.show();
    toast.addEventListener("hidden.bs.toast", () => toast.remove());
  }

  async function fetchJson(url, options = {}) {
    const { headers: extraHeaders, cache, ...restOptions } = options;
    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
        ...(extraHeaders || {}),
      },
      cache: cache ?? "no-store",
      ...restOptions,
    });

    const contentType = response.headers.get("content-type");
    const isJson = contentType && contentType.includes("application/json");
    const data = isJson ? await response.json().catch(() => ({})) : {};

    if (!response.ok) {
      const message =
        data?.error ||
        data?.message ||
        `Request failed (status ${response.status})`;
      throw new Error(message);
    }

    return data;
  }

  function escapeHtml(text) {
    if (typeof text !== "string") {
      return text ?? "";
    }
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatDateTime(value) {
    if (!value) {
      return "-";
    }
    try {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return value;
      }
      return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
    } catch (err) {
      return value;
    }
  }

  // Expose utility functions to modules
  window.LPM.utils = {
    showToast,
    fetchJson,
    escapeHtml,
    formatDateTime,
  };

  const tabIdToName = {
    "#overview-pane": "overview",
    "#protected-pane": "protected",
    "#manual-pane": "manual",
    "#translate-pane": "translate",
  };

  function updateTabInUrl(tabName) {
    try {
      const url = new URL(window.location.href);
      if (tabName) {
        url.searchParams.set("tab", tabName);
      } else {
        url.searchParams.delete("tab");
      }
      window.history.replaceState({}, "", url.toString());
    } catch (err) {
      // ignore URL update errors
    }
  }

  function switchToTab(tabId, persist = true) {
    const container = document.getElementById("manageTabContent");
    if (!container) return;

    const panes = container.querySelectorAll(".tab-pane");
    panes.forEach((pane) => {
      pane.classList.remove("show", "active");
    });
    const target = container.querySelector(tabId);
    if (target) {
      target.classList.add("show", "active");
    }

    if (persist) {
      const tabName = tabIdToName[tabId] || "";
      updateTabInUrl(tabName);
    }
  }

  // Expose switchToTab to modules
  window.LPM.switchToTab = switchToTab;

  function tabIdFromName(name) {
    if (name === "protected") return "#protected-pane";
    if (name === "manual") return "#manual-pane";
    if (name === "translate") return "#translate-pane";
    return "#overview-pane";
  }

  function initTabFromUrl() {
    try {
      const url = new URL(window.location.href);
      const tab = url.searchParams.get("tab");
      const tabId = tabIdFromName(tab);
      switchToTab(tabId, false);
    } catch (err) {
      // ignore URL parsing issues
    }
  }

  /**
   * Update the sync status display in the header.
   * @param {string|null} lastSyncedAt - ISO timestamp or null
   * @param {boolean} isSyncing - Whether sync is in progress
   * @param {string|null} errorMessage - Error message if sync failed
   */
  function updateSyncStatusDisplay(
    lastSyncedAt,
    isSyncing = false,
    errorMessage = null
  ) {
    if (isSyncing) {
      // Show syncing state
      if (selectors.syncSpinner) {
        selectors.syncSpinner.classList.remove("d-none");
        selectors.syncSpinner.classList.add("spin-icon");
      }
      if (selectors.syncStatusText) {
        selectors.syncStatusText.textContent = t("manage.sync.syncing");
        selectors.syncStatusText.classList.remove("d-none");
      }
      if (selectors.lastSyncedTime) {
        selectors.lastSyncedTime.classList.add("d-none");
      }
      if (selectors.reloadSourceLink) {
        selectors.reloadSourceLink.classList.add("d-none");
      }
    } else if (errorMessage) {
      // Show error state
      if (selectors.syncSpinner) {
        selectors.syncSpinner.classList.add("d-none");
      }
      if (selectors.syncStatusText) {
        selectors.syncStatusText.innerHTML = `<span class="text-danger">${t(
          "manage.sync.sync_failed"
        )}</span>`;
        selectors.syncStatusText.classList.remove("d-none");
      }
      if (selectors.lastSyncedTime) {
        selectors.lastSyncedTime.classList.add("d-none");
      }
      if (selectors.reloadSourceLink) {
        selectors.reloadSourceLink.classList.remove("d-none");
      }
    } else {
      // Show completed state
      if (selectors.syncSpinner) {
        selectors.syncSpinner.classList.add("d-none");
      }
      if (selectors.syncStatusText) {
        selectors.syncStatusText.innerHTML = `<i class="bi bi-clock-history me-1"></i>${t(
          "manage.sync.last_synced"
        )}`;
        selectors.syncStatusText.classList.remove("d-none");
      }
      if (selectors.lastSyncedTime) {
        selectors.lastSyncedTime.textContent = lastSyncedAt
          ? formatDateTime(lastSyncedAt)
          : "-";
        selectors.lastSyncedTime.classList.remove("d-none");
      }
      if (selectors.reloadSourceLink) {
        selectors.reloadSourceLink.classList.remove("d-none");
      }
    }
  }

  function updateOverviewCards() {
    if (!state.project) {
      return;
    }

    const {
      name,
      source_language: sourceLanguage,
      source_language_name: sourceLanguageName,
      source_file_path: sourceFilePath,
      source_key_count: sourceKeyCount,
      updated_at: updatedAt,
      last_synced_at: lastSyncedAt,
    } = state.project;

    if (selectors.projectTitle) {
      selectors.projectTitle.textContent = name || t("manage.overview.title");
    }
    if (selectors.projectSubtitle) {
      if (sourceFilePath) {
        selectors.projectSubtitle.textContent = `${t(
          "manage.overview.source_file_label"
        )} ${sourceFilePath}`;
      } else if (updatedAt) {
        selectors.projectSubtitle.textContent = `${t(
          "manage.overview.last_updated"
        )} ${formatDateTime(updatedAt)}`;
      } else {
        selectors.projectSubtitle.textContent = t(
          "manage.overview.source_file_path_not_configured"
        );
      }
    }
    // Display last synced time (only update if sync is complete)
    if (lastSyncedAt && !state.autoSyncInProgress) {
      updateSyncStatusDisplay(lastSyncedAt);
    }
    if (selectors.sourceLanguageValue) {
      const languageLabel = sourceLanguageName
        ? `${sourceLanguageName} (${sourceLanguage})`
        : sourceLanguage || "-";
      selectors.sourceLanguageValue.textContent = languageLabel;
    }
    if (selectors.sourceKeysCount) {
      const fallbackKeyCount =
        typeof sourceKeyCount === "number"
          ? sourceKeyCount
          : state.stats?.total_keys ?? state.stats?.all_keys;
      selectors.sourceKeysCount.textContent =
        typeof fallbackKeyCount === "number" ? fallbackKeyCount : "-";
    }
  }

  function renderLanguageSummary() {
    if (!selectors.languageProgressTable || !state.stats) {
      return;
    }

    const tbody = selectors.languageProgressTable.querySelector("tbody");
    if (!tbody) return;

    const languages = state.stats.languages || [];
    if (!languages.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="text-center text-muted py-4">
            ${t("manage.overview.no_target_languages")}
          </td>
        </tr>
      `;
      if (selectors.targetLanguageCount) {
        selectors.targetLanguageCount.textContent = "0";
      }
      if (selectors.targetLanguageSummary) {
        selectors.targetLanguageSummary.textContent = t(
          "manage.overview.add_translation_files"
        );
      }
      return;
    }

    const rows = languages
      .map((lang) => {
        const completion = lang.completion_rate ?? 0;
        const badgeClass =
          completion >= 100
            ? "bg-success"
            : completion >= 60
            ? "bg-primary"
            : "bg-warning text-dark";
        return `
          <tr data-language="${escapeHtml(lang.language_code)}">
            <td>
              <div class="fw-semibold">${escapeHtml(
                lang.language_name || lang.language_code
              )}</div>
              <div class="small text-muted">${escapeHtml(
                lang.language_code
              )}</div>
            </td>
            <td class="text-center">${lang.translated_count ?? 0}</td>
            <td class="text-center">${lang.locked_count ?? 0}</td>
            <td class="text-center">${lang.missing_count ?? 0}</td>
            <td class="text-end">
              <span class="badge ${badgeClass}">
                ${completion.toFixed(1)}%
              </span>
            </td>
          </tr>
        `;
      })
      .join("");

    tbody.innerHTML = rows;

    if (selectors.targetLanguageCount) {
      selectors.targetLanguageCount.textContent = String(languages.length);
    }

    if (selectors.targetLanguageSummary) {
      const completed = languages.filter(
        (lang) => (lang.completion_rate ?? 0) >= 100
      ).length;
      selectors.targetLanguageSummary.textContent = t(
        "manage.overview.languages_summary",
        { count: languages.length, completed: completed }
      );
    }
  }

  function renderPagesTable() {
    if (!selectors.pagesTable) {
      return;
    }
    const tbody = selectors.pagesTable.querySelector("tbody");
    if (!tbody) return;

    if (!state.pages.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="2" class="text-center text-muted py-4">
            ${t("manage.overview.pages_table.no_pages_detected")}
          </td>
        </tr>
      `;
      if (selectors.pageCount) {
        selectors.pageCount.textContent = "0";
      }
      return;
    }

    tbody.innerHTML = state.pages
      .map(
        (page) => `
          <tr data-page="${escapeHtml(page.page)}">
            <td>${escapeHtml(page.page || "(root)")}</td>
            <td class="text-end">${page.key_count ?? 0}</td>
          </tr>
        `
      )
      .join("");

    if (selectors.pageCount) {
      selectors.pageCount.textContent = String(state.pages.length);
    }

    if (selectors.manualPageSelect) {
      const options = [
        '<option value="">Select a page</option>',
        ...state.pages.map(
          (page) =>
            `<option value="${escapeHtml(page.page)}">${escapeHtml(
              page.page || "(root)"
            )} (${page.key_count ?? 0})</option>`
        ),
      ];
      selectors.manualPageSelect.innerHTML = options.join("");
    }
  }

  // NOTE: Manual translation functions (resetManualSelectionState, updateManualBulkButtons,
  // renderManualTranslations) moved to manage-manual.js

  // NOTE: renderProtectedTerms and markProtectedTermsDirty moved to manage-protected.js

  async function loadProject() {
    try {
      const data = await fetchJson(`${API_BASE}`);
      state.project = data.project || null;
      updateOverviewCards();
    } catch (error) {
      console.error(error);
      showToast(t("errors.server_error"), "danger");
    }
  }

  async function loadStats() {
    try {
      const data = await fetchJson(`${API_BASE}/stats`);
      state.stats = data;
      renderLanguageSummary();
      // Source key count might be returned from stats if not present in project
      if (
        selectors.sourceKeysCount &&
        state.stats &&
        typeof state.stats.total_keys === "number"
      ) {
        selectors.sourceKeysCount.textContent = state.stats.total_keys;
      }
    } catch (error) {
      console.error(error);
      showToast(t("errors.server_error"), "danger");
    }
  }

  async function loadLanguages() {
    try {
      const data = await fetchJson(`${API_BASE}/languages`);
      state.languages = data.languages || [];
      renderLanguageSummary(); // refresh summary badges with names if new names provided
      populateManualLanguageHints();
    } catch (error) {
      console.error(error);
      showToast(t("errors.server_error"), "danger");
    }
  }

  // Expose loadStats and loadLanguages to modules
  window.LPM.loadStats = loadStats;
  window.LPM.loadLanguages = loadLanguages;
  window.LPM.autoSyncSourceFile = autoSyncSourceFile;

  function populateManualLanguageHints() {
    // No-op for now; placeholder hook if we need to display languages elsewhere.
  }

  async function loadPages() {
    try {
      const data = await fetchJson(`${API_BASE}/pages`);
      state.pages = data.pages || [];
      renderPagesTable();
    } catch (error) {
      console.error(error);
      showToast(t("errors.server_error"), "danger");
    }
  }

  function bindTabShortcuts() {
    if (selectors.protectedTermsBtn) {
      selectors.protectedTermsBtn.addEventListener("click", () => {
        switchToTab("#protected-pane");
      });
    }
    if (selectors.manualTranslateBtn) {
      selectors.manualTranslateBtn.addEventListener("click", () => {
        switchToTab("#manual-pane");
      });
    }
  }

  function bindTabLinks() {
    document.querySelectorAll("[data-tab-link]").forEach((el) => {
      el.addEventListener("click", (event) => {
        event.preventDefault();
        const tabName = el.getAttribute("data-tab-link");
        const tabId = tabIdFromName(tabName);
        switchToTab(tabId);
      });
    });

    document
      .querySelectorAll('#manageTabContent button[data-bs-toggle="tab"]')
      .forEach((tabButton) => {
        tabButton.addEventListener("shown.bs.tab", (event) => {
          const target = event.target?.getAttribute("data-bs-target");
          if (target) {
            const tabName = tabIdToName[target] || "";
            updateTabInUrl(tabName);
          }
        });
      });
  }

  function getSelectedLanguages() {
    return state.languages
      .filter((lang) => lang.language_code !== state.project?.source_language)
      .map((lang) => lang.language_code);
  }

  /**
   * Auto-sync the source language file with the database.
   * This function is called automatically on page load and before translation jobs.
   * It returns a promise that resolves to an object with success status and optional error.
   *
   * @param {Object} options - Options for auto-sync
   * @param {boolean} options.silent - If true, don't show success toasts (default: false)
   * @param {boolean} options.showProgress - If true, show a syncing progress toast (default: true)
   * @returns {Promise<{success: boolean, error?: string, summary?: object}>}
   */
  async function autoSyncSourceFile(options = {}) {
    const { silent = false, showProgress = true } = options;

    if (state.autoSyncInProgress) {
      console.log("Auto-sync already in progress, skipping...");
      return { success: true, error: null, skipped: true };
    }

    state.autoSyncInProgress = true;

    // Update UI to show syncing state
    updateSyncStatusDisplay(null, true);

    try {
      if (showProgress) {
        showToast(t("manage.sync.syncing"), "info");
      }

      const data = await fetchJson(`${API_BASE}/sync?dry_run=false`, {
        method: "POST",
      });

      const summary = data.summary || {};
      const hasChanges =
        summary.new_keys > 0 ||
        summary.updated_keys > 0 ||
        summary.deleted_keys > 0;

      // Refresh project data to get updated last_synced_at
      await loadProject();

      // Update UI to show completed state
      const lastSyncedAt = state.project?.last_synced_at;
      updateSyncStatusDisplay(lastSyncedAt, false);

      if (hasChanges) {
        // If there were changes, also refresh stats and pages
        await Promise.all([loadStats(), loadPages()]);

        if (!silent) {
          const changeDetails = [];
          if (summary.new_keys > 0)
            changeDetails.push(`${summary.new_keys} new`);
          if (summary.updated_keys > 0)
            changeDetails.push(`${summary.updated_keys} updated`);
          if (summary.deleted_keys > 0)
            changeDetails.push(`${summary.deleted_keys} deleted`);
          showToast(
            `Source file synced: ${changeDetails.join(", ")} keys.`,
            "success"
          );
        }
      } else if (!silent) {
        showToast(
          t("manage.translate.messages.source_synced_no_changes"),
          "success"
        );
      }

      return { success: true, summary };
    } catch (error) {
      console.error("Auto-sync failed:", error);
      const errorMessage = error?.message || t("manage.sync.sync_failed");

      // Update UI to show error state
      updateSyncStatusDisplay(null, false, errorMessage);

      showToast(`Sync failed: ${errorMessage}`, "danger");
      return { success: false, error: errorMessage };
    } finally {
      state.autoSyncInProgress = false;
    }
  }

  // NOTE: Translate Tab functions moved to manage-translate.js
  // (startTranslationJob, loadTranslateTabSettings, loadTranslateTabLanguages,
  //  updateTranslateStartButton, startTranslateJob, pollTranslateProgress, cancelTranslateJob,
  //  updateTranslateProgress, addTranslateBriefing, showTranslateCompletion, resetTranslateTab,
  //  formatNumber, setupTranslateTabListeners, initTranslateTab, checkAndResumeActiveJob)

  // Content removed - see manage-translate.js

  function bindEvents() {
    if (selectors.reloadProjectBtn) {
      selectors.reloadProjectBtn.addEventListener("click", handleSyncDryRun);
    }
    if (selectors.syncApplyBtn) {
      selectors.syncApplyBtn.addEventListener("click", () => {
        void applySyncChanges();
      });
    }
    if (selectors.startTranslateBtn) {
      selectors.startTranslateBtn.addEventListener("click", () => {
        // Switch to translate tab
        switchToTab("#translate-pane");
      });
    }
    if (selectors.reloadSourceLink) {
      selectors.reloadSourceLink.addEventListener("click", (e) => {
        e.preventDefault();
        void autoSyncSourceFile({ silent: false, showProgress: true });
      });
    }

    // NOTE: Translate Tab event bindings moved to manage-translate.js

    // Fix accessibility issue: remove focus from close button before modal hides
    // This prevents ARIA warnings when modals are closed with focused elements inside
    const modalsToFix = [
      selectors.manualLanguageModal,
      selectors.suggestionsModal,
    ];

    modalsToFix.forEach((modal) => {
      if (modal) {
        modal.addEventListener("hide.bs.modal", () => {
          // Remove focus from any focused element inside the modal before it hides
          const focusedElement = modal.querySelector(":focus");
          if (focusedElement) {
            focusedElement.blur();
          }
        });
      }
    });

    // NOTE: Protected terms event bindings moved to manage-protected.js
    // NOTE: Manual translation event bindings moved to manage-manual.js
  }

  // NOTE: importFailedItemsToManual moved to manage-manual.js (LPM.manual.importFailedItems)
  // NOTE: checkAndResumeActiveJob moved to manage-translate.js (LPM.translate.checkAndResumeActiveJob)

  async function init() {
    bindEvents();
    bindTabShortcuts();
    bindTabLinks();
    initTabFromUrl();

    // Initialize modules
    if (window.LPM.protected) {
      window.LPM.protected.init();
    }
    if (window.LPM.manual) {
      window.LPM.manual.init();
    }
    if (window.LPM.translate) {
      await window.LPM.translate.init();
    }

    // Auto-sync source file only on overview tab (not on other tabs like protected, manual, translate)
    // Delay sync by 1-2 seconds to avoid blocking page initialization
    const urlParams = new URLSearchParams(window.location.search);
    const currentTab = urlParams.get("tab") || "overview";
    if (currentTab === "overview") {
      // Use setTimeout to delay sync, making it non-blocking
      setTimeout(() => {
        void autoSyncSourceFile({ silent: false, showProgress: true });
      }, 1500); // 1.5 second delay
    }

    await Promise.allSettled([
      loadProject(),
      loadStats(),
      loadLanguages(),
      loadPages(),
      window.LPM.protected ? window.LPM.protected.load() : Promise.resolve(),
    ]);

    // Reload project settings after project is loaded (to ensure chunk size is set correctly)
    if (window.LPM.translate && window.LPM.translate.loadProjectSettings) {
      await window.LPM.translate.loadProjectSettings();
    }

    // Check for active job and resume if found
    if (window.LPM.translate) {
      await window.LPM.translate.checkAndResumeActiveJob();
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
