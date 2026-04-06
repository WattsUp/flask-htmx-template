"use strict";
const dialog = {
  pending: false,
  /**
   * Close dialog if no pending changes
   *
   * @param {boolean} force true will ignore pending changes
   */
  close(force) {
    if (!force && this.pending) {
      this.confirm("Discard draft?", "Discard", () => {
        this.pending = false;
        htmx.find("#dialog").innerHTML = "";
      });
      return;
    }
    htmx.find("#dialog").innerHTML = "";
    this.reset();
  },
  /**
   * On dialog changes, set pending flag
   */
  changes() {
    this.pending = true;
  },
  /**
   * On dialog reset, reset pending flag
   */
  reset() {
    this.pending = false;
    if (location.hash == "#dialog") history.back();
  },
  /**
   * Check if all required element are populated
   *
   * @return boolean true if all required elements are filled
   */
  checkRequired() {
    let allFilled = true;
    htmx.findAll("#dialog [required]").forEach((e) => {
      if (!allFilled) return;
      if (!e.value) {
        allFilled = false;
        return;
      }
    });
    return allFilled;
  },
  /**
   * Update dialog save button
   */
  updateSave() {
    const saveBtn = htmx.find("#dialog-save");
    if (!saveBtn) return;
    const allFilled = this.checkRequired();
    const anyInvalid = htmx.find("#dialog error:not(:empty)") != null;
    saveBtn.disabled = !allFilled || anyInvalid;
  },
  /**
   * Add event listeners to the dialog
   */
  addListeners() {
    const d = htmx.find("#dialog");
    htmx.findAll(d, "[required]").forEach((e) => {
      htmx.on(e, "input", this.updateSave.bind(this));
    });
    htmx.findAll(d, "input, textarea, select").forEach((e) => {
      htmx.on(e, "input", this.changes.bind(this));
      if (e.getAttribute("name") != "label") {
        htmx.on(e, "keydown", (evt) => {
          if (evt.key == "Enter") {
            evt.preventDefault();
            this.focusNext(e);
          }
        });
      }
      htmx.on(e, "focus", (evt) => {
        // Smooth scroll nearest
        evt.preventDefault();
        e.scrollIntoView({ block: "nearest" });
      });
    });
  },
  /**
   * Focus the next dialog input
   *
   * @param {Element} start - Starting element to search from
   */
  focusNext(start) {
    const d = htmx.find("#dialog");
    const results = htmx.findAll(
      d,
      "input:not(:disabled), textarea:not(:disabled), select:not(:disabled)",
    );
    for (const next of results) {
      if (
        next.compareDocumentPosition(start) === Node.DOCUMENT_POSITION_PRECEDING
      ) {
        next.focus({ preventScroll: true });
        if (next.getAttribute("type") != "date") {
          next.selectionStart = 0;
          next.selectionEnd = next.value.length;
        }
        return;
      }
    }
  },
  /**
   * On load of a dialog, addListeners and autofocus
   */
  onLoad() {
    this.addListeners();
    // Only autofocus for not mobile
    if (window.screen.width >= 768) {
      const d = htmx.find("#dialog");
      const firstInput = htmx.find(d, "input, textarea, select");
      firstInput.focus();
      if (firstInput.type == "text") {
        const n = firstInput.value.length;
        firstInput.setSelectionRange(n, n);
      }
    }
  },
  /**
   * Create confirm dialog
   *
   * @param {String} headline Headline text
   * @param {String} actionLabel Label for the action button
   * @param {Function} action Event handler for the action button
   * @param {String} details Explanation text
   */
  confirm(headline, actionLabel, action, details) {
    const e = htmx.find("#confirm-dialog");
    e.innerHTML = `
            <div><h1>${headline}</h1></div>
            <p>${details ?? ""}</p>
            <div class="flex justify-end">
                <button class="btn-text" onclick="dialog.closeConfirm()">Cancel</button>
                <button class="btn-text" onclick="dialog.closeConfirm()">
                    ${actionLabel}
                </button>
            </div>
            `;
    htmx.on(htmx.find(e, "button:last-child"), "click", action);
  },
  /**
   * Close confirm dialog
   */
  closeConfirm() {
    htmx.find("#confirm-dialog").innerHTML = "";
  },
  /**
   * @param {Event} event - Triggering event
   */
  onHashChange(event) {
    if (location.hash) return;
    if (!this.pending) {
      this.close();
      return;
    }
    window.location.hash = "dialog";
    this.confirm("Discard draft?", "Discard", () => {
      this.close(true);
      history.back();
    });
  },
};

htmx.on(window, "hashchange", dialog.onHashChange.bind(dialog));
htmx.on("reset-dialog", dialog.reset.bind(dialog));
