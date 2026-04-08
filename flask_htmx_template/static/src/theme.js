"use strict";
const themeEdit = {
  _timer: null,

  /**
   * Initialize the theme editor.
   *
   * @param {string} swatch - Current swatch hex color (e.g. "#3f6837")
   * @param {string} mood - Current mood name (e.g. "TONAL_SPOT")
   */
  init(swatch, mood) {
    const hue = Math.round(tinycolor(swatch).toHsl().h);
    const slider = htmx.find("#theme-hue");
    slider.value = hue;
    this._updateSwatch(hue);

    htmx.on(slider, "input", () => {
      this._updateSwatch(parseInt(slider.value));
      this._schedulePreview();
    });

    const moodSelect = htmx.find("#theme-mood-select");
    moodSelect.value = mood;
    htmx.on(moodSelect, "change", () => this._schedulePreview());
  },

  /**
   * Update the visible swatch preview and the hidden swatch value.
   *
   * @param {number} hue - Hue 0–359
   */
  _updateSwatch(hue) {
    const hex = tinycolor({ h: hue, s: 0.6, l: 0.4 }).toHexString();
    htmx.find("#theme-preview-swatch").style.background = hex;
    htmx.find("#theme-swatch").value = hex;
  },

  _schedulePreview() {
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this._preview(), 400);
  },

  /**
   * Fetch /theme.css with current swatch+mood and inject via #theme-live.
   */
  _preview() {
    const swatch = htmx.find("#theme-swatch").value;
    const mood = htmx.find("#theme-mood-select").value;
    htmx.find("#theme-mood-hidden").value = mood;
    const link = htmx.find("#theme-live");
    link.href = `/theme.css?swatch=${encodeURIComponent(swatch)}&mood=${encodeURIComponent(mood)}`;
  },
};
