# KumoRoute

輕量的跨平台 Mihomo 桌面客戶端（Windows / Linux / macOS），內建 [mihomo](https://github.com/MetaCubeX/mihomo) 核心，並相容 Clash 配置。

官方網站：https://cypwlp.github.io/kumoroute/

自訂鏡像域名 `kumoroute.cypilu.cloud`（及 `kumoroute.cypilu.online`）已預留；目前騰訊 DNSPod 仍可能回傳備案攔截頁，待完成合規備案後再切換。

> v0.2.0 起由 **MyClash** 更名為 **KumoRoute**；首次啟動會自動把舊資料目錄遷移到 `KumoRoute`。

正式客戶端為 **Rust / Tauri 2**（`tauri/`），圖形介面與 Python 後備版（`client/`）共用同一套 HTML/CSS/JS。

- 一鍵系統代理（退出自動還原；Windows 登錄檔 / GNOME gsettings / macOS networksetup）
- Clash 訂閱管理（遠端訂閱 / 本機 YAML）
- 代理頁以「目前策略組 → 實際出口」呈現，策略組側欄＋節點搜尋／篩選，避免大型訂閱清單失焦
- 節點選擇、整組測速、模式切換（規則 / 全局 / 直連）
- 即時上下行速度、連線數、日誌
- 本機流量統計：今日、近 7 日趨勢、近 30 日累計、峰值連線與速度
- 節點健康度：最近 10 次延遲、平均延遲、逾時率、穩定性與推薦節點
- 統計管理：CSV／JSON 匯出、清除統計、每日與近 7 日流量上限提醒
- 核心與代理事件：核心啟動／重啟、最近啟動、系統代理時長、訂閱更新歷史
- 流量歸屬：配置、策略組、節點；可選記錄熱門網域與規則命中（僅本機）
- 更新檢查：啟動時自動檢查新版本並提示下載頁（不自動執行未簽名安裝檔）
- 本機當機紀錄與去識別化診斷預覽／匯出（可先檢查再寫檔）
- 代理設定先落盤再套用；啟動時自動恢復上次異常退出留下的系統代理
- Rust 三平台整合自測（`cargo test`＋實際啟動內附 mihomo）
- 依賴稽核（RustSec、pip-audit）與 CycloneDX／SPDX SBOM
- 嚴格 CSP、Tauri 視窗 capability 與 KumoRoute 命令白名單
- 隱私政策與使用條款
- GitHub Actions 乾淨 runner 的 Windows／Linux／macOS core 與建置 smoke tests
- 內置 GeoIP/GeoSite 資料庫，導入訂閱即用（免從 GitHub 下載 geodata）
- 核心崩潰自動重啟（60 秒內最多 5 次）＋日誌自動輪轉
- 托盤常駐、關窗不退出、單實例
- Windows Job Object 綁定 mihomo：主程序被強制終止時核心由系統一併結束
- NSIS 安裝／卸載前檢查 `core\mihomo.exe`，避免核心鎖檔造成覆寫失敗
- 發佈形態：Windows 品牌化 NSIS 安裝精靈＋免安裝 zip；Linux AppImage＋deb；macOS Universal dmg

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
git tag v0.5.3
git push origin v0.5.3
```

下載站按鈕指向 `releases/latest/download/KumoRoute-win-x64.zip`（見 `site/app.js`）。
Pages：Settings → Pages → Source 選「GitHub Actions」，推送後自動部署 `site/`。

## 鏡像（騰訊雲裸 IP）

- 主站：https://cypwlp.github.io/kumoroute/ （GitHub Pages）
- IP 備援：http://129.204.149.106/
- 自訂鏡像：`kumoroute.cypilu.cloud`、`kumoroute.cypilu.online`（暫緩；中國大陸主機需 ICP 備案才能穩定使用 HTTPS）
- 同步：`bash packaging/deploy-tencent.sh`（SSH 到 `ubuntu@129.204.149.106`，上傳 `site/` 到 `/var/www/kumoroute`）
- nginx 站點：`/etc/nginx/sites-available/kumoroute`；Let’s Encrypt 憑證已配置，待域名可合規對外服務後啟用

本機打包（已編譯後）：`python packaging/pack.py`，產物在 `dist/`。

## 安全與測試

```powershell
$env:PATH="$HOME\.cargo\bin;$env:PATH"
cargo test --manifest-path tauri/Cargo.toml -- --test-threads=1
cargo run --manifest-path tauri/Cargo.toml -- --core-self-test
python -m unittest discover -s tests -p "test_*.py" -v
```

CI 會在 Windows、Linux、macOS 執行 Rust 單元測試與實際核心自測；`Dependency security` workflow 會執行 RustSec、pip-audit 與 CycloneDX SBOM。Release 也會附上 SPDX SBOM。

診斷資料只在本機產生；預覽內容會遮蔽 URL、IP、日誌端點及 token／password 等敏感欄位，確認後才寫入檔案。

## 授權

- 客戶端程式碼：[MIT](LICENSE)
- 第三方元件與獨立性聲明：[NOTICE.md](NOTICE.md)
- 隱私政策：[PRIVACY.md](PRIVACY.md)
- 使用條款：[TERMS.md](TERMS.md)
- 內附 mihomo 核心：[GPL-3.0](client/core/LICENSE-GPL3.txt)，版權歸 [MetaCubeX](https://github.com/MetaCubeX/mihomo) 所有
