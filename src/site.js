/* Patrik Novák – fotografie. Bez knihoven: úvodní prolínání, prohlížeč fotografií, formulář. */
(function () {
  "use strict";
  var doc = document, root = doc.documentElement;
  var T = {};
  try { T = JSON.parse(doc.getElementById("i18n").textContent); } catch (e) {}
  var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── ochrana fotografií ─────────────────────────────── */
  if (root.classList.contains("protect")) {
    doc.addEventListener("contextmenu", function (e) {
      if (e.target && e.target.tagName === "IMG") e.preventDefault();
    });
    doc.addEventListener("dragstart", function (e) {
      if (e.target && e.target.tagName === "IMG") e.preventDefault();
    });
  }

  /* ── úvodní stránka: pomalé prolínání ───────────────── */
  var hero = doc.querySelector(".hero");
  if (hero) {
    var slides = [].slice.call(hero.querySelectorAll(".slide"));
    var at = 0, timer = null;
    var wake = function (s) {
      var img = s.querySelector("img");
      if (img && img.dataset.srcset) {
        img.srcset = img.dataset.srcset; img.src = img.dataset.src;
        delete img.dataset.srcset;
      }
      return img;
    };
    var step = function () {
      var next = (at + 1) % slides.length, img = wake(slides[next]);
      var go = function () {
        slides[at].classList.remove("on"); slides[next].classList.add("on"); at = next;
        if (slides.length > 1) wake(slides[(at + 1) % slides.length]);
      };
      if (img.complete && img.naturalWidth) go();
      else { img.addEventListener("load", go, { once: true }); }
    };
    if (slides.length > 1 && !calm) {
      window.addEventListener("load", function () {
        wake(slides[1]);
        timer = setInterval(function () { if (!doc.hidden) step(); }, 6500);
      });
    }
  }

  /* ── prohlížeč fotografií ───────────────────────────── */
  var links = [].slice.call(doc.querySelectorAll(".grid a"));
  if (links.length) {
    var lb = doc.createElement("div");
    lb.className = "lb"; lb.setAttribute("role", "dialog"); lb.setAttribute("aria-modal", "true");
    lb.setAttribute("aria-label", T.viewer || "");
    var arrow = function (d) {
      return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + d + '"/></svg>';
    };
    lb.innerHTML =
      '<div class="stage"><img alt="" draggable="false"></div>' +
      '<button class="nav prev" type="button" aria-label="' + (T.prev || "") + '">' + arrow("M15 4l-8 8 8 8") + "</button>" +
      '<button class="nav next" type="button" aria-label="' + (T.next || "") + '">' + arrow("M9 4l8 8-8 8") + "</button>" +
      '<button class="x" type="button" aria-label="' + (T.close || "") + '">' + arrow("M5 5l14 14M19 5L5 19") + "</button>" +
      '<div class="count" aria-live="polite"></div>';
    doc.body.appendChild(lb);
    var stage = lb.querySelector(".stage"), pic = stage.querySelector("img"), count = lb.querySelector(".count");
    var cur = -1, opener = null;

    var fit = function (a) {
      var w = +a.dataset.w, h = +a.dataset.h, r = stage.getBoundingClientRect();
      return Math.max(1, Math.round(Math.min(r.width, r.height * w / h, w)));
    };
    var show = function (i, quiet) {
      cur = (i + links.length) % links.length;
      var a = links[cur];
      pic.classList.remove("ready");
      var fresh = new Image();
      fresh.sizes = fit(a) + "px";
      fresh.srcset = a.dataset.m + " " + a.dataset.mw + "w, " + a.href + " " + a.dataset.w + "w";
      fresh.src = a.href;
      var mine = cur;
      var put = function () {
        if (mine !== cur) return;
        pic.sizes = fresh.sizes; pic.srcset = fresh.srcset; pic.src = fresh.currentSrc || fresh.src;
        pic.alt = a.querySelector("img").alt;
        pic.width = +a.dataset.w; pic.height = +a.dataset.h;
        requestAnimationFrame(function () { pic.classList.add("ready"); });
      };
      if (fresh.decode) fresh.decode().then(put, put); else fresh.onload = put;
      count.textContent = (cur + 1) + " / " + links.length;
      if (!quiet) history.replaceState(null, "", "#" + (cur + 1));
      var n = links[(cur + 1) % links.length], pre = new Image();
      pre.sizes = fit(n) + "px"; pre.srcset = n.dataset.m + " " + n.dataset.mw + "w, " + n.href + " " + n.dataset.w + "w";
    };
    var open = function (i) {
      opener = doc.activeElement;
      lb.classList.add("open"); doc.body.classList.add("locked");
      requestAnimationFrame(function () { lb.classList.add("show"); });
      show(i);
      lb.querySelector(".x").focus({ preventScroll: true });
    };
    var close = function () {
      lb.classList.remove("show"); doc.body.classList.remove("locked");
      setTimeout(function () { lb.classList.remove("open"); pic.removeAttribute("srcset"); pic.removeAttribute("src"); }, calm ? 0 : 300);
      history.replaceState(null, "", location.pathname + location.search);
      var a = links[cur];
      if (a) { a.focus({ preventScroll: true }); a.scrollIntoView({ block: "nearest" }); }
      else if (opener) opener.focus();
      cur = -1;
    };
    links.forEach(function (a, i) {
      a.addEventListener("click", function (e) {
        if (e.metaKey || e.ctrlKey || e.shiftKey) return;
        e.preventDefault(); open(i);
      });
    });
    lb.querySelector(".prev").addEventListener("click", function () { show(cur - 1); });
    lb.querySelector(".next").addEventListener("click", function () { show(cur + 1); });
    lb.querySelector(".x").addEventListener("click", close);
    stage.addEventListener("click", function (e) { if (e.target === stage) close(); });
    doc.addEventListener("keydown", function (e) {
      if (cur < 0) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowLeft") show(cur - 1);
      else if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); show(cur + 1); }
      else if (e.key === "Tab") {
        var f = [].slice.call(lb.querySelectorAll("button")), k = f.indexOf(doc.activeElement);
        e.preventDefault(); f[(k + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
      }
    });
    var x0 = null, y0 = null;
    lb.addEventListener("touchstart", function (e) {
      if (e.touches.length === 1) { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; } else { x0 = null; }
    }, { passive: true });
    lb.addEventListener("touchend", function (e) {
      if (x0 === null) return;
      var dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0; x0 = null;
      if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy) * 1.4) show(cur + (dx < 0 ? 1 : -1));
      else if (dy > 90 && Math.abs(dy) > Math.abs(dx) * 1.4) close();
    }, { passive: true });
    var start = parseInt(location.hash.slice(1), 10);
    if (start >= 1 && start <= links.length) open(start - 1);
  }

  /* ── kontaktní formulář ─────────────────────────────── */
  var form = doc.querySelector("form[data-contact]");
  if (form) {
    var status = form.querySelector(".status"), btn = form.querySelector("button");
    var say = function (text, bad) { status.textContent = text; status.classList.toggle("err", !!bad); };
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var key = form.querySelector('[name="access_key"]').value;
      if (!key) { say(T.formOff, true); return; }
      if (!form.checkValidity()) { form.reportValidity(); return; }
      btn.disabled = true; say(T.sending);
      var data = {};
      new FormData(form).forEach(function (v, k) { data[k] = v; });
      fetch(form.action, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(data)
      }).then(function (r) { return r.json(); }).then(function (j) {
        if (j && j.success) { form.reset(); say(T.sent); }
        else { say(T.failed, true); }
      }).catch(function () { say(T.failed, true); }).then(function () { btn.disabled = false; });
    });
  }
})();
