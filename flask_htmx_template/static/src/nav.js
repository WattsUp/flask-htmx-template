"use strict";
const nav = {
  barOn: true,
  overrideBarOff: false,
  lastToggleY: null,
  barHeight: null,
  barTranslate: 0,
  fabRatio: null,
  bar: null,
  fab: null,
  /**
   * On click, open nav-drawer
   */
  openDrawer: function () {
    htmx.addClass(htmx.find("#nav-drawer"), "open");
  },
  /**
   * On click of scrim, close nav-drawer
   *
   * @param {Event} evt Triggering event
   */
  closeDrawer: function (evt) {
    // if no event or clicking a label, close drawer
    if (!evt || evt.target.matches("a, a *, button, button *")) {
      htmx.removeClass(htmx.find("#nav-drawer"), "open");
    }
  },
  /**
   * On new page, update nav buttons to indicate active page
   */
  update: function () {
    const query = "nav button, nav a";
    const currentPath = window.location.pathname;
    htmx.findAll(query).forEach((e) => {
      const url = e && (e.getAttribute("hx-get") || e.getAttribute("hx-post"));
      const path = url && url.split("?")[0];
      if (path && path == currentPath) htmx.addClass(e, "nav-current");
      else htmx.removeClass(e, "nav-current");
    });
  },
  /**
   * On scroll down, hide nav elements. On up, show
   */
  onScroll: function () {
    // Only do stuff for mobile
    if (window.screen.width >= 768) {
      return;
    }
    const scrollY = window.scrollY;

    const hyst = 20;
    if (nav.lastToggleY == null) {
      nav.lastToggleY = scrollY;
    }

    if (nav.barOn) {
      nav.lastToggleY = Math.min(scrollY, nav.lastToggleY ?? scrollY);
      if (scrollY > nav.lastToggleY + hyst) {
        nav.updateBar(false);
      }
    } else {
      nav.lastToggleY = Math.max(scrollY, nav.lastToggleY ?? scrollY);
      if (scrollY < nav.lastToggleY - hyst) {
        nav.updateBar(true);
      }
    }
  },
  /**
   * Update bar translate
   *
   * @param {Boolean} on true show the bar
   */
  updateBar: function (on) {
    on = on ?? nav.barOn;
    nav.barOn = on;

    if (nav.overrideBarOff) on = false;

    if (nav.bar == null) nav.bar = htmx.find("#nav-bar");
    if (nav.barHeight == null) {
      const rect = nav.bar.getBoundingClientRect();
      nav.barHeight = rect.height;
    }

    if (nav.fab == null) nav.fab = htmx.find("#nav-fab");
    if (nav.fabRatio == null) {
      const rect = nav.fab.getBoundingClientRect();
      nav.fabRatio =
        (rect.width + window.screen.width - rect.right) / nav.barHeight;
    }

    nav.barTranslate = on ? 0 : nav.barHeight * 1.1;
    const fabTranslate = nav.barTranslate * nav.fabRatio;

    nav.bar.style.translate = `0 ${nav.barTranslate}px`;
    nav.fab.style.translate = `${fabTranslate}px ${-nav.barTranslate}px`;
  },
  /**
   * Set override to force close the bar
   *
   * @param {Boolean} on true will unset the override
   */
  setOverrideBarOff: function (on) {
    nav.overrideBarOff = !(on ?? false);
    nav.updateBar();
  },
};

htmx.on(window, "scroll", nav.onScroll);
htmx.onLoad(nav.update);
