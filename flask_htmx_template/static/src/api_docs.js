"use strict";

const apiDocs = {
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
