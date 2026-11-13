(function () {
  try {
    const raw = localStorage.getItem("kumoroute.preferences.v1");
    const prefs = raw ? JSON.parse(raw) : {};
    const theme = ["system", "dark", "light"].includes(prefs.theme) ? prefs.theme : "system";
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme === "light" ? "light" : theme === "dark" ? "dark" : "light dark";
  } catch (e) {
    document.documentElement.dataset.theme = "system";
  }
})();