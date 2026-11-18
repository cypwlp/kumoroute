(function () {
  try {
    const raw = localStorage.getItem("kumoroute.preferences.v1");
    const prefs = raw ? JSON.parse(raw) : {};
    const theme = ["system", "dark", "light", "contrast"].includes(prefs.theme) ? prefs.theme : "system";
    const fontSize = ["small", "normal", "large"].includes(prefs.fontSize) ? prefs.fontSize : "normal";
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.fontSize = fontSize;
    document.documentElement.style.colorScheme =
      theme === "light" ? "light" : theme === "system" ? "light dark" : "dark";
  } catch (e) {
    document.documentElement.dataset.theme = "system";
    document.documentElement.dataset.fontSize = "normal";
  }
})();
