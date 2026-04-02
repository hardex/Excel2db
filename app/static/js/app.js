// Excel2DB — app.js
// Minimal JS for enhanced UX; core functionality is server-rendered.

(function () {
  "use strict";

  // Auto-dismiss flash messages after 6 seconds
  const flashes = document.querySelectorAll(".flash");
  flashes.forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity 0.5s";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 500);
    }, 6000);
  });

  // Highlight active nav link based on current path
  const path = window.location.pathname;
  document.querySelectorAll(".nav-links a").forEach(function (link) {
    const href = link.getAttribute("href");
    if (href && path.startsWith(href) && href !== "/") {
      link.style.background = "rgba(255,255,255,.2)";
      link.style.color = "#fff";
    }
  });

  // Confirm before delete forms (fallback if onclick handler not present)
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      const msg = form.dataset.confirm || "Are you sure?";
      if (!window.confirm(msg)) {
        e.preventDefault();
      }
    });
  });

})();
