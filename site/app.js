"use strict";

// GitHub repo（部署前如需更換，改這裡）
const REPO_URL = "https://github.com/cypwlp/myclash";
const DOWNLOAD_URL = REPO_URL + "/releases/latest/download/MyClash-win-x64.zip";

document.getElementById("github-top").href = REPO_URL;
document.getElementById("github-btn").href = REPO_URL;
document.getElementById("github-foot").href = REPO_URL;
document.getElementById("download-btn").href = DOWNLOAD_URL;
