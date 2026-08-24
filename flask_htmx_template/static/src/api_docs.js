"use strict";

const apiDocs = {
  /**
   * Copy the configured API bearer token and announce the result.
   *
   * @param {Event} evt - Click event from the copy button
   */
  async copyBearerToken(evt) {
    const button = evt.currentTarget;
    const token = document.getElementById("api-bearer-token");
    const status = document.getElementById("api-bearer-token-copy-status");
    if (!button || !token || !status) return;

    const value = token.textContent.trim();

    let copied = false;
    try {
      if (!navigator.clipboard?.writeText)
        throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(value);
      copied = true;
    } catch (_error) {
      // NOTE: Clipboard API access can be unavailable outside secure contexts.
      const fallback = document.createElement("textarea");
      fallback.value = value;
      fallback.setAttribute("readonly", "");
      fallback.style.position = "fixed";
      fallback.style.opacity = "0";
      try {
        document.body.appendChild(fallback);
        fallback.select();
        copied = document.execCommand("copy");
      } catch (_fallbackError) {
        copied = false;
      } finally {
        fallback.remove();
      }
    }

    status.textContent = copied
      ? "Bearer token copied to clipboard."
      : "Unable to copy bearer token.";
    button.setAttribute(
      "aria-label",
      copied ? "Bearer token copied" : "Copy bearer token",
    );
  },

  /**
   * Switch between example and schema snippet views for a response entry.
   *
   * Expects the button's parent to be immediately followed by the
   * snippet-example and snippet-schema elements as siblings.
   *
   * @param {Event} evt - Click event from a snippet toggle button
   */
  loadSnippet(evt) {
    const btn = evt.currentTarget;
    if (btn.classList.contains("btn-tonal")) return;

    const controls = btn.parentElement;
    const exampleSnippet = controls.nextElementSibling;
    const schemaSnippet = exampleSnippet.nextElementSibling;

    htmx.toggleClass(exampleSnippet, "hidden");
    htmx.toggleClass(schemaSnippet, "hidden");

    const exampleBtn = htmx.find(controls, ".btn-example");
    const schemaBtn = htmx.find(controls, ".btn-schema");

    htmx.toggleClass(exampleBtn, "btn-tonal");
    htmx.toggleClass(exampleBtn, "btn-text");
    htmx.toggleClass(schemaBtn, "btn-tonal");
    htmx.toggleClass(schemaBtn, "btn-text");
  },
};
