"use strict";

const chips = {
  /**
   *
   * On input, add a chip
   *
   * @param {Event} evt - Triggering event
   * @param {String} name - Name of chip input
   */
  append(evt, name) {
    // If validation response, ignore event
    if (evt.detail.xhr.response) return;
    // If not enter key event, ignore event
    if (evt.detail.requestConfig.triggeringEvent.type !== "keydown") return;

    const tgt = evt.target;
    if (!tgt.value) {
      dialog.focusNext(tgt);
      return;
    }

    // Create a chip
    const chip = document.createElement("div");
    chip.innerHTML = `
      <input type="hidden" name="${name}" value="${tgt.value}" />
      ${tgt.value}
      <icon onclick="this.parentNode.remove()">clear</icon>
    `;

    tgt.parentNode.insertBefore(chip, tgt);
    tgt.value = "";
    tgt.scrollIntoView({
      block: "nearest",
      inline: "end",
      container: "nearest",
    });
  },
};
