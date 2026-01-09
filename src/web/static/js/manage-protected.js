/**
 * Protected Terms Module
 * Handles protected terms management including CRUD operations and AI suggestions.
 *
 * Depends on: manage.js (must be loaded first to provide LPM namespace)
 */
(function (LPM) {
  "use strict";

  if (!LPM) {
    console.warn("LPM namespace not found; manage-protected.js disabled.");
    return;
  }

  LPM.protected = {};

  // ============================================
  // STATE
  // ============================================

  LPM.protected.state = {
    availableKeys: [],
    availableModels: [],
    currentProvider: null,
    selectedKeys: [], // For key selection modal
    allKeysData: [], // Store all keys data for filtering
    categoryMetadata: {}, // Will be initialized in init() after i18n is loaded
    keySelectionContext: null, // 'add' or 'edit-{index}' to track modal context
  };

  // ============================================
  // RENDERING
  // ============================================

  LPM.protected.render = function () {
    const { state, selectors, utils } = LPM;
    if (!selectors.protectedTermsTable) return;
    const tbody = selectors.protectedTermsTable.querySelector("tbody");
    if (!tbody) return;

    const activeCategory = selectors.protectedFilterCategory
      ? selectors.protectedFilterCategory.value
      : "";

    const sortOrder = selectors.protectedSortOrder
      ? selectors.protectedSortOrder.value
      : "updated_at_desc";

    // Filter entries and preserve original index
    const entriesWithIndex = state.protectedTerms
      .map((term, originalIndex) => ({ term, originalIndex }))
      .filter(({ term }) => {
        if (!activeCategory) return true;
        return (term.category || "") === activeCategory;
      });

    if (!entriesWithIndex.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" class="text-center text-muted py-5">
            ${
              activeCategory
                ? t("manage.protected.list.no_terms_in_category")
                : t("manage.protected.list.empty")
            }
          </td>
        </tr>
      `;
      return;
    }

    // Sort entries
    entriesWithIndex.sort((a, b) => {
      const termA = a.term;
      const termB = b.term;

      switch (sortOrder) {
        case "term_asc":
          return (termA.term || "").localeCompare(termB.term || "");
        case "term_desc":
          return (termB.term || "").localeCompare(termA.term || "");
        case "updated_at_asc": {
          // Use updated_at if available, otherwise fall back to created_at, then id
          const timeA = termA.updated_at
            ? new Date(termA.updated_at).getTime()
            : termA.created_at
            ? new Date(termA.created_at).getTime()
            : termA.id || 0;
          const timeB = termB.updated_at
            ? new Date(termB.updated_at).getTime()
            : termB.created_at
            ? new Date(termB.created_at).getTime()
            : termB.id || 0;
          return timeA - timeB;
        }
        case "updated_at_desc":
        default: {
          // Use updated_at if available, otherwise fall back to created_at, then id
          const timeA = termA.updated_at
            ? new Date(termA.updated_at).getTime()
            : termA.created_at
            ? new Date(termA.created_at).getTime()
            : termA.id || 0;
          const timeB = termB.updated_at
            ? new Date(termB.updated_at).getTime()
            : termB.created_at
            ? new Date(termB.created_at).getTime()
            : termB.id || 0;
          return timeB - timeA;
        }
      }
    });

    tbody.innerHTML = entriesWithIndex
      .map(({ term, originalIndex }) => {
        const keyScopes = term.key_scopes || [];
        const keyScopesDisplay =
          keyScopes.length > 0
            ? keyScopes.slice(0, 2).join(", ") +
              (keyScopes.length > 2 ? ` +${keyScopes.length - 2} more` : "")
            : `<span class="badge bg-secondary">${t(
                "manage.protected.global",
                {}
              )}</span>`;

        return `
          <tr data-index="${originalIndex}">
            <td>
              <input
                type="text"
                class="form-control form-control-sm protected-term-input"
                value="${utils.escapeHtml(term.term)}"
              />
            </td>
            <td>
              <select class="form-select form-select-sm protected-category-select">
                <option value="brand" ${
                  !term.category || term.category === "brand" ? "selected" : ""
                }>
                  ${t("manage.protected.add_term.category_brand")}
                </option>
                <option value="technical" ${
                  term.category === "technical" ? "selected" : ""
                }>
                  ${t("manage.protected.add_term.category_technical")}
                </option>
                <option value="url" ${
                  term.category === "url" ? "selected" : ""
                }>
                  ${t("manage.protected.add_term.category_url")}
                </option>
                <option value="code" ${
                  term.category === "code" ? "selected" : ""
                }>
                  ${t("manage.protected.add_term.category_code")}
                </option>
              </select>
            </td>
            <td>
              <div class="input-group input-group-sm">
                <input
                  type="text"
                  class="form-control protected-key-scopes-input"
                  value="${
                    keyScopes.length > 0
                      ? utils.escapeHtml(JSON.stringify(keyScopes))
                      : ""
                  }"
                  placeholder="${t("manage.protected.global_protection", {})}"
                  readonly />
                <button class="btn btn-secondary protected-edit-key-scopes-btn" type="button" data-index="${originalIndex}">
                  <i class="bi bi-pencil"></i> ${t("common.edit")}
                </button>
              </div>
            </td>
            <td class="text-end">
              <button class="btn btn-sm btn-danger protected-delete-btn">
                <i class="bi bi-trash"></i>
              </button>
            </td>
          </tr>
        `;
      })
      .join("");
  };

  // ============================================
  // EVENT HANDLERS
  // ============================================

  LPM.protected.handleAdd = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    const term = selectors.protectedTermInput.value.trim();
    if (!term) {
      utils.showToast("Enter a term before adding.", "warning");
      return;
    }

    // Get category from radio buttons
    const categoryRadio = document.querySelector(
      'input[name="protected-category"]:checked'
    );
    const category = categoryRadio ? categoryRadio.value : "brand";

    // Get key scopes from textarea (comma-separated or JSON array format)
    const keyScopesInput = document.getElementById(
      "protected-key-scopes-input"
    );
    const keyScopesText = keyScopesInput ? keyScopesInput.value.trim() : "";
    let keyScopes = [];
    if (keyScopesText) {
      try {
        // Try to parse as JSON array first
        keyScopes = JSON.parse(keyScopesText);
        if (!Array.isArray(keyScopes)) {
          keyScopes = [];
        }
      } catch {
        // If not JSON, treat as comma-separated
        keyScopes = keyScopesText
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean);
      }
    }

    const newTerm = {
      term,
      category,
      is_regex: false,
      key_scopes: keyScopes,
    };

    try {
      // Use /add endpoint (append mode) instead of replace-all
      const response = await utils.fetchJson(
        `${API_BASE}/protected-terms/add`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ terms: [newTerm] }),
        }
      );

      // Clear form
      selectors.protectedTermInput.value = "";
      const brandRadio = document.getElementById("protected-category-brand");
      if (brandRadio) brandRadio.checked = true;
      if (keyScopesInput) keyScopesInput.value = "";

      // Reload to get updated data from server
      await LPM.protected.load();

      const addedCount = response.added_count || 0;
      const mergedCount = response.merged_count || 0;
      if (addedCount > 0) {
        utils.showToast(t("manage.protected.term_added", {}), "success");
      } else if (mergedCount > 0) {
        utils.showToast(t("manage.protected.term_merged", {}), "info");
      }
    } catch (error) {
      console.error("Add term error:", error);
      utils.showToast(`Failed to add term: ${error.message}`, "danger");
    }
  };

  LPM.protected.handleTableInteraction = async function (event) {
    const { state, utils, API_BASE } = LPM;
    const row = event.target.closest("tr[data-index]");
    if (!row) return;
    const index = Number.parseInt(row.dataset.index, 10);
    if (Number.isNaN(index)) return;
    const entry = state.protectedTerms[index];
    if (!entry) return;

    // Check if this is a delete button click
    const deleteBtn = event.target.classList.contains("protected-delete-btn")
      ? event.target
      : event.target.closest(".protected-delete-btn");

    if (deleteBtn) {
      event.preventDefault();
      event.stopPropagation(); // Prevent event from bubbling up
      event.stopImmediatePropagation(); // Prevent other handlers

      // Prevent double-click or multiple rapid clicks
      if (deleteBtn.disabled || deleteBtn.dataset.deleting === "true") {
        return;
      }

      // Mark as deleting to prevent duplicate processing
      deleteBtn.dataset.deleting = "true";
      deleteBtn.disabled = true;

      const termId = entry.id;
      if (!termId) {
        utils.showToast(t("manage.protected.term_id_not_found", {}), "danger");
        deleteBtn.dataset.deleting = "false";
        deleteBtn.disabled = false;
        return;
      }

      try {
        // Delete using DELETE API
        await utils.fetchJson(`${API_BASE}/protected-terms/${termId}`, {
          method: "DELETE",
        });

        // Remove from state and re-render
        state.protectedTerms.splice(index, 1);
        LPM.protected.render();
        utils.showToast(t("manage.protected.term_deleted", {}), "success");
      } catch (error) {
        console.error("Delete term error:", error);
        utils.showToast(`Failed to delete term: ${error.message}`, "danger");
        throw error;
      } finally {
        // Clean up after a delay
        setTimeout(() => {
          deleteBtn.dataset.deleting = "false";
          deleteBtn.disabled = false;
        }, 500);
      }

      return;
    }

    if (event.target.classList.contains("protected-term-input")) {
      entry.term = event.target.value;
      // Auto-save on blur
      if (event.type === "blur") {
        try {
          await LPM.protected.saveSingleTerm(index, true); // Pass true to show success toast
        } catch (error) {
          // Error toast already shown in saveSingleTerm
        }
      }
      return;
    }

    if (event.target.classList.contains("protected-category-select")) {
      entry.category = event.target.value || null;
      await LPM.protected.saveSingleTerm(index);
      LPM.protected.render();
      return;
    }

    if (
      event.target.classList.contains("protected-edit-key-scopes-btn") ||
      event.target.closest(".protected-edit-key-scopes-btn")
    ) {
      event.preventDefault();
      const btn =
        event.target.closest(".protected-edit-key-scopes-btn") || event.target;
      const termIndex = Number.parseInt(btn.dataset.index, 10);
      if (!Number.isNaN(termIndex)) {
        await LPM.protected.openKeySelectionModalForEdit(termIndex);
      }
      return;
    }
  };

  // ============================================
  // KEY SELECTION MODAL
  // ============================================

  LPM.protected.openKeySelectionModal = async function () {
    // Open modal for adding new term (from Add Protected Term form)
    const { state } = LPM;
    state.keySelectionContext = "add";
    await LPM.protected._openKeySelectionModalInternal(null);
  };

  LPM.protected.openKeySelectionModalForEdit = async function (termIndex) {
    // Open modal for editing existing term (from table)
    const { state } = LPM;
    state.keySelectionContext = `edit-${termIndex}`;
    await LPM.protected._openKeySelectionModalInternal(termIndex);
  };

  LPM.protected._openKeySelectionModalInternal = async function (termIndex) {
    const { state, utils, API_BASE } = LPM;
    const modal = document.getElementById("protectedKeySelectionModal");
    const table = document.getElementById("protected-key-selection-table");
    const tbody = table ? table.querySelector("tbody") : null;
    const filterInput = document.getElementById("protected-key-filter-input");
    const addBtn = document.getElementById("protected-keys-add-btn");

    if (!modal || !tbody) return;

    try {
      let existingKeyScopes = [];

      if (
        termIndex !== null &&
        termIndex >= 0 &&
        termIndex < state.protectedTerms.length
      ) {
        // Editing existing term from table
        existingKeyScopes = state.protectedTerms[termIndex].key_scopes || [];
      } else {
        // Adding new term from form
        const keyScopesInput = document.getElementById(
          "protected-key-scopes-input"
        );
        const keyScopesText = keyScopesInput ? keyScopesInput.value.trim() : "";
        if (keyScopesText) {
          try {
            existingKeyScopes = JSON.parse(keyScopesText);
            if (!Array.isArray(existingKeyScopes)) {
              existingKeyScopes = [];
            }
          } catch {
            existingKeyScopes = keyScopesText
              .split(",")
              .map((k) => k.trim())
              .filter(Boolean);
          }
        }
      }

      // Load all keys with source text
      const data = await utils.fetchJson(`${API_BASE}/keys`);
      const keys = data.keys || [];
      state.allKeysData = keys; // Store for filtering

      // Initialize selected keys with existing key scopes
      state.selectedKeys = [...existingKeyScopes];

      // Update button text based on context
      if (addBtn) {
        if (termIndex !== null) {
          addBtn.textContent = t("common.save", {});
        } else {
          addBtn.textContent = t(
            "manage.protected.key_selection_modal.add_btn"
          );
        }
      }

      // Render table
      LPM.protected.renderKeySelectionTable(keys, existingKeyScopes);

      // Render selected keys display
      LPM.protected.renderSelectedKeysDisplay();

      // Setup filter
      if (filterInput) {
        filterInput.value = "";
        // Create new handler for this modal instance
        const filterHandler = (e) => {
          const filterText = e.target.value.toLowerCase().trim();
          const filteredKeys = filterText
            ? state.allKeysData.filter(
                (k) =>
                  (k.key_path || "").toLowerCase().includes(filterText) ||
                  (k.source_text || "").toLowerCase().includes(filterText)
              )
            : state.allKeysData;
          // Use current selectedKeys instead of existingKeyScopes
          LPM.protected.renderKeySelectionTable(
            filteredKeys,
            state.selectedKeys
          );
        };
        // Remove old listener if exists and add new one
        if (state._filterHandler) {
          filterInput.removeEventListener("input", state._filterHandler);
        }
        state._filterHandler = filterHandler;
        filterInput.addEventListener("input", filterHandler);
      }

      // Show modal
      const bsModal = new bootstrap.Modal(modal, { backdrop: "static" });
      bsModal.show();
    } catch (error) {
      console.error(error);
      utils.showToast(`Failed to load keys: ${error.message}`, "danger");
    }
  };

  LPM.protected.renderKeySelectionTable = function (
    keys,
    initialKeyScopes = []
  ) {
    const { state, utils } = LPM;
    const table = document.getElementById("protected-key-selection-table");
    const tbody = table ? table.querySelector("tbody") : null;
    if (!tbody) return;

    if (keys.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="3" class="text-center text-muted py-4">
            ${t("manage.protected.no_keys_found", {})}
          </td>
        </tr>
      `;
      return;
    }

    // Use state.selectedKeys as the source of truth
    // It's initialized from initialKeyScopes when modal opens, and updated by user interactions
    const selectedKeysToUse = state.selectedKeys;

    tbody.innerHTML = keys
      .map((key) => {
        const isSelected = selectedKeysToUse.includes(key.key_path);
        return `
        <tr data-key-path="${utils.escapeHtml(
          key.key_path
        )}" style="cursor: pointer;" class="${
          isSelected ? "table-active" : ""
        }">
          <td>
            <input
              type="checkbox"
              class="form-check-input key-select-checkbox"
              data-key-path="${utils.escapeHtml(key.key_path)}"
              ${isSelected ? "checked" : ""}
            />
          </td>
          <td>${utils.escapeHtml(key.key_path)}</td>
          <td class="text-muted small">${utils.escapeHtml(
            (key.source_text || "").substring(0, 100)
          )}</td>
        </tr>
      `;
      })
      .join("");

    // Add click handlers for rows
    tbody.querySelectorAll("tr[data-key-path]").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.type === "checkbox") return;
        const checkbox = row.querySelector(".key-select-checkbox");
        if (checkbox) {
          checkbox.checked = !checkbox.checked;
          checkbox.dispatchEvent(new Event("change"));
        }
      });
    });

    // Add change handlers for checkboxes
    tbody.querySelectorAll(".key-select-checkbox").forEach((checkbox) => {
      checkbox.addEventListener("change", (e) => {
        const keyPath = e.target.dataset.keyPath;
        if (e.target.checked) {
          if (!state.selectedKeys.includes(keyPath)) {
            state.selectedKeys.push(keyPath);
          }
        } else {
          state.selectedKeys = state.selectedKeys.filter((k) => k !== keyPath);
        }
        LPM.protected.updateKeySelectionSelectAll();
        // Update row highlight
        const row = e.target.closest("tr[data-key-path]");
        if (row) {
          if (e.target.checked) {
            row.classList.add("table-active");
          } else {
            row.classList.remove("table-active");
          }
        }
        // Update selected keys display
        LPM.protected.renderSelectedKeysDisplay();
      });
    });

    LPM.protected.updateKeySelectionSelectAll();
    // Render selected keys display
    LPM.protected.renderSelectedKeysDisplay();
  };

  LPM.protected.updateKeySelectionSelectAll = function () {
    const selectAll = document.getElementById("protected-keys-select-all");
    const checkboxes = document.querySelectorAll(".key-select-checkbox");
    const checkedCount = Array.from(checkboxes).filter(
      (cb) => cb.checked
    ).length;

    if (selectAll) {
      selectAll.checked =
        checkedCount === checkboxes.length && checkboxes.length > 0;
      selectAll.indeterminate =
        checkedCount > 0 && checkedCount < checkboxes.length;
    }
  };

  LPM.protected.renderSelectedKeysDisplay = function () {
    const { state, utils } = LPM;
    const container = document.getElementById("selected-keys-display-container");
    const display = document.getElementById("selected-keys-display");
    
    if (!container || !display) return;

    const selectedKeys = state.selectedKeys || [];

    // Show/hide container based on whether there are selected keys
    if (selectedKeys.length === 0) {
      container.style.display = "none";
      return;
    }

    container.style.display = "block";

    // Render selected keys as badges with remove buttons
    display.innerHTML = selectedKeys
      .map((keyPath) => {
        const escapedKeyPath = utils.escapeHtml(keyPath);
        return `
          <span class="badge bg-primary d-inline-flex align-items-center gap-1" style="font-size: 0.875rem;">
            <code style="background: transparent; color: inherit; padding: 0; font-size: 0.875rem;">${escapedKeyPath}</code>
            <button
              type="button"
              class="btn-close btn-close-white"
              style="font-size: 0.5rem; opacity: 0.8;"
              data-key-path="${escapedKeyPath}"
              aria-label="Remove"
              title="Remove ${escapedKeyPath}"></button>
          </span>
        `;
      })
      .join("");

    // Add click handlers for remove buttons
    display.querySelectorAll(".btn-close").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const keyPath = btn.dataset.keyPath;
        LPM.protected.removeSelectedKey(keyPath);
      });
    });
  };

  LPM.protected.removeSelectedKey = function (keyPath) {
    const { state } = LPM;
    
    // Remove from state.selectedKeys
    state.selectedKeys = state.selectedKeys.filter((k) => k !== keyPath);

    // Uncheck checkbox in table if it exists
    // Find all checkboxes and match by data attribute value
    const checkboxes = document.querySelectorAll(".key-select-checkbox");
    checkboxes.forEach((checkbox) => {
      if (checkbox.dataset.keyPath === keyPath) {
        checkbox.checked = false;
        // Update row highlight
        const row = checkbox.closest("tr[data-key-path]");
        if (row) {
          row.classList.remove("table-active");
        }
      }
    });

    // Update select all checkbox state
    LPM.protected.updateKeySelectionSelectAll();
    
    // Update selected keys display
    LPM.protected.renderSelectedKeysDisplay();
  };

  LPM.protected.handleKeySelectionSelectAll = function (event) {
    const checked = event.target.checked;
    const { state } = LPM;

    document.querySelectorAll(".key-select-checkbox").forEach((checkbox) => {
      checkbox.checked = checked;
      const keyPath = checkbox.dataset.keyPath;
      if (checked) {
        if (!state.selectedKeys.includes(keyPath)) {
          state.selectedKeys.push(keyPath);
        }
      } else {
        state.selectedKeys = state.selectedKeys.filter((k) => k !== keyPath);
      }
      // Update row highlight
      const row = checkbox.closest("tr[data-key-path]");
      if (row) {
        if (checked) {
          row.classList.add("table-active");
        } else {
          row.classList.remove("table-active");
        }
      }
    });
    // Update selected keys display
    LPM.protected.renderSelectedKeysDisplay();
  };

  LPM.protected.addSelectedKeysToInput = async function () {
    const { state, utils } = LPM;
    const modalElement = document.getElementById("protectedKeySelectionModal");
    const modal = modalElement
      ? bootstrap.Modal.getInstance(modalElement)
      : null;

    // Format as JSON array (same as database format)
    const keyScopesJson = JSON.stringify(state.selectedKeys);

    // Determine context
    if (
      state.keySelectionContext &&
      state.keySelectionContext.startsWith("edit-")
    ) {
      // Editing existing term from table
      const termIndex = Number.parseInt(
        state.keySelectionContext.replace("edit-", ""),
        10
      );
      if (
        !Number.isNaN(termIndex) &&
        termIndex >= 0 &&
        termIndex < state.protectedTerms.length
      ) {
        state.protectedTerms[termIndex].key_scopes = state.selectedKeys;
        // Auto-save using PUT API
        try {
          await LPM.protected.saveSingleTerm(termIndex, true);

          // Close modal and ensure backdrop is removed
          if (modal) {
            modal.hide();
            // Manually remove backdrop if it still exists after a short delay
            setTimeout(() => {
              const backdrop = document.querySelector(".modal-backdrop");
              if (backdrop) {
                backdrop.remove();
              }
              // Remove modal-open class from body if it exists
              document.body.classList.remove("modal-open");
              document.body.style.overflow = "";
              document.body.style.paddingRight = "";
            }, 300);
          }

          LPM.protected.render();
        } catch (error) {
          console.error(error);
          utils.showToast(`Failed to save changes: ${error.message}`, "danger");
          return;
        }
      }
    } else {
      // Adding new term from form
      const keyScopesInput = document.getElementById(
        "protected-key-scopes-input"
      );
      if (keyScopesInput) {
        keyScopesInput.value = keyScopesJson;
      }

      // Close modal
      if (modal) {
        modal.hide();
      }
    }

    // Clear filter
    const filterInput = document.getElementById("protected-key-filter-input");
    if (filterInput) {
      filterInput.value = "";
    }

    // Clear selection and context
    state.selectedKeys = [];
    state.keySelectionContext = null;
  };

  // ============================================
  // API OPERATIONS
  // ============================================

  LPM.protected.saveSingleTerm = async function (
    index,
    showSuccessToast = false
  ) {
    const { state, selectors, utils, API_BASE } = LPM;
    if (index < 0 || index >= state.protectedTerms.length) return;

    const term = state.protectedTerms[index];
    const termId = term.id;
    if (!termId) {
      utils.showToast("Term ID not found. Please reload the page.", "danger");
      return;
    }

    try {
      const payload = {
        term: term.term,
        category: term.category,
        is_regex: !!term.is_regex,
        key_scopes: term.key_scopes || [],
      };
      const response = await utils.fetchJson(
        `${API_BASE}/protected-terms/${termId}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      // Update local state with server response
      if (response.term) {
        state.protectedTerms[index] = {
          ...state.protectedTerms[index],
          ...response.term,
          key_scopes: response.term.key_scopes || [],
        };
      }

      // Show success toast if requested
      if (showSuccessToast) {
        utils.showToast(t("manage.protected.term_saved", {}), "success");
      }
    } catch (error) {
      console.error(error);
      utils.showToast(`Failed to save term: ${error.message}`, "danger");
      throw error; // Re-throw to allow caller to handle
    }
  };

  LPM.protected.load = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    try {
      const data = await utils.fetchJson(`${API_BASE}/protected-terms`);
      state.protectedTerms = (data.terms || []).map((term) => ({
        ...term,
        key_scopes: term.key_scopes || [],
      }));
      if (selectors.protectedEnableSwitch) {
        selectors.protectedEnableSwitch.checked = !!data.enabled;
      }
      LPM.protected.render();
    } catch (error) {
      console.error(error);
      utils.showToast(
        `Failed to load protected terms: ${error.message}`,
        "danger"
      );
    }
  };

  LPM.protected.loadAvailableKeys = async function () {
    const { state, utils, API_BASE } = LPM;
    try {
      const data = await utils.fetchJson(`${API_BASE}/keys?simple=true`);
      state.availableKeys = data.key_paths || [];
    } catch (error) {
      console.error(error);
    }
  };

  LPM.protected.loadAvailableModels = async function () {
    const { state, utils } = LPM;
    try {
      const data = await utils.fetchJson("/api/settings");
      const settings = data.config || data;

      // Get built-in providers from API meta, fallback to defaults
      const builtInProviders = data.meta?.builtin_providers || [
        { id: "openai", name: "OpenAI" },
        { id: "deepseek", name: "DeepSeek" },
        { id: "gemini", name: "Gemini" },
      ];

      // Build provider/model list grouped by provider (same as translate page)
      const providerGroups = [];
      const topLevelKeys = ["ai_provider", "log_mode", "translation"];

      // Check built-in providers
      for (const provider of builtInProviders) {
        const providerConfig = settings[provider.id];
        if (
          !providerConfig?.api_key ||
          providerConfig.api_key === "YOUR_API_KEY_HERE"
        ) {
          continue;
        }

        // Get models array (handle both old 'model' and new 'models' format)
        let models = providerConfig.models || [];
        if (!models.length && providerConfig.model) {
          models = [providerConfig.model];
        }

        if (models.length > 0) {
          providerGroups.push({
            id: provider.id,
            name: provider.name,
            models: models.filter((m) => m && typeof m === "string"),
          });
        }
      }

      // Check custom providers
      const builtInProviderIds = builtInProviders.map((p) => p.id);
      Object.keys(settings).forEach((key) => {
        if (
          !builtInProviderIds.includes(key) &&
          !topLevelKeys.includes(key) &&
          typeof settings[key] === "object" &&
          settings[key] !== null &&
          settings[key].api_key
        ) {
          // This is a custom provider
          const providerConfig = settings[key];
          const apiKey = providerConfig.api_key || "";

          if (apiKey && apiKey !== "YOUR_API_KEY_HERE") {
            // Get models array
            let models = providerConfig.models || [];
            if (!models.length && providerConfig.model) {
              models = [providerConfig.model];
            }

            if (models.length > 0) {
              const displayName =
                key.charAt(0).toUpperCase() + key.slice(1).replace(/-/g, " ");
              providerGroups.push({
                id: key,
                name: displayName,
                models: models.filter((m) => m && typeof m === "string"),
              });
            }
          }
        }
      });

      state.availableModels = providerGroups;
      state.currentProvider = settings.ai_provider;

      // Update model selector (same format as translate page)
      const modelSelect = document.getElementById("protected-model-select");
      if (modelSelect) {
        modelSelect.innerHTML = "";

        if (providerGroups.length === 0) {
          const option = document.createElement("option");
          option.value = "";
          option.textContent = "No models available";
          modelSelect.appendChild(option);
          return;
        }

        // Create optgroups for each provider
        providerGroups.forEach((group) => {
          const optgroup = document.createElement("optgroup");
          optgroup.label = group.name;

          group.models.forEach((model, index) => {
            const option = document.createElement("option");
            option.value = `${group.id}:${model}`;
            option.textContent = model;
            // Select first model of default provider
            if (group.id === state.currentProvider && index === 0) {
              option.selected = true;
            }
            optgroup.appendChild(option);
          });

          modelSelect.appendChild(optgroup);
        });
      }
    } catch (error) {
      console.error(error);
    }
  };

  LPM.protected.updateSettings = async function (enabled) {
    const { selectors, utils, API_BASE } = LPM;
    try {
      await utils.fetchJson(`${API_BASE}/protected-terms/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      utils.showToast(
        `Protected terms ${enabled ? "enabled" : "disabled"} for this project.`,
        "success"
      );
    } catch (error) {
      console.error(error);
      utils.showToast(
        `Failed to update protected term settings: ${error.message}`,
        "danger"
      );
      if (selectors.protectedEnableSwitch) {
        selectors.protectedEnableSwitch.checked = !enabled;
      }
    }
  };

  // ============================================
  // SUGGESTIONS
  // ============================================

  LPM.protected.analyze = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    if (!selectors.suggestionsModal || !window.bootstrap) {
      utils.showToast(t("manage.protected.modal_unavailable", {}), "danger");
      return;
    }
    try {
      selectors.protectedAnalyzeBtn.disabled = true;
      selectors.protectedAnalyzeBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>${t(
        "manage.protected.analyzing",
        {}
      )}`;

      const modelSelect = document.getElementById("protected-model-select");
      const modelSelection =
        modelSelect && modelSelect.value ? modelSelect.value : null;

      // Parse provider:model format
      let provider = null;
      let modelOverride = null;
      if (modelSelection && modelSelection.includes(":")) {
        const parts = modelSelection.split(":");
        provider = parts[0];
        modelOverride = parts.slice(1).join(":"); // Handle model names with colons
      } else if (modelSelection) {
        // Fallback: if no colon, treat as model only
        modelOverride = modelSelection;
      }

      const data = await utils.fetchJson(
        `${API_BASE}/protected-terms/analyze`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: provider,
            model_override: modelOverride,
          }),
        }
      );
      state.protectedSuggestions = data.suggestions || [];
      LPM.protected.populateSuggestions();
      const modal = new bootstrap.Modal(selectors.suggestionsModal, {
        backdrop: "static",
      });
      modal.show();
    } catch (error) {
      console.error(error);
      utils.showToast(
        `Failed to analyse protected terms: ${error.message}`,
        "danger"
      );
    } finally {
      selectors.protectedAnalyzeBtn.disabled = false;
      selectors.protectedAnalyzeBtn.innerHTML = `<i class="bi bi-search-heart me-1"></i>${t(
        "manage.protected.analyze.analyze_btn"
      )}`;
    }
  };

  LPM.protected.populateSuggestions = function () {
    const { state, selectors, utils } = LPM;
    if (!selectors.suggestionsTable) return;
    const tbody = selectors.suggestionsTable.querySelector("tbody");
    if (!tbody) return;

    if (!state.protectedSuggestions.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" class="text-center text-muted py-4">
            ${t("manage.protected.suggestions_modal.empty")}
          </td>
        </tr>
      `;
      if (selectors.suggestionsSelectAll) {
        selectors.suggestionsSelectAll.disabled = true;
        selectors.suggestionsSelectAll.checked = false;
      }
      if (selectors.suggestionsApplyBtn) {
        selectors.suggestionsApplyBtn.disabled = true;
      }
      return;
    }

    // Get category display names
    const categoryNames = LPM.protected.state?.categoryMetadata || {};

    tbody.innerHTML = state.protectedSuggestions
      .map((item, index) => {
        const categoryValue = item.category || "";
        const categoryDisplay =
          categoryNames[categoryValue] || categoryValue || "Uncategorized";
        return `
        <tr data-index="${index}">
          <td>
            <input type="checkbox" class="form-check-input suggestion-select" />
          </td>
          <td>${utils.escapeHtml(item.term)}</td>
          <td>${utils.escapeHtml(categoryDisplay)}</td>
          <td>${utils.escapeHtml(String(item.match_count || 0))}</td>
        </tr>
      `;
      })
      .join("");

    if (selectors.suggestionsSelectAll) {
      selectors.suggestionsSelectAll.disabled = false;
      selectors.suggestionsSelectAll.checked = false;
    }
    if (selectors.suggestionsApplyBtn) {
      selectors.suggestionsApplyBtn.disabled = true;
    }
  };

  LPM.protected.handleSuggestionSelection = function (event) {
    const { selectors } = LPM;
    if (event.target.id === "protected-suggestions-select-all") {
      const checked = event.target.checked;
      selectors.suggestionsTable
        ?.querySelectorAll(".suggestion-select")
        .forEach((checkbox) => {
          checkbox.checked = checked;
        });
      if (selectors.suggestionsApplyBtn) {
        selectors.suggestionsApplyBtn.disabled = !checked;
      }
      return;
    }

    if (event.target.classList.contains("suggestion-select")) {
      const checkboxes = Array.from(
        selectors.suggestionsTable.querySelectorAll(".suggestion-select")
      );
      const checkedCount = checkboxes.filter(
        (checkbox) => checkbox.checked
      ).length;
      if (selectors.suggestionsSelectAll) {
        selectors.suggestionsSelectAll.checked =
          checkedCount === checkboxes.length;
        selectors.suggestionsSelectAll.indeterminate =
          checkedCount > 0 && checkedCount < checkboxes.length;
      }
      if (selectors.suggestionsApplyBtn) {
        selectors.suggestionsApplyBtn.disabled = checkedCount === 0;
      }
    }
  };

  LPM.protected.applySuggestions = async function () {
    const { state, selectors, utils } = LPM;
    const checkboxes = Array.from(
      selectors.suggestionsTable.querySelectorAll(".suggestion-select")
    );
    const selected = checkboxes
      .map((checkbox, index) => (checkbox.checked ? index : null))
      .filter((index) => index !== null)
      .map((index) => state.protectedSuggestions[index]);

    if (!selected.length) {
      utils.showToast("Select at least one suggestion to add.", "warning");
      return;
    }

    // Prepare terms to add using incremental add API
    const termsToAdd = selected.map((suggestion) => ({
      term: suggestion.term,
      category: suggestion.category,
      is_regex: suggestion.is_regex || false,
      key_scopes: [],
    }));

    try {
      const { utils, API_BASE } = LPM;
      const response = await utils.fetchJson(
        `${API_BASE}/protected-terms/add`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ terms: termsToAdd }),
        }
      );

      // Reload to get updated data from server (with IDs)
      await LPM.protected.load();

      const modal = bootstrap.Modal.getInstance(selectors.suggestionsModal);
      if (modal) {
        modal.hide();
      }

      const addedCount = response.added_count || 0;
      const skippedCount = response.skipped_count || 0;
      if (addedCount > 0) {
        const plural = addedCount > 1 ? "s" : "";
        const skippedText =
          skippedCount > 0 ? ` ${skippedCount} skipped (duplicates).` : "";
        utils.showToast(
          t("manage.protected.terms_added", {
            count: addedCount,
            plural: plural,
            skipped: skippedText,
          }),
          "success"
        );
      } else if (skippedCount > 0) {
        const plural = skippedCount > 1 ? "s" : "";
        utils.showToast(
          t("manage.protected.all_terms_exist", {
            count: skippedCount,
            plural: plural,
          }),
          "info"
        );
      }
    } catch (error) {
      console.error("Apply suggestions error:", error);
      utils.showToast(`Failed to add terms: ${error.message}`, "danger");
    }
  };

  // ============================================
  // EVENT BINDING
  // ============================================

  LPM.protected.bindEvents = function () {
    const { selectors } = LPM;

    if (selectors.protectedAddBtn) {
      selectors.protectedAddBtn.addEventListener("click", (event) => {
        event.preventDefault();
        void LPM.protected.handleAdd();
      });
    }

    if (selectors.protectedAnalyzeBtn) {
      selectors.protectedAnalyzeBtn.addEventListener("click", (event) => {
        event.preventDefault();
        void LPM.protected.analyze();
      });
    }

    // Add key button
    const addKeyBtn = document.getElementById("protected-add-key-btn");
    if (addKeyBtn) {
      addKeyBtn.addEventListener("click", (event) => {
        event.preventDefault();
        void LPM.protected.openKeySelectionModal();
      });
    }

    // Key selection modal events
    const keySelectAll = document.getElementById("protected-keys-select-all");
    if (keySelectAll) {
      keySelectAll.addEventListener(
        "change",
        LPM.protected.handleKeySelectionSelectAll
      );
    }

    const keyAddBtn = document.getElementById("protected-keys-add-btn");
    if (keyAddBtn) {
      keyAddBtn.addEventListener("click", (event) => {
        event.preventDefault();
        void LPM.protected.addSelectedKeysToInput();
      });
    }

    // Clear context when modal is hidden
    const keyModal = document.getElementById("protectedKeySelectionModal");
    if (keyModal) {
      keyModal.addEventListener("hidden.bs.modal", () => {
        LPM.protected.state.keySelectionContext = null;
        LPM.protected.state.selectedKeys = [];
        // Ensure backdrop is removed
        const backdrop = document.querySelector(".modal-backdrop");
        if (backdrop) {
          backdrop.remove();
        }
        // Remove modal-open class from body if it exists
        document.body.classList.remove("modal-open");
        document.body.style.overflow = "";
        document.body.style.paddingRight = "";
      });
    }

    if (selectors.protectedFilterCategory) {
      selectors.protectedFilterCategory.addEventListener("change", () => {
        LPM.protected.render();
      });
    }

    if (selectors.protectedSortOrder) {
      selectors.protectedSortOrder.addEventListener("change", () => {
        LPM.protected.render();
      });
    }

    if (selectors.protectedTermsTable) {
      selectors.protectedTermsTable.addEventListener(
        "input",
        LPM.protected.handleTableInteraction
      );
      selectors.protectedTermsTable.addEventListener(
        "change",
        LPM.protected.handleTableInteraction
      );
      selectors.protectedTermsTable.addEventListener(
        "blur",
        LPM.protected.handleTableInteraction,
        true
      );
      selectors.protectedTermsTable.addEventListener(
        "click",
        LPM.protected.handleTableInteraction
      );
    }

    if (selectors.protectedEnableSwitch) {
      selectors.protectedEnableSwitch.addEventListener("change", (event) => {
        LPM.protected.updateSettings(event.target.checked);
      });
    }

    if (selectors.suggestionsTable && selectors.suggestionsModal) {
      selectors.suggestionsTable.addEventListener(
        "change",
        LPM.protected.handleSuggestionSelection
      );
    }

    if (selectors.suggestionsSelectAll) {
      selectors.suggestionsSelectAll.addEventListener(
        "change",
        LPM.protected.handleSuggestionSelection
      );
    }

    if (selectors.suggestionsApplyBtn) {
      selectors.suggestionsApplyBtn.addEventListener("click", (event) => {
        event.preventDefault();
        void LPM.protected.applySuggestions();
      });
    }
  };

  // ============================================
  // INITIALIZATION
  // ============================================

  LPM.protected.init = async function () {
    // Initialize category metadata after i18n is loaded
    LPM.protected.state.categoryMetadata = {
      brand: t("manage.protected.add_term.category_brand"),
      technical: t("manage.protected.add_term.category_technical"),
      url: t("manage.protected.add_term.category_url"),
      code: t("manage.protected.add_term.category_code"),
    };
    LPM.protected.bindEvents();
    await LPM.protected.loadAvailableKeys();
    await LPM.protected.loadAvailableModels();
    await LPM.protected.load();
  };
})(window.LPM);
