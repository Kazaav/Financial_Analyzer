(function () {
  "use strict";

  /* ── Upload queue ─────────────────────────────────────────────── */
  function initUploader(container) {
    // The data-upload-queue attribute may be on the FORM itself or on a wrapping DIV.
    // Find the actual <form> element so FormData(form) works.
    var form = container.tagName === "FORM" ? container : container.querySelector("form");
    if (!form) return;
    var fileInput = container.querySelector("[data-file-input]");
    var fileList  = container.querySelector("[data-file-list]");
    var emptyState= container.querySelector("[data-empty-state]");
    var chooseBtn = container.querySelector("[data-choose-files]");
    var clearBtn  = container.querySelector("[data-clear-files]");
    var submitBtn = container.querySelector("[data-upload-submit], [type='submit']");
    var countEl   = container.querySelector("[data-file-count]");
    var dropZone  = container.querySelector("[data-drop-zone]") || container;
    var files     = [];

    if (!fileInput) return;

    function formatSize(bytes) {
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
      return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }

    function render() {
      if (fileList) {
        fileList.innerHTML = "";
        files.forEach(function (f, i) {
          var li = document.createElement("li");
          li.className = "queue-item";
          li.innerHTML =
            '<span class="queue-item-icon">&#128196;</span>' +
            '<span class="queue-name">' + escHtml(f.name) + '</span>' +
            '<span class="queue-meta">' + formatSize(f.size) + '</span>' +
            '<button type="button" class="remove-file" aria-label="削除" data-idx="' + i + '">&#10005;</button>';
          fileList.appendChild(li);
        });
        fileList.querySelectorAll(".remove-file").forEach(function (btn) {
          btn.addEventListener("click", function () {
            files.splice(Number(btn.dataset.idx), 1);
            render();
          });
        });
      }
      var count = files.length;
      if (countEl) countEl.textContent = count;
      if (emptyState) emptyState.hidden = count > 0;
      if (submitBtn) submitBtn.disabled = count === 0;
    }

    function addFiles(newFiles) {
      Array.from(newFiles).forEach(function (f) {
        if (f.name.toLowerCase().endsWith(".pdf")) files.push(f);
      });
      render();
    }

    function buildFormData(originalForm) {
      var fd = new FormData(originalForm);
      // Remove native file input entries and replace with queued files
      try { fd.delete("files"); } catch(e) {}
      files.forEach(function (f) { fd.append("files", f); });
      return fd;
    }

    // Intercept submit to inject queued files
    form.addEventListener("submit", function (e) {
      if (files.length === 0) { e.preventDefault(); return; }
      e.preventDefault();
      var fd = buildFormData(form);
      form.classList.add("is-uploading");
      if (submitBtn) submitBtn.disabled = true;
      fetch(form.action, { method: "POST", body: fd })
        .then(function (res) {
          if (res.redirected) { window.location.href = res.url; }
          else if (res.ok) { window.location.reload(); }
          else { form.classList.remove("is-uploading"); if (submitBtn) submitBtn.disabled = false; }
        })
        .catch(function () {
          form.classList.remove("is-uploading");
          if (submitBtn) submitBtn.disabled = false;
        });
    });

    fileInput.addEventListener("change", function () {
      addFiles(fileInput.files);
      fileInput.value = "";
    });
    if (chooseBtn) chooseBtn.addEventListener("click", function () { fileInput.click(); });
    if (clearBtn)  clearBtn.addEventListener("click",  function () { files = []; render(); });

    // Drag & drop
    dropZone.addEventListener("dragover", function (e) {
      e.preventDefault();
      dropZone.classList.add("is-dragging");
    });
    dropZone.addEventListener("dragleave", function (e) {
      if (!dropZone.contains(e.relatedTarget)) dropZone.classList.remove("is-dragging");
    });
    dropZone.addEventListener("drop", function (e) {
      e.preventDefault();
      dropZone.classList.remove("is-dragging");
      addFiles(e.dataTransfer.files);
    });

    // Make drop zone clickable as a whole (if no choose button)
    if (!chooseBtn) {
      dropZone.addEventListener("click", function () { fileInput.click(); });
    }

    render();
  }

  /* ── Delete form checkboxes ───────────────────────────────────── */
  function initDeleteForm(form) {
    var submitBtn = form.querySelector("[type='submit']");
    function update() {
      var checked = form.querySelectorAll("input[type='checkbox']:checked").length;
      if (submitBtn) submitBtn.disabled = checked === 0;
    }
    form.querySelectorAll("input[type='checkbox']").forEach(function (cb) {
      cb.addEventListener("change", update);
    });
    update();
  }

  /* ── Custom doc selection ─────────────────────────────────────── */
  function initDocumentSelectionTools(form) {
    var selectAll = form.querySelector("[data-doc-select-all]");
    var invert    = form.querySelector("[data-doc-invert]");
    var clear     = form.querySelector("[data-doc-clear]");
    var countEl   = form.querySelector("[data-doc-selected-count]");
    var list      = form.querySelector("[data-doc-selection-list]");

    function getBoxes() { return list ? Array.from(list.querySelectorAll("input[type='checkbox']")) : []; }
    function updateCount() {
      if (!countEl) return;
      countEl.textContent = getBoxes().filter(function (b) { return b.checked; }).length;
    }
    if (list) list.addEventListener("change", updateCount);
    if (selectAll) selectAll.addEventListener("click", function () {
      getBoxes().forEach(function (b) { b.checked = true; }); updateCount();
    });
    if (invert) invert.addEventListener("click", function () {
      getBoxes().forEach(function (b) { b.checked = !b.checked; }); updateCount();
    });
    if (clear) clear.addEventListener("click", function () {
      getBoxes().forEach(function (b) { b.checked = false; }); updateCount();
    });
    updateCount();
  }

  /* ── Inner switchers (ranking / chart metric) ─────────────────── */
  function initSwitchers() {
    document.querySelectorAll("[data-switcher]").forEach(function (container) {
      var buttons = Array.from(container.querySelectorAll("[data-switch-target]"));
      var panels  = Array.from(container.querySelectorAll("[data-switch-panel]"));
      function activate(target) {
        buttons.forEach(function (b) {
          var active = b.dataset.switchTarget === target;
          b.classList.toggle("is-active", active);
          b.setAttribute("aria-selected", active ? "true" : "false");
        });
        panels.forEach(function (p) {
          var active = p.dataset.switchPanel === target;
          p.classList.toggle("is-active", active);
          p.hidden = !active;
        });
      }
      buttons.forEach(function (b) {
        b.addEventListener("click", function () { activate(b.dataset.switchTarget); });
      });
      var first = buttons.find(function (b) { return b.classList.contains("is-active"); }) || buttons[0];
      if (first) activate(first.dataset.switchTarget);
    });
  }

  /* ── Category dashboard (metric / chart categories) ──────────── */
  function initMetricCategoryDashboards() {
    document.querySelectorAll("[data-category-dashboard]").forEach(function (dashboard) {
      var buttons = Array.from(dashboard.querySelectorAll("[data-category-target]"));
      var panels  = Array.from(dashboard.querySelectorAll("[data-category-panel]"));
      function activate(target) {
        buttons.forEach(function (b) {
          var active = b.dataset.categoryTarget === target;
          b.classList.toggle("is-active", active);
          b.setAttribute("aria-selected", active ? "true" : "false");
        });
        panels.forEach(function (p) {
          var active = p.dataset.categoryPanel === target;
          p.classList.toggle("is-active", active);
          p.hidden = !active;
        });
      }
      buttons.forEach(function (b) {
        b.addEventListener("click", function () { activate(b.dataset.categoryTarget); });
      });
      var first = buttons.find(function (b) { return b.classList.contains("is-active"); }) || buttons[0];
      if (first) activate(first.dataset.categoryTarget);
    });
  }

  /* ── Info tooltips (formula) ──────────────────────────────────── */
  function initInfoTooltips() {
    var triggers = document.querySelectorAll(".info-dot[data-info-tooltip]");
    if (!triggers.length) return;
    var tip = document.createElement("div");
    tip.className = "info-floating-tooltip";
    tip.hidden = true;
    document.body.appendChild(tip);
    function place(x, y) {
      tip.hidden = false;
      var m = 12, off = 14;
      var w = tip.offsetWidth || 280, h = tip.offsetHeight || 60;
      tip.style.left = Math.max(m, Math.min(x + off, window.innerWidth - w - m)) + "px";
      tip.style.top  = Math.max(m, Math.min(y - h - off, window.innerHeight - h - m)) + "px";
    }
    triggers.forEach(function (t) {
      t.addEventListener("pointerenter", function (e) {
        tip.textContent = t.dataset.infoTooltip || "";
        place(e.clientX, e.clientY);
      });
      t.addEventListener("pointermove", function (e) { place(e.clientX, e.clientY); });
      t.addEventListener("pointerleave", function ()  { tip.hidden = true; });
      t.addEventListener("focus", function () {
        tip.textContent = t.dataset.infoTooltip || "";
        var r = t.getBoundingClientRect();
        place(r.left, r.top);
      });
      t.addEventListener("blur", function () { tip.hidden = true; });
    });
  }

  /* ── Chart point / bar tooltips ──────────────────────────────── */
  function initTrendTooltips() {
    var points = document.querySelectorAll("[data-point-tooltip]");
    if (!points.length) return;
    var tip = document.createElement("div");
    tip.className = "trend-floating-tooltip";
    tip.hidden = true;
    document.body.appendChild(tip);
    function move(e) {
      var off = 14;
      tip.style.left = Math.min(e.clientX + off, window.innerWidth  - (tip.offsetWidth  || 200) - 12) + "px";
      tip.style.top  = Math.max(12, e.clientY - (tip.offsetHeight || 50) - off) + "px";
    }
    points.forEach(function (p) {
      p.addEventListener("pointerenter", function (e) { tip.textContent = p.dataset.pointTooltip || ""; tip.hidden = false; p.classList.add("is-active"); move(e); });
      p.addEventListener("pointermove", move);
      p.addEventListener("pointerleave", function () { tip.hidden = true; p.classList.remove("is-active"); });
      p.addEventListener("focus", function () {
        tip.textContent = p.dataset.pointTooltip || ""; tip.hidden = false; p.classList.add("is-active");
        var r = p.getBoundingClientRect();
        tip.style.left = Math.min(r.left + 12, window.innerWidth - 220) + "px";
        tip.style.top  = Math.max(12, r.top - 50) + "px";
      });
      p.addEventListener("blur", function () { tip.hidden = true; p.classList.remove("is-active"); });
    });
  }

  /* ── Tab navigation ───────────────────────────────────────────── */
  function initTabs() {
    var nav = document.querySelector("[data-tab-nav]");
    if (!nav) return;

    function activate(target, pushHash) {
      // Re-query each time so dynamically added/removed elements are not stale.
      var buttons = nav.querySelectorAll("[data-tab-target]");
      var panels  = document.querySelectorAll("[data-tab-panel]");
      buttons.forEach(function (b) {
        var active = b.dataset.tabTarget === target;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-selected", active ? "true" : "false");
      });
      panels.forEach(function (p) {
        var active = p.dataset.tabPanel === target;
        if (active) {
          p.removeAttribute("hidden");
        } else {
          p.setAttribute("hidden", "");
        }
      });
      if (pushHash && history.replaceState) {
        history.replaceState(null, "", "#tab-" + target);
      }
    }

    // Event delegation on the nav so clicks always reach this handler
    // regardless of init order, re-renders, or missing per-button listeners.
    nav.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-tab-target]");
      if (!btn || !nav.contains(btn)) return;
      e.preventDefault();
      activate(btn.dataset.tabTarget, true);
      // Bring sticky header back into view if user had scrolled deep into the
      // previous tab. With body-scroll layout this just works.
      window.scrollTo({ top: 0, behavior: "auto" });
    });

    // Restore from hash
    var hash = window.location.hash.replace("#tab-", "");
    var firstBtn = nav.querySelector("[data-tab-target]");
    var initialTarget = null;
    nav.querySelectorAll("[data-tab-target]").forEach(function (b) {
      if (b.dataset.tabTarget === hash) initialTarget = hash;
    });
    if (!initialTarget) {
      var activeBtn = nav.querySelector(".tab-btn.is-active[data-tab-target]");
      initialTarget = (activeBtn && activeBtn.dataset.tabTarget)
                   || (firstBtn && firstBtn.dataset.tabTarget);
    }
    if (initialTarget) activate(initialTarget, false);

    // If there's a flash notice (report generated, PDF added etc.) and we're
    // on default tab, that's fine. But if URL says manage, go there.
    var noticeEl = document.querySelector(".manage-notice");
    if (noticeEl && !hash) activate("manage", false);
  }

  /* ── Sidebar form: mode segmented control + auto-submit ──────── */
  function initSidebarForm() {
    var form = document.querySelector("[data-sidebar-form]");
    if (!form) return;

    var modeInput = form.querySelector("[data-mode-value]");
    var modeBtns  = Array.from(form.querySelectorAll("[data-mode-btn]"));
    var allModes  = ["same_year", "same_company", "custom"];

    function applyMode(newMode) {
      if (modeInput) modeInput.value = newMode;
      // Reset irrelevant filter values so stale params don't bleed across modes
      var yearSel    = form.querySelector("select[name='selected_year']");
      var companySel = form.querySelector("select[name='selected_company']");
      if (yearSel    && newMode !== "same_year")    yearSel.value    = "";
      if (companySel && newMode !== "same_company") companySel.value = "";
      // Update button active states
      modeBtns.forEach(function (b) {
        var active = b.dataset.modeBtn === newMode;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-selected", active ? "true" : "false");
      });
      // Swap form class so CSS shows the right filters immediately
      allModes.forEach(function (m) { form.classList.remove("mode-is-" + m); });
      form.classList.add("mode-is-" + newMode);
    }

    modeBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var newMode = btn.dataset.modeBtn;
        if (modeInput && modeInput.value === newMode) return;
        applyMode(newMode);
        if (newMode !== "custom") {
          form.submit(); // auto-navigate for simple modes
        }
        // custom: just reveals the filters; user clicks 分析を更新
      });
    });

    // Auto-submit on year / company selects
    form.querySelectorAll("[data-auto-submit]").forEach(function (el) {
      el.addEventListener("change", function () { form.submit(); });
    });

    // Keep chart-type-opt active class in sync with radio state
    form.querySelectorAll("input[name='chart_type']").forEach(function (radio) {
      radio.addEventListener("change", function () {
        form.querySelectorAll(".chart-type-opt").forEach(function (label) {
          var r = label.querySelector("input[type='radio']");
          label.classList.toggle("is-active", r ? r.checked : false);
        });
      });
    });
  }

  /* ── Escape HTML ──────────────────────────────────────────────── */
  function escHtml(str) {
    return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  /* ── Source page viewer (C3 PDF 原文モーダル) ──────────────────── */
  function initSourcePopup() {
    var modal = document.querySelector("[data-source-modal]");
    if (!modal) return;
    var imgEl     = modal.querySelector("[data-source-modal-image]");
    var loadingEl = modal.querySelector("[data-source-modal-loading]");
    var errorEl   = modal.querySelector("[data-source-modal-error]");
    var titleEl   = modal.querySelector("[data-source-modal-title]");
    var companyEl = modal.querySelector("[data-source-modal-company]");
    var sectionEl = modal.querySelector("[data-source-modal-section]");
    var labelEl   = modal.querySelector("[data-source-modal-label]");
    var pageEl    = modal.querySelector("[data-source-modal-page]");

    function open(btn) {
      var analysis = btn.dataset.sourceAnalysis;
      var docId    = btn.dataset.sourceDoc;
      var page     = btn.dataset.sourcePage;
      var label    = btn.dataset.sourceLabel || "";
      var section  = btn.dataset.sourceSection || "";
      var company  = btn.dataset.sourceCompany || "";
      var year     = btn.dataset.sourceYear || "";
      var metric   = btn.dataset.sourceMetric || "";

      companyEl.textContent = company + (year ? " · " + year + "年度" : "");
      titleEl.textContent   = metric;
      sectionEl.textContent = section;
      labelEl.textContent   = label;
      pageEl.textContent    = "PDF p." + page;

      imgEl.style.display = "none";
      errorEl.hidden = true;
      loadingEl.style.display = "block";
      modal.hidden = false;
      document.body.style.overflow = "hidden";

      var url = "/source-page/" + encodeURIComponent(analysis) + "/" + encodeURIComponent(docId) + "/" + encodeURIComponent(page) + ".png";
      imgEl.onload  = function () { loadingEl.style.display = "none"; imgEl.style.display = "block"; };
      imgEl.onerror = function () { loadingEl.style.display = "none"; errorEl.hidden = false; };
      imgEl.src = url + "?t=" + Date.now();
    }

    function close() {
      modal.hidden = true;
      document.body.style.overflow = "";
      imgEl.src = "";
    }

    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-source-popup]");
      if (btn) { e.preventDefault(); open(btn); return; }
      if (e.target.closest("[data-source-close]")) close();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !modal.hidden) close();
    });
  }

  /* ── Sidebar drawer toggle (mobile) ───────────────────────────── */
  function initSidebarDrawer() {
    var toggle = document.querySelector("[data-sidebar-toggle]");
    if (!toggle) return;
    var body = document.body;
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      body.classList.toggle("sidebar-open");
    });
    // Tap outside to close
    document.addEventListener("click", function (e) {
      if (!body.classList.contains("sidebar-open")) return;
      var sidebar = document.querySelector(".sidebar");
      if (sidebar && !sidebar.contains(e.target) && e.target !== toggle) {
        body.classList.remove("sidebar-open");
      }
    });
    // ESC closes
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") body.classList.remove("sidebar-open");
    });
  }

  /* ── Init ─────────────────────────────────────────────────────── */
  document.querySelectorAll("[data-upload-queue]").forEach(initUploader);
  document.querySelectorAll("[data-delete-form]").forEach(initDeleteForm);
  document.querySelectorAll("[data-doc-selection-form]").forEach(initDocumentSelectionTools);
  initSwitchers();
  initMetricCategoryDashboards();
  initInfoTooltips();
  initTrendTooltips();
  initTabs();
  initSidebarForm();
  initSidebarDrawer();
  initSourcePopup();
})();
