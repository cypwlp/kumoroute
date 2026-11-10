"use strict";

// TODO: 部署前替換成你的 GitHub repo 位址
const REPO_URL = "https://github.com/OWNER/REPO";
const DOWNLOAD_URL = REPO_URL + "/releases/latest/download/MyClash-win-x64.zip";

document.getElementById("github-top").href = REPO_URL;
document.getElementById("github-btn").href = REPO_URL;
document.getElementById("github-foot").href = REPO_URL;
document.getElementById("download-btn").href = DOWNLOAD_URL;
