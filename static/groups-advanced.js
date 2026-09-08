/* Advanced duplicate listing — Directory Printer-style field picker. */
(() => {
  const KEY = "mmc-group-cols-v1";

  const FIELDS = [
    { id: "role", label: "Role (KEEP / extra)", on: true },
    { id: "title", label: "Group title", on: true },
    { id: "kind", label: "Kind", on: false },
    { id: "drive", label: "Drive", on: true },
    { id: "file", label: "File name", on: true },
    { id: "stem", label: "Name without extension", on: false },
    { id: "ext", label: "Extension", on: false },
    { id: "path", label: "Full path", on: false },
    { id: "size", label: "File size", on: true },
    { id: "score", label: "Score", on: true },
    { id: "summary", label: "Quality summary", on: true },
    { id: "res", label: "Resolution", on: false },
    { id: "vcodec", label: "Video codec", on: false },
    { id: "acodec", label: "Audio codec", on: false },
    { id: "source", label: "Source", on: false },
    { id: "hdr", label: "HDR", on: false },
    { id: "duration", label: "Duration", on: false },
    { id: "edition", label: "Edition", on: false },
  ];

  function loadState() {
    try {
      const raw = JSON.parse(localStorage.getItem(KEY) || "null");
      if (!raw || !Array.isArray(raw.fields)) return { fields: FIELDS.map((f) => ({ ...f })) };
      const byId = Object.fromEntries(FIELDS.map((f) => [f.id, f]));
      const seen = new Set();
      const fields = [];
      raw.fields.forEach((item) => {
        if (!item || !byId[item.id] || seen.has(item.id)) return;
        seen.add(item.id);
        fields.push({ ...byId[item.id], on: Boolean(item.on) });
      });
      FIELDS.forEach((f) => {
        if (!seen.has(f.id)) fields.push({ ...f });
      });
      return { fields };
    } catch (_err) {
      return { fields: FIELDS.map((f) => ({ ...f })) };
    }
  }

  function saveState(state) {
    localStorage.setItem(KEY, JSON.stringify({ fields: state.fields }));
  }

  function visible(state) {
    return state.fields.filter((f) => f.on);
  }

  function applyColumns(state) {
    const order = visible(state).map((f) => f.id);
    document.querySelectorAll("[data-adv-table] tr").forEach((tr) => {
      const cells = [...tr.children].filter((el) => el.dataset && el.dataset.col);
      const map = {};
      cells.forEach((el) => {
        map[el.dataset.col] = el;
      });
      order.forEach((id) => {
        if (map[id]) tr.appendChild(map[id]);
      });
      cells.forEach((el) => {
        el.hidden = !order.includes(el.dataset.col);
      });
    });
    document.querySelectorAll("[data-span]").forEach((el) => {
      el.colSpan = Math.max(1, order.length);
    });
  }

  function renderPicker(host, state) {
    host.innerHTML = "";
    state.fields.forEach((field, index) => {
      const row = document.createElement("label");
      row.className = "fi-row" + (field.on ? " on" : "");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = field.on;
      box.addEventListener("change", () => {
        field.on = box.checked;
        saveState(state);
        renderPicker(host, state);
        applyColumns(state);
      });
      const name = document.createElement("span");
      name.textContent = field.label;
      const up = document.createElement("button");
      up.type = "button";
      up.className = "btn small";
      up.textContent = "↑";
      up.disabled = index === 0;
      up.addEventListener("click", () => {
        if (index === 0) return;
        const tmp = state.fields[index - 1];
        state.fields[index - 1] = state.fields[index];
        state.fields[index] = tmp;
        saveState(state);
        renderPicker(host, state);
        applyColumns(state);
      });
      const down = document.createElement("button");
      down.type = "button";
      down.className = "btn small";
      down.textContent = "↓";
      down.disabled = index === state.fields.length - 1;
      down.addEventListener("click", () => {
        if (index === state.fields.length - 1) return;
        const tmp = state.fields[index + 1];
        state.fields[index + 1] = state.fields[index];
        state.fields[index] = tmp;
        saveState(state);
        renderPicker(host, state);
        applyColumns(state);
      });
      row.appendChild(box);
      row.appendChild(name);
      row.appendChild(up);
      row.appendChild(down);
      host.appendChild(row);
    });
  }

  function compareValues(a, b, numeric) {
    if (numeric) return (Number(a) || 0) - (Number(b) || 0);
    return String(a || "").localeCompare(String(b || ""), undefined, {
      numeric: true,
      sensitivity: "base",
    });
  }

  function sortFiles() {
    const field = (document.querySelector("[data-file-sort]") || {}).value || "name";
    const desc = Boolean(document.querySelector("[data-file-desc]:checked"));
    const numeric = field === "size" || field === "score";
    document.querySelectorAll("[data-group-body]").forEach((body) => {
      const rows = [...body.querySelectorAll("tr[data-file]")];
      rows.sort((a, b) => {
        const av = a.getAttribute("data-" + field) || "";
        const bv = b.getAttribute("data-" + field) || "";
        const cmp = compareValues(av, bv, numeric);
        return desc ? -cmp : cmp;
      });
      rows.forEach((row) => body.appendChild(row));
    });
  }

  function setListingMode() {
    const mode = (document.querySelector("[data-list-mode]:checked") || {}).value || "both";
    document.querySelectorAll("[data-group-head], [data-group-foot]").forEach((el) => {
      el.hidden = mode === "files";
    });
    document.querySelectorAll("tr[data-file] [data-col='title']").forEach((el) => {
      el.classList.toggle("col-quiet", mode === "both");
    });
  }

  function csvEscape(value) {
    const text = String(value || "").replace(/\r?\n/g, " ");
    if (/[",]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
    return text;
  }

  function saveListing(state) {
    const cols = visible(state);
    const lines = [cols.map((c) => csvEscape(c.label)).join(",")];
    document.querySelectorAll("[data-adv-table] tbody tr[data-file]").forEach((tr) => {
      const cells = {};
      [...tr.children].forEach((td) => {
        if (td.dataset.col) cells[td.dataset.col] = td.innerText.trim();
      });
      lines.push(cols.map((c) => csvEscape(cells[c.id] || "")).join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "duplicate-listing.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  ready(() => {
    const root = document.querySelector("[data-advanced]");
    if (!root) return;
    const picker = root.querySelector("[data-file-info]");
    const state = loadState();
    renderPicker(picker, state);
    applyColumns(state);
    sortFiles();
    setListingMode();

    root.querySelectorAll("[data-file-sort], [data-file-desc], [data-file-asc]").forEach((el) => {
      el.addEventListener("change", sortFiles);
    });
    root.querySelectorAll("[data-list-mode]").forEach((el) => {
      el.addEventListener("change", setListingMode);
    });
    const saveBtn = root.querySelector("[data-save-listing]");
    if (saveBtn) saveBtn.addEventListener("click", () => saveListing(state));
    const printBtn = root.querySelector("[data-print-listing]");
    if (printBtn) printBtn.addEventListener("click", () => window.print());
  });
})();
