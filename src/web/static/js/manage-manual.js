/**
 * Manual Translation Module
 * Handles manual translation worklist, key search, and bulk operations.
 *
 * Depends on: manage.js (must be loaded first to provide LPM namespace)
 */
(function (LPM) {
  "use strict";

  if (!LPM) {
    console.warn("LPM namespace not found; manage-manual.js disabled.");
    return;
  }

  LPM.manual = {};

  // ============================================
  // HELPER FUNCTIONS
  // ============================================

  LPM.manual.derivePageName = function (keyPath) {
    if (!keyPath) return "";
    const parts = keyPath.split(".");
    return parts[0] || "";
  };

  LPM.manual.worklistKey = function (keyPath, languageCode) {
    return `${keyPath}__${languageCode}`;
  };

  LPM.manual.getLanguageLabel = function (code) {
    const { state } = LPM;
    const found = state.languages.find((lang) => lang.language_code === code);
    if (found) {
      return found.language_name || found.name || found.language_code || code;
    }
    return code;
  };

  // ============================================
  // SELECTION STATE
  // ============================================

  LPM.manual.resetSelectionState = function () {
    const { state, selectors } = LPM;
    state.manual.selectedRows.clear();
    if (selectors.manualSelectAll) {
      selectors.manualSelectAll.checked = false;
      selectors.manualSelectAll.indeterminate = false;
      selectors.manualSelectAll.disabled = !state.manual.translations.length;
    }
    LPM.manual.updateBulkButtons();
  };

  LPM.manual.updateBulkButtons = function () {
    const { state, selectors } = LPM;
    const hasSelection = state.manual.selectedRows.size > 0;
    const controls = [
      selectors.manualSaveSelectedBtn,
      selectors.manualUnlockSelectedBtn,
    ];
    controls.forEach((btn) => {
      if (!btn) return;
      btn.disabled = !hasSelection;
    });
    if (selectors.manualRefreshBtn) {
      selectors.manualRefreshBtn.disabled = !state.manual.currentKey;
    }
  };

  LPM.manual.updateWorklistBulkButtons = function () {
    const { state, selectors } = LPM;
    const hasSelection = state.manual.worklistSelected.size > 0;
    if (selectors.manualSaveSelectedBtn) {
      selectors.manualSaveSelectedBtn.disabled = !hasSelection;
    }
    if (selectors.manualUnlockSelectedBtn) {
      selectors.manualUnlockSelectedBtn.disabled = !hasSelection;
    }
  };

  // ============================================
  // RENDERING
  // ============================================

  LPM.manual.renderTranslations = function (filterTerm = "") {
    const { state, selectors, utils } = LPM;
    if (!selectors.manualTranslationTable) return;
    const tbody = selectors.manualTranslationTable.querySelector("tbody");
    if (!tbody) return;

    if (!state.manual.translations.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="text-center text-muted py-5">
            ${
              state.manual.currentKey
                ? t("manage.manual.no_translations_found", {})
                : t("manage.manual.select_key_to_load", {})
            }
          </td>
        </tr>
      `;
      LPM.manual.resetSelectionState();
      return;
    }

    const term = filterTerm.trim().toLowerCase();
    const rows = state.manual.translations
      .filter((entry) => {
        if (!term) return true;
        const languageMatch = entry.language_code?.toLowerCase().includes(term);
        const textMatch = entry.translated_text?.toLowerCase().includes(term);
        return languageMatch || textMatch;
      })
      .map((entry) => {
        const languageLabel = entry.language_name
          ? `${entry.language_name} (${entry.language_code})`
          : entry.language_code;
        const status = entry.status || "missing";
        let badgeClass = "bg-secondary";
        if (status === "ai_translated") badgeClass = "bg-info text-dark";
        if (status === "locked") badgeClass = "bg-success";
        if (status === "needs_review") badgeClass = "bg-warning text-dark";
        if (status === "missing") badgeClass = "bg-danger";

        const textareaValue = entry.translated_text ?? "";
        const rowSelected = state.manual.selectedRows.has(entry.language_code);

        return `
          <tr data-language="${utils.escapeHtml(entry.language_code)}">
            <td>
              <input
                class="form-check-input manual-select-row"
                type="checkbox"
                ${rowSelected ? "checked" : ""}
              />
            </td>
            <td>
              <div class="fw-semibold">${utils.escapeHtml(languageLabel)}</div>
              <div class="small text-muted">${utils.escapeHtml(
                entry.language_code
              )}</div>
            </td>
            <td>
              <textarea
                class="form-control manual-translation-input"
                rows="2"
              >${utils.escapeHtml(textareaValue)}</textarea>
            </td>
            <td class="text-end">
              <span class="badge ${badgeClass} text-uppercase">${utils.escapeHtml(
          status
        )}</span>
            </td>
            <td class="text-end">
              <div class="btn-group btn-group-sm">
                <button class="btn btn-success manual-save-lock-btn">
                  Save &amp; Lock
                </button>
                <button class="btn btn-outline-secondary manual-unlock-btn">
                  Unlock
                </button>
              </div>
            </td>
          </tr>
        `;
      })
      .join("");

    tbody.innerHTML =
      rows ||
      `
      <tr>
        <td colspan="5" class="text-center text-muted py-4">
          No translations matched your filter.
        </td>
      </tr>
    `;

    if (selectors.manualSelectAll) {
      selectors.manualSelectAll.disabled = !state.manual.translations.length;
      selectors.manualSelectAll.checked =
        state.manual.selectedRows.size === state.manual.translations.length &&
        state.manual.translations.length > 0;
      selectors.manualSelectAll.indeterminate =
        state.manual.selectedRows.size > 0 &&
        state.manual.selectedRows.size < state.manual.translations.length;
    }

    LPM.manual.updateBulkButtons();
  };

  LPM.manual.renderKeyResults = function () {
    const { state, selectors, utils } = LPM;
    const table = selectors.manualKeyResultsTable;
    if (!table) return;
    const tbody = table.querySelector("tbody");
    if (!tbody) return;

    if (!state.manual.keyResults.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" class="text-center text-muted py-4">
            No keys found. Try another search.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = state.manual.keyResults
      .map((item, index) => {
        const sourceText = item.source_text || "";
        return `
          <tr data-key-index="${index}">
            <td class="font-monospace">${utils.escapeHtml(item.key_path)}</td>
            <td>${utils.escapeHtml(
              item.page || LPM.manual.derivePageName(item.key_path)
            )}</td>
            <td>${utils.escapeHtml(sourceText)}</td>
            <td class="text-end">
              <button class="btn btn-sm btn-primary manual-key-add-btn">
                Add to Manual List
              </button>
            </td>
          </tr>
        `;
      })
      .join("");
  };

  LPM.manual.renderLanguageSelectModal = function () {
    const { state, selectors, utils } = LPM;
    if (!selectors.manualLanguageList) return;
    const list = selectors.manualLanguageList;
    const sourceLanguage = state.project?.source_language;
    const languages = state.languages.filter(
      (lang) => lang.language_code !== sourceLanguage
    );

    if (!languages.length) {
      list.innerHTML =
        '<div class="text-muted">No target languages available.</div>';
      return;
    }

    list.innerHTML = languages
      .map(
        (lang) => `
        <label class="form-check d-flex align-items-center gap-2">
          <input class="form-check-input manual-language-option" type="checkbox" value="${utils.escapeHtml(
            lang.language_code
          )}" />
          <span>${utils.escapeHtml(
            lang.language_name || lang.name || lang.language_code
          )} (${utils.escapeHtml(lang.language_code)})</span>
        </label>
      `
      )
      .join("");
  };

  LPM.manual.renderWorklist = function (sortOrder = null) {
    const { state, selectors, utils } = LPM;
    const table = selectors.manualWorklistTable;
    if (!table) return;
    const tbody = table.querySelector("tbody");
    if (!tbody) return;

    const sortValue =
      sortOrder ||
      (selectors.manualWorklistSort
        ? selectors.manualWorklistSort.value
        : "last_translated_at_desc");

    // Get all items with original index (no filtering)
    let rowsWithIndex = state.manual.worklist.map((item, originalIndex) => ({
      item,
      originalIndex,
    }));

    // Separate newly added items (from search) from existing items (from database)
    // Newly added items have _addedAt timestamp and are only in UI, not in database
    // They should always appear at the top until page refresh
    const newItems = rowsWithIndex.filter(({ item }) => item._addedAt);
    const existingItems = rowsWithIndex.filter(({ item }) => !item._addedAt);

    // Sort newly added items by add time (newest first)
    newItems.sort((a, b) => b.item._addedAt - a.item._addedAt);

    // Sort existing items by user-selected sort order
    existingItems.sort((a, b) => {
      const itemA = a.item;
      const itemB = b.item;
      switch (sortValue) {
        case "key_path_asc":
          return (itemA.key_path || "").localeCompare(itemB.key_path || "");
        case "key_path_desc":
          return (itemB.key_path || "").localeCompare(itemA.key_path || "");
        case "source_text_asc":
          return (itemA.source_text || "").localeCompare(
            itemB.source_text || ""
          );
        case "source_text_desc":
          return (itemB.source_text || "").localeCompare(
            itemA.source_text || ""
          );
        case "language_asc": {
          const langA = itemA.language_name || itemA.language_code || "";
          const langB = itemB.language_name || itemB.language_code || "";
          return langA.localeCompare(langB);
        }
        case "language_desc": {
          const langA = itemA.language_name || itemA.language_code || "";
          const langB = itemB.language_name || itemB.language_code || "";
          return langB.localeCompare(langA);
        }
        case "last_translated_at_asc": {
          const timeA = itemA.last_translated_at
            ? new Date(itemA.last_translated_at).getTime()
            : 0;
          const timeB = itemB.last_translated_at
            ? new Date(itemB.last_translated_at).getTime()
            : 0;
          return timeA - timeB;
        }
        case "last_translated_at_desc":
        default: {
          const timeA = itemA.last_translated_at
            ? new Date(itemA.last_translated_at).getTime()
            : 0;
          const timeB = itemB.last_translated_at
            ? new Date(itemB.last_translated_at).getTime()
            : 0;
          return timeB - timeA;
        }
      }
    });

    // Combine: newly added items first, then existing items
    rowsWithIndex = [...newItems, ...existingItems];

    const rows = rowsWithIndex.map((r) => r.item);

    if (!rows.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center text-muted py-5">
            Add keys and languages to start manual translation.
          </td>
        </tr>
      `;
      if (selectors.manualWorklistSelectAll) {
        selectors.manualWorklistSelectAll.checked = false;
        selectors.manualWorklistSelectAll.disabled = true;
      }
      LPM.manual.updateWorklistBulkButtons();
      return;
    }

    tbody.innerHTML = rowsWithIndex
      .map(({ item, originalIndex }) => {
        const key = LPM.manual.worklistKey(item.key_path, item.language_code);
        const selected = state.manual.worklistSelected.has(key);
        const badgeClass =
          item.status === "locked"
            ? "bg-success"
            : item.status === "ai_translated"
            ? "bg-info text-dark"
            : item.status === "needs_review"
            ? "bg-warning text-dark"
            : "bg-secondary";
        return `
          <tr data-worklist-index="${originalIndex}" data-key="${utils.escapeHtml(
          item.key_path
        )}" data-language="${utils.escapeHtml(item.language_code)}">
            <td>
              <input class="form-check-input manual-worklist-select" type="checkbox" ${
                selected ? "checked" : ""
              } />
            </td>
            <td>
              <div class="fw-semibold">${utils.escapeHtml(
                item.source_text || "-"
              )}</div>
              <div class="small text-muted font-monospace">${utils.escapeHtml(
                item.key_path
              )}</div>
            </td>
            <td>
              <div class="fw-semibold">${utils.escapeHtml(
                item.language_name || item.language_code
              )}</div>
              <div class="small text-muted">${utils.escapeHtml(
                item.language_code
              )}</div>
            </td>
            <td>
              <textarea
                class="form-control form-control-sm manual-worklist-text"
                rows="2"
              >${utils.escapeHtml(
                item.pending_text ?? item.translated_text ?? ""
              )}</textarea>
            </td>
            <td class="text-end">
              <span class="badge ${badgeClass} text-uppercase">${utils.escapeHtml(
          item.status || "missing"
        )}</span>
            </td>
            <td class="text-end">
              <div class="btn-group btn-group-sm">
                <button class="btn btn-success manual-worklist-save-lock">
                  ${t("manage.manual.worklist.save_lock")}
                </button>
                <button class="btn btn-secondary manual-worklist-unlock">
                  ${t("manage.manual.worklist.unlock")}
                </button>
                <button class="btn btn-danger manual-worklist-delete" title="${t(
                  "manage.manual.worklist.remove_from_list"
                )}">
                  <i class="bi bi-trash"></i>
                </button>
              </div>
            </td>
          </tr>
        `;
      })
      .join("");

    if (selectors.manualWorklistSelectAll) {
      const allSelected =
        rows.length &&
        rows.every((item) =>
          state.manual.worklistSelected.has(
            LPM.manual.worklistKey(item.key_path, item.language_code)
          )
        );
      const anySelected = rows.some((item) =>
        state.manual.worklistSelected.has(
          LPM.manual.worklistKey(item.key_path, item.language_code)
        )
      );
      selectors.manualWorklistSelectAll.checked = allSelected;
      selectors.manualWorklistSelectAll.indeterminate =
        !allSelected && anySelected;
      selectors.manualWorklistSelectAll.disabled = !rows.length;
    }

    LPM.manual.updateWorklistBulkButtons();
  };

  // ============================================
  // LANGUAGE MODAL
  // ============================================

  LPM.manual.openLanguageModal = function (keyEntry) {
    const { state, selectors } = LPM;
    state.manual.pendingAddKey = keyEntry?.key_path || null;
    state.manual.pendingAddSourceText = keyEntry?.source_text || "";
    LPM.manual.renderLanguageSelectModal();
    if (!selectors.manualLanguageModal || !window.bootstrap) return;
    const modal =
      bootstrap.Modal.getInstance(selectors.manualLanguageModal) ||
      new bootstrap.Modal(selectors.manualLanguageModal, {
        backdrop: "static",
      });
    modal.show();
  };

  LPM.manual.handleConfirmLanguages = async function () {
    const { state, selectors, utils } = LPM;
    const modalEl = selectors.manualLanguageModal;
    if (!modalEl) return;
    const modal =
      bootstrap.Modal.getInstance(modalEl) ||
      new bootstrap.Modal(modalEl, { backdrop: "static" });

    const checked = Array.from(
      selectors.manualLanguageList?.querySelectorAll(
        ".manual-language-option:checked"
      ) || []
    ).map((input) => input.value);

    if (!state.manual.pendingAddKey) {
      utils.showToast(t("manage.manual.no_key_selected", {}), "warning");
      return;
    }
    if (!checked.length) {
      utils.showToast(
        t("manage.manual.select_at_least_one_language", {}),
        "warning"
      );
      return;
    }

    try {
      await LPM.manual.addKeyLanguagesToWorklist({
        keyPath: state.manual.pendingAddKey,
        sourceText: state.manual.pendingAddSourceText || "",
        languages: checked,
      });
      modal.hide();
      utils.showToast(t("manage.manual.add_to_list"), "success");
    } catch (error) {
      console.error(error);
      utils.showToast(
        `Failed to add to manual list: ${error.message}`,
        "danger"
      );
    } finally {
      state.manual.pendingAddKey = null;
      state.manual.pendingAddSourceText = null;
    }
  };

  // ============================================
  // API OPERATIONS
  // ============================================

  LPM.manual.fetchTranslationsForKey = async function (keyPath) {
    const { state, utils, API_BASE } = LPM;
    if (state.manual.translationCache.has(keyPath)) {
      return state.manual.translationCache.get(keyPath);
    }
    const data = await utils.fetchJson(
      `${API_BASE}/translations?key=${encodeURIComponent(keyPath)}`
    );
    state.manual.translationCache.set(keyPath, data);
    return data;
  };

  LPM.manual.addKeyLanguagesToWorklist = async function ({
    keyPath,
    sourceText,
    languages,
  }) {
    const { state } = LPM;
    const translationPayload = await LPM.manual.fetchTranslationsForKey(
      keyPath
    );
    const existingTranslations = translationPayload?.translations || [];
    const page = LPM.manual.derivePageName(keyPath);

    // Add items to the beginning of the list (most recent first)
    languages.forEach((languageCode) => {
      const duplicate = state.manual.worklist.find(
        (item) =>
          item.key_path === keyPath && item.language_code === languageCode
      );
      if (duplicate) {
        return;
      }
      const translation =
        existingTranslations.find(
          (entry) => entry.language_code === languageCode
        ) || {};
      const initialText = translation.translated_text ?? "";
      // Add to the beginning of the list with timestamp marker
      // New items will always appear at the top regardless of sort order
      state.manual.worklist.unshift({
        key_path: keyPath,
        page,
        source_text: sourceText,
        language_code: languageCode,
        language_name: LPM.manual.getLanguageLabel(languageCode),
        translated_text: initialText,
        pending_text: initialText,
        status: translation.status || "missing",
        _addedAt: Date.now(), // Mark as newly added item
      });
    });

    LPM.manual.renderWorklist();
  };

  LPM.manual.saveTranslations = async function ({
    languages,
    lock = false,
    unlock = false,
  }) {
    const { state, selectors, utils, API_BASE } = LPM;
    if (!languages.length) {
      utils.showToast(
        t("manage.manual.select_at_least_one_language_to_update", {}),
        "warning"
      );
      return;
    }
    const key = state.manual.currentKey;
    if (!key) {
      utils.showToast(
        t("manage.manual.select_key_before_saving", {}),
        "warning"
      );
      return;
    }
    try {
      LPM.manual.toggleActions(true);
      const body = {
        key_path: key,
        entries: languages.map((code) => {
          const translation = state.manual.translations.find(
            (entry) => entry.language_code === code
          );
          return {
            language_code: code,
            translated_text:
              translation?.pending_text ?? translation?.translated_text ?? "",
            status: lock
              ? "locked"
              : unlock
              ? "ai_translated"
              : translation?.status,
          };
        }),
      };
      await utils.fetchJson(`${API_BASE}/translations`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      utils.showToast(t("manage.manual.translations_updated", {}), "success");
      // Refresh translations (stub - function may not exist)
      // await queryManualTranslations();
    } catch (error) {
      console.error(error);
      utils.showToast(
        `Failed to save translations: ${error.message}`,
        "danger"
      );
    } finally {
      LPM.manual.toggleActions(false);
    }
  };

  LPM.manual.saveSingleWorklistRow = async function (index, { status }) {
    const { state, selectors, utils, API_BASE } = LPM;
    const item = state.manual.worklist[index];
    if (!item) return;
    const textArea = selectors.manualWorklistTable?.querySelector(
      `tr[data-worklist-index="${index}"] .manual-worklist-text`
    );
    const translatedText = textArea ? textArea.value : item.pending_text || "";
    try {
      await utils.fetchJson(`${API_BASE}/translations`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key_path: item.key_path,
          entries: [
            {
              language_code: item.language_code,
              translated_text: translatedText,
              status: status || item.status || "needs_review",
            },
          ],
        }),
      });
      item.translated_text = translatedText;
      item.pending_text = translatedText;
      item.status = status || item.status || "needs_review";
      LPM.manual.renderWorklist();
      utils.showToast(t("manage.manual.saved", {}), "success");
    } catch (error) {
      console.error(error);
      utils.showToast(`Failed to save: ${error.message}`, "danger");
    }
  };

  LPM.manual.handleBulkSaveLock = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    const selectedKeys = Array.from(state.manual.worklistSelected);
    if (!selectedKeys.length) return;
    const payloadByKey = new Map();

    state.manual.worklist.forEach((item, index) => {
      const key = LPM.manual.worklistKey(item.key_path, item.language_code);
      if (!state.manual.worklistSelected.has(key)) return;
      const textArea = selectors.manualWorklistTable?.querySelector(
        `tr[data-worklist-index="${index}"] .manual-worklist-text`
      );
      const translatedText = textArea
        ? textArea.value
        : item.pending_text || "";
      const entries = payloadByKey.get(item.key_path) || [];
      entries.push({
        language_code: item.language_code,
        translated_text: translatedText,
        status: "locked",
      });
      payloadByKey.set(item.key_path, entries);
    });

    try {
      for (const [keyPath, entries] of payloadByKey.entries()) {
        await utils.fetchJson(`${API_BASE}/translations`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key_path: keyPath, entries }),
        });
      }
      state.manual.worklist.forEach((item) => {
        const key = LPM.manual.worklistKey(item.key_path, item.language_code);
        if (state.manual.worklistSelected.has(key)) {
          item.translated_text =
            item.pending_text ?? item.translated_text ?? "";
          item.status = "locked";
        }
      });
      LPM.manual.renderWorklist();
      utils.showToast(t("manage.manual.saved_locked", {}), "success");
    } catch (error) {
      console.error(error);
      utils.showToast(`Failed to save selected: ${error.message}`, "danger");
    }
  };

  LPM.manual.handleBulkUnlock = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    const selectedKeys = Array.from(state.manual.worklistSelected);
    if (!selectedKeys.length) return;
    const payloadByKey = new Map();

    state.manual.worklist.forEach((item) => {
      const key = LPM.manual.worklistKey(item.key_path, item.language_code);
      if (!state.manual.worklistSelected.has(key)) return;
      const entries = payloadByKey.get(item.key_path) || [];
      entries.push({
        language_code: item.language_code,
        translated_text: item.pending_text ?? item.translated_text ?? "",
        status: "ai_translated",
      });
      payloadByKey.set(item.key_path, entries);
    });

    try {
      for (const [keyPath, entries] of payloadByKey.entries()) {
        await utils.fetchJson(`${API_BASE}/translations`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key_path: keyPath, entries }),
        });
      }
      state.manual.worklist.forEach((item) => {
        const key = LPM.manual.worklistKey(item.key_path, item.language_code);
        if (state.manual.worklistSelected.has(key)) {
          item.status = "ai_translated";
        }
      });
      state.manual.worklistSelected.clear();
      LPM.manual.renderWorklist();
      utils.showToast(t("manage.manual.unlocked", {}), "success");
    } catch (error) {
      console.error(error);
      utils.showToast(`Failed to unlock selected: ${error.message}`, "danger");
    }
  };

  LPM.manual.handleSearchKeys = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    const searchTerm = selectors.manualSearchInput
      ? selectors.manualSearchInput.value.trim()
      : "";
    const page = selectors.manualPageSelect
      ? selectors.manualPageSelect.value
      : "";

    const params = new URLSearchParams();
    if (searchTerm) params.set("search", searchTerm);
    if (page) params.set("page", page);

    const url =
      params.toString().length > 0
        ? `${API_BASE}/keys?${params.toString()}`
        : `${API_BASE}/keys`;

    try {
      const data = await utils.fetchJson(url);
      state.manual.keyResults = data.keys || [];
      LPM.manual.renderKeyResults();
    } catch (error) {
      console.error(error);
      utils.showToast(`Failed to search keys: ${error.message}`, "danger");
    }
  };

  LPM.manual.ensureLockedItemsLoaded = async function () {
    const { state, utils, API_BASE } = LPM;
    if (state.manual.lockedLoaded) return;
    try {
      const data = await utils.fetchJson(`${API_BASE}/manual-locked`);
      const items = data.items || [];
      items.forEach((item) => {
        const duplicate = state.manual.worklist.find(
          (row) =>
            row.key_path === item.key_path &&
            row.language_code === item.language_code
        );
        if (duplicate) {
          duplicate.source_text = item.source_text;
          duplicate.translated_text = item.translated_text ?? "";
          duplicate.pending_text = item.translated_text ?? "";
          duplicate.status = item.status || "locked";
          return;
        }
        state.manual.worklist.push({
          key_path: item.key_path,
          page: item.page || LPM.manual.derivePageName(item.key_path),
          source_text: item.source_text,
          language_code: item.language_code,
          language_name:
            item.language_name ||
            LPM.manual.getLanguageLabel(item.language_code),
          translated_text: item.translated_text ?? "",
          pending_text: item.translated_text ?? "",
          status: item.status || "locked",
          last_translated_at: item.last_translated_at || null,
        });
      });
      state.manual.lockedLoaded = true;
    } catch (error) {
      console.error(error);
      utils.showToast(
        `Failed to load locked items: ${error.message}`,
        "danger"
      );
    }
  };

  // ============================================
  // UI HELPERS
  // ============================================

  LPM.manual.toggleActions = function (disabled) {
    const { selectors } = LPM;
    [
      selectors.manualSaveSelectedBtn,
      selectors.manualUnlockSelectedBtn,
      selectors.manualRefreshBtn,
      selectors.manualQueryBtn,
    ].forEach((el) => el && (el.disabled = disabled));
  };

  // ============================================
  // EVENT HANDLERS
  // ============================================

  LPM.manual.handleTableInteraction = function (event) {
    const { state } = LPM;
    const row = event.target.closest("tr[data-language]");
    if (!row) return;
    const languageCode = row.dataset.language;
    if (!languageCode) return;

    if (event.target.classList.contains("manual-select-row")) {
      if (event.target.checked) {
        state.manual.selectedRows.add(languageCode);
      } else {
        state.manual.selectedRows.delete(languageCode);
      }
      LPM.manual.updateBulkButtons();
      const { selectors } = LPM;
      if (selectors.manualSelectAll) {
        selectors.manualSelectAll.checked =
          state.manual.selectedRows.size === state.manual.translations.length &&
          state.manual.translations.length > 0;
        selectors.manualSelectAll.indeterminate =
          state.manual.selectedRows.size > 0 &&
          state.manual.selectedRows.size < state.manual.translations.length;
      }
      return;
    }

    if (event.target.classList.contains("manual-save-lock-btn")) {
      event.preventDefault();
      const textarea = row.querySelector(".manual-translation-input");
      const text = textarea ? textarea.value : "";
      const translation = state.manual.translations.find(
        (entry) => entry.language_code === languageCode
      );
      if (translation) {
        translation.pending_text = text;
      }
      void LPM.manual.saveTranslations({
        languages: [languageCode],
        lock: true,
      });
      return;
    }

    if (event.target.classList.contains("manual-unlock-btn")) {
      event.preventDefault();
      void LPM.manual.saveTranslations({
        languages: [languageCode],
        lock: false,
        unlock: true,
      });
      return;
    }

    if (event.target.classList.contains("manual-translation-input")) {
      const translation = state.manual.translations.find(
        (entry) => entry.language_code === languageCode
      );
      if (translation) {
        translation.pending_text = event.target.value;
      }
    }
  };

  LPM.manual.handleSelectAll = function (event) {
    const { state, selectors } = LPM;
    if (!selectors.manualTranslationTable) return;
    const check = event.target.checked;
    state.manual.selectedRows.clear();
    if (check) {
      state.manual.translations.forEach((entry) =>
        state.manual.selectedRows.add(entry.language_code)
      );
    }
    selectors.manualTranslationTable
      .querySelectorAll(".manual-select-row")
      .forEach((input) => {
        input.checked = check;
      });
    LPM.manual.updateBulkButtons();
  };

  LPM.manual.handleBulkSave = function (lock = true) {
    const { state, selectors } = LPM;
    const languages = Array.from(state.manual.selectedRows);
    languages.forEach((code) => {
      const row = selectors.manualTranslationTable?.querySelector(
        `tr[data-language="${CSS.escape(code)}"]`
      );
      if (row) {
        const textarea = row.querySelector(".manual-translation-input");
        const translation = state.manual.translations.find(
          (entry) => entry.language_code === code
        );
        if (translation && textarea) {
          translation.pending_text = textarea.value;
        }
      }
    });
    void LPM.manual.saveTranslations({
      languages,
      lock,
      unlock: !lock,
    });
  };

  LPM.manual.handleWorklistSelectAll = function (event) {
    const { state } = LPM;
    const check = event.target.checked;
    state.manual.worklistSelected.clear();
    state.manual.worklist.forEach((item) => {
      if (check) {
        state.manual.worklistSelected.add(
          LPM.manual.worklistKey(item.key_path, item.language_code)
        );
      }
    });
    LPM.manual.renderWorklist();
  };

  LPM.manual.handleWorklistTableInteraction = function (event) {
    const { state, selectors } = LPM;
    const row = event.target.closest("tr[data-key][data-language]");
    if (!row) return;
    const keyPath = row.dataset.key;
    const languageCode = row.dataset.language;
    const selectionKey = LPM.manual.worklistKey(keyPath, languageCode);

    if (event.target.classList.contains("manual-worklist-select")) {
      if (event.target.checked) {
        state.manual.worklistSelected.add(selectionKey);
      } else {
        state.manual.worklistSelected.delete(selectionKey);
      }
      LPM.manual.updateWorklistBulkButtons();
      if (selectors.manualWorklistSelectAll) {
        const worklist = state.manual.worklist;
        const allSelected =
          worklist.length &&
          worklist.every((item) =>
            state.manual.worklistSelected.has(
              LPM.manual.worklistKey(item.key_path, item.language_code)
            )
          );
        selectors.manualWorklistSelectAll.checked = allSelected;
        selectors.manualWorklistSelectAll.indeterminate =
          !allSelected && state.manual.worklistSelected.size > 0;
      }
      return;
    }

    if (event.target.classList.contains("manual-worklist-save-lock")) {
      event.preventDefault();
      const rowIndex = Number.parseInt(row.dataset.worklistIndex, 10);
      void LPM.manual.saveSingleWorklistRow(rowIndex, { status: "locked" });
      return;
    }

    if (event.target.classList.contains("manual-worklist-unlock")) {
      event.preventDefault();
      const rowIndex = Number.parseInt(row.dataset.worklistIndex, 10);
      void LPM.manual.saveSingleWorklistRow(rowIndex, {
        status: "ai_translated",
      });
      return;
    }

    if (event.target.classList.contains("manual-worklist-text")) {
      const rowIndex = Number.parseInt(row.dataset.worklistIndex, 10);
      const item = state.manual.worklist[rowIndex];
      if (item) {
        item.pending_text = event.target.value;
      }
      return;
    }

    // Delete button - remove item from worklist
    if (
      event.target.classList.contains("manual-worklist-delete") ||
      event.target.closest(".manual-worklist-delete")
    ) {
      event.preventDefault();
      const rowIndex = Number.parseInt(row.dataset.worklistIndex, 10);
      LPM.manual.removeWorklistItem(rowIndex);
      return;
    }
  };

  /**
   * Remove an item from the worklist and delete from database.
   * @param {number} rowIndex - The index of the item in state.manual.worklist
   */
  LPM.manual.removeWorklistItem = async function (rowIndex) {
    const { state, utils, API_BASE } = LPM;
    const item = state.manual.worklist[rowIndex];
    if (!item) return;

    // Confirm deletion
    if (
      !confirm(
        `Delete translation for "${item.key_path}" (${
          item.language_name || item.language_code
        })?`
      )
    ) {
      return;
    }

    try {
      // Delete from database
      const response = await utils.fetchJson(`${API_BASE}/translations`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key_path: item.key_path,
          language_code: item.language_code,
        }),
      });

      if (response.error) {
        throw new Error(response.error);
      }

      // Remove from selection if selected
      const selectionKey = LPM.manual.worklistKey(
        item.key_path,
        item.language_code
      );
      state.manual.worklistSelected.delete(selectionKey);

      // Remove from worklist
      state.manual.worklist.splice(rowIndex, 1);

      // Re-render
      LPM.manual.renderWorklist();
      utils.showToast(t("manage.manual.translation_deleted", {}), "success");
    } catch (error) {
      console.error("Failed to delete translation:", error);
      utils.showToast(`Failed to delete: ${error.message}`, "danger");
    }
  };

  // ============================================
  // IMPORT FROM FAILED TRANSLATIONS
  // ============================================

  LPM.manual.importFailedItems = function (failedItems) {
    const { state, utils } = LPM;
    if (!failedItems || !failedItems.length) {
      utils.showToast(t("manage.manual.no_failed_items_to_import", {}), "info");
      return;
    }

    failedItems.forEach((item) => {
      const duplicate = state.manual.worklist.find(
        (row) =>
          row.key_path === item.key_path &&
          row.language_code === item.language_code
      );
      if (duplicate) {
        return; // Skip duplicates
      }

      const languageName = LPM.manual.getLanguageLabel(item.language_code);
      // Add to the beginning of the list with timestamp marker
      // New items will always appear at the top regardless of sort order
      state.manual.worklist.unshift({
        key_path: item.key_path,
        page: LPM.manual.derivePageName(item.key_path),
        source_text: item.source_text || "",
        language_code: item.language_code,
        language_name: languageName,
        translated_text: "",
        pending_text: "",
        status: "missing",
        _addedAt: Date.now(), // Mark as newly added item
      });
    });

    LPM.manual.renderWorklist();
    // Switch to manual tab
    if (window.LPM.switchToTab) {
      window.LPM.switchToTab("#manual-pane");
    }
    utils.showToast(
      `Imported ${failedItems.length} failed items to manual translation list.`,
      "success"
    );
  };

  // ============================================
  // EVENT BINDING
  // ============================================

  LPM.manual.bindEvents = function () {
    const { selectors } = LPM;

    if (selectors.manualSearchBtn) {
      selectors.manualSearchBtn.addEventListener("click", (event) => {
        event.preventDefault();
        void LPM.manual.handleSearchKeys();
      });
    }

    if (selectors.manualKeyResultsTable) {
      selectors.manualKeyResultsTable.addEventListener("click", (event) => {
        const row = event.target.closest("tr[data-key-index]");
        if (!row || !event.target.classList.contains("manual-key-add-btn")) {
          return;
        }
        const index = Number.parseInt(row.dataset.keyIndex, 10);
        const { state } = LPM;
        const keyEntry = state.manual.keyResults[index];
        if (keyEntry) {
          LPM.manual.openLanguageModal(keyEntry);
        }
      });
    }

    if (selectors.manualLanguageConfirmBtn) {
      selectors.manualLanguageConfirmBtn.addEventListener("click", (event) => {
        event.preventDefault();
        void LPM.manual.handleConfirmLanguages();
      });
    }

    if (selectors.manualWorklistSort) {
      selectors.manualWorklistSort.addEventListener("change", () => {
        LPM.manual.renderWorklist();
      });
    }

    if (selectors.manualWorklistSelectAll) {
      selectors.manualWorklistSelectAll.addEventListener(
        "change",
        LPM.manual.handleWorklistSelectAll
      );
    }

    if (selectors.manualWorklistTable) {
      selectors.manualWorklistTable.addEventListener(
        "click",
        LPM.manual.handleWorklistTableInteraction
      );
      selectors.manualWorklistTable.addEventListener(
        "input",
        LPM.manual.handleWorklistTableInteraction
      );
    }

    if (selectors.manualSaveSelectedBtn) {
      selectors.manualSaveSelectedBtn.addEventListener("click", (event) => {
        event.preventDefault();
        void LPM.manual.handleBulkSaveLock();
      });
    }

    if (selectors.manualUnlockSelectedBtn) {
      selectors.manualUnlockSelectedBtn.addEventListener("click", (event) => {
        event.preventDefault();
        void LPM.manual.handleBulkUnlock();
      });
    }
  };

  // ============================================
  // INITIALIZATION
  // ============================================

  LPM.manual.init = async function () {
    LPM.manual.bindEvents();
    // Automatically load all locked translations when page loads
    await LPM.manual.ensureLockedItemsLoaded();
    LPM.manual.renderWorklist();
  };
})(window.LPM);
