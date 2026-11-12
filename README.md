# KumoRoute

輕量的跨平台 Mihomo 桌面客戶端（Windows / Linux / macOS），內建 [mihomo](https://github.com/MetaCubeX/mihomo) 核心，並相容 Clash 配置。

官方網站：https://kumoroute.cypilu.online/

GitHub Pages 備援：https://cypwlp.github.io/kumoroute/

> v0.2.0 起由 **MyClash** 更名為 **KumoRoute**；首次啟動會自動把舊資料目錄遷移到 `KumoRoute`。

正式客戶端為 **Rust / Tauri 2**（`tauri/`），圖形介面與 Python 後備版（`client/`）共用同一套 HTML/CSS/JS。

- 一鍵系統代理（退出自動還原；Windows 登錄檔 / GNOME gsettings / macOS networksetup）
- Clash 訂閱管理（遠端訂閱 / 本機 YAML）
- 節點選擇、整組測速、模式切換（規則 / 全局 / 直連）
- 即時上下行速度、連線數、日誌
- 內置 GeoIP/GeoSite 資料庫，導入訂閱即用（免從 GitHub 下載 geodata）
- 核心崩潰自動重啟（60 秒內最多 5 次）＋日誌自動輪轉
- 托盤常駐、關窗不退出、單實例
- 發佈形態：Windows 安裝包（NSIS）＋免安裝 zip；Linux AppImage＋deb；macOS Universal dmg

> KumoRoute 只提供客戶端，不包含、不販售任何節點或訂閱服務。

## 專案結構

```
tauri/                  正式客戶端（Rust / Tauri 2）
  src/                  後端：核心管理、訂閱、系統代理、托盤、commands
  tauri.conf.json       frontendDist 指向 ../client/ui
  .cargo/config.toml    crates 鏡像＋target 目錄
client/                 共用 UI＋Python 後備版
  ui/                   HTML/CSS/JS（pywebview / Tauri / DEMO 三模式）
  app.py                Python 後備後端
  core/                 mihomo.exe＋geodata（不提交）與 GPL-3.0 授權文本
  tools/                fetch_core / make_icon
site/                   下載站（GitHub Pages）
.github/workflows/      Pages 部署工作流
```

## 建置

```powershell
cd tauri
cargo build --release          # 快速可執行檔
# 或產出安裝包（需 Tauri CLI）
npm i -g @tauri-apps/cli@^2
tauri build
```

- **Windows**：`tauri build` 產出 NSIS 安裝包（`target/release/bundle/nsis/`）；本機實測 GNU toolchain 也能直接 `cargo build`。
- **Linux**：需 `libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev patchelf`，產出 AppImage／deb。
- **macOS**：`tauri build --target universal-apple-darwin` 產出通用 dmg（未簽名，首次需右鍵開啟）。
- 核心與 geodata：`python client/tools/fetch_core.py`（依當前平台下載對應 mihomo）。

## 本機開發（Python 後備）

```powershell
cd client
python -m pip install -r requirements.txt
python tools\fetch_core.py
python app.py
```

## 發佈（自動）

推送 `v*` tag 即由 GitHub Actions 自動編譯、打包並建立 Release（含 `KumoRoute-win-x64.zip` 與 `SHA256SUMS.txt`）：

```powershell
git tag v0.2.1
git push origin v0.2.1
```

下載站按鈕指向 `releases/latest/download/KumoRoute-win-x64.zip`（見 `site/app.js`）。
Pages：Settings → Pages → Source 選「GitHub Actions」，推送後自動部署 `site/`。

## 鏡像（騰訊雲裸 IP）

- 正式站：https://kumoroute.cypilu.online/ （Tencent Cloud + Let’s Encrypt）
- IP 備援：http://129.204.149.106/
- 同步：`bash packaging/deploy-tencent.sh`（SSH 到 `ubuntu@129.204.149.106`，上傳 `site/` 到 `/var/www/kumoroute`）
- nginx 站點：`/etc/nginx/sites-available/kumoroute`；憑證由 Certbot 自動續期

本機打包（已編譯後）：`python packaging/pack.py`，產物在 `dist/`。

## 授權

- 客戶端程式碼：[MIT](LICENSE)
- 第三方元件與獨立性聲明：[NOTICE.md](NOTICE.md)
- 內附 mihomo 核心：[GPL-3.0](client/core/LICENSE-GPL3.txt)，版權歸 [MetaCubeX](https://github.com/MetaCubeX/mihomo) 所有
