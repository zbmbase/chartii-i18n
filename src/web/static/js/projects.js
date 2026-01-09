/**
 * Front-end logic for interacting with the project management REST API.
 */
(function () {
  const API_BASE = "/api/projects";

  const selectors = {
    tableBody: document.getElementById("project-table-body"),
    createButton: document.getElementById("create-project-btn"),
    createModalElement: document.getElementById("createProjectModal"),
    createForm: document.getElementById("create-project-form"),
    submitButton: document.getElementById("submit-project-btn"),
    projectNameInput: document.getElementById("project-name"),
    sourceFileInput: document.getElementById("source-file-path"),
    sourceFileValidationMessage: document.getElementById(
      "source-file-validation-message"
    ),
    translationContextInput: document.getElementById("translation-context"),
    translationContextCounter: document.getElementById(
      "translation-context-counter"
    ),
  };

  const state = {
    projects: [],
    isSubmitting: false,
    editingProjectId: null, // Track which project is being edited
  };

  function setFieldValid(field) {
    if (!field) return;
    field.classList.add("is-valid");
    field.classList.remove("is-invalid");
  }

  function setFieldInvalid(field) {
    if (!field) return;
    field.classList.add("is-invalid");
    field.classList.remove("is-valid");
  }

  function clearFieldState(field) {
    if (!field) return;
    field.classList.remove("is-valid", "is-invalid");
  }

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

  function updateSubmitButtonText() {
    if (!selectors.submitButton) return;
    const label = selectors.submitButton.querySelector(".submit-label");
    if (label) {
      const isEditing = state.editingProjectId !== null;
      label.textContent = isEditing
        ? t("projects.create_modal.update_btn")
        : t("projects.create_modal.create_btn");
    }
  }

  function setSubmitting(isSubmitting) {
    state.isSubmitting = isSubmitting;
    if (!selectors.submitButton) return;
    selectors.submitButton.disabled = isSubmitting;
    const spinner = selectors.submitButton.querySelector(".spinner-border");
    const label = selectors.submitButton.querySelector(".submit-label");
    if (spinner) {
      spinner.classList.toggle("d-none", !isSubmitting);
    }
    if (label) {
      const isEditing = state.editingProjectId !== null;
      label.textContent = isSubmitting
        ? isEditing
          ? t("projects.create_modal.updating")
          : t("projects.create_modal.creating")
        : isEditing
        ? t("projects.create_modal.update_btn")
        : t("projects.create_modal.create_btn");
    }
  }

  function renderProjects() {
    if (!selectors.tableBody) return;

    if (!state.projects.length) {
      selectors.tableBody.innerHTML = `
        <tr class="placeholder-row">
          <td colspan="5" class="text-center text-muted py-4">
            ${t("projects.no_projects")}
          </td>
        </tr>
      `;
      return;
    }

    const rows = state.projects
      .map((project) => {
        const sourceFilePath = project.source_file_path || "-";
        const languageFileCount = project.language_file_count || 0;
        return `
          <tr data-project-id="${project.id}">
            <td>${project.id}</td>
            <td>${escapeHtml(project.name)}</td>
            <td class="font-monospace small source-path-cell" title="${escapeHtml(
              sourceFilePath
            )}">${escapeHtml(sourceFilePath)}</td>
            <td>${languageFileCount}</td>
            <td class="text-end">
              <div class="btn-group" role="group">
                <button class="btn btn-sm btn-primary manage-btn" data-project-id="${
                  project.id
                }">
                  ${t("common.manage")}
                </button>
                <button class="btn btn-sm btn-secondary edit-btn" data-project-id="${
                  project.id
                }">
                  ${t("common.edit")}
                </button>
                <button class="btn btn-sm btn-danger delete-btn" data-project-id="${
                  project.id
                }">
                  ${t("common.delete")}
                </button>
              </div>
            </td>
          </tr>
        `;
      })
      .join("");

    selectors.tableBody.innerHTML = rows;

    // Bind event listeners for action buttons
    bindActionButtons();
  }

  async function fetchProjects() {
    try {
      const response = await fetch(`${API_BASE}/`, {
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }

      const payload = await response.json();
      state.projects = payload.projects || [];
      renderProjects();
    } catch (error) {
      console.error(error);
      showAlert(
        t("projects.messages.load_failed", { error: error.message }),
        "danger"
      );
    }
  }

  function updateCharacterCount(textarea, counter) {
    if (!counter) return;
    const currentLength = textarea ? textarea.value.length : 0;
    const maxLength = textarea ? textarea.maxLength : 1000;
    counter.textContent = t("projects.create_modal.context_counter", {
      current: currentLength,
      max: maxLength,
    });
  }

  function resetForm() {
    if (!selectors.createForm) return;
    selectors.createForm.reset();
    selectors.createForm.classList.remove("was-validated");
    state.editingProjectId = null;

    // Reset modal title
    const modalTitle = document.getElementById("createProjectModalLabel");
    if (modalTitle) {
      modalTitle.textContent = t("projects.create_modal.title");
    }

    // Reset help text visibility (show create mode, hide edit mode)
    const helpCreate = document.getElementById("source-file-help-create");
    const helpEdit = document.getElementById("source-file-help-edit");
    if (helpCreate) helpCreate.classList.remove("d-none");
    if (helpEdit) helpEdit.classList.add("d-none");

    // Show import mode section (only for create mode)
    const importModeSection = document.getElementById("import-mode-section");
    if (importModeSection) importModeSection.classList.remove("d-none");

    // Update submit button text
    updateSubmitButtonText();

    // Enable all fields
    if (selectors.sourceFileInput) {
      selectors.sourceFileInput.disabled = false;
      selectors.sourceFileInput.setAttribute("required", "required"); // Restore required for create mode
      selectors.sourceFileInput.value = "";
      selectors.sourceFileInput.placeholder = "";
      clearFieldState(selectors.sourceFileInput);
    }

    // Reset import mode radio buttons
    const retranslateRadio = document.getElementById("import-mode-retranslate");
    const mergeRadio = document.getElementById("import-mode-merge");
    if (retranslateRadio) {
      retranslateRadio.disabled = false;
      retranslateRadio.setAttribute("required", "required"); // Restore required for create mode
      retranslateRadio.checked = true;
    }
    if (mergeRadio) {
      mergeRadio.disabled = false;
      mergeRadio.setAttribute("required", "required"); // Restore required for create mode
    }

    if (selectors.projectNameInput) {
      selectors.projectNameInput.value = "";
      clearFieldState(selectors.projectNameInput);
    }
    if (selectors.translationContextInput) {
      selectors.translationContextInput.value = "";
      clearFieldState(selectors.translationContextInput);
    }
    // Reset character count
    updateCharacterCount(
      selectors.translationContextInput,
      selectors.translationContextCounter
    );
    // Reset validation state
    if (selectors.sourceFileValidationMessage) {
      selectors.sourceFileValidationMessage.classList.add("d-none");
      selectors.sourceFileValidationMessage.textContent = "";
    }
  }

  let validationTimeout = null;

  function debounce(func, wait) {
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(validationTimeout);
        func(...args);
      };
      clearTimeout(validationTimeout);
      validationTimeout = setTimeout(later, wait);
    };
  }

  async function validateSourceFilePath(filePath) {
    // Get elements dynamically for reliability
    const sourceFileInput = document.getElementById("source-file-path");
    const validationMessage = document.getElementById(
      "source-file-validation-message"
    );

    if (!filePath || filePath.trim() === "") {
      // Clear validation state if input is empty
      if (sourceFileInput) {
        clearFieldState(sourceFileInput);
      }
      if (validationMessage) {
        validationMessage.classList.add("d-none");
        validationMessage.textContent = "";
      }
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/validate-source-path`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ file_path: filePath }),
      });

      const data = await response.json();

      if (data.valid) {
        // Show success state - only show checkmark when validation passes
        if (validationMessage) {
          validationMessage.textContent = data.message;
          validationMessage.classList.remove("d-none");
          validationMessage.classList.add("text-success");
          validationMessage.classList.remove("text-danger");
        }
        if (sourceFileInput) {
          setFieldValid(sourceFileInput);
        }
      } else {
        // Show error state - no checkmark when validation fails
        if (validationMessage) {
          validationMessage.textContent = data.message;
          validationMessage.classList.remove("d-none");
          validationMessage.classList.add("text-danger");
          validationMessage.classList.remove("text-success");
        }
        if (sourceFileInput) {
          setFieldInvalid(sourceFileInput);
        }
      }
    } catch (error) {
      console.error("Error validating file path:", error);
      // On error, clear validation state
      if (sourceFileInput) {
        clearFieldState(sourceFileInput);
      }
      if (validationMessage) {
        validationMessage.classList.add("d-none");
      }
    }
  }

  const debouncedValidate = debounce((filePath) => {
    validateSourceFilePath(filePath);
  }, 500);

  function handleAutofillValidation(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;

    const value = input.value.trim();
    if (value) {
      // Force re-application of validation class
      input.classList.remove("is-valid");
      // Use multiple methods to ensure icon appears
      setTimeout(() => {
        setFieldValid(input);
      }, 0);
      requestAnimationFrame(() => {
        setFieldValid(input);
      });
    }
  }

  function bindInputValidation() {
    // Use event delegation on the form - simplest and most reliable approach
    if (!selectors.createForm) return;

    // Project Name validation - simple and classic
    selectors.createForm.addEventListener("input", (event) => {
      const target = event.target;

      // Project Name validation
      if (target.id === "project-name") {
        const value = target.value.trim();
        if (value) {
          setFieldValid(target);
        } else {
          clearFieldState(target);
        }
      }

      // Project Summary validation
      if (target.id === "translation-context") {
        const value = target.value.trim();
        // Update character count (get element dynamically)
        const counter = document.getElementById("translation-context-counter");
        if (counter) {
          updateCharacterCount(target, counter);
        }
        if (value) {
          setFieldValid(target);
        } else {
          clearFieldState(target);
        }
      }

      // Source File Path validation
      if (target.id === "source-file-path") {
        const filePath = target.value.trim();
        // Clear previous validation state when user types
        clearFieldState(target);
        const validationMessage = document.getElementById(
          "source-file-validation-message"
        );
        if (validationMessage) {
          validationMessage.classList.add("d-none");
          validationMessage.textContent = "";
        }
        // Debounce validation
        if (filePath) {
          debouncedValidate(filePath);
        }
      }
    });

    // Change event for browser autofill
    selectors.createForm.addEventListener("change", (event) => {
      const target = event.target;

      // Project Name validation (handles autofill)
      if (target.id === "project-name") {
        const value = target.value.trim();
        if (value) {
          // Force re-application of validation class to ensure icon appears
          target.classList.remove("is-valid");
          // Use requestAnimationFrame to ensure DOM update
          requestAnimationFrame(() => {
            setFieldValid(target);
          });
        } else {
          clearFieldState(target);
        }
      }

      // Project Summary validation (handles autofill)
      if (target.id === "translation-context") {
        const value = target.value.trim();
        const counter = document.getElementById("translation-context-counter");
        if (counter) {
          updateCharacterCount(target, counter);
        }
        if (value) {
          // Force re-application of validation class
          target.classList.remove("is-valid");
          requestAnimationFrame(() => {
            setFieldValid(target);
          });
        } else {
          clearFieldState(target);
        }
      }
    });

    // Blur validation for better UX
    selectors.createForm.addEventListener(
      "blur",
      (event) => {
        const target = event.target;

        // Project Name blur validation
        if (target.id === "project-name") {
          const value = target.value.trim();
          if (value) {
            setFieldValid(target);
          } else {
            setFieldInvalid(target);
          }
        }

        // Project Summary blur validation
        if (target.id === "translation-context") {
          const value = target.value.trim();
          if (value) {
            setFieldValid(target);
          } else {
            setFieldInvalid(target);
          }
        }

        // Source File Path blur validation
        if (target.id === "source-file-path") {
          const filePath = target.value.trim();
          if (filePath) {
            validateSourceFilePath(filePath);
          }
        }
      },
      true
    ); // Use capture phase to ensure blur events are caught
  }

  function bindEvents() {
    if (
      selectors.createButton &&
      selectors.createModalElement &&
      window.bootstrap
    ) {
      const modal = new window.bootstrap.Modal(selectors.createModalElement, {
        backdrop: "static", // Prevent closing when clicking outside the modal
        keyboard: false, // Prevent closing with ESC key
      });

      selectors.createButton.addEventListener("click", () => {
        resetForm();
        modal.show();
      });

      // Check for autofilled values after modal is shown and poll for changes
      let autofillPollInterval = null;
      selectors.createModalElement.addEventListener("shown.bs.modal", () => {
        // Update submit button text based on editing state
        updateSubmitButtonText();

        const projectNameInput = document.getElementById("project-name");
        let lastProjectNameValue = projectNameInput
          ? projectNameInput.value
          : "";

        const translationContextInput = document.getElementById(
          "translation-context"
        );
        let lastTranslationContextValue = translationContextInput
          ? translationContextInput.value
          : "";

        // Poll for value changes to catch autofill
        autofillPollInterval = setInterval(() => {
          // Check Project Name
          if (projectNameInput) {
            const currentValue = projectNameInput.value;
            if (currentValue !== lastProjectNameValue) {
              lastProjectNameValue = currentValue;
              if (currentValue.trim()) {
                handleAutofillValidation("project-name");
              }
            }
          }

          // Check Project Summary
          if (translationContextInput) {
            const currentValue = translationContextInput.value;
            if (currentValue !== lastTranslationContextValue) {
              lastTranslationContextValue = currentValue;
              if (currentValue.trim()) {
                handleAutofillValidation("translation-context");
                const counter = document.getElementById(
                  "translation-context-counter"
                );
                if (counter) {
                  updateCharacterCount(translationContextInput, counter);
                }
              }
            }
          }
        }, 150); // Poll every 150ms to catch autofill

        // Also check immediately after a delay
        setTimeout(() => {
          if (projectNameInput && projectNameInput.value.trim()) {
            handleAutofillValidation("project-name");
          }
          if (translationContextInput && translationContextInput.value.trim()) {
            handleAutofillValidation("translation-context");
            const counter = document.getElementById(
              "translation-context-counter"
            );
            if (counter) {
              updateCharacterCount(translationContextInput, counter);
            }
          }
        }, 100);
      });

      // Clean up polling and reset form when modal is hidden
      // Fix accessibility issue: remove focus from close button before modal hides
      // This prevents ARIA warnings when modals are closed with focused elements inside
      selectors.createModalElement.addEventListener("hide.bs.modal", () => {
        // Remove focus from any focused element inside the modal before it hides
        const focusedElement =
          selectors.createModalElement.querySelector(":focus");
        if (focusedElement) {
          focusedElement.blur();
        }
      });

      selectors.createModalElement.addEventListener("hidden.bs.modal", () => {
        if (autofillPollInterval) {
          clearInterval(autofillPollInterval);
          autofillPollInterval = null;
        }
        resetForm();
      });

      // Bind input validation once - event delegation handles everything
      bindInputValidation();

      // Bind form submit event (only once)
      if (selectors.createForm) {
        selectors.createForm.addEventListener("submit", async (event) => {
          event.preventDefault();
          event.stopPropagation();

          // Prevent duplicate submissions
          if (state.isSubmitting) {
            return;
          }

          selectors.createForm.classList.add("was-validated");

          if (!selectors.createForm.checkValidity()) {
            showAlert(t("projects.messages.validation_required"), "warning");
            return;
          }

          const formData = new FormData(selectors.createForm);
          const isEditing = state.editingProjectId !== null;

          const payload = {
            name: formData.get("name")?.toString().trim(),
            translation_context:
              formData.get("translation_context")?.toString().trim() || "",
          };

          // Get source file path (required for both create and edit)
          payload.source_file_path = formData
            .get("source_file_path")
            ?.toString()
            .trim();

          // Validate source file path
          const sourcePath = payload.source_file_path || "";
          const absolutePathPattern = /^([A-Za-z]:\\|\\\\|\/)/;
          if (!absolutePathPattern.test(sourcePath)) {
            showAlert(
              t("projects.messages.validation_absolute_path"),
              "warning"
            );
            if (selectors.sourceFileInput) {
              selectors.sourceFileInput.focus();
            }
            return;
          }

          // Only include import_mode for new projects
          if (!isEditing) {
            payload.import_mode =
              formData.get("import_mode")?.toString() || "retranslate";
          }

          await submitProject(payload, modal);
        });
      }
    }
  }

  function bindActionButtons() {
    document.querySelectorAll(".manage-btn").forEach((btn) => {
      const projectId = parseInt(btn.dataset.projectId, 10);
      if (Number.isNaN(projectId)) {
        btn.disabled = true;
        return;
      }
      btn.disabled = false;
      btn.addEventListener("click", () => {
        window.location.href = `/projects/${projectId}/manage`;
      });
    });

    // Bind edit buttons
    document.querySelectorAll(".edit-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const projectId = parseInt(e.target.dataset.projectId);
        await editProject(projectId);
      });
    });

    // Bind delete buttons
    document.querySelectorAll(".delete-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const projectId = parseInt(e.target.dataset.projectId);
        await deleteProject(projectId);
      });
    });
  }

  async function editProject(projectId) {
    try {
      // Fetch project details
      const response = await fetch(`${API_BASE}/${projectId}`, {
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to load project: ${response.status}`);
      }

      const data = await response.json();
      const project = data.project;

      if (!project) {
        throw new Error("Project not found");
      }

      // Set editing state
      state.editingProjectId = projectId;

      // Update modal title
      const modalTitle = document.getElementById("createProjectModalLabel");
      if (modalTitle) {
        modalTitle.textContent = t("projects.create_modal.edit_title");
      }

      // Update submit button text
      updateSubmitButtonText();

      // Update help text visibility (hide create mode, show edit mode)
      const helpCreate = document.getElementById("source-file-help-create");
      const helpEdit = document.getElementById("source-file-help-edit");
      if (helpCreate) helpCreate.classList.add("d-none");
      if (helpEdit) helpEdit.classList.remove("d-none");

      // Hide import mode section (not needed in edit mode)
      const importModeSection = document.getElementById("import-mode-section");
      if (importModeSection) importModeSection.classList.add("d-none");

      // Fill form with project data
      if (selectors.projectNameInput) {
        selectors.projectNameInput.value = project.name || "";
        if (project.name) {
          setFieldValid(selectors.projectNameInput);
        }
      }

      if (selectors.translationContextInput) {
        selectors.translationContextInput.value =
          project.translation_context || "";
        if (project.translation_context) {
          setFieldValid(selectors.translationContextInput);
        }
        // Update character count
        if (selectors.translationContextCounter) {
          updateCharacterCount(
            selectors.translationContextInput,
            selectors.translationContextCounter
          );
        }
      }

      // Enable source file path for editing (but keep import mode disabled)
      if (selectors.sourceFileInput) {
        selectors.sourceFileInput.disabled = false;
        selectors.sourceFileInput.setAttribute("required", "required"); // Keep required in edit mode
        selectors.sourceFileInput.value = project.source_file_path || "";
        // Clear validation state to allow re-validation
        clearFieldState(selectors.sourceFileInput);
        // Validate the source file path if it exists
        if (project.source_file_path) {
          // Use a small delay to ensure the input is updated
          setTimeout(() => {
            const filePath = selectors.sourceFileInput.value.trim();
            if (filePath) {
              validateSourceFilePath(filePath);
            }
          }, 100);
        }
      }

      // Disable import mode (not editable)
      const retranslateRadio = document.getElementById(
        "import-mode-retranslate"
      );
      const mergeRadio = document.getElementById("import-mode-merge");
      if (retranslateRadio) {
        retranslateRadio.disabled = true;
        retranslateRadio.removeAttribute("required");
      }
      if (mergeRadio) {
        mergeRadio.disabled = true;
        mergeRadio.removeAttribute("required");
      }

      // Show modal
      if (selectors.createModalElement && window.bootstrap) {
        const modal =
          window.bootstrap.Modal.getInstance(selectors.createModalElement) ||
          new window.bootstrap.Modal(selectors.createModalElement);
        modal.show();
      }
    } catch (error) {
      console.error(error);
      showAlert(
        t("projects.messages.load_failed", { error: error.message }),
        "danger"
      );
    }
  }

  async function deleteProject(projectId) {
    const project = state.projects.find((p) => p.id === projectId);
    const projectName = project ? project.name : `Project #${projectId}`;

    if (
      !confirm(t("projects.messages.delete_confirm", { name: projectName }))
    ) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/${projectId}`, {
        method: "DELETE",
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          data.error || `Failed to delete project: ${response.status}`
        );
      }

      showAlert(
        t("projects.messages.deleted", { name: projectName }),
        "success"
      );
      await fetchProjects();
    } catch (error) {
      console.error(error);
      showAlert(
        t("projects.messages.delete_failed", { error: error.message }),
        "danger"
      );
    }
  }

  async function submitProject(payload, modalInstance) {
    try {
      setSubmitting(true);

      const isEditing = state.editingProjectId !== null;
      const url = isEditing
        ? `${API_BASE}/${state.editingProjectId}`
        : `${API_BASE}/`;
      const method = isEditing ? "PUT" : "POST";

      // For editing, send name, translation_context, and source_file_path
      // (source_file_path can be updated if language pack path changed)
      if (isEditing) {
        payload = {
          name: payload.name,
          translation_context: payload.translation_context,
          source_file_path: payload.source_file_path,
        };
      }

      const response = await fetch(url, {
        method: method,
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const message =
          data?.error ||
          `Project ${isEditing ? "update" : "creation"} failed (status code ${
            response.status
          })`;
        throw new Error(message);
      }

      modalInstance.hide();
      showAlert(
        isEditing
          ? t("projects.messages.updated", { name: payload.name })
          : t("projects.messages.created", { name: payload.name }),
        "success"
      );

      await fetchProjects();
    } catch (error) {
      console.error(error);
      showAlert(
        state.editingProjectId
          ? t("projects.messages.update_failed", { error: error.message })
          : t("projects.messages.create_failed", { error: error.message }),
        "danger"
      );
    } finally {
      setSubmitting(false);
    }
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

  document.addEventListener("DOMContentLoaded", () => {
    fetchProjects();
    bindEvents();
  });
})();
