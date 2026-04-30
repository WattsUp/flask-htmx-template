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
    const controls = btn.parentElement;
    const exampleSnippet = htmx.find(controls, ".snippet-example");
    const schemaSnippet = htmx.find(controls, ".snippet-schema");

    const showExample = btn.classList.contains("btn-example");

    exampleSnippet.classList.toggle("hidden", !showExample);
    schemaSnippet.classList.toggle("hidden", showExample);

    const exampleBtn = htmx.find(controls, ".btn-example");
    const schemaBtn = htmx.find(controls, ".btn-schema");

    exampleBtn.classList.toggle("btn-tonal", showExample);
    exampleBtn.classList.toggle("btn-text", !showExample);
    schemaBtn.classList.toggle("btn-tonal", !showExample);
    schemaBtn.classList.toggle("btn-text", showExample);
  },
};
