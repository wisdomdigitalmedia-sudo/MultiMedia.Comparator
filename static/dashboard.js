/* Dashboard charts, nav glider, skeleton hydrate, long-job veil. */
(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  function easeOut(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function animate(duration, draw) {
    if (reduce) {
      draw(1);
      return;
    }
    const start = performance.now();
    function frame(now) {
      const t = Math.min(1, (now - start) / duration);
      draw(easeOut(t));
      if (t < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function el(tag, attrs, children) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, String(v)));
    (children || []).forEach((c) => node.appendChild(c));
    return node;
  }

  function moveGlider() {
    const nav = document.querySelector("[data-nav-desk]");
    const glider = nav && nav.querySelector(".nav-glider");
    const current = nav && nav.querySelector('[aria-current="page"]');
    if (!nav || !glider || !current) return;
    const nr = nav.getBoundingClientRect();
    const cr = current.getBoundingClientRect();
    glider.style.width = `${cr.width}px`;
    glider.style.transform = `translateX(${cr.left - nr.left}px)`;
  }

  let veilTimer = null;
  let veilTick = null;
  let veilStarted = 0;

  function processingVeil() {
    return document.querySelector("[data-veil]");
  }

  function hideProcessing() {
    const veil = processingVeil();
    if (veilTimer) {
      clearTimeout(veilTimer);
      veilTimer = null;
    }
    if (veilTick) {
      clearInterval(veilTick);
      veilTick = null;
    }
    if (!veil) return;
    veil.classList.remove("on");
    veil.setAttribute("aria-hidden", "true");
  }

  function showProcessing(title, copy) {
    const veil = processingVeil();
    if (!veil) return;
    if (veilTimer) {
      clearTimeout(veilTimer);
      veilTimer = null;
    }
    const heading = veil.querySelector("[data-veil-title]");
    const body = veil.querySelector("[data-veil-copy]");
    const elapsed = veil.querySelector("[data-veil-elapsed]");
    if (heading) heading.textContent = title || "Working…";
    if (body) {
      body.textContent =
        copy ||
        "Stay on this page. The overlay means the app is running — not the browser tab spinner.";
    }
    veilStarted = Date.now();
    if (elapsed) elapsed.textContent = "";
    if (veilTick) clearInterval(veilTick);
    veilTick = setInterval(() => {
      const s = Math.floor((Date.now() - veilStarted) / 1000);
      if (!elapsed) return;
      if (s < 5) elapsed.textContent = "Starting…";
      else elapsed.textContent = `${s}s elapsed — still working`;
    }, 250);
    veil.classList.add("on");
    veil.setAttribute("aria-hidden", "false");
  }

  function scheduleProcessing(title, delayMs) {
    if (veilTimer) clearTimeout(veilTimer);
    veilTimer = setTimeout(() => {
      showProcessing(title || "Still working…");
    }, delayMs == null ? 5000 : delayMs);
  }

  function bindVeil() {
    const veil = processingVeil();
    if (!veil) return;

    document.addEventListener("submit", (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      const method = (form.getAttribute("method") || "get").toLowerCase();
      const submitter = event.submitter;
      const label =
        (submitter && submitter.getAttribute("data-slow")) ||
        form.getAttribute("data-slow");
      if (label) {
        showProcessing(label);
        return;
      }
      if (method === "post") {
        scheduleProcessing("Still working…", 5000);
      }
    });

    window.addEventListener("pageshow", (event) => {
      if (event.persisted) hideProcessing();
    });
  }

  function bindDeleteModal() {
    const modal = document.querySelector("[data-del-modal]");
    if (!modal) return;
    const step1 = modal.querySelector('[data-del-step="1"]');
    const step2 = modal.querySelector('[data-del-step="2"]');
    const form = modal.querySelector("[data-del-form]");

    function close() {
      modal.classList.remove("on");
      modal.setAttribute("aria-hidden", "true");
      if (step1) step1.hidden = false;
      if (step2) step2.hidden = true;
      if (form) form.reset();
    }

    function fill(sel, text) {
      const node = modal.querySelector(sel);
      if (node) node.textContent = text || "";
    }

    function openFrom(btn) {
      const path = btn.getAttribute("data-path") || "";
      const name = btn.getAttribute("data-name") || "";
      const drive = btn.getAttribute("data-drive") || "";
      const size = btn.getAttribute("data-size") || "";
      const keep = btn.getAttribute("data-keep") === "1";
      const group = btn.getAttribute("data-group") || "";
      if (!path) return;
      fill("[data-del-name]", name);
      fill("[data-del-path]", path);
      fill("[data-del-meta]", [drive, size].filter(Boolean).join(" · "));
      fill("[data-del-name-2]", name);
      fill("[data-del-path-2]", path);
      fill("[data-del-meta-2]", [drive, size].filter(Boolean).join(" · "));
      modal.querySelectorAll("[data-del-keep], [data-del-keep-2]").forEach((el) => {
        el.hidden = !keep;
      });
      if (form) {
        form.path.value = path;
        form.confirm_path.value = path;
        form.group_key.value = group;
        form.next.value = window.location.pathname + window.location.search;
        const keepField = form.querySelector("[data-del-keep-field]");
        if (keepField) keepField.value = keep ? "yes" : "";
      }
      if (step1) step1.hidden = false;
      if (step2) step2.hidden = true;
      modal.classList.add("on");
      modal.setAttribute("aria-hidden", "false");
    }

    document.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-delete-file]");
      if (btn) {
        event.preventDefault();
        openFrom(btn);
      }
    });
    modal.querySelectorAll("[data-del-cancel]").forEach((btn) => {
      btn.addEventListener("click", close);
    });
    const cont = modal.querySelector("[data-del-continue]");
    if (cont) {
      cont.addEventListener("click", () => {
        if (step1) step1.hidden = true;
        if (step2) step2.hidden = false;
      });
    }
    modal.addEventListener("click", (event) => {
      if (event.target === modal) close();
    });
  }

  function countUp(node, to, suffix) {
    if (!node) return;
    const target = Number(to);
    if (!Number.isFinite(target)) {
      node.textContent = "—";
      return;
    }
    animate(900, (p) => {
      const val = target * p;
      const digits = target < 10 ? 1 : 0;
      node.textContent = `${val.toFixed(digits)}${suffix || ""}`;
    });
  }

  function drawRing(host, pctFree) {
    const svg = host.querySelector("svg");
    if (!svg) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const size = 220;
    const cx = 110;
    const cy = 110;
    const r = 84;
    const c = 2 * Math.PI * r;
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    svg.appendChild(
      el("circle", {
        cx, cy, r,
        fill: "none",
        stroke: "#1e293b",
        "stroke-width": 16,
      })
    );
    const arc = el("circle", {
      cx, cy, r,
      fill: "none",
      stroke: "url(#freeGrad)",
      "stroke-width": 16,
      "stroke-linecap": "round",
      transform: `rotate(-90 ${cx} ${cy})`,
      "stroke-dasharray": `${c}`,
      "stroke-dashoffset": `${c}`,
    });
    const defs = el("defs", {}, [
      el("linearGradient", { id: "freeGrad", x1: "0%", y1: "0%", x2: "100%", y2: "0%" }, [
        el("stop", { offset: "0%", "stop-color": "#14b8a6" }),
        el("stop", { offset: "100%", "stop-color": "#5eead4" }),
      ]),
    ]);
    svg.appendChild(defs);
    svg.appendChild(arc);
    const known = pctFree != null && Number.isFinite(Number(pctFree));
    const dest = known ? Math.max(0, Math.min(100, Number(pctFree))) / 100 : 0;
    animate(1100, (p) => {
      arc.setAttribute("stroke-dashoffset", String(c * (1 - dest * p)));
    });
  }

  function drawColumns(host, drives) {
    const svg = host.querySelector("svg");
    if (!svg) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const known = drives.filter((d) => d.capacity_known);
    const w = host.clientWidth || 640;
    const h = Math.max(220, Math.min(320, Math.round(w * 0.38)));
    const pad = { t: 18, r: 12, b: 42, l: 12 };
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", String(h));
    svg.setAttribute("role", "img");
    svg.setAttribute(
      "aria-label",
      known.length
        ? `Free space for ${known.length} drives with reported capacity`
        : "No capacity figures to chart"
    );

    if (!known.length) return;

    const innerW = w - pad.l - pad.r;
    const innerH = h - pad.t - pad.b;
    const gap = Math.max(8, Math.min(18, innerW / known.length / 4));
    const barW = Math.max(16, (innerW - gap * (known.length - 1)) / known.length);
    const maxFree = Math.max(...known.map((d) => d.free_bytes || 0), 1);

    known.forEach((d, i) => {
      const x = pad.l + i * (barW + gap);
      const frac = (d.free_bytes || 0) / maxFree;
      const barH = Math.max(4, innerH * frac);
      const y = pad.t + innerH;
      const tone =
        d.tone === "critical" ? "#fb7185" : d.tone === "warn" ? "#f5c14a" : "#5eead4";
      const g = el("g", {});
      const track = el("rect", {
        x,
        y: pad.t,
        width: barW,
        height: innerH,
        rx: 7,
        fill: "#0b1016",
      });
      const bar = el("rect", {
        x,
        y,
        width: barW,
        height: 0,
        rx: 7,
        fill: tone,
      });
      const label = el("text", {
        x: x + barW / 2,
        y: h - 14,
        fill: "#9aa6b6",
        "font-size": known.length > 8 ? 10 : 12,
        "text-anchor": "middle",
        "font-family": "Segoe UI, system-ui, sans-serif",
      });
      label.textContent = d.letter || (d.name || "?").slice(0, 2);
      const title = el("title", {});
      title.textContent = `${d.name}: ${d.free_label} free of ${d.total_label}`;
      g.appendChild(title);
      g.appendChild(track);
      g.appendChild(bar);
      g.appendChild(label);
      svg.appendChild(g);
      animate(900 + i * 40, (p) => {
        const hh = barH * p;
        bar.setAttribute("height", String(hh));
        bar.setAttribute("y", String(y - hh));
      });
    });
  }

  function fillMeters() {
    document.querySelectorAll("[data-meter]").forEach((node, i) => {
      const pct = Number(node.getAttribute("data-meter"));
      const fill = node.querySelector("i");
      if (!fill || !Number.isFinite(pct)) return;
      const apply = () => {
        fill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
      };
      if (reduce) apply();
      else setTimeout(apply, 80 + i * 45);
    });
  }

  function setCapacityStatus(text, show) {
    document.querySelectorAll("[data-capacity-status]").forEach((node) => {
      if (show && text) node.textContent = text;
      node.hidden = !show;
    });
  }

  function hydrateDashboard(data) {
    const root = document.querySelector("[data-dashboard]");
    if (!root) return;
    window.__DASHBOARD__ = data;
    root.setAttribute("data-ready", "1");

    const freePct = data.space && data.space.free_pct;
    const ringHost = root.querySelector("[data-ring]");
    if (ringHost) drawRing(ringHost, freePct);
    countUp(root.querySelector("[data-count-free]"), freePct, "%");

    const colHost = root.querySelector("[data-cols]");
    if (colHost) {
      drawColumns(colHost, data.drives || []);
      if (!colHost.dataset.ro) {
        colHost.dataset.ro = "1";
        const ro = new ResizeObserver(() => {
          const latest = window.__DASHBOARD__;
          drawColumns(colHost, (latest && latest.drives) || []);
        });
        ro.observe(colHost);
      }
    }
    fillMeters();
  }

  async function loadDashboard() {
    const root = document.querySelector("[data-dashboard]");
    if (!root) return;
    const fallback = window.__DASHBOARD__ || null;
    let data = fallback;
    try {
      const res = await fetch("/api/dashboard", { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error("dashboard api");
      data = await res.json();
      hydrateDashboard(data);
    } catch (_err) {
      if (fallback) hydrateDashboard(fallback);
      else root.setAttribute("data-ready", "1");
    }

    const unknown =
      (data && data.space && data.space.unknown_count) ||
      Number(root.getAttribute("data-unknown") || "0");
    if (!unknown) return;

    setCapacityStatus("Reading sizes from the media host…", true);
    scheduleProcessing("Reading drive sizes from the media host…", 5000);
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 60000);
      const res = await fetch("/api/dashboard?fill=1", {
        headers: { Accept: "application/json" },
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      hideProcessing();
      if (!res.ok) throw new Error("capacity fill");
      const filled = await res.json();
      const before = Number(root.getAttribute("data-known") || "0");
      const after = (filled.space && filled.space.known_count) || 0;
      if (after > before) {
        location.reload();
        return;
      }
      const err = filled.capacity_fill && (filled.capacity_fill.errors || [])[0];
      setCapacityStatus(
        err
          ? `Could not fill remaining sizes (${err})`
          : "Those volumes still have no size from the agent.",
        true
      );
    } catch (_err) {
      hideProcessing();
      setCapacityStatus("Could not reach the media-host agent for missing sizes.", true);
    }
  }

  ready(() => {
    moveGlider();
    window.addEventListener("resize", moveGlider);
    bindVeil();
    bindDeleteModal();
    loadDashboard();
    if (!document.querySelector("[data-dashboard]")) fillMeters();
  });
})();
