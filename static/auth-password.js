(function () {
  document.querySelectorAll(".auth-password-wrap .auth-password-toggle").forEach(function (btn) {
    var wrap = btn.closest(".auth-password-wrap");
    if (!wrap) return;
    var input = wrap.querySelector("input");
    if (!input) return;
    btn.addEventListener("click", function () {
      var willShow = input.type === "password";
      input.type = willShow ? "text" : "password";
      btn.textContent = willShow ? "Hide" : "Show";
      btn.setAttribute("aria-pressed", willShow ? "true" : "false");
      btn.setAttribute("aria-label", willShow ? "Hide password" : "Show password");
    });
  });
})();
