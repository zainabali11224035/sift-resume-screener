// Dark / light mode toggle. Preference is saved per-browser in localStorage.
(function () {
  var toggle = document.getElementById("themeToggle");
  if (!toggle) return;

  function isDark() {
    return document.documentElement.getAttribute("data-theme") === "dark";
  }

  toggle.addEventListener("click", function () {
    if (isDark()) {
      document.documentElement.removeAttribute("data-theme");
      localStorage.setItem("sift-theme", "light");
    } else {
      document.documentElement.setAttribute("data-theme", "dark");
      localStorage.setItem("sift-theme", "dark");
    }
  });
})();
