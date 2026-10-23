/* Tema antes del primer paint: sin flash y sin script inline (CSP). */
(function () {
  try {
    var saved = localStorage.getItem("cerberus-theme");
    document.documentElement.dataset.theme = saved === "light" ? "light" : "dark";
  } catch (e) {
    document.documentElement.dataset.theme = "dark";
  }
})();
