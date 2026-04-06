"use strict";
/**
 * Get theme colors
 *
 * @param {String} name Name of color to get
 * @return {String} Hex string of color
 */
function getThemeColor(name) {
  const style = getComputedStyle(document.body);
  return style.getPropertyValue(`--color-${name}`);
}

/**
 * Downsample data to monthly min/max/avg values
 *
 * @param {Array} dates Array of sample dates
 * @param {Array} values Array of sample values
 * @return {Object} Object with the following keys
 * @return {Array} labels
 * @return {Array} min
 * @return {Array} max
 * @return {Array} avg
 */
function downsampleMonths(dates, values) {
  let labels = [];
  let min = [];
  let max = [];
  let avg = [];

  let currentMonth = dates[0].slice(0, 7);
  let currentMin = values[0];
  let currentMax = values[0];
  let currentSum = 0;
  let currentN = 0;
  for (let i = 0; i < dates.length; ++i) {
    let month = dates[i].slice(0, 7);
    let v = values[i];

    if (month != currentMonth) {
      labels.push(currentMonth);
      min.push(currentMin);
      max.push(currentMax);
      avg.push(currentSum / currentN);

      currentMonth = month;
      currentMin = v;
      currentMax = v;
      currentSum = 0;
      currentN = 0;
    }

    currentMin = Math.min(currentMin, v);
    currentMax = Math.max(currentMax, v);
    currentSum += v;
    ++currentN;
  }
  labels.push(currentMonth);
  min.push(currentMin);
  max.push(currentMax);
  avg.push(currentSum / currentN);

  return {
    labels: labels,
    min: min,
    max: max,
    avg: avg,
  };
}

/**
 * Create currency formatter from spec
 *
 * @param {Object} spec See Python side: Currency
 * @returns function(x: Number, coarse: Boolean = false): String
 */
function newCurrencyFormat(spec) {
  const formatter = new Intl.NumberFormat("nu", {
    useGrouping: "always",
    minimumFractionDigits: Math.max(0, spec.precision),
    maximumFractionDigits: Math.max(0, spec.precision),
  });
  const formatterCoarse = new Intl.NumberFormat("nu", {
    useGrouping: "always",
    minimumFractionDigits: Math.max(0, spec.precision_coarse),
    maximumFractionDigits: Math.max(0, spec.precision_coarse),
  });
  function format(x, coarse, formattedNumber) {
    coarse = coarse ?? false;

    let s = "";
    if (!spec.plus_is_prefix && !spec.symbol_is_suffix) s += spec.symbol;

    if (x < 0) {
      s += "-";
      x = -x;
    } else if (spec.plus) {
      s += "+";
    }

    if (spec.plus_is_prefix && !spec.symbol_is_suffix) s += spec.symbol;

    if (!formattedNumber) {
      let p = coarse ? spec.precision_coarse : spec.precision;
      let exp = Math.pow(10, p);

      x = Math.round(x * exp) / exp;

      formattedNumber = coarse
        ? formatterCoarse.format(x)
        : formatter.format(x);
    }
    s += formattedNumber.replaceAll(/[.,]/g, (g) => {
      return g == "." ? spec.sep_dec : spec.sep_1k;
    });

    if (spec.symbol_is_suffix) s += spec.symbol;

    return s;
  }

  return format;
}

/**
 * Format ticks as money
 *
 * @param {Number} value Value of current tick
 * @param {Number} index Index of current tick
 * @param {Object} ticks Array of all ticks
 * @return {String} Label for current tick
 */
function formatMoneyTicks(value, index, ticks) {
  if (index == 0) {
    const formatter0 = new Intl.NumberFormat("nu", {
      useGrouping: "always",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
    const formatter1 = new Intl.NumberFormat("nu", {
      useGrouping: "always",
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });

    const cf = this.chart.config.options.currencyFormat;
    const step = Math.abs(ticks[0].value - ticks[1].value);
    const smallest = Math.min(...ticks.map((t) => Math.abs(t.value)));
    ticks.forEach((t) => {
      let v = null;
      if (step >= 1_000_000) {
        v = formatter0.format(Math.abs(t.value / 1_000_000)) + "M";
      } else if (step >= 100_000 && smallest >= 1_000_000) {
        v = formatter1.format(Math.abs(t.value / 1_000_000)) + "M";
      } else if (step >= 1_000) {
        v = formatter0.format(Math.abs(t.value / 1_000)) + "k";
      } else if (step >= 100 && smallest >= 1_000) {
        v = formatter1.format(Math.abs(t.value / 1_000)) + "k";
      }
      t.label = cf(t.value, false, v);
    });
  }
  return ticks[index].label;
}

/**
 * Format ticks as percent
 *
 * @param {Number} value Value of current tick
 * @param {Number} index Index of current tick
 * @param {Object} ticks Array of all ticks
 * @return {String} Label for current tick
 */
function formatPercentTicks(value, index, ticks) {
  if (index == 0) {
    const step = Math.abs(ticks[0].value - ticks[1].value);
    const smallest = Math.min(...ticks.map((t) => Math.abs(t.value)));
    ticks.forEach((t) => {
      t.label = `${t.value.toFixed(0)}%`;
    });
  }
  return ticks[index].label;
}

/**
 * Format ticks as date
 *
 * @param {Number} value Value of current tick
 * @param {Number} index Index of current tick
 * @param {Object} ticks Array of all ticks
 * @return {String} Label for current tick
 */
function formatDateTicks(value, index, ticks) {
  if (index == 0) {
    const chart = this.chart;
    const labels = chart.data.labels;
    const dateMode = chart.config.options.scales.x.ticks.dateMode;
    switch (dateMode) {
      case "years":
        ticks.forEach((t, i) => {
          let l = labels[i];
          if (l.slice(-2) == "01") t.label = l.slice(0, 4);
        });
        break;
      case "months":
        formatDateTicksMonths.bind(this)(value, index, ticks);
        break;
      case "weeks":
        ticks.forEach((t, i) => {
          let l = labels[i];
          let date = new Date(l);
          // Mark each Sunday
          if (date.getUTCDay() == 0) t.label = l.slice(5, 10);
        });
        break;
      case "days":
        ticks.forEach((t, i) => (t.label = labels[i].slice(5, 10)));
        break;
      default:
        ticks.forEach((t, i) => (t.label = labels[i]));
        break;
    }
  }
  return ticks[index].label;
}

/**
 * Format ticks as month string
 *
 * @param {Number} value Value of current tick
 * @param {Number} index Index of current tick
 * @param {Object} ticks Array of all ticks
 * @return {String} Label for current tick
 */
function formatDateTicksMonths(value, index, ticks) {
  if (index == 0) {
    const chart = this.chart;
    const labels = chart.data.labels;
    const months = {
      "01": "Jan",
      "02": "Feb",
      "03": "Mar",
      "04": "Apr",
      "05": "May",
      "06": "Jun",
      "07": "Jul",
      "08": "Aug",
      "09": "Sep",
      10: "Oct",
      11: "Nov",
      12: "Dec",
    };
    ticks.forEach((t, i) => {
      let l = labels[i];
      if (l.length == 7 || l.slice(-2) == "01") {
        t.label = months[l.slice(5, 7)];
      }
    });
  }
  return ticks[index].label;
}

/**
 * Compute the average of an array
 *
 * @param {Array} array Array to compute over
 * @return {Number} Average value
 */
const average = (array) => array.reduce((a, b) => a + b) / array.length;

/**
 * Configures chart defaults
 */
function setChartDefaults() {
  Chart.defaults.font.family = "'liberation-sans', 'sans-serif'";
}

/**
 * Expand a range about the center
 *
 * @param {Number} min Minimum of range
 * @param {Number} max Maximum of range
 * @param {Number} number Expansion ratio 0.0 will not expand, 1.0 will double
 * @return {Object} Object with the following keys
 * @return {Number} min New range minimum
 * @return {Number} max New range maximum
 */
function widenRange(min, max, amount) {
  const center = (min + max) / 2;
  const range = (max - min) * (1 + amount);
  return { min: center - range / 2, max: center + range / 2 };
}

/**
 * Check if item is object
 *
 * @param {Object} item to check
 * @return {Boolean} true if item is an object
 */
function isObject(item) {
  return item && typeof item === "object" && !Array.isArray(item);
}

/**
 * Merge nested objects
 *
 * @param {Object} target Target object to merge into
 * @param {Object} sources Object keys to override
 * @return {Object} Merged objects
 */
function merge(target, ...sources) {
  if (!sources.length) return target;
  const source = sources.shift();

  if (isObject(target) && isObject(source)) {
    for (const key in source) {
      if (isObject(source[key])) {
        if (!target[key]) Object.assign(target, { [key]: {} });
        merge(target[key], source[key]);
      } else {
        Object.assign(target, { [key]: source[key] });
      }
    }
  }
  return merge(target, ...sources);
}

/**
 * Wrap words over multiple lines
 *
 * @param {Array} rawLines Array of original lines, will keep separate
 * @param {Number} maxWidth Maximum width of a lines
 * @param {Number} maxLines Maximum number of lines
 * @param {2DContext} ctx Canvas drawing context
 * @return {Array} Array of wrapped lines
 */
function word_wrap(rawLines, maxWidth, maxLines, ctx) {
  if (maxLines < 1) {
    return [];
  }
  const lines = [];
  for (const rawLine of rawLines) {
    if (!rawLine) {
      continue;
    }
    const words = rawLine.split(" ");
    let currentLine = null;
    for (const word of words) {
      const newLine = currentLine ? currentLine + " " + word : word;
      const width = ctx.measureText(newLine).width;
      if (width < maxWidth) {
        currentLine = newLine;
      } else if (currentLine) {
        const wordWidth = ctx.measureText(word).width;
        if (wordWidth >= maxWidth) {
          return lines;
        }
        lines.push(currentLine);
        if (lines.length == maxLines) {
          return lines;
        }
        currentLine = word;
      } else {
        // word alone doesn't fit
        return lines;
      }
    }
    if (currentLine) {
      lines.push(currentLine);
      if (lines.length == maxLines) {
        return lines;
      }
    }
  }
  return lines;
}

/**
 * On htmx send error, show error bar
 *
 * @param {Event} event Triggering event
 */
function appSendError(evt) {
  const url = evt.detail.pathInfo.finalRequestPath;
  const e = htmx.find("#hx-error");
  htmx.removeClass(e, "hidden");
  htmx.find(e, "span").innerHTML = `Failed to send request for '${url}'`;
}

/**
 * On htmx response error, show error bar
 *
 * @param {Event} event Triggering event
 */
function appResponseError(evt) {
  const e = htmx.find("#hx-error");
  htmx.removeClass(e, "hidden");
  htmx.find(e, "span").innerHTML = evt.detail.error;
}

/**
 * On changes, clear all page history and force a cache miss
 */
function appClearHistory() {
  setTimeout(() => {
    sessionStorage.removeItem("htmx-history-cache");
  }, 100);
}
htmx.on("clear-history", appClearHistory);

/**
 * On key press of a select label, go to the matching element, ignoring emojis
 *
 * @param {Event} evt - Triggering event
 */
function onSelectKey(evt) {
  const k = evt.key.toLowerCase();
  if (k.length != 1 || !k.match(/[a-z]/)) return;
  const e = evt.target;

  const values = [];
  for (const option of e.options) {
    if (option.disabled) continue;
    const cat = option.innerText.toLowerCase().trim();
    if (cat[0] == k) values[values.length] = option.value;
  }
  const i = values.indexOf(e.value) + 1;
  e.value = values[i % values.length];
}

/**
 * Add current timezone to HTMX requests
 *
 * @param {Event} evt - Triggering event
 */
function addTimezone(evt) {
  const d = new Date();
  evt.detail.headers["Timezone-Offset"] = d.getTimezoneOffset();
}

/** Update the colors of color swatches */
function updateColorSwatches() {
  htmx.findAll("div[color-spin]").forEach((e) => {
    const border = e.getAttribute("border");
    const bg = e.getAttribute("bg");
    const spin = Number(e.getAttribute("color-spin"));
    e.style.borderColor = tinycolor(getThemeColor(border))
      .spin(spin)
      .toHexString();
    e.style.backgroundColor =
      tinycolor(getThemeColor(bg)).spin(spin).toHexString() + "80";
  });
}

/*
 * DELETE is supposed to use request parameters but form is way better
 * htmx 2.x followed the spec properly, revert
 */
htmx.config.methodsThatUseUrlParams = ["get"];
