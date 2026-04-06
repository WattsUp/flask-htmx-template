"use strict";
const snackbar = {
  duration: 2500,
  timeout: null,
  /**
   * Show snackbar with a message
   *
   * @param {String} msg Message to display
   */
  show: function (msg) {
    const e = htmx.find("#snackbar");
    e.innerHTML = msg;
    htmx.addClass(e, "open");

    if (self.timeout) clearTimeout(self.timeout);
    self.timeout = setTimeout(this.hide, this.duration);
  },
  /**
   * Hide the snackbar
   */
  hide: function () {
    const e = htmx.find("#snackbar");
    htmx.removeClass(e, "open");
  },
};
