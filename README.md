# MyClash

輕量的 Windows 桌面 Clash 客戶端：Python + WebView2 圖形介面，內建 [mihomo](https://github.com/MetaCubeX/mihomo) 核心。

- 一鍵系統代理（退出自動還原）
- Clash 訂閱管理（遠端訂閱 / 本機 YAML）
- 節點選擇、整組測速、模式切換（規則 / 全局 / 直連）
- 即時上下行速度、連線數、日誌
- 托盤常駐、關窗不退出

> MyClash 只提供客戶端，不包含、不販售任何節點或訂閱服務。

## 專案結構

```
client/                 客戶端原始碼
  app.py                後端：核心管理、訂閱、系統代理、托盤、JS API
  ui/                   前端（HTML/CSS/JS，瀏覽器直接打開為 DEMO 模式）
  core/                 mihomo.exe（不提交）與 GPL-3.0 授權文本
  tools/fetch_core.py   下載 mihomo 核心
  tools/make_icon.py    產生圖示
  build.bat             一鍵建置
site/                   下載站（GitHub Pages）
.github/workflows/      Pages 部署工作流
```

## 本機開發

```powershell
cd client
python -m pip install -r requirements.txt
python tools\fetch_core.py        # 下載 mihomo.exe 到 client\core\
python app.py
```

環境變數（測試用）：`MYCLASH_DEBUG=1` 開 devtools；`MYCLASH_AUTOCLOSE=15` 15 秒後自動退出；`MYCLASH_SELFTEST=1` 載入後把 DOM 狀態寫入日誌。

## 建置可攜版

```powershell
cd client
build.bat
```

產物：`dist\MyClash\`（含 `core\mihomo.exe`），壓縮後即 `MyClash-win-x64.zip`。

## 發佈

1. GitHub 建立 Release（例如 `v0.1.0`），上傳 `MyClash-win-x64.zip`。
2. 下載站的下載按鈕指向 `releases/latest/download/MyClash-win-x64.zip`（見 `site/app.js` 的 `REPO_URL`）。
3. Pages：Settings → Pages → Source 選「GitHub Actions」，推送後 `deploy.yml` 自動部署 `site/`。

## 授權

- 客戶端程式碼：[MIT](LICENSE)
- 內附 mihomo 核心：[GPL-3.0](client/core/LICENSE-GPL3.txt)，版權歸 [MetaCubeX](https://github.com/MetaCubeX/mihomo) 所有
