/**
 * Translation Module
 * Handles translate tab and translation job management.
 *
 * Depends on: manage.js (must be loaded first to provide LPM namespace)
 */
(function (LPM) {
  "use strict";

  if (!LPM) {
    console.warn("LPM namespace not found; manage-translate.js disabled.");
    return;
  }

  LPM.translate = {};

  // ============================================
  // TRANSLATE TAB FUNCTIONS
  // ============================================

  LPM.translate.formatNumber = function (num) {
    return new Intl.NumberFormat().format(num || 0);
  };

  // Generate unique identifier for a progress item
  // Used for deduplication and tracking processed items
  LPM.translate.getProgressItemId = function (progressItem) {
    if (
      !progressItem ||
      !progressItem.phase ||
      !progressItem.current_language
    ) {
      return null;
    }

    const langCode = progressItem.current_language;
    const phase = progressItem.phase;

    // For batch_done, include batch number to make it unique
    if (phase === "batch_done" && progressItem.current_batch > 0) {
      return `${langCode}_${phase}_${progressItem.current_batch}`;
    }

    // For other phases, use language + phase
    return `${langCode}_${phase}`;
  };

  // Check if a phase allows updates (completed phase may be updated after retry)
  LPM.translate.isUpdatablePhase = function (phase) {
    return phase === "completed";
  };

  // Format completion message for a language
  LPM.translate.formatCompletionMessage = function (options) {
    const {
      languageName,
      successCount = 0,
      failureCount = 0,
      tokenUsage = null,
    } = options;

    const total = successCount + failureCount;
    let message = tokenUsage
      ? t("manage.translate.messages.language_completed_with_tokens", {
          languageName,
          total,
          successCount,
          failureCount,
          inputTokens: LPM.translate.formatNumber(
            tokenUsage.prompt_tokens || 0
          ),
          outputTokens: LPM.translate.formatNumber(
            tokenUsage.completion_tokens || 0
          ),
        })
      : t("manage.translate.messages.language_completed", {
          languageName,
          total,
          successCount,
          failureCount,
        });

    return message;
  };

  // Unified handler for language completion
  // Note: This function is called after deduplication, so it can safely process
  LPM.translate.handleLanguageCompletion = function (options) {
    const { state, selectors } = LPM;
    const {
      langCode,
      langName,
      successCount = 0,
      failureCount = 0,
      tokenUsage = null,
      failedItems = [],
    } = options;

    // Check if this language's completion was already shown
    // This prevents duplicate completion messages during polling
    if (langCode === state.translate.lastCompletedLanguage) {
      // Check if this is an update (different stats)
      const lastStats = state.translate.lastCompletedStats?.[langCode];
      if (lastStats) {
        const isUpdate =
          lastStats.successCount !== successCount ||
          lastStats.failureCount !== failureCount;
        if (!isUpdate) {
          // Same stats, skip to avoid duplicate message
          return;
        }
      } else {
        // No previous stats, but language already completed, skip
        return;
      }
    }

    // Build message
    const message = LPM.translate.formatCompletionMessage({
      languageName: langName,
      successCount,
      failureCount,
      tokenUsage,
    });

    // Accumulate token usage if available
    if (tokenUsage) {
      state.translate.totalTokenUsage.prompt_tokens +=
        tokenUsage.prompt_tokens || 0;
      state.translate.totalTokenUsage.completion_tokens +=
        tokenUsage.completion_tokens || 0;

      // Update UI
      if (selectors.translateSummaryTokenInput) {
        selectors.translateSummaryTokenInput.textContent =
          LPM.translate.formatNumber(
            state.translate.totalTokenUsage.prompt_tokens
          );
      }
      if (selectors.translateSummaryTokenOutput) {
        selectors.translateSummaryTokenOutput.textContent =
          LPM.translate.formatNumber(
            state.translate.totalTokenUsage.completion_tokens
          );
      }
    }

    // Update last completed language and stats
    state.translate.lastCompletedLanguage = langCode;
    if (!state.translate.lastCompletedStats) {
      state.translate.lastCompletedStats = {};
    }
    state.translate.lastCompletedStats[langCode] = {
      successCount,
      failureCount,
    };

    // Add briefing with language code for filtering
    LPM.translate.addBriefing(
      failureCount > 0 ? "warning" : "success",
      message,
      failedItems,
      false, // isFinalSummary
      langCode // languageCode for filtering
    );
  };

  // Unified progress item processor - handles both history and current progress
  // This function is called after deduplication check, so it can safely process the item
  LPM.translate.processProgressItem = function (progressItem) {
    const { state, selectors } = LPM;

    // Skip if invalid
    if (!progressItem.phase || !progressItem.current_language) {
      return;
    }

    const langCode = progressItem.current_language;
    const langName = progressItem.current_language_name || langCode;
    const phase = progressItem.phase;

    // Only process briefing phases
    const briefingPhases = [
      "checking",
      "checked",
      "tasks_found",
      "no_work",
      "file_generated",
      "starting",
      "batch_done",
      "completed",
    ];
    if (!briefingPhases.includes(phase)) {
      return;
    }

    // Process based on phase
    switch (progressItem.phase) {
      case "checking":
        LPM.translate.addBriefing(
          "info",
          `Checking ${langName} (${langCode})...`
        );
        break;

      case "checked":
        const totalKeys = progressItem.total_items || 0;
        const completedKeys = progressItem.success_count || 0;
        const missingKeys = progressItem.failure_count || 0;
        LPM.translate.addBriefing(
          "info",
          `Total: ${totalKeys}, Completed: ${completedKeys}, Missing: ${missingKeys}`
        );
        break;

      case "tasks_found":
        const mode =
          progressItem.mode || state.translate.mode || "missing_only";
        const missingCount = progressItem.missing_count || 0;
        const aiCount = progressItem.ai_count || 0;
        const lockedCount = progressItem.locked_count || 0;
        const totalTasks = progressItem.total_tasks || 0;

        if (mode === "missing_only") {
          if (missingCount > 0) {
            LPM.translate.addBriefing(
              "info",
              `${missingCount} missing entr${
                missingCount !== 1 ? "ies" : "y"
              } will be translated`
            );
          }
        } else if (mode === "missing_and_ai") {
          if (missingCount > 0) {
            LPM.translate.addBriefing(
              "info",
              `${missingCount} missing entr${
                missingCount !== 1 ? "ies" : "y"
              } will be translated`
            );
          }
          if (lockedCount > 0) {
            LPM.translate.addBriefing(
              "info",
              `Manual translated (locked): ${lockedCount}`
            );
          }
          if (aiCount > 0) {
            LPM.translate.addBriefing(
              "info",
              `${aiCount} AI-generated entr${
                aiCount !== 1 ? "ies" : "y"
              } will be re-translated`
            );
          }
        } else if (mode === "full") {
          if (totalTasks > 0) {
            const lockedText =
              lockedCount > 0 ? ` (${lockedCount} locked)` : "";
            LPM.translate.addBriefing(
              "info",
              `${totalTasks} entr${
                totalTasks !== 1 ? "ies" : "y"
              } will be translated${lockedText}`
            );
          }
        } else if (mode === "validate_only") {
          if (totalTasks > 0) {
            LPM.translate.addBriefing(
              "info",
              `${totalTasks} entr${
                totalTasks !== 1 ? "ies" : "y"
              } will be validated`
            );
          }
        }
        break;

      case "no_work":
        const noWorkMode =
          progressItem.mode || state.translate.mode || "missing_only";
        if (noWorkMode === "missing_only") {
          LPM.translate.addBriefing(
            "info",
            `No missing entries. Skipping ${langName} (${langCode}).`
          );
        } else if (noWorkMode === "validate_only") {
          LPM.translate.addBriefing(
            "info",
            `No translations to validate. Skipping ${langName} (${langCode}).`
          );
        } else {
          LPM.translate.addBriefing(
            "success",
            `All translations complete for ${langName} (${langCode}).`
          );
        }
        break;

      case "file_generated":
        LPM.translate.addBriefing("success", `Generated: ${langCode}.json`);
        break;

      case "starting":
        const startingMode =
          progressItem.mode || state.translate.mode || "missing_only";
        const actionText =
          startingMode === "validate_only"
            ? t("manage.translate.messages.validating")
            : t("manage.translate.messages.translating");
        LPM.translate.addBriefing(
          "info",
          `${actionText} ${langName} (${langCode})...`
        );

        // Simple progress calculation: based on languages only
        let startingPercent = 0;
        if (progressItem.total_languages > 0) {
          startingPercent = Math.round(
            (progressItem.completed_languages / progressItem.total_languages) *
              100
          );
          startingPercent = Math.max(0, Math.min(100, startingPercent));
        }

        LPM.translate.updateProgress(
          startingPercent,
          `${actionText} ${langName} (${langCode})...`
        );
        state.translate.lastProgressPercent = startingPercent;
        state.translate.lastLanguage = langCode;
        state.translate.currentBatch = 0;
        state.translate.currentPhase = "";
        state.translate.lastTotalBatches = progressItem.total_batches || 0;
        break;

      case "batch_done":
        if (progressItem.current_batch > 0 && progressItem.total_batches > 0) {
          // batch_done is already deduplicated by getProgressItemId (includes batch number)
          // So we can safely process it here
          const keysInfo =
            progressItem.batch_keys_count > 0
              ? ` (${progressItem.batch_keys_count} keys)`
              : "";
          let tokenInfo = "";
          if (
            progressItem.token_usage &&
            (progressItem.token_usage.prompt_tokens > 0 ||
              progressItem.token_usage.completion_tokens > 0)
          ) {
            const promptTokens = progressItem.token_usage.prompt_tokens || 0;
            const completionTokens =
              progressItem.token_usage.completion_tokens || 0;
            tokenInfo = ` (Tokens: Input: ${LPM.translate.formatNumber(
              promptTokens
            )}, Output: ${LPM.translate.formatNumber(completionTokens)})`;
          }
          LPM.translate.addBriefing(
            "info",
            `Batch ${progressItem.current_batch}/${progressItem.total_batches} done${keysInfo}${tokenInfo}`
          );

          if (
            progressItem.current_batch > (state.translate.currentBatch || 0)
          ) {
            state.translate.currentBatch = progressItem.current_batch;
          }

          // Simple progress calculation: based on languages and batches
          let overallPercent = 0;
          if (
            progressItem.total_languages > 0 &&
            progressItem.total_batches > 0
          ) {
            // Progress = (completed languages + current language batch progress) / total languages
            const completedLanguageProgress =
              progressItem.completed_languages / progressItem.total_languages;
            const currentLanguageBatchProgress =
              progressItem.current_batch / progressItem.total_batches;
            const currentLanguageProgress =
              currentLanguageBatchProgress / progressItem.total_languages;
            overallPercent = Math.round(
              (completedLanguageProgress + currentLanguageProgress) * 100
            );
            overallPercent = Math.max(0, Math.min(100, overallPercent));
          } else if (progressItem.total_languages > 0) {
            // Fallback: only use completed languages if batch info is not available
            overallPercent = Math.round(
              (progressItem.completed_languages /
                progressItem.total_languages) *
                100
            );
            overallPercent = Math.max(0, Math.min(100, overallPercent));
          }

          if (progressItem.total_batches > 0) {
            const isValidating = state.translate.mode === "validate_only";
            const actionText = isValidating
              ? t("manage.translate.messages.validating")
              : t("manage.translate.messages.translating");
            const statusText = `${actionText} ${langName} (${langCode}) - Batch ${progressItem.current_batch}/${progressItem.total_batches}...`;
            LPM.translate.updateProgress(overallPercent, statusText);
            state.translate.lastProgressPercent = overallPercent;
          }
        }
        break;

      case "completed":
        // completed phase allows updates (after retry), so always process the latest
        console.log(
          "[processProgressItem] completed phase - progressItem.failed_items:",
          progressItem.failed_items
        );
        LPM.translate.handleLanguageCompletion({
          langCode: langCode,
          langName: langName,
          successCount: progressItem.success_count || 0,
          failureCount: progressItem.failure_count || 0,
          tokenUsage: progressItem.token_usage,
          failedItems: progressItem.failed_items || [],
        });
        state.translate.currentPhase = "completed";
        break;
    }
  };

  LPM.translate.loadProjectSettings = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    // Don't check state.project here - we'll fetch it directly from API
    // This allows this function to be called even if state.project is not yet loaded

    try {
      const data = await utils.fetchJson(`${API_BASE}`);
      const project = data.project || {};

      // Update state.project if it's not set yet
      if (!state.project && project.id) {
        state.project = project;
      }

      // Load saved project settings
      const savedProvider = project.translation_ai_provider;
      const savedChunkSize = project.translation_chunk_size_words;

      // Save the full provider:model value for later use in loadSettings
      if (savedProvider) {
        state.translate.savedProviderSelection = savedProvider; // Can be "provider" or "provider:model"
        // Extract just the provider ID for backward compatibility
        if (savedProvider.includes(":")) {
          state.translate.selectedProvider = savedProvider.split(":")[0];
        } else {
          state.translate.selectedProvider = savedProvider;
        }
      }

      // Load chunk size from project settings
      const chunkSizeInput = document.getElementById(
        "translate-chunk-size-words"
      );
      if (chunkSizeInput) {
        // Only set value if we have a saved value, otherwise keep the current value (user might have modified it)
        if (savedChunkSize !== null && savedChunkSize !== undefined) {
          chunkSizeInput.value = savedChunkSize;
        }
      }
    } catch (error) {
      console.error("Failed to load project settings:", error);
    }
  };

  LPM.translate.loadSettings = async function () {
    const { state, selectors, utils } = LPM;
    try {
      const data = await utils.fetchJson("/api/settings");
      const settings = data.config || data;

      // Get built-in providers from API meta, fallback to defaults
      const builtInProviders = data.meta?.builtin_providers || [
        { id: "openai", name: "OpenAI" },
        { id: "deepseek", name: "DeepSeek" },
        { id: "gemini", name: "Gemini" },
      ];

      // Build provider/model list grouped by provider
      const providerGroups = [];

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

      state.translate.availableProviders = providerGroups;
      // Use project's saved provider if available, otherwise use global default
      if (!state.translate.selectedProvider) {
        state.translate.selectedProvider = settings.ai_provider;
      }

      if (selectors.translateProvider) {
        selectors.translateProvider.innerHTML = "";

        if (providerGroups.length === 0) {
          if (selectors.translateProviderError) {
            selectors.translateProviderError.classList.remove("d-none");
          }
          return;
        }

        // Get saved provider selection (can be "provider" or "provider:model")
        const savedSelection = state.translate.savedProviderSelection || null;
        let selectedValue = null;

        // Create optgroups for each provider
        providerGroups.forEach((group) => {
          const optgroup = document.createElement("optgroup");
          optgroup.label = group.name;

          group.models.forEach((model, index) => {
            const option = document.createElement("option");
            const optionValue = `${group.id}:${model}`;
            option.value = optionValue;
            option.textContent = model;

            // Select based on saved selection
            if (savedSelection) {
              // If saved selection matches this option exactly, select it
              if (savedSelection === optionValue) {
                option.selected = true;
                selectedValue = optionValue;
              }
              // If saved selection is just provider ID and this is the first model, select it
              else if (
                savedSelection === group.id &&
                index === 0 &&
                !selectedValue
              ) {
                option.selected = true;
                selectedValue = optionValue;
              }
            } else {
              // Fallback: select first model of default provider
              if (
                group.id === state.translate.selectedProvider &&
                index === 0 &&
                !selectedValue
              ) {
                option.selected = true;
                selectedValue = optionValue;
              }
            }

            optgroup.appendChild(option);
          });

          selectors.translateProvider.appendChild(optgroup);
        });
      }
    } catch (error) {
      console.error("Failed to load translate settings:", error);
    }
  };

  LPM.translate.loadLanguages = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    try {
      const data = await utils.fetchJson(`${API_BASE}/stats`);
      const sourceLanguage = state.project?.source_language || "en";

      const languages = (data.languages || []).filter(
        (lang) => lang.language_code !== sourceLanguage
      );

      // Sort languages: first by missing count (has missing first), then by language name (a-z)
      languages.sort((a, b) => {
        const aMissing = a.missing_count || 0;
        const bMissing = b.missing_count || 0;
        const aHasMissing = aMissing > 0;
        const bHasMissing = bMissing > 0;

        // First priority: has missing comes first
        if (aHasMissing !== bHasMissing) {
          return bHasMissing ? 1 : -1;
        }

        // Second priority: sort by language name (a-z)
        const aName = (a.language_name || "").toLowerCase();
        const bName = (b.language_name || "").toLowerCase();
        return aName.localeCompare(bName);
      });

      const urlParams = new URLSearchParams(window.location.search);
      const preselectLang = urlParams.get("preselect");

      if (selectors.translateLanguagesTbody) {
        selectors.translateLanguagesTbody.innerHTML = "";

        languages.forEach((lang) => {
          const tr = document.createElement("tr");
          const completionRate = lang.completion_rate || 0;
          const isComplete = completionRate >= 100;
          const missing = lang.missing_count || 0;

          let shouldCheck = false;
          if (preselectLang) {
            shouldCheck = lang.language_code === preselectLang;
          } else {
            shouldCheck = !isComplete;
          }

          const checkboxId = `translate-lang-${lang.language_code}`;
          tr.innerHTML = `
            <td>
              <input class="form-check-input translate-lang-checkbox" type="checkbox"
                     id="${checkboxId}" value="${
            lang.language_code
          }" data-missing="${missing}" ${shouldCheck ? "checked" : ""}>
            </td>
            <td>
              <label for="${checkboxId}" class="form-check-label mb-0">
                <span class="fw-semibold">${lang.language_name}</span>
                <small class="text-muted ms-1">(${lang.language_code})</small>
              </label>
            </td>
            <td>
              <div class="progress" style="width: 100px; height: 6px;">
                <div class="progress-bar ${
                  isComplete ? "bg-success" : "bg-primary"
                }"
                     style="width: ${completionRate}%"></div>
              </div>
              <small class="text-muted">${completionRate.toFixed(0)}%</small>
            </td>
            <td>
              ${
                missing > 0
                  ? `<span class="badge bg-warning text-dark">${missing}</span>`
                  : '<span class="badge bg-success">Complete</span>'
              }
            </td>
          `;
          selectors.translateLanguagesTbody.appendChild(tr);
        });

        LPM.translate.updateStartButton();
      }
    } catch (error) {
      console.error("Failed to load translate languages:", error);
    }
  };

  LPM.translate.updateStartButton = function () {
    const { state, selectors } = LPM;
    const selectedCount = document.querySelectorAll(
      ".translate-lang-checkbox:checked"
    ).length;
    const hasProvider = state.translate.availableProviders.length > 0;
    const strategy = document.querySelector(
      'input[name="translate-strategy"]:checked'
    )?.value;
    const isFullMode = strategy === "full";
    const confirmChecked =
      selectors.translateConfirmUnderstand?.checked || false;

    const canStart =
      selectedCount > 0 && hasProvider && (!isFullMode || confirmChecked);

    if (selectors.translateStartBtn) {
      selectors.translateStartBtn.disabled = !canStart;
      selectors.translateStartBtn.innerHTML = `<i class="bi bi-play-fill me-1"></i> ${t(
        "manage.translate.messages.start_translation_with_languages",
        { count: selectedCount }
      )}`;
    }
  };

  LPM.translate.startFromTab = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    const selectedLanguages = [];
    document
      .querySelectorAll(".translate-lang-checkbox:checked")
      .forEach((cb) => {
        selectedLanguages.push(cb.value);
      });

    if (selectedLanguages.length === 0) return;

    // Auto-sync source file before starting translation
    utils.showToast(
      t("manage.translate.messages.syncing_before_translation"),
      "info"
    );
    const syncResult = await LPM.autoSyncSourceFile({
      silent: true,
      showProgress: false,
    });

    if (!syncResult.success) {
      utils.showToast(
        `Sync failed: ${syncResult.error}. Translation aborted.`,
        "danger"
      );
      return;
    }

    // Show sync result
    if (syncResult.summary) {
      const summary = syncResult.summary;
      const hasChanges =
        summary.new_keys > 0 ||
        summary.updated_keys > 0 ||
        summary.deleted_keys > 0;
      if (hasChanges) {
        const changeDetails = [];
        if (summary.new_keys > 0) changeDetails.push(`${summary.new_keys} new`);
        if (summary.updated_keys > 0)
          changeDetails.push(`${summary.updated_keys} updated`);
        if (summary.deleted_keys > 0)
          changeDetails.push(`${summary.deleted_keys} deleted`);
        utils.showToast(
          `Source file synced: ${changeDetails.join(", ")} keys.`,
          "success"
        );
      } else {
        utils.showToast(
          t("manage.translate.messages.source_synced_no_changes"),
          "success"
        );
      }
    }

    state.translate.selectedLanguages = selectedLanguages;

    const strategy =
      document.querySelector('input[name="translate-strategy"]:checked')
        ?.value || "missing_only";
    const includeLocked = selectors.translateIncludeLocked?.checked || false;
    const generateFiles = selectors.translateGenerateFiles?.checked || true;
    const providerSelection = selectors.translateProvider?.value || "";

    // Parse provider:model format
    let provider = providerSelection;
    let model = null;
    if (providerSelection.includes(":")) {
      const parts = providerSelection.split(":");
      provider = parts[0];
      model = parts.slice(1).join(":"); // Handle model names with colons
    }

    state.translate.mode = strategy;

    // Update selected provider in state (use parsed provider, not the full selection string)
    state.translate.selectedProvider = provider;

    if (selectors.translateConfigSection) {
      selectors.translateConfigSection.classList.add("d-none");
    }
    if (selectors.translateProgressSection) {
      selectors.translateProgressSection.classList.remove("d-none");
    }
    if (selectors.translateCompletionActions) {
      selectors.translateCompletionActions.classList.add("d-none");
    }
    if (selectors.translateCancelBtn) {
      selectors.translateCancelBtn.disabled = false;
      selectors.translateCancelBtn.classList.remove("d-none");
    }

    const isValidating = strategy === "validate_only";
    const actionText = isValidating ? "validation" : "translation";
    LPM.translate.updateProgress(0, `Starting ${actionText}...`);
    if (selectors.translateSummaryTranslated)
      selectors.translateSummaryTranslated.textContent = "0";
    if (selectors.translateSummarySucceeded)
      selectors.translateSummarySucceeded.textContent = "0";
    if (selectors.translateSummaryFailed)
      selectors.translateSummaryFailed.textContent = "0";
    if (selectors.translateSummaryTokenInput)
      selectors.translateSummaryTokenInput.textContent = "0";
    if (selectors.translateSummaryTokenOutput)
      selectors.translateSummaryTokenOutput.textContent = "0";
    if (selectors.translateBriefingLog)
      selectors.translateBriefingLog.innerHTML = "";

    try {
      // Get AI provider and chunk size
      // Use the parsed provider from above (already extracted from providerSelection)
      const chunkSizeInput = document.getElementById(
        "translate-chunk-size-words"
      );
      const chunkSizeWords = chunkSizeInput
        ? parseInt(chunkSizeInput.value) || 300
        : 300;

      const requestBody = {
        languages: selectedLanguages,
        mode: strategy,
        include_locked: includeLocked,
        generate_files: generateFiles,
        ai_provider: providerSelection, // Save full "provider:model" format to database (backend will parse it)
        chunk_size_words: chunkSizeWords,
      };
      // Note: Backend will parse providerSelection and extract model if needed
      // We still include model explicitly for backward compatibility
      if (model) {
        requestBody.model = model;
      }

      const response = await utils.fetchJson(`${API_BASE}/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });

      state.translate.jobId = response.job_id;
      state.translate.isRunning = true;
      state.translate.currentLanguageIndex = -1;
      state.translate.currentBatch = 0;
      state.translate.currentPhase = "";
      state.translate.lastLanguage = "";
      state.translate.lastTotalBatches = 0;
      state.translate.lastCompletedLanguage = "";
      state.translate.lastCompletedStats = {}; // Reset completion stats for new job
      state.translate.processedProgressItems = new Set(); // Reset processed progress items for new job
      state.translate.totalTokenUsage = {
        prompt_tokens: 0,
        completion_tokens: 0,
      }; // Reset token usage
      state.translate.lastProgressPercent = 0; // Reset progress percentage

      const jobTypeText = isValidating
        ? t("manage.translate.messages.validation")
        : t("manage.translate.messages.translation");
      LPM.translate.addBriefing(
        "info",
        `${jobTypeText} job started (${selectedLanguages.length} languages, mode: ${strategy})`
      );

      LPM.translate.pollProgress();
    } catch (error) {
      console.error("Failed to start translation:", error);
      LPM.translate.addBriefing("error", `Error: ${error.message}`);
      LPM.translate.showCompletion(false);
    }
  };

  LPM.translate.pollProgress = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    if (!state.translate.isRunning) return;

    try {
      const data = await utils.fetchJson(
        `${API_BASE}/progress?job_id=${state.translate.jobId}`
      );

      // Initialize processedProgressItems Set if not exists
      if (!state.translate.processedProgressItems) {
        state.translate.processedProgressItems = new Set();
      }

      // 1. Process history items with deduplication
      if (data.progress_history && Array.isArray(data.progress_history)) {
        if (data.progress_history.length > 0) {
          console.debug(
            `[Translation Progress] Processing ${data.progress_history.length} history entries`
          );
        }

        for (const item of data.progress_history) {
          const itemId = LPM.translate.getProgressItemId(item);
          if (!itemId) continue;

          const isUpdatable = LPM.translate.isUpdatablePhase(item.phase);
          const alreadyProcessed =
            state.translate.processedProgressItems.has(itemId);

          // For updatable phases (completed), check if stats changed
          let shouldProcess = !alreadyProcessed;
          if (isUpdatable && alreadyProcessed) {
            // Check if this is a different completion (different stats)
            // This allows updates after retry, but prevents duplicate processing
            const langCode = item.current_language;
            const lastStats = state.translate.lastCompletedStats?.[langCode];
            if (lastStats) {
              const isUpdate =
                lastStats.successCount !== (item.success_count || 0) ||
                lastStats.failureCount !== (item.failure_count || 0);
              if (isUpdate) {
                // Stats changed, this is a real update (e.g., after retry)
                // Remove old entries for this language
                for (const key of state.translate.processedProgressItems) {
                  if (key.startsWith(`${langCode}_completed`)) {
                    state.translate.processedProgressItems.delete(key);
                  }
                }
                shouldProcess = true;
              }
            } else {
              // No previous stats, but already processed - skip to avoid duplicate
              shouldProcess = false;
            }
          }

          if (shouldProcess) {
            // Process the item
            LPM.translate.processProgressItem(item);

            // Mark as processed
            state.translate.processedProgressItems.add(itemId);
          }
        }
      }

      // 2. Process current progress if running
      if (
        data.state === "running" &&
        data.progress &&
        data.progress.phase &&
        data.progress.current_language
      ) {
        const itemId = LPM.translate.getProgressItemId(data.progress);
        if (itemId) {
          const isUpdatable = LPM.translate.isUpdatablePhase(
            data.progress.phase
          );

          // Check if already in history (by comparing ID)
          const inHistory = data.progress_history?.some(
            (h) => LPM.translate.getProgressItemId(h) === itemId
          );

          const alreadyProcessed =
            state.translate.processedProgressItems.has(itemId);

          // For updatable phases (completed), check if stats changed
          let shouldProcess = !inHistory && !alreadyProcessed;
          if (isUpdatable && !inHistory && alreadyProcessed) {
            // Check if this is a different completion (different stats)
            const langCode = data.progress.current_language;
            const lastStats = state.translate.lastCompletedStats?.[langCode];
            if (lastStats) {
              const isUpdate =
                lastStats.successCount !== (data.progress.success_count || 0) ||
                lastStats.failureCount !== (data.progress.failure_count || 0);
              if (isUpdate) {
                // Stats changed, this is a real update (e.g., after retry)
                // Remove old entries for this language
                for (const key of state.translate.processedProgressItems) {
                  if (key.startsWith(`${langCode}_completed`)) {
                    state.translate.processedProgressItems.delete(key);
                  }
                }
                shouldProcess = true;
              }
            } else {
              // No previous stats, but already processed - skip to avoid duplicate
              shouldProcess = false;
            }
          }

          if (shouldProcess) {
            // Process the item
            LPM.translate.processProgressItem(data.progress);

            // Mark as processed
            state.translate.processedProgressItems.add(itemId);
          }
        }
      }

      // 1. Check terminal states (after processing history)
      if (
        data.state === "completed" ||
        data.state === "failed" ||
        data.state === "cancelled"
      ) {
        state.translate.isRunning = false;

        if (data.result) {
          const result = data.result;
          const isValidating = state.translate.mode === "validate_only";
          const actionName = isValidating
            ? t("manage.translate.messages.validation")
            : t("manage.translate.messages.translation");
          // Always show "completed" regardless of success or failure
          // The actual success/failure status is shown in the briefing message
          LPM.translate.updateProgress(100, `${actionName} completed!`);

          if (isValidating) {
            if (selectors.translateSummaryFailedLabel)
              selectors.translateSummaryFailedLabel.textContent = t(
                "manage.translate.messages.total_cleared"
              );
            if (selectors.translateSummaryTranslated)
              selectors.translateSummaryTranslated.textContent =
                result.total_validated || 0;
            if (selectors.translateSummarySucceeded)
              selectors.translateSummarySucceeded.textContent =
                (result.total_validated || 0) - (result.total_cleared || 0);
            if (selectors.translateSummaryFailed)
              selectors.translateSummaryFailed.textContent =
                result.total_cleared || 0;

            const validationMessage =
              result.message ||
              `Validation ${data.state}. Validated: ${
                result.total_validated || 0
              }, Valid: ${
                (result.total_validated || 0) - (result.total_cleared || 0)
              }, Cleared: ${result.total_cleared || 0}`;

            const messageType =
              result.total_validated === 0 ||
              result.skipped_languages?.length > 0
                ? "warning"
                : "success";

            LPM.translate.addBriefing(messageType, validationMessage);
          } else {
            if (selectors.translateSummaryFailedLabel)
              selectors.translateSummaryFailedLabel.textContent = t(
                "manage.translate.progress.total_failed"
              );
            if (selectors.translateSummaryTranslated)
              selectors.translateSummaryTranslated.textContent =
                result.total_translated || 0;
            if (selectors.translateSummarySucceeded)
              selectors.translateSummarySucceeded.textContent =
                (result.total_translated || 0) - (result.total_failed || 0);
            if (selectors.translateSummaryFailed)
              selectors.translateSummaryFailed.textContent =
                result.total_failed || 0;

            // Use result.token_usage if available (from backend), otherwise use accumulated totalTokenUsage
            const finalTokenUsage =
              result.token_usage || state.translate.totalTokenUsage;
            if (
              finalTokenUsage &&
              (finalTokenUsage.prompt_tokens > 0 ||
                finalTokenUsage.completion_tokens > 0)
            ) {
              if (selectors.translateSummaryTokenInput)
                selectors.translateSummaryTokenInput.textContent =
                  LPM.translate.formatNumber(
                    finalTokenUsage.prompt_tokens || 0
                  );
              if (selectors.translateSummaryTokenOutput)
                selectors.translateSummaryTokenOutput.textContent =
                  LPM.translate.formatNumber(
                    finalTokenUsage.completion_tokens || 0
                  );
            }

            // Build message with token usage if available
            // When all languages are completed (data.state === "completed" or "failed"), show "All translation completed"
            // "failed" state also means all languages are processed, just with some failures
            // Otherwise show "Translation cancelled"
            const isAllCompleted =
              data.state === "completed" || data.state === "failed";
            const succeededCount =
              (result.total_translated || 0) - (result.total_failed || 0);
            const failedCount = result.total_failed || 0;

            let finalMessage;
            if (isAllCompleted) {
              // Format similar to per-language completion message
              finalMessage = `All translation completed. Translated: ${
                result.total_translated || 0
              }, Succeeded: ${succeededCount}, Failed: ${failedCount}`;
            } else {
              finalMessage = `Translation ${data.state}. Total: ${
                result.total_translated || 0
              }, Succeeded: ${succeededCount}, Failed: ${failedCount}`;
            }

            // Add token usage to message if available
            if (
              finalTokenUsage &&
              (finalTokenUsage.prompt_tokens > 0 ||
                finalTokenUsage.completion_tokens > 0)
            ) {
              if (isAllCompleted) {
                // Format similar to per-language completion message
                finalMessage += `, Token In/Out: ${LPM.translate.formatNumber(
                  finalTokenUsage.prompt_tokens || 0
                )} / ${LPM.translate.formatNumber(
                  finalTokenUsage.completion_tokens || 0
                )}`;
              } else {
                finalMessage += `, Token Input: ${LPM.translate.formatNumber(
                  finalTokenUsage.prompt_tokens || 0
                )}, Token Output: ${LPM.translate.formatNumber(
                  finalTokenUsage.completion_tokens || 0
                )}`;
              }
            }

            // Check if there are failed items to show link
            console.log(
              "[pollProgress] result.failed_items:",
              result.failed_items
            );
            const failedItems = result.failed_items || [];
            const hasFailedItems =
              Array.isArray(failedItems) && failedItems.length > 0;

            // Use success type when all languages are completed, regardless of failed count
            const messageType = isAllCompleted
              ? "success"
              : result.success
              ? "success"
              : "warning";

            // When all languages are completed, first add a completion notice
            if (isAllCompleted) {
              LPM.translate.addBriefing(
                "success",
                t("manage.translate.messages.translation_completed")
              );
            }

            // Then add the translation summary
            LPM.translate.addBriefing(
              messageType,
              finalMessage,
              hasFailedItems ? failedItems : [],
              isAllCompleted, // Pass flag to indicate this is the final summary
              null // No language filter for final summary (show all languages)
            );

            // Note: Per-language completion messages are already handled by processProgressItem
            // when processing progress_history, so we don't need to add them again here
          }
        }

        LPM.translate.showCompletion(data.state === "completed");
        await Promise.all([LPM.loadStats(), LPM.loadLanguages()]);
        return; // Stop polling - job is finished
      }

      // 2. Handle running state - only handle special phases not covered by processProgressItem
      if (data.state === "running") {
        const progress = data.progress || {};
        const langName =
          progress.current_language_name || progress.current_language || "";
        const langCode = progress.current_language || "";

        // Handle retrying phase - don't update progress bar
        if (
          progress.phase === "retrying" &&
          state.translate.currentPhase !== "retrying"
        ) {
          LPM.translate.addBriefing(
            "warning",
            `Retrying ${progress.retry_keys_count} failed keys...`
          );
          state.translate.currentPhase = "retrying";
          // Skip progress update entirely for retrying phase
        } else if (progress.phase === "saving") {
          // Don't update progress during saving - keep previous value
          let percent = state.translate.lastProgressPercent || 0;
          if (
            state.translate.lastProgressPercent === undefined ||
            isNaN(state.translate.lastProgressPercent) ||
            state.translate.lastProgressPercent < 0 ||
            state.translate.lastProgressPercent > 100
          ) {
            // Fallback: calculate based on languages if lastProgressPercent is invalid
            if (progress.total_languages > 0) {
              percent = Math.round(
                (progress.completed_languages / progress.total_languages) * 100
              );
              percent = Math.max(0, Math.min(100, percent));
            }
          }
          LPM.translate.updateProgress(
            percent,
            `Saving translations for ${langName}...`
          );
        }

        // Update summary stats
        if (
          selectors.translateSummaryTranslated &&
          progress.current_item !== undefined
        ) {
          selectors.translateSummaryTranslated.textContent =
            progress.current_item || 0;
        }
        if (
          selectors.translateSummarySucceeded &&
          progress.success_count !== undefined
        ) {
          selectors.translateSummarySucceeded.textContent =
            progress.success_count || 0;
        }
        if (
          selectors.translateSummaryFailed &&
          progress.failure_count !== undefined
        ) {
          selectors.translateSummaryFailed.textContent =
            progress.failure_count || 0;
        }

        // ALWAYS reschedule when still running (critical fix)
        state.translate.pollInterval = setTimeout(
          LPM.translate.pollProgress,
          2000
        );
      }
    } catch (error) {
      console.error("Failed to poll progress:", error);

      // Check if job not found or expired (404 error)
      const isJobNotFound =
        error.message &&
        (error.message.includes("Job not found") ||
          error.message.includes("expired") ||
          error.message.includes("404"));

      if (isJobNotFound) {
        // Job expired or not found - try to get latest job first
        try {
          const latestData = await utils.fetchJson(
            `${API_BASE}/progress?latest=true`
          );

          if (latestData.job_id && latestData.state === "running") {
            // Found a new running job - update jobId and continue polling
            console.log(
              `[Translation] Job expired, switching to latest job: ${latestData.job_id}`
            );
            state.translate.jobId = latestData.job_id;
            state.translate.pollInterval = setTimeout(
              LPM.translate.pollProgress,
              2000
            );
            return;
          }
        } catch (latestError) {
          console.warn("Failed to fetch latest job:", latestError);
        }

        // No active job found - stop polling
        console.log(
          "[Translation] Job expired and no active job found, stopping polling"
        );
        state.translate.isRunning = false;
        LPM.translate.addBriefing(
          "warning",
          t("manage.translate.messages.job_expired")
        );
        return;
      }

      // For other errors, reschedule polling (unless stopped)
      if (state.translate.isRunning) {
        state.translate.pollInterval = setTimeout(
          LPM.translate.pollProgress,
          5000
        );
      }
    }
  };

  LPM.translate.cancelJob = async function () {
    const { state, selectors, utils, API_BASE } = LPM;
    if (!state.translate.jobId) return;

    if (selectors.translateCancelBtn) {
      selectors.translateCancelBtn.disabled = true;
    }

    try {
      await utils.fetchJson(`${API_BASE}/translate/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: state.translate.jobId }),
      });

      state.translate.isRunning = false;
      if (state.translate.pollInterval) {
        clearTimeout(state.translate.pollInterval);
      }

      const actionName =
        state.translate.mode === "validate_only"
          ? t("manage.translate.messages.validation")
          : t("manage.translate.messages.translation");
      LPM.translate.addBriefing(
        "warning",
        t("manage.translate.messages.translation_cancelled")
      );
      LPM.translate.showCompletion(false);
    } catch (error) {
      console.error("Failed to cancel:", error);
    }
  };

  LPM.translate.updateProgress = function (percent, status) {
    const { selectors } = LPM;
    if (selectors.translateProgressPercent) {
      selectors.translateProgressPercent.textContent = `${percent}%`;
    }
    if (selectors.translateProgressStatus) {
      selectors.translateProgressStatus.textContent = status;
    }
    if (selectors.translateProgressBar) {
      selectors.translateProgressBar.style.width = `${percent}%`;
      selectors.translateProgressBar.setAttribute("aria-valuenow", percent);
    }
  };

  LPM.translate.addBriefing = function (
    type,
    message,
    failedItems,
    isFinalSummary,
    languageCode
  ) {
    const { selectors, state } = LPM;
    if (!selectors.translateBriefingLog) return;

    const entry = document.createElement("div");
    entry.className = `briefing-entry ${type}`;

    const timestamp = new Date().toLocaleTimeString();
    const icon =
      type === "success"
        ? "check-circle-fill"
        : type === "error"
        ? "x-circle-fill"
        : type === "warning"
        ? "exclamation-triangle-fill"
        : "info-circle-fill";

    entry.innerHTML = `
      <span class="text-muted">[${timestamp}]</span>
      <i class="bi bi-${icon} ms-1 ${
      type === "success"
        ? "text-success"
        : type === "error"
        ? "text-danger"
        : type === "warning"
        ? "text-warning"
        : "text-info"
    }"></i>
      ${message}
    `;

    selectors.translateBriefingLog.appendChild(entry);
    selectors.translateBriefingLog.scrollTop =
      selectors.translateBriefingLog.scrollHeight;

    // Add separate briefing entry for "View failed translation keys" link if there are failed items
    console.log(
      "[addBriefing] failedItems:",
      failedItems,
      "isFinalSummary:",
      isFinalSummary
    );
    if (failedItems && Array.isArray(failedItems) && failedItems.length > 0) {
      // Store failed items in memory (merge with existing ones)
      // Use key_path + language_code as unique identifier to avoid duplicates
      const existingKeys = new Set(
        (state.translate.failedItems || []).map(
          (item) => `${item.key_path}:${item.language_code}`
        )
      );

      const newItems = failedItems.filter(
        (item) => !existingKeys.has(`${item.key_path}:${item.language_code}`)
      );

      state.translate.failedItems = [
        ...(state.translate.failedItems || []),
        ...newItems,
      ];

      const linkEntry = document.createElement("div");
      linkEntry.className = `briefing-entry ${type}`;
      const linkTimestamp = new Date().toLocaleTimeString();
      const linkId = `view-failed-keys-${Date.now()}-${Math.random()
        .toString(36)
        .substr(2, 9)}`;

      const linkIcon =
        type === "success"
          ? "check-circle-fill"
          : type === "error"
          ? "x-circle-fill"
          : type === "warning"
          ? "exclamation-triangle-fill"
          : "info-circle-fill";
      const linkIconClass =
        type === "success"
          ? "text-success"
          : type === "error"
          ? "text-danger"
          : type === "warning"
          ? "text-warning"
          : "text-info";

      const linkText = isFinalSummary
        ? t("manage.translate.messages.view_all_failed_keys", {})
        : t("manage.translate.messages.view_failed_keys", {});

      linkEntry.innerHTML = `
        <span class="text-muted">[${linkTimestamp}]</span>
        <i class="bi bi-${linkIcon} ms-1 ${linkIconClass}"></i>
        <a href="#" class="ms-2" id="${linkId}" style="text-decoration: underline;">${linkText}</a>
      `;

      selectors.translateBriefingLog.appendChild(linkEntry);
      selectors.translateBriefingLog.scrollTop =
        selectors.translateBriefingLog.scrollHeight;

      // Click handler - show modal with language filter if not final summary
      setTimeout(() => {
        const link = document.getElementById(linkId);
        if (link) {
          link.addEventListener("click", (e) => {
            e.preventDefault();
            // If not final summary and has language code, filter by language
            const filterLang = isFinalSummary ? null : languageCode;
            LPM.translate.showFailedKeysModal(filterLang);
          });
        }
      }, 0);
    }
  };

  /**
   * Show the failed translation keys modal.
   * Reads from state.translate.failedItems (memory), no database fetch needed.
   * @param {string|null} filterLanguageCode - If provided, only show items for this language
   */
  LPM.translate.showFailedKeysModal = function (filterLanguageCode = null) {
    const { utils, state } = LPM;

    // Store the current filter in state for later use (e.g., after setAsCorrect)
    state.translate.currentFailedKeysFilter = filterLanguageCode;

    const tbody = document.getElementById("failed-translation-keys-tbody");
    if (!tbody) {
      console.error("Failed translation keys table body not found");
      return;
    }

    // Read from memory and optionally filter by language
    let itemsToShow = state.translate.failedItems || [];
    if (filterLanguageCode) {
      itemsToShow = itemsToShow.filter(
        (item) => item.language_code === filterLanguageCode
      );
    }

    // If no items, show empty state
    if (itemsToShow.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="text-center text-muted py-4">
            All failed translation keys have been processed.
          </td>
        </tr>
      `;

      const modal = new bootstrap.Modal(
        document.getElementById("failedTranslationKeysModal")
      );
      modal.show();
      return;
    }

    // Clear existing content
    tbody.innerHTML = "";

    // Truncate long text for display
    const truncateText = (text, maxLength = 100) => {
      if (!text) return "";
      if (text.length <= maxLength) return text;
      return text.substring(0, maxLength) + "...";
    };

    // Create index mapping: filtered index -> original index
    const allItems = state.translate.failedItems || [];
    const indexMap = [];
    itemsToShow.forEach((item) => {
      const originalIndex = allItems.indexOf(item);
      indexMap.push(originalIndex);
    });

    // Populate table with filtered items
    itemsToShow.forEach((item, filteredIndex) => {
      const originalIndex = indexMap[filteredIndex];
      const row = document.createElement("tr");
      row.dataset.index = originalIndex; // Keep original index for operations
      row.style.cursor = "pointer";

      const language = item.language_name || item.language_code || "";
      const keyPath = item.key_path || "";
      const sourceText = item.source_text || "";
      const error = item.error || t("errors.unknown_error");

      row.innerHTML = `
        <td>
          <input
            type="checkbox"
            class="form-check-input failed-key-checkbox"
            data-index="${originalIndex}" />
        </td>
        <td><code>${utils.escapeHtml(keyPath)}</code></td>
        <td title="${utils.escapeHtml(sourceText)}">${utils.escapeHtml(
        truncateText(sourceText, 150)
      )}</td>
        <td>${utils.escapeHtml(language)}</td>
        <td><small class="text-danger">${utils.escapeHtml(error)}</small></td>
      `;
      tbody.appendChild(row);
    });

    // Bind row click handler
    tbody.querySelectorAll("tr").forEach((row) => {
      row.addEventListener("click", (e) => {
        // Don't toggle if clicking on checkbox directly
        if (e.target.type === "checkbox") {
          return;
        }
        const checkbox = row.querySelector(".failed-key-checkbox");
        if (checkbox) {
          checkbox.checked = !checkbox.checked;
          LPM.translate.updateFailedKeysSelectAll();
        }
      });
    });

    // Bind select all checkbox
    const selectAllCheckbox = document.getElementById("failed-keys-select-all");
    if (selectAllCheckbox) {
      selectAllCheckbox.checked = false;
      selectAllCheckbox.addEventListener("change", (e) => {
        const checkboxes = tbody.querySelectorAll(".failed-key-checkbox");
        checkboxes.forEach((cb) => {
          cb.checked = e.target.checked;
        });
        LPM.translate.updateFailedKeysSelectAll();
      });
    }

    // Initialize button state (disabled by default)
    const addBtn = document.getElementById("failed-keys-add-to-protected-btn");
    if (addBtn) {
      addBtn.disabled = true;
    }

    // Bind individual checkbox change
    tbody.addEventListener("change", (e) => {
      if (e.target.classList.contains("failed-key-checkbox")) {
        LPM.translate.updateFailedKeysSelectAll();
      }
    });

    // Bind add to protected terms button
    const addToProtectedBtn = document.getElementById(
      "failed-keys-add-to-protected-btn"
    );
    if (addToProtectedBtn) {
      // Remove existing listeners
      const newBtn = addToProtectedBtn.cloneNode(true);
      addToProtectedBtn.parentNode.replaceChild(newBtn, addToProtectedBtn);

      newBtn.addEventListener("click", () => {
        LPM.translate.addFailedKeysToProtected();
      });
    }

    // Bind category select change
    const categorySelect = document.getElementById(
      "failed-keys-protection-category"
    );
    if (categorySelect) {
      categorySelect.addEventListener("change", () => {
        LPM.translate.updateFailedKeysSelectAll();
      });
    }

    // Bind set as correct button
    const setAsCorrectBtn = document.getElementById(
      "failed-keys-set-as-correct-btn"
    );
    if (setAsCorrectBtn) {
      // Remove existing listeners
      const newBtn = setAsCorrectBtn.cloneNode(true);
      setAsCorrectBtn.parentNode.replaceChild(newBtn, setAsCorrectBtn);

      newBtn.addEventListener("click", () => {
        LPM.translate.setFailedKeysAsCorrect();
      });
    }

    // Show modal
    const modal = new bootstrap.Modal(
      document.getElementById("failedTranslationKeysModal")
    );
    modal.show();

    // Update button states after modal is shown
    LPM.translate.updateFailedKeysSelectAll();
  };

  LPM.translate.updateFailedKeysSelectAll = function () {
    const tbody = document.getElementById("failed-translation-keys-tbody");
    if (!tbody) return;

    const checkboxes = tbody.querySelectorAll(".failed-key-checkbox");
    const checked = tbody.querySelectorAll(".failed-key-checkbox:checked");
    const selectAllCheckbox = document.getElementById("failed-keys-select-all");
    const addBtn = document.getElementById("failed-keys-add-to-protected-btn");
    const categorySelect = document.getElementById(
      "failed-keys-protection-category"
    );

    if (selectAllCheckbox && checkboxes.length > 0) {
      selectAllCheckbox.checked = checked.length === checkboxes.length;
      selectAllCheckbox.indeterminate =
        checked.length > 0 && checked.length < checkboxes.length;
    }

    // Update button disabled state based on selection and category
    const setAsCorrectBtn = document.getElementById(
      "failed-keys-set-as-correct-btn"
    );
    const hasSelection = checked.length > 0;
    const hasValidCategory =
      categorySelect && categorySelect.value && categorySelect.value !== "";

    if (addBtn) {
      addBtn.disabled = !hasSelection || !hasValidCategory;
    }
    if (setAsCorrectBtn) {
      setAsCorrectBtn.disabled = !hasSelection;
    }
  };

  LPM.translate.addFailedKeysToProtected = async function () {
    const { utils, state, API_BASE } = LPM;
    const tbody = document.getElementById("failed-translation-keys-tbody");
    if (!tbody || !state.translate.failedItems) {
      return;
    }

    // Get selected checkboxes
    const selectedCheckboxes = tbody.querySelectorAll(
      ".failed-key-checkbox:checked"
    );
    if (selectedCheckboxes.length === 0) {
      utils.showToast("Please select at least one key.", "warning");
      return;
    }

    // Get selected category
    const categorySelect = document.getElementById(
      "failed-keys-protection-category"
    );
    const category = categorySelect ? categorySelect.value : "brand";
    if (!category) {
      utils.showToast(
        t("manage.translate.messages.please_select_protection_category"),
        "warning"
      );
      return;
    }

    // Get project ID
    const projectId = state.project?.id;
    if (!projectId) {
      utils.showToast("Project not found.", "danger");
      return;
    }

    // Collect selected items
    // Use the same variable as displayed in the UI (item.source_text)
    const selectedItems = [];
    selectedCheckboxes.forEach((checkbox) => {
      const index = parseInt(checkbox.dataset.index, 10);
      const item = state.translate.failedItems[index];
      if (item && item.key_path && item.source_text) {
        // Use the exact same variable as the UI display (line 2079: const sourceText = item.source_text || "")
        selectedItems.push({
          term: item.source_text, // Same as UI display: item.source_text
          category: category,
          is_regex: false,
          key_scopes: [item.key_path], // Scope to this specific key
        });
      }
    });

    if (selectedItems.length === 0) {
      utils.showToast("No valid keys selected.", "warning");
      return;
    }

    // Prepare terms to add (no need to fetch existing terms - API will handle duplicates)
    const termsToAdd = selectedItems.map((item) => ({
      term: item.term,
      category: item.category,
      is_regex: item.is_regex || false,
      key_scopes: item.key_scopes || [],
    }));

    // Disable button during request
    const addBtn = document.getElementById("failed-keys-add-to-protected-btn");
    const originalText = addBtn ? addBtn.textContent : "";
    if (addBtn) {
      addBtn.disabled = true;
      addBtn.textContent = t("manage.translate.messages.adding");
    }

    try {
      // Add protected terms (API will skip duplicates)

      const response = await utils.fetchJson(
        `${API_BASE}/protected-terms/add`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ terms: termsToAdd }),
        }
      );

      console.log("[Add to Protected] Response received:", response);

      // Check if response indicates success
      if (!response || (response.error && !response.terms)) {
        const errorMsg =
          response?.error ||
          t("manage.translate.messages.failed_to_add_protected_terms");
        console.error("[Add to Protected] Error:", errorMsg, response);
        throw new Error(errorMsg);
      }

      // Get counts from response
      const addedCount = response.added_count || 0;
      const mergedCount = response.merged_count || 0;

      console.log(
        `[Add to Protected] Added: ${addedCount}, Merged: ${mergedCount}`
      );

      // Remove successfully added items from state and UI
      const selectedIndices = new Set(
        Array.from(selectedCheckboxes).map((cb) =>
          parseInt(cb.dataset.index, 10)
        )
      );

      // Prepare items to remove for memory update (before removing from state)
      const itemsToRemove = Array.from(selectedCheckboxes)
        .map((checkbox) => {
          const index = parseInt(checkbox.dataset.index, 10);
          return state.translate.failedItems[index];
        })
        .filter(Boolean);

      // Remove from state (keep items that were not selected)
      state.translate.failedItems = state.translate.failedItems.filter(
        (item, idx) => !selectedIndices.has(idx)
      );

      // Re-render table with remaining items, respecting the current language filter
      const filterLanguageCode = state.translate.currentFailedKeysFilter;
      let itemsToShow = state.translate.failedItems;
      if (filterLanguageCode) {
        itemsToShow = itemsToShow.filter(
          (item) => item.language_code === filterLanguageCode
        );
      }

      tbody.innerHTML = "";
      if (itemsToShow.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="5" class="text-center text-muted py-4">
              All failed keys have been added to protected terms.
            </td>
          </tr>
        `;
      } else {
        // Truncate long text for display
        const truncateText = (text, maxLength = 100) => {
          if (!text) return "";
          if (text.length <= maxLength) return text;
          return text.substring(0, maxLength) + "...";
        };

        // Create index mapping: filtered index -> original index
        const allItems = state.translate.failedItems;
        const indexMap = [];
        itemsToShow.forEach((item) => {
          const originalIndex = allItems.indexOf(item);
          indexMap.push(originalIndex);
        });

        itemsToShow.forEach((item, filteredIndex) => {
          const originalIndex = indexMap[filteredIndex];
          const row = document.createElement("tr");
          row.dataset.index = originalIndex; // Keep original index for operations
          row.style.cursor = "pointer";

          const language =
            item.language_name || item.language_code || "Unknown";
          const keyPath = item.key_path || "Unknown";
          const sourceText = item.source_text || "";
          const error = item.error || "Unknown error";

          row.innerHTML = `
            <td>
              <input
                type="checkbox"
                class="form-check-input failed-key-checkbox"
                data-index="${originalIndex}" />
            </td>
            <td><code>${utils.escapeHtml(keyPath)}</code></td>
            <td title="${utils.escapeHtml(sourceText)}">${utils.escapeHtml(
            truncateText(sourceText, 150)
          )}</td>
            <td>${utils.escapeHtml(language)}</td>
            <td><small class="text-danger">${utils.escapeHtml(
              error
            )}</small></td>
          `;
          tbody.appendChild(row);
        });

        // Re-bind row click handlers
        tbody.querySelectorAll("tr").forEach((row) => {
          row.addEventListener("click", (e) => {
            // Don't toggle if clicking on checkbox directly
            if (e.target.type === "checkbox") {
              return;
            }
            const checkbox = row.querySelector(".failed-key-checkbox");
            if (checkbox) {
              checkbox.checked = !checkbox.checked;
              LPM.translate.updateFailedKeysSelectAll();
            }
          });
        });

        // Re-bind checkbox change handlers
        tbody.addEventListener("change", (e) => {
          if (e.target.classList.contains("failed-key-checkbox")) {
            LPM.translate.updateFailedKeysSelectAll();
          }
        });

        // Update select all checkbox state
        LPM.translate.updateFailedKeysSelectAll();
      }

      // Update select all checkbox
      LPM.translate.updateFailedKeysSelectAll();

      // Show success message using counts from response
      let message = `Successfully added ${addedCount} key(s) to protected terms.`;
      if (mergedCount > 0) {
        message += ` ${mergedCount} key(s) were merged with existing protected terms.`;
      }
      utils.showToast(message, "success");

      // Refresh Protected Terms tab data
      if (LPM.protected && typeof LPM.protected.load === "function") {
        LPM.protected.load().catch(() => {});
      }
    } catch (error) {
      console.error("Failed to add keys to protected terms:", error);
      utils.showToast(
        `Failed to add keys to protected terms: ${error.message}`,
        "danger"
      );
    } finally {
      if (addBtn) {
        addBtn.disabled = false;
        addBtn.textContent = originalText;
      }
    }
  };

  LPM.translate.setFailedKeysAsCorrect = async function () {
    const { utils, state, API_BASE } = LPM;
    const tbody = document.getElementById("failed-translation-keys-tbody");
    if (!tbody || !state.translate.failedItems) {
      return;
    }

    // Get selected checkboxes
    const selectedCheckboxes = tbody.querySelectorAll(
      ".failed-key-checkbox:checked"
    );
    if (selectedCheckboxes.length === 0) {
      utils.showToast("Please select at least one key.", "warning");
      return;
    }

    // Get project ID
    const projectId = state.project?.id;
    if (!projectId) {
      utils.showToast("Project not found.", "danger");
      return;
    }

    // Collect selected items
    const selectedItems = [];
    selectedCheckboxes.forEach((checkbox) => {
      const index = parseInt(checkbox.dataset.index, 10);
      const item = state.translate.failedItems[index];
      if (item && item.key_path && item.language_code && item.source_text) {
        selectedItems.push(item);
      }
    });

    if (selectedItems.length === 0) {
      utils.showToast("No valid keys selected.", "warning");
      return;
    }

    // Group by key_path (API requires one request per key_path)
    const itemsByKeyPath = {};
    selectedItems.forEach((item) => {
      const keyPath = item.key_path;
      if (!itemsByKeyPath[keyPath]) {
        itemsByKeyPath[keyPath] = [];
      }
      itemsByKeyPath[keyPath].push(item);
    });

    // Disable button during request
    const setAsCorrectBtn = document.getElementById(
      "failed-keys-set-as-correct-btn"
    );
    const originalText = setAsCorrectBtn ? setAsCorrectBtn.textContent : "";
    if (setAsCorrectBtn) {
      setAsCorrectBtn.disabled = true;
      setAsCorrectBtn.textContent = t("manage.translate.messages.saving");
    }

    try {
      // Save translations for each key_path
      let successCount = 0;
      let errorCount = 0;

      for (const [keyPath, items] of Object.entries(itemsByKeyPath)) {
        try {
          const entries = items.map((item) => ({
            language_code: item.language_code,
            translated_text: item.source_text, // Use source_text as translated_text (same in both languages)
            status: "locked", // Mark as locked to indicate manually confirmed correct translation
          }));

          await utils.fetchJson(`${API_BASE}/translations`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              key_path: keyPath,
              entries: entries,
            }),
          });

          successCount += items.length;
        } catch (error) {
          console.error(
            `Failed to save translation for key ${keyPath}:`,
            error
          );
          errorCount += items.length;
        }
      }

      if (errorCount > 0) {
        utils.showToast(
          `Saved ${successCount} translation(s), but ${errorCount} failed.`,
          "warning"
        );
      } else {
        utils.showToast(
          `Successfully saved ${successCount} translation(s) as correct.`,
          "success"
        );
      }

      // Remove successfully saved items from state and UI
      const selectedIndices = new Set(
        Array.from(selectedCheckboxes).map((cb) =>
          parseInt(cb.dataset.index, 10)
        )
      );

      // Only remove items that were successfully saved
      // For simplicity, we'll remove all selected items if at least one was saved
      if (successCount > 0) {
        // Remove from state (keep items that were not selected)
        state.translate.failedItems = state.translate.failedItems.filter(
          (item, idx) => !selectedIndices.has(idx)
        );

        // Re-render table with remaining items, respecting the current language filter
        const filterLanguageCode = state.translate.currentFailedKeysFilter;
        let itemsToShow = state.translate.failedItems;
        if (filterLanguageCode) {
          itemsToShow = itemsToShow.filter(
            (item) => item.language_code === filterLanguageCode
          );
        }

        tbody.innerHTML = "";
        if (itemsToShow.length === 0) {
          tbody.innerHTML = `
            <tr>
              <td colspan="5" class="text-center text-muted py-4">
                All failed keys have been processed.
              </td>
            </tr>
          `;
        } else {
          // Truncate long text for display
          const truncateText = (text, maxLength = 100) => {
            if (!text) return "";
            if (text.length <= maxLength) return text;
            return text.substring(0, maxLength) + "...";
          };

          // Create index mapping: filtered index -> original index
          const allItems = state.translate.failedItems;
          const indexMap = [];
          itemsToShow.forEach((item) => {
            const originalIndex = allItems.indexOf(item);
            indexMap.push(originalIndex);
          });

          itemsToShow.forEach((item, filteredIndex) => {
            const originalIndex = indexMap[filteredIndex];
            const row = document.createElement("tr");
            row.dataset.index = originalIndex; // Keep original index for operations
            row.style.cursor = "pointer";

            const language =
              item.language_name || item.language_code || "Unknown";
            const keyPath = item.key_path || "Unknown";
            const sourceText = item.source_text || "";
            const error = item.error || "Unknown error";

            row.innerHTML = `
              <td>
                <input
                  type="checkbox"
                  class="form-check-input failed-key-checkbox"
                  data-index="${originalIndex}" />
              </td>
              <td><code>${utils.escapeHtml(keyPath)}</code></td>
              <td title="${utils.escapeHtml(sourceText)}">${utils.escapeHtml(
              truncateText(sourceText, 150)
            )}</td>
              <td>${utils.escapeHtml(language)}</td>
              <td><small class="text-danger">${utils.escapeHtml(
                error
              )}</small></td>
            `;
            tbody.appendChild(row);
          });

          // Re-bind row click handlers
          tbody.querySelectorAll("tr").forEach((row) => {
            row.addEventListener("click", (e) => {
              // Don't toggle if clicking on checkbox directly
              if (e.target.type === "checkbox") {
                return;
              }
              const checkbox = row.querySelector(".failed-key-checkbox");
              if (checkbox) {
                checkbox.checked = !checkbox.checked;
                LPM.translate.updateFailedKeysSelectAll();
              }
            });
          });

          // Re-bind checkbox change handlers
          tbody.addEventListener("change", (e) => {
            if (e.target.classList.contains("failed-key-checkbox")) {
              LPM.translate.updateFailedKeysSelectAll();
            }
          });

          // Update select all checkbox state
          LPM.translate.updateFailedKeysSelectAll();
        }

        // Refresh Manual Translation tab data by resetting the loaded flag and reloading
        if (LPM.state && LPM.state.manual && LPM.manual) {
          LPM.state.manual.lockedLoaded = false;
          LPM.manual
            .ensureLockedItemsLoaded?.()
            .then(() => LPM.manual.renderWorklist?.())
            .catch(() => {});
        }
      }
    } catch (error) {
      console.error("Failed to set keys as correct:", error);
      utils.showToast(
        `Failed to save translations: ${error.message}`,
        "danger"
      );
    } finally {
      if (setAsCorrectBtn) {
        setAsCorrectBtn.disabled = false;
        setAsCorrectBtn.textContent = originalText;
      }
    }
  };

  LPM.translate.showCompletion = function (success) {
    const { selectors } = LPM;
    if (selectors.translateCancelBtn) {
      selectors.translateCancelBtn.classList.add("d-none");
    }
    if (selectors.translateCompletionActions) {
      selectors.translateCompletionActions.classList.remove("d-none");
    }

    if (selectors.translateProgressBar) {
      selectors.translateProgressBar.classList.remove(
        "progress-bar-animated",
        "progress-bar-striped"
      );
      selectors.translateProgressBar.classList.add(
        success ? "bg-success" : "bg-warning"
      );
    }
  };

  LPM.translate.resetTab = function () {
    const { state, selectors } = LPM;
    if (selectors.translateConfigSection) {
      selectors.translateConfigSection.classList.remove("d-none");
    }
    if (selectors.translateProgressSection) {
      selectors.translateProgressSection.classList.add("d-none");
    }
    if (selectors.translateBriefingLog) {
      selectors.translateBriefingLog.innerHTML = "";
    }
    if (selectors.translateProgressBar) {
      selectors.translateProgressBar.classList.remove(
        "bg-success",
        "bg-warning"
      );
      selectors.translateProgressBar.classList.add(
        "progress-bar-animated",
        "progress-bar-striped"
      );
      selectors.translateProgressBar.style.width = "0%";
    }
    state.translate.currentLanguageIndex = -1;
    state.translate.failedItems = []; // Clear failed items on reset
  };

  LPM.translate.checkAndResumeActiveJob = async function () {
    const { state, selectors, API_BASE } = LPM;
    try {
      const response = await fetch(`${API_BASE}/progress?latest=1`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });

      if (!response.ok) {
        console.debug("Error checking active job:", response.status);
        return;
      }

      const data = await response.json();

      if (data.job_id && data.state === "running") {
        state.translate.jobId = data.job_id;
        state.translate.isRunning = true;
        state.translate.currentLanguageIndex = -1;
        state.translate.currentBatch = 0;
        state.translate.currentPhase = "";
        state.translate.lastLanguage = "";
        state.translate.lastTotalBatches = 0;
        state.translate.lastCompletedLanguage = "";
        state.translate.lastCompletedStats = {}; // Reset completion stats
        state.translate.totalTokenUsage = {
          prompt_tokens: 0,
          completion_tokens: 0,
        }; // Reset token usage
        state.translate.lastProgressPercent = 0; // Reset progress percentage

        // Rebuild processedProgressItems Set and lastCompletedStats based on current progress_history
        // This prevents duplicate processing when resuming after page refresh
        state.translate.processedProgressItems = new Set();
        if (data.progress_history && Array.isArray(data.progress_history)) {
          for (const item of data.progress_history) {
            const itemId = LPM.translate.getProgressItemId(item);
            if (itemId) {
              state.translate.processedProgressItems.add(itemId);

              // Rebuild lastCompletedStats for completed phases
              if (item.phase === "completed" && item.current_language) {
                const langCode = item.current_language;
                if (!state.translate.lastCompletedStats[langCode]) {
                  state.translate.lastCompletedStats[langCode] = {
                    successCount: item.success_count || 0,
                    failureCount: item.failure_count || 0,
                  };
                } else {
                  // Update if this is a newer completion (after retry)
                  state.translate.lastCompletedStats[langCode] = {
                    successCount: item.success_count || 0,
                    failureCount: item.failure_count || 0,
                  };
                }
                state.translate.lastCompletedLanguage = langCode;
              }
            }
          }
        }

        LPM.switchToTab("#translate-pane");
        // Hide config section and show progress section
        if (selectors.translateConfigSection) {
          selectors.translateConfigSection.classList.add("d-none");
        }
        if (selectors.translateProgressSection) {
          selectors.translateProgressSection.classList.remove("d-none");
        }
        if (selectors.translateCancelBtn) {
          selectors.translateCancelBtn.disabled = false;
          selectors.translateCancelBtn.classList.remove("d-none");
        }
        if (selectors.translateCompletionActions) {
          selectors.translateCompletionActions.classList.add("d-none");
        }

        LPM.translate.addBriefing(
          "info",
          t("manage.translate.messages.resuming_job", {})
        );

        LPM.translate.pollProgress();
      }
    } catch (error) {
      console.debug("No active job found or error:", error);
    }
  };

  // ============================================
  // EVENT BINDING
  // ============================================

  LPM.translate.bindEvents = function () {
    const { selectors } = LPM;

    // Translate Tab events
    if (selectors.translateSelectAll) {
      selectors.translateSelectAll.addEventListener("change", (e) => {
        document.querySelectorAll(".translate-lang-checkbox").forEach((cb) => {
          cb.checked = e.target.checked;
        });
        LPM.translate.updateStartButton();
      });
    }

    if (selectors.translateLanguagesTbody) {
      selectors.translateLanguagesTbody.addEventListener("change", (e) => {
        if (e.target.classList.contains("translate-lang-checkbox")) {
          LPM.translate.updateStartButton();
        }
      });
    }

    document
      .querySelectorAll('input[name="translate-strategy"]')
      .forEach((radio) => {
        radio.addEventListener("change", (e) => {
          const isFullMode = e.target.value === "full";
          if (selectors.translateFullWarning) {
            selectors.translateFullWarning.classList.toggle(
              "d-none",
              !isFullMode
            );
          }
          if (!isFullMode) {
            if (selectors.translateIncludeLocked)
              selectors.translateIncludeLocked.checked = false;
            if (selectors.translateConfirmUnderstand)
              selectors.translateConfirmUnderstand.checked = false;
          }
          LPM.translate.updateStartButton();
        });
      });

    if (selectors.translateConfirmUnderstand) {
      selectors.translateConfirmUnderstand.addEventListener(
        "change",
        LPM.translate.updateStartButton
      );
    }

    if (selectors.translateStartBtn) {
      selectors.translateStartBtn.addEventListener("click", () => {
        void LPM.translate.startFromTab();
      });
    }

    if (selectors.translateCancelBtn) {
      selectors.translateCancelBtn.addEventListener("click", () => {
        void LPM.translate.cancelJob();
      });
    }

    if (selectors.translateBackBtn) {
      selectors.translateBackBtn.addEventListener("click", () => {
        if (selectors.translateCompletionActions) {
          selectors.translateCompletionActions.classList.add("d-none");
        }
        LPM.translate.resetTab();
        void LPM.translate.loadLanguages();
      });
    }

    if (selectors.translateAgainBtn) {
      selectors.translateAgainBtn.addEventListener("click", () => {
        if (selectors.translateCompletionActions) {
          selectors.translateCompletionActions.classList.add("d-none");
        }
        void LPM.translate.startFromTab();
      });
    }
  };

  // ============================================
  // INITIALIZATION
  // ============================================

  LPM.translate.init = async function () {
    LPM.translate.bindEvents();
    await LPM.translate.loadProjectSettings();
    await LPM.translate.loadSettings();
    await LPM.translate.loadLanguages();
  };
})(window.LPM);
