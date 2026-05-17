(function () {
  document.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest && e.target.closest("[data-copy]");
    if (!btn) return;
    var id = btn.getAttribute("data-copy");
    if (!id) return;
    var el = document.getElementById(id);
    if (!el) return;
    var text = el.textContent.trim();
    if (!navigator.clipboard || !navigator.clipboard.writeText) return;
    navigator.clipboard.writeText(text).then(function () {
      var done = btn.getAttribute("data-copy-done") || "복사됨";
      var prev = btn.textContent;
      btn.textContent = done;
      window.setTimeout(function () {
        btn.textContent = prev;
      }, 1300);
    });
  });
})();
