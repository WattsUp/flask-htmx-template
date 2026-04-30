"use strict";

const apiDocs = {
  /**
   * Switch between example and schema snippet views for a response entry.
   *
   * Expects the button's parent to contain snippet-example and snippet-schema
   * elements as well as btn-example and btn-schema buttons.
   *
   * @param {Event} evt - Click event from a snippet toggle button
   */
  loadSnippet(evt) {
    const btn = evt.currentTarget;
    if (btn.classList.contains("btn-tonal")) return;

    const details = htmx.closest(btn, "details");
    const exampleSnippet = htmx.find(details, ".snippet-example");
    const schemaSnippet = htmx.find(details, ".snippet-schema");

    htmx.toggleClass(exampleSnippet, "hidden");
    htmx.toggleClass(schemaSnippet, "hidden");

    const exampleBtn = htmx.find(details, ".btn-example");
    const schemaBtn = htmx.find(details, ".btn-schema");

    htmx.toggleClass(exampleBtn, "btn-tonal");
    htmx.toggleClass(exampleBtn, "btn-text");
    htmx.toggleClass(schemaBtn, "btn-tonal");
    htmx.toggleClass(schemaBtn, "btn-text");
  },
};
