"use strict";
// trigger deploy

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

document.getElementById("github-top").href = REPO_URL;
document.getElementById("github-btn").href = REPO_URL;
document.getElementById("github-foot").href = REPO_URL;

Object.entries(ASSETS).forEach(([key, file]) => {
  const el = document.getElementById(key) || document.querySelector(`[data-dl="${key}"]`);
  if (el) el.href = DL_BASE + file;
});
