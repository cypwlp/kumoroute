"use strict";
// Keeps repo/download URLs in one place. All links are also hard-coded in the
// HTML so the page still works when scripting is blocked; this script only
// rewrites them when REPO_URL / filenames change.

// GitHub repo（部署前如需更換，改這裡）
const REPO_URL = "https://github.com/cypwlp/kumoroute";
const DL_BASE = REPO_URL + "/releases/latest/download/";

const ASSETS = {
  "download-btn": "KumoRoute-win-x64-setup.exe",
  "win-setup": "KumoRoute-win-x64-setup.exe",
  "win-zip": "KumoRoute-win-x64.zip",
  "linux-appimage": "KumoRoute-linux-x86_64.AppImage",
  "linux-deb": "KumoRoute-linux-amd64.deb",
  "mac-dmg": "KumoRoute-macos-universal.dmg",
};

["github-top", "github-btn", "github-foot"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.href = REPO_URL;
});

Object.entries(ASSETS).forEach(([key, file]) => {
  const elements = new Set([
    document.getElementById(key),
    ...document.querySelectorAll(`[data-dl="${key}"]`),
  ].filter(Boolean));
  elements.forEach((el) => { el.href = DL_BASE + file; });
});
