/**
 * Front-end logic for system settings management.
 */

// Global function to toggle password visibility
function togglePasswordVisibility(inputId, buttonElement) {
  const input = document.getElementById(inputId);
  const icon = buttonElement.querySelector("i");

  if (input.type === "password") {
    input.type = "text";
    icon.className = "bi bi-eye-slash-fill"; // Hide icon (filled)
  } else {
    input.type = "password";
    icon.className = "bi bi-eye-fill"; // Show icon (filled)
  }
}

(function () {
  const API_BASE = "/api/settings";

  const selectors = {
    settingsButton: document.getElementById("settings-btn"),
    settingsModalElement: document.getElementById("settingsModal"),
    settingsForm: document.getElementById("settings-form"),
    submitButton: document.getElementById("submit-settings-btn"),
    aiProviderSelect: document.getElementById("ai-provider"),
    // General settings
    logModeOff: document.getElementById("log-mode-off"),
    logModeDebug: document.getElementById("log-mode-debug"),
    // Provider containers
    builtInProvidersContainer: document.getElementById(
      "built-in-providers-container"
    ),
    customProvidersContainer: document.getElementById(
      "custom-providers-container"
    ),
    customProvidersGroup: document.getElementById("custom-providers-group"),
    // Templates
    providerConfigTemplate: document.getElementById("provider-config-template"),
    // Clear logs button
    clearLogsBtn: document.getElementById("clear-logs-btn"),
  };

  // Built-in provider definitions - loaded from API
  // Will be populated from state.meta.builtinProviders after loadSettings()

  // Helper function to get selector for a provider input
  function getProviderSelector(providerId, field) {
    return document.getElementById(`${providerId}-${field}`);
  }

  // Helper function to get all model inputs for a provider
  function getProviderModelInputs(providerId) {
    return [
      getProviderSelector(providerId, "model-1"),
      getProviderSelector(providerId, "model-2"),
      getProviderSelector(providerId, "model-3"),
      getProviderSelector(providerId, "model-4"),
      getProviderSelector(providerId, "model-5"),
    ].filter((input) => input !== null);
  }

  const state = {
    isSubmitting: false,
    settingsModal: null,
    customProviders: {}, // Map of provider name -> config
    addingNewProvider: false,
    meta: {
      builtinProviders: [], // [{id: "openai", name: "OpenAI"}, ...]
      providerDefaults: { max_retries: 3, timeout: 120 },
      providerNamePattern: "^[a-zA-Z0-9_-]+$",
    },
  };

  function showAlert(message, variant = "info") {
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
    const toastDelay = variant === "danger" ? 8000 : 5000;
    const toastInstance = new bootstrap.Toast(toast, { delay: toastDelay });
    toastInstance.show();

    toast.addEventListener("hidden.bs.toast", () => {
      toast.remove();
    });
  }

  function setSubmitting(isSubmitting) {
    state.isSubmitting = isSubmitting;
    if (!selectors.submitButton) return;
    selectors.submitButton.disabled = isSubmitting;
    const spinner = selectors.submitButton.querySelector(".spinner-border");
    const label = selectors.submitButton.querySelector(
      ".submit-settings-label"
    );
    if (spinner) {
      spinner.classList.toggle("d-none", !isSubmitting);
    }
    if (label) {
      label.textContent = isSubmitting
        ? t("settings.buttons.saving")
        : t("settings.buttons.save");
    }
  }

  /**
   * Create provider config using unified template
   * @param {Object} options - Configuration options
   * @param {string} options.providerPrefix - Provider ID/prefix (e.g., "openai", "my-custom-ai")
   * @param {string} options.displayName - Display name (e.g., "OpenAI", "My Custom AI")
   * @param {string} options.scenario - Scenario: "builtin", "custom", or "new"
   * @param {Object} options.config - Optional existing config data
   * @returns {HTMLElement|null} Created config element
   */
  function createProviderConfig({
    providerPrefix,
    displayName,
    scenario,
    config,
  }) {
    if (!selectors.providerConfigTemplate) return null;

    const template = selectors.providerConfigTemplate.content.cloneNode(true);
    const configDiv = template.querySelector(".provider-config");

    // Determine replacements based on scenario
    let headerStyle, titleStyle, titleSuffix, deleteButton, providerNameField;
    let apiUrlRequired = "";
    let apiUrlPlaceholder = "https://api.example.com/v1/chat/completions";
    let apiUrlDescription = "OpenAI-compatible services";
    let apiKeyHintText = displayName;

    if (scenario === "new") {
      // New provider: show provider name field, simple header
      headerStyle = "";
      titleStyle = "border-bottom pb-2 mb-3";
      titleSuffix = "";
      deleteButton = "";
      providerNameField = `
        <div class="col-12">
          <label for="${providerPrefix}-name" class="form-label">${t(
        "settings.api.new_provider.name_label"
      )}</label>
          <input
            type="text"
            class="form-control"
            id="${providerPrefix}-name"
            name="${providerPrefix}_name"
            placeholder="my-custom-ai" />
          <div class="invalid-feedback" id="${providerPrefix}-name-error" style="display: none">
            ${t("settings.api.new_provider.name_invalid")}
          </div>
          <div class="form-text">
            ${t("settings.api.new_provider.name_help")}
          </div>
        </div>`;
      apiUrlRequired = " *";
      apiUrlPlaceholder = "https://api.example.com/v1/chat/completions";
      apiUrlDescription = "OpenAI-compatible services";
      apiKeyHintText = "";
    } else if (scenario === "custom") {
      // Custom provider: show delete button, flex header
      headerStyle = "d-flex justify-content-between align-items-center mb-3";
      titleStyle = "border-bottom pb-2 mb-0 flex-grow-1";
      titleSuffix = "";
      deleteButton = `
        <div class="ms-3">
          <button
            class="btn btn-sm btn-danger"
            type="button"
            data-provider="${providerPrefix}"
            onclick="deleteCustomProvider('${providerPrefix}')">
            ${t("settings.api.delete_btn")}
          </button>
        </div>`;
      providerNameField = "";
      apiUrlRequired = " *";
      apiUrlPlaceholder = "https://api.example.com/v1/chat/completions";
      apiUrlDescription = "OpenAI-compatible services";
      apiKeyHintText = "";
    } else {
      // Built-in provider: simple header, no delete button
      headerStyle = "";
      titleStyle = "border-bottom pb-2 mb-3";
      titleSuffix = "Configuration";
      deleteButton = "";
      providerNameField = "";
      apiUrlRequired = "";
      apiUrlPlaceholder = "";
      apiUrlDescription = `${displayName}-compatible services`;
      apiKeyHintText = displayName;
    }

    // Replace all placeholders
    let html = configDiv.outerHTML
      .replace(/__PROVIDER_PREFIX__/g, providerPrefix)
      .replace(/__PROVIDER_DISPLAY_NAME__/g, displayName)
      .replace(/__HEADER_STYLE__/g, headerStyle)
      .replace(/__TITLE_STYLE__/g, titleStyle)
      .replace(/__TITLE_SUFFIX__/g, titleSuffix)
      .replace(/__DELETE_BUTTON__/g, deleteButton)
      .replace(/__PROVIDER_NAME_FIELD__/g, providerNameField)
      .replace(/__API_URL_REQUIRED__/g, apiUrlRequired)
      .replace(/__API_URL_PLACEHOLDER__/g, apiUrlPlaceholder)
      .replace(/__API_URL_DESCRIPTION__/g, apiUrlDescription)
      .replace(/__API_KEY_HINT_TEXT__/g, apiKeyHintText);

    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = html;
    const newConfig = tempDiv.firstElementChild;

    // Load values if config provided
    if (config) {
      const apiUrlInput = newConfig.querySelector(`#${providerPrefix}-api-url`);
      const apiKeyInput = newConfig.querySelector(`#${providerPrefix}-api-key`);
      const modelInputs = [
        newConfig.querySelector(`#${providerPrefix}-model-1`),
        newConfig.querySelector(`#${providerPrefix}-model-2`),
        newConfig.querySelector(`#${providerPrefix}-model-3`),
        newConfig.querySelector(`#${providerPrefix}-model-4`),
        newConfig.querySelector(`#${providerPrefix}-model-5`),
      ];

      if (apiUrlInput) apiUrlInput.value = config.api_url || "";
      if (apiKeyInput) apiKeyInput.value = config.api_key || "";

      const models = Array.isArray(config.models) ? config.models : [];
      modelInputs.forEach((input, index) => {
        if (input && models[index]) {
          input.value = models[index];
        }
      });
    }

    return newConfig;
  }

  function createBuiltInProviderConfig(providerId, displayName) {
    return createProviderConfig({
      providerPrefix: providerId,
      displayName: displayName,
      scenario: "builtin",
    });
  }

  function initializeBuiltInProviders() {
    if (!selectors.builtInProvidersContainer) return;

    // Clear container
    selectors.builtInProvidersContainer.innerHTML = "";

    // Create config sections for each built-in provider (from state.meta)
    state.meta.builtinProviders.forEach((provider) => {
      const configSection = createBuiltInProviderConfig(
        provider.id,
        provider.name
      );
      if (configSection) {
        selectors.builtInProvidersContainer.appendChild(configSection);
      }
    });
  }

  function populateProviderDropdown() {
    if (!selectors.aiProviderSelect) return;

    // Get the optgroup and add_new option
    const customGroup = selectors.customProvidersGroup;
    const addNewOption = selectors.aiProviderSelect.querySelector(
      'option[value="__add_new__"]'
    );

    // Remove existing built-in options (before the optgroup)
    const existingOptions = selectors.aiProviderSelect.querySelectorAll(
      "option:not([value='__add_new__'])"
    );
    existingOptions.forEach((opt) => {
      if (!opt.closest("optgroup")) {
        opt.remove();
      }
    });

    // Add built-in providers at the beginning
    state.meta.builtinProviders.forEach((provider) => {
      const option = document.createElement("option");
      option.value = provider.id;
      option.textContent = provider.name;
      // Insert before the optgroup
      if (customGroup) {
        selectors.aiProviderSelect.insertBefore(option, customGroup);
      } else if (addNewOption) {
        selectors.aiProviderSelect.insertBefore(option, addNewOption);
      } else {
        selectors.aiProviderSelect.appendChild(option);
      }
    });
  }

  function highlightActiveProvider(provider) {
    // Hide all provider configs
    const allConfigs = document.querySelectorAll(".provider-config");
    allConfigs.forEach((config) => {
      config.style.display = "none";
    });

    // Show only the active provider config
    const activeConfig = document.getElementById(`${provider}-config`);
    if (activeConfig) {
      activeConfig.style.display = "block";
    }
  }

  function createCustomProviderConfig(providerName, providerConfig) {
    const displayName =
      providerName.charAt(0).toUpperCase() +
      providerName.slice(1).replace(/-/g, " ");

    return createProviderConfig({
      providerPrefix: providerName,
      displayName: displayName,
      scenario: "custom",
      config: providerConfig,
    });
  }

  function addCustomProviderToDropdown(providerName, displayName) {
    if (!selectors.customProvidersGroup) return;

    const option = document.createElement("option");
    option.value = providerName;
    option.textContent = displayName;
    selectors.customProvidersGroup.appendChild(option);
  }

  function removeCustomProviderFromDropdown(providerName) {
    if (!selectors.customProvidersGroup) return;
    const option = selectors.customProvidersGroup.querySelector(
      `option[value="${providerName}"]`
    );
    if (option) option.remove();
  }

  function loadCustomProviders(config) {
    // Clear existing custom providers
    if (selectors.customProvidersContainer) {
      selectors.customProvidersContainer.innerHTML = "";
    }
    if (selectors.customProvidersGroup) {
      selectors.customProvidersGroup.innerHTML = "";
    }
    state.customProviders = {};

    // Get built-in provider IDs from state.meta
    const builtInProviderIds = state.meta.builtinProviders.map((p) => p.id);
    Object.keys(config).forEach((key) => {
      if (
        !builtInProviderIds.includes(key) &&
        key !== "ai_provider" &&
        key !== "log_mode" &&
        key !== "translation" &&
        key !== "prompts" &&
        typeof config[key] === "object" &&
        config[key] !== null &&
        config[key].api_key !== undefined
      ) {
        // This is a custom provider
        const providerName = key;
        const providerConfig = config[key];
        state.customProviders[providerName] = providerConfig;

        // Create config section
        const configSection = createCustomProviderConfig(
          providerName,
          providerConfig
        );
        if (configSection && selectors.customProvidersContainer) {
          selectors.customProvidersContainer.appendChild(configSection);
        }

        // Add to dropdown
        const displayName =
          providerName.charAt(0).toUpperCase() +
          providerName.slice(1).replace(/-/g, " ");
        addCustomProviderToDropdown(providerName, displayName);
      }
    });
  }

  function clearNewProviderInputs() {
    const inputs = [
      "new-provider-name",
      "new-provider-api-url",
      "new-provider-api-key",
      "new-provider-model-1",
      "new-provider-model-2",
      "new-provider-model-3",
      "new-provider-model-4",
      "new-provider-model-5",
    ];

    inputs.forEach((id) => {
      const input = document.getElementById(id);
      if (input) {
        input.value = "";
        input.classList.remove("is-invalid");
      }
    });

    // Clear error message
    const errorDiv = document.getElementById("new-provider-name-error");
    if (errorDiv) {
      errorDiv.style.display = "none";
    }
  }

  function handleAddNewProvider() {
    // Hide all existing provider configs
    const allConfigs = document.querySelectorAll(".provider-config");
    allConfigs.forEach((config) => {
      config.style.display = "none";
    });

    // Create or show new provider config section
    let newProviderConfig = document.getElementById("new-provider-config");
    if (!newProviderConfig) {
      // Create new provider config using unified template
      newProviderConfig = createProviderConfig({
        providerPrefix: "new-provider",
        displayName: t("settings.api.new_provider.title"),
        scenario: "new",
      });
      if (newProviderConfig) {
        newProviderConfig.id = "new-provider-config";
        newProviderConfig.setAttribute("data-provider", "__new__");
        // Insert before custom providers container
        if (selectors.customProvidersContainer) {
          selectors.customProvidersContainer.parentNode.insertBefore(
            newProviderConfig,
            selectors.customProvidersContainer
          );
        } else if (selectors.builtInProvidersContainer) {
          selectors.builtInProvidersContainer.parentNode.insertBefore(
            newProviderConfig,
            selectors.builtInProvidersContainer.nextSibling
          );
        }
      }
    }

    if (newProviderConfig) {
      newProviderConfig.style.display = "block";
      // Clear all inputs
      clearNewProviderInputs();
      // Focus on provider name input
      const nameInput = document.getElementById("new-provider-name");
      if (nameInput) {
        nameInput.focus();
      }
    }
  }

  function handleProviderChange(value) {
    if (value === "__add_new__") {
      handleAddNewProvider();
    } else {
      // Hide new provider config if switching away
      const newProviderConfig = document.getElementById("new-provider-config");
      if (newProviderConfig) {
        newProviderConfig.style.display = "none";
      }
      highlightActiveProvider(value);
    }
  }

  function validateNewProvider() {
    const providerName = document
      .getElementById("new-provider-name")
      ?.value?.trim();
    const apiUrl = document
      .getElementById("new-provider-api-url")
      ?.value?.trim();
    const apiKey = document
      .getElementById("new-provider-api-key")
      ?.value?.trim();

    // Validate provider name
    if (!providerName) {
      showAlert(t("settings.messages.provider_name_required"), "warning");
      const nameInput = document.getElementById("new-provider-name");
      if (nameInput) {
        nameInput.focus();
        nameInput.classList.add("is-invalid");
      }
      return false;
    }

    // Use pattern from API meta
    const namePattern = new RegExp(state.meta.providerNamePattern);
    if (!namePattern.test(providerName)) {
      showAlert(t("settings.messages.provider_name_invalid"), "warning");
      const nameInput = document.getElementById("new-provider-name");
      const errorDiv = document.getElementById("new-provider-name-error");
      if (nameInput) {
        nameInput.focus();
        nameInput.classList.add("is-invalid");
      }
      if (errorDiv) {
        errorDiv.style.display = "block";
      }
      return false;
    }

    // Check if provider already exists
    const builtInProviderIds = state.meta.builtinProviders.map((p) => p.id);
    if (
      state.customProviders[providerName] ||
      builtInProviderIds.includes(providerName)
    ) {
      showAlert(t("settings.messages.provider_exists"), "warning");
      const nameInput = document.getElementById("new-provider-name");
      if (nameInput) {
        nameInput.focus();
        nameInput.classList.add("is-invalid");
      }
      return false;
    }

    // Validate API URL
    if (!apiUrl) {
      showAlert(t("settings.messages.api_url_required_custom"), "warning");
      const urlInput = document.getElementById("new-provider-api-url");
      if (urlInput) {
        urlInput.focus();
        urlInput.classList.add("is-invalid");
      }
      return false;
    }

    // Validate API Key
    if (!apiKey) {
      showAlert(t("settings.messages.api_key_required_custom"), "warning");
      const keyInput = document.getElementById("new-provider-api-key");
      if (keyInput) {
        keyInput.focus();
        keyInput.classList.add("is-invalid");
      }
      return false;
    }

    // Models are optional - no validation needed

    return true;
  }

  // Global function to reset provider to default values (called from template)
  window.resetProviderToDefault = function (providerId) {
    // Find if this is a built-in provider
    const builtInProvider = state.meta.builtinProviders.find(
      (p) => p.id === providerId
    );

    if (builtInProvider) {
      // For built-in providers, fetch defaults from API and reset
      fetch(API_BASE)
        .then((response) => response.json())
        .then((data) => {
          const defaultConfig = data.config?.[providerId] || {};
          const apiUrlInput = getProviderSelector(providerId, "api-url");
          const apiKeyInput = getProviderSelector(providerId, "api-key");
          const modelInputs = getProviderModelInputs(providerId);

          // Reset API URL to default
          if (apiUrlInput) {
            apiUrlInput.value = defaultConfig.api_url || "";
          }

          // Clear API Key (user needs to re-enter)
          if (apiKeyInput) {
            apiKeyInput.value = "";
          }

          // Reset models to defaults
          const defaultModels = defaultConfig.models || [];
          modelInputs.forEach((input, index) => {
            if (input) {
              input.value = defaultModels[index] || "";
            }
          });

          showAlert(
            t("settings.messages.config_reset", {
              provider: builtInProvider.name,
            }),
            "success"
          );
        })
        .catch((error) => {
          console.error("Failed to fetch default config:", error);
          showAlert(t("settings.messages.reset_failed"), "danger");
        });
    } else {
      // For custom providers, just clear the fields
      const apiUrlInput = document.getElementById(`${providerId}-api-url`);
      const apiKeyInput = document.getElementById(`${providerId}-api-key`);
      const modelInputs = [
        document.getElementById(`${providerId}-model-1`),
        document.getElementById(`${providerId}-model-2`),
        document.getElementById(`${providerId}-model-3`),
        document.getElementById(`${providerId}-model-4`),
        document.getElementById(`${providerId}-model-5`),
      ];

      if (apiUrlInput) apiUrlInput.value = "";
      if (apiKeyInput) apiKeyInput.value = "";
      modelInputs.forEach((input) => {
        if (input) input.value = "";
      });

      showAlert(t("settings.messages.fields_cleared"), "info");
    }
  };

  // Global function for delete button (called from template)
  window.deleteCustomProvider = function (providerName) {
    if (
      !confirm(
        t("settings.messages.delete_provider_confirm", { name: providerName })
      )
    ) {
      return;
    }

    // Remove from state
    delete state.customProviders[providerName];

    // Remove config section
    const configSection = document.getElementById(`${providerName}-config`);
    if (configSection) {
      configSection.remove();
    }

    // Remove from dropdown
    removeCustomProviderFromDropdown(providerName);

    // Always switch to openai after deletion
    const defaultProvider =
      state.meta.builtinProviders.length > 0
        ? state.meta.builtinProviders[0].id
        : "openai";
    if (selectors.aiProviderSelect) {
      selectors.aiProviderSelect.value = defaultProvider;
    }
    highlightActiveProvider(defaultProvider);

    showAlert(
      t("settings.messages.provider_deleted", { name: providerName }),
      "info"
    );
  };

  function getLogMode() {
    if (selectors.logModeDebug && selectors.logModeDebug.checked) {
      return "debug";
    }
    return "off";
  }

  function setLogMode(mode) {
    const value = mode === "debug" ? "debug" : "off";
    if (selectors.logModeOff) {
      selectors.logModeOff.checked = value === "off";
    }
    if (selectors.logModeDebug) {
      selectors.logModeDebug.checked = value === "debug";
    }
  }

  function updateApiKeyHint(apiKeyInput, hintElement, providerName) {
    if (!hintElement) return;

    const apiKey = apiKeyInput?.value?.trim() || "";
    const isEmpty = !apiKey || apiKey === "YOUR_API_KEY_HERE";

    if (isEmpty) {
      hintElement.textContent = t("settings.messages.api_key_empty", {
        provider: providerName,
      });
      hintElement.classList.remove("text-muted");
      hintElement.classList.add("text-danger");
    } else {
      hintElement.textContent = t("settings.api.api_key_help", {
        provider: providerName,
      });
      hintElement.classList.remove("text-danger");
      hintElement.classList.add("text-muted");
    }
  }

  function loadSettings() {
    fetch(API_BASE)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        // Handle both {config: {...}} and direct config object formats
        const config = data.config || data || {};

        // Load meta information from API
        if (data.meta) {
          state.meta.builtinProviders = data.meta.builtin_providers || [];
          state.meta.providerDefaults = data.meta.provider_defaults || {
            max_retries: 3,
            timeout: 120,
          };
          state.meta.providerNamePattern =
            data.meta.provider_name_pattern || "^[a-zA-Z0-9_-]+$";
        }

        // Initialize built-in providers UI (now that we have meta data)
        initializeBuiltInProviders();

        // Populate provider dropdown
        populateProviderDropdown();

        // Load general settings
        setLogMode(config.log_mode || "off");

        // Set AI provider (default to first built-in provider if not set)
        const defaultProvider =
          state.meta.builtinProviders.length > 0
            ? state.meta.builtinProviders[0].id
            : "openai";
        const provider = config.ai_provider || defaultProvider;
        if (selectors.aiProviderSelect) {
          selectors.aiProviderSelect.value = provider;
        }
        highlightActiveProvider(provider);

        // Load built-in provider configs
        state.meta.builtinProviders.forEach((providerInfo) => {
          const providerId = providerInfo.id;
          const providerConfig = config[providerId] || {};

          // Load API URL (from config, will have default from backend if empty)
          const apiUrlInput = getProviderSelector(providerId, "api-url");
          if (apiUrlInput) {
            apiUrlInput.value = providerConfig.api_url || "";
          }

          // Load API Key
          const apiKeyInput = getProviderSelector(providerId, "api-key");
          if (apiKeyInput) {
            apiKeyInput.value = providerConfig.api_key || "";
          }

          // Load models array
          const models = Array.isArray(providerConfig.models)
            ? providerConfig.models
            : [];
          const modelInputs = getProviderModelInputs(providerId);
          modelInputs.forEach((input, index) => {
            if (input) {
              const modelValue = models[index];
              input.value =
                modelValue && typeof modelValue === "string" ? modelValue : "";
            }
          });

          // Update API key hint
          const apiKeyHint = getProviderSelector(providerId, "api-key-hint");
          if (apiKeyInput && apiKeyHint) {
            updateApiKeyHint(apiKeyInput, apiKeyHint, providerInfo.name);
          }
        });

        // Load custom providers
        loadCustomProviders(config);

        // Set up API key hint listeners for built-in providers
        state.meta.builtinProviders.forEach((providerInfo) => {
          const providerId = providerInfo.id;
          const apiKeyInput = getProviderSelector(providerId, "api-key");
          const apiKeyHint = getProviderSelector(providerId, "api-key-hint");
          if (apiKeyInput && apiKeyHint) {
            // Remove any existing listener to avoid duplicates
            apiKeyInput.removeEventListener("input", apiKeyInput._hintHandler);
            apiKeyInput._hintHandler = () => {
              updateApiKeyHint(apiKeyInput, apiKeyHint, providerInfo.name);
            };
            apiKeyInput.addEventListener("input", apiKeyInput._hintHandler);
          }
        });

        // Hide loading state and show content (if it was shown)
      })
      .catch((error) => {
        console.error("Failed to load settings:", error);
        showAlert(t("settings.messages.load_failed"), "danger");
      });
  }

  function validateForm() {
    const provider = selectors.aiProviderSelect?.value;
    if (!provider) {
      showAlert(t("settings.messages.select_provider"), "warning");
      return false;
    }

    // Handle "Add New AI Provider" option
    if (provider === "__add_new__") {
      // Validate new provider form
      return validateNewProvider();
    }

    // If showing new provider config, validate it
    const newProviderConfig = document.getElementById("new-provider-config");
    if (newProviderConfig && newProviderConfig.style.display !== "none") {
      return validateNewProvider();
    }

    // Validate selected provider's required fields (models are optional)
    const builtInProvider = state.meta.builtinProviders.find(
      (p) => p.id === provider
    );
    if (!builtInProvider) {
      // Custom provider validation (only API URL and API Key are required)
      const apiUrlInput = document.getElementById(`${provider}-api-url`);
      const apiKeyInput = document.getElementById(`${provider}-api-key`);

      const apiUrl = apiUrlInput?.value?.trim();
      const apiKey = apiKeyInput?.value?.trim();

      if (!apiUrl) {
        showAlert(t("settings.messages.api_url_required_custom"), "warning");
        if (apiUrlInput) {
          apiUrlInput.focus();
          apiUrlInput.classList.add("is-invalid");
        }
        return false;
      }

      if (!apiKey) {
        showAlert(t("settings.messages.api_key_required_custom"), "warning");
        if (apiKeyInput) {
          apiKeyInput.focus();
          apiKeyInput.classList.add("is-invalid");
        }
        return false;
      }
    }

    return true;
  }

  function saveSettings() {
    if (!validateForm()) {
      return;
    }

    setSubmitting(true);

    // Helper to collect models array from inputs (filter empty values)
    const collectModels = (modelInputs) => {
      return modelInputs
        .map((input) => input?.value?.trim() || "")
        .filter((model) => model !== "");
    };

    let finalProvider = selectors.aiProviderSelect?.value;

    // Check if we're saving a new provider
    const newProviderConfig = document.getElementById("new-provider-config");
    if (newProviderConfig && newProviderConfig.style.display !== "none") {
      // Create new provider from form inputs
      const providerName = document
        .getElementById("new-provider-name")
        ?.value?.trim();
      if (providerName) {
        // Collect models
        const modelInputs = [
          document.getElementById("new-provider-model-1"),
          document.getElementById("new-provider-model-2"),
          document.getElementById("new-provider-model-3"),
          document.getElementById("new-provider-model-4"),
          document.getElementById("new-provider-model-5"),
        ];
        const models = collectModels(modelInputs);

        // Add to state
        state.customProviders[providerName] = {
          api_url: document.getElementById("new-provider-api-url")?.value || "",
          api_key: document.getElementById("new-provider-api-key")?.value || "",
          models: models,
          max_retries: state.meta.providerDefaults.max_retries,
          timeout: state.meta.providerDefaults.timeout,
        };

        // Create config section and add to dropdown
        const configSection = createCustomProviderConfig(
          providerName,
          state.customProviders[providerName]
        );
        if (configSection && selectors.customProvidersContainer) {
          selectors.customProvidersContainer.appendChild(configSection);
        }

        const displayName =
          providerName.charAt(0).toUpperCase() +
          providerName.slice(1).replace(/-/g, " ");
        addCustomProviderToDropdown(providerName, displayName);

        // Select the new provider
        finalProvider = providerName;
        if (selectors.aiProviderSelect) {
          selectors.aiProviderSelect.value = providerName;
        }

        // Hide new provider config
        newProviderConfig.style.display = "none";
        clearNewProviderInputs();
      }
    }

    const config = {
      ai_provider: finalProvider,
      log_mode: getLogMode(),
    };

    // Save built-in provider configs
    state.meta.builtinProviders.forEach((providerInfo) => {
      const providerId = providerInfo.id;
      const apiUrlInput = getProviderSelector(providerId, "api-url");
      const apiKeyInput = getProviderSelector(providerId, "api-key");
      const modelInputs = getProviderModelInputs(providerId);

      config[providerId] = {
        api_url: apiUrlInput?.value || "",
        api_key: apiKeyInput?.value || "",
        models: collectModels(modelInputs),
        max_retries: state.meta.providerDefaults.max_retries,
        timeout: state.meta.providerDefaults.timeout,
      };
    });

    // Add custom providers
    Object.keys(state.customProviders).forEach((providerName) => {
      const apiUrlInput = document.getElementById(`${providerName}-api-url`);
      const apiKeyInput = document.getElementById(`${providerName}-api-key`);
      const modelInputs = [
        document.getElementById(`${providerName}-model-1`),
        document.getElementById(`${providerName}-model-2`),
        document.getElementById(`${providerName}-model-3`),
        document.getElementById(`${providerName}-model-4`),
        document.getElementById(`${providerName}-model-5`),
      ];

      config[providerName] = {
        api_url: apiUrlInput?.value || "",
        api_key: apiKeyInput?.value || "",
        models: collectModels(modelInputs),
        max_retries: state.meta.providerDefaults.max_retries,
        timeout: state.meta.providerDefaults.timeout,
      };
    });

    fetch(API_BASE, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ config }),
    })
      .then((response) => {
        if (!response.ok) {
          return response.json().then((data) => {
            throw new Error(
              data.error || `HTTP error! status: ${response.status}`
            );
          });
        }
        return response.json();
      })
      .then((data) => {
        showAlert(t("settings.messages.saved"), "success");

        // If we created a new provider, show its config
        if (finalProvider && state.customProviders[finalProvider]) {
          highlightActiveProvider(finalProvider);
        }

        // Close modal after a short delay
        setTimeout(() => {
          if (state.settingsModal) {
            state.settingsModal.hide();
          }

          // Refresh translate tab settings if LPM is available and we're on the manage page
          if (window.LPM && window.LPM.translate) {
            // Reload provider settings
            if (typeof window.LPM.translate.loadSettings === "function") {
              window.LPM.translate.loadSettings();
            }
            // Update start button state
            if (typeof window.LPM.translate.updateStartButton === "function") {
              window.LPM.translate.updateStartButton();
            }
          }
        }, 1000);
      })
      .catch((error) => {
        console.error("Failed to save settings:", error);
        showAlert(
          error.message || t("settings.messages.save_failed"),
          "danger"
        );
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  function bindEvents() {
    // Settings button click
    if (selectors.settingsButton) {
      selectors.settingsButton.addEventListener("click", () => {
        if (state.settingsModal) {
          loadSettings();
          state.settingsModal.show();
        }
      });
    }

    // AI Provider change
    if (selectors.aiProviderSelect) {
      selectors.aiProviderSelect.addEventListener("change", (e) => {
        handleProviderChange(e.target.value);
      });
    }

    // Form submission
    if (selectors.settingsForm) {
      selectors.settingsForm.addEventListener("submit", (e) => {
        e.preventDefault();
        saveSettings();
      });
    }

    // Clear validation classes on input
    const allInputs = document.querySelectorAll(
      "#settingsModal input, #settingsModal select"
    );
    allInputs.forEach((input) => {
      input.addEventListener("input", () => {
        input.classList.remove("is-invalid");
      });
    });

    // Note: API key hint listeners for built-in providers are now set up
    // in loadSettings() after meta data is loaded from API

    // Clear logs button
    if (selectors.clearLogsBtn) {
      selectors.clearLogsBtn.addEventListener("click", clearLogs);
    }
  }

  async function clearLogs() {
    if (!confirm(t("settings.messages.logs_clear_confirm"))) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/logs`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Failed to clear logs");
      }

      const data = await response.json();
      alert(data.message || t("settings.messages.logs_cleared"));
    } catch (error) {
      console.error("Failed to clear logs:", error);
      alert(t("settings.messages.logs_clear_failed", { error: error.message }));
    }
  }

  function initialize() {
    // Note: Built-in provider configs are now initialized in loadSettings()
    // after meta data is loaded from API

    // Initialize Bootstrap modal
    if (selectors.settingsModalElement) {
      state.settingsModal = new bootstrap.Modal(
        selectors.settingsModalElement,
        {
          backdrop: "static",
          keyboard: false,
        }
      );

      // Hide all provider configs immediately on initialization to prevent flash
      const allConfigs = document.querySelectorAll(".provider-config");
      allConfigs.forEach((config) => {
        config.style.display = "none";
      });

      // Set default provider (openai) as visible immediately
      const defaultProvider = "openai";
      const defaultConfig = document.getElementById(
        `${defaultProvider}-config`
      );
      if (defaultConfig) {
        defaultConfig.style.display = "block";
      }

      // Load settings when modal starts showing (before animation completes)
      // This allows data to load during the modal animation
      selectors.settingsModalElement.addEventListener("show.bs.modal", () => {
        loadSettings();
      });

      // Fix accessibility issue: remove focus from close button before modal hides
      // This prevents ARIA warnings when modals are closed with focused elements inside
      selectors.settingsModalElement.addEventListener("hide.bs.modal", () => {
        // Remove focus from any focused element inside the modal before it hides
        const focusedElement =
          selectors.settingsModalElement.querySelector(":focus");
        if (focusedElement) {
          focusedElement.blur();
        }
        // Clear new provider inputs when modal closes
        const newProviderConfig = document.getElementById(
          "new-provider-config"
        );
        if (newProviderConfig) {
          newProviderConfig.style.display = "none";
        }
        clearNewProviderInputs();
      });
    }

    bindEvents();
  }

  // Initialize when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize);
  } else {
    initialize();
  }
})();
