# KumoRoute

輕量的跨平台 Mihomo 桌面客戶端（Windows / Linux / macOS），內建 [mihomo](https://github.com/MetaCubeX/mihomo) 核心，並相容 Clash 配置。

官方網站：https://cypwlp.github.io/kumoroute/

自訂鏡像域名 `kumoroute.cypilu.cloud`（及 `kumoroute.cypilu.online`）已預留；目前騰訊 DNSPod 仍可能回傳備案攔截頁，待完成合規備案後再切換。

> v0.2.0 起由 **MyClash** 更名為 **KumoRoute**；首次啟動會自動把舊資料目錄遷移到 `KumoRoute`。

正式客戶端為 **Rust / Tauri 2**（`tauri/`），圖形介面與 Python 後備版（`client/`）共用同一套 HTML/CSS/JS。

- 一鍵系統代理（退出自動還原；Windows 登錄檔 / GNOME gsettings / macOS networksetup）
- Windows 內建 VPN 管理：新增／編輯／刪除設定檔、首次登入後由 Windows 認證管理員加密保存憑證、清除憑證、連線時自動關閉系統代理，以及計量網路與漫遊進階設定
- VPN／代理協調：只用代理、只用 VPN、兩者共存三種模式；連線後以真實 HTTP 請求驗證，VPN 建立但網路不可用時會自動斷線並恢復原本代理狀態
- Clash 訂閱管理（遠端訂閱 / 本機 YAML）；可設定 6／12／24 小時自動更新，核心重載失敗時自動回滚，並支援不含 VPN 憑證的 JSON 備份與安全回復
- 代理頁以「目前策略組 → 實際出口」呈現；節點延遲含更新時間、成功率、抖動、最近失敗原因，支援單節點重測、過期自動重測、局部刷新保留捲動位置，以及大型清單分段載入
- 節點品質策略：固定節點／自動選擇／最低延遲；連續兩次逾時會自動排除，策略與最近 10 次測速結果會保存在本機
- 群組測速支援最多 6 個節點並行、顯示進度並可中途取消
- 介面個人化：跟隨系統／深色／淺色／高對比主題，字型大小（小／標準／大），繁體中文／简体中文／English 即時切換並保存偏好；自訂配置與節點名稱不被翻譯
- 節點選擇、整組測速、模式切換（規則 / 全局 / 直連）
- 即時上下行速度、連線數、日誌
- 本機流量統計：今日、近 7 日趨勢、近 30 日累計、峰值連線與速度
- 節點健康度：最近 10 次延遲、平均延遲、逾時率、穩定性與推薦節點
- 統計管理：CSV／JSON 匯出、清除統計、每日與近 7 日流量上限提醒
- 核心與代理事件：核心啟動／重啟、最近啟動、系統代理時長、訂閱更新歷史
- 流量歸屬：配置、策略組、節點；可選記錄熱門網域與規則命中（僅本機）
- 更新：啟動時自動檢查新版本；每個版本第一次發現時顯示非強制更新視窗（稍後／查看／立即更新），支援下載進度、取消、安裝版／ZIP 分流與上一版備份還原；Windows 安裝版以 `/UPDATE /P /R` 原地覆蓋、只顯示進度並自動重啟，不需先卸載
- Windows Authenticode 簽章準備：GitHub Actions 可透過憑證 secrets 自動匯入 PFX、使用 Tauri signing config 並驗證簽章（見 `SIGNING.md`）
- 本機當機紀錄與去識別化診斷預覽／匯出（可先檢查再寫檔）
- 代理設定先落盤再套用；啟動時自動恢復上次異常退出留下的系統代理
- Rust 三平台整合自測（`cargo test`＋實際啟動內附 mihomo）
- 依賴稽核（RustSec、pip-audit）與 CycloneDX／SPDX SBOM
- 嚴格 CSP、Tauri 視窗 capability 與 KumoRoute 命令白名單
- 隱私政策與使用條款
- GitHub Actions 乾淨 runner 的 Windows／Linux／macOS core 與建置 smoke tests
- 內置 GeoIP/GeoSite 資料庫，導入訂閱即用（免從 GitHub 下載 geodata）
- 核心崩潰自動重啟（60 秒內最多 5 次）＋日誌自動輪轉；日誌支援搜尋、只顯示警告／錯誤與重複訊息合併
- IPv6／DNS 智慧診斷：除路由外會測試實際 IPv6 連線，直接比對 DNS 解析出口與代理出口 IP，檢查 DoH／DoT 衝突與 IPv6 優先問題；重複錯誤會合併成單一診斷事件
- 一鍵網路修復：關閉 IPv6、切換備用 DNS、恢復自動 DNS、清除 DNS 快取並重新載入核心
- IPv6 自動偵測：沒有預設 IPv6 路由時關閉核心 IPv6，避免反覆出現 unreachable network 日誌
- 版本發佈工具：`python scripts/release.py 0.8.4` 同步版本並驗證跨後端契約
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
site/                   下載站（GitHub Pages；截圖原檔在 packaging/screenshots）
docs/                   部署與鏡像說明
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
git tag v0.8.4
git push origin v0.8.4
```

下載站按鈕指向 `releases/latest/download/KumoRoute-win-x64.zip`（見 `site/app.js`）。
Pages：Settings → Pages → Source 選「GitHub Actions」，推送後自動部署 `site/`。

下載站維護：

- 截圖原檔放 `packaging/screenshots/*.png`（不進部署目錄），改圖後執行 `python scripts/optimize_site_images.py` 產生 `site/assets/*-800.webp`、`*-1600.webp` 與 1200×630 的 `og.jpg`。
- 頁面全部下載連結都寫死在 HTML（`app.js` 只做 URL 覆寫），JS 被攔截也能下載。
- `site/404.html` 為 GitHub Pages 錯誤頁；各頁以 `<meta http-equiv="Content-Security-Policy">` 限制來源（Pages 無法送 response header）。
- 三語靜態頁面：`site/`（繁中，`x-default`）、`site/zh-cn/`（简中）、`site/en/`（English）；三者的 `hreflang` 與 `sitemap.xml` 必須同步修改，子目錄用相對路径（`../assets/`）以同時相容 GitHub Pages 子路径與 Cloudflare 根域名。
- 法務頁同样有三語版本：`privacy.html` / `terms.html` 與兩個子目錄下的同名頁；翻譯頁頂端註明「繁中原文為準」，修改任一版本時其餘兩個語言也必須同步。
- 回報入口：`feedback.html` 與兩個子目錄下的同名頁由 `scripts/gen_feedback_pages.py` 產生（三語 + hreflang + 預填 GitHub Issue 連結）；改完執行 `python scripts/gen_feedback_pages.py`，部署 workflow 會檢查是否與原始碼同步。网站本身不收集任何資料，不會有後端或數據上傳。
- CSS 內聯：`site/style.css` 是唯一來源，改完執行 `python scripts/inline_css.py`，它會把壓縮後的 CSS 內聯到六個頁面、寫回 `_headers`，並用 `sha256` 寫進 CSP（不用 `unsafe-inline`）。部署 workflow 會跑 `--check`，忘記重生就擋下部署。
- `python scripts/release.py <version>` 會同步版本字串（含三個語言的頁面與快取參數）並刷新 `site/sitemap.xml` 的 `<lastmod>`。

## 部署與鏡像

- 主站：https://cypwlp.github.io/kumoroute/（GitHub Pages，push `site/**` 自動部署）
- 第二站：Cloudflare Pages（`.github/workflows/deploy-cloudflare.yml`，需 CF secrets；提供真正的 HTTP 安全標頭與自訂域名）
- 裸 IP 備援：http://129.204.149.106/（`bash packaging/deploy-tencent.sh`）
- 大陸下載／更新鏡像：http://129.204.149.106/downloads/（`bash packaging/sync_mirror.sh` 手動同步；VM 上另有每 6 小時的 cron 自動檢查新版）。App 更新會先試 GitHub，失敗自動改讀此鏡像；`kumoroute.cypilu.cloud` 域名會被 DNSPod 備案攔截頁接管，**請只用裸 IP**。
- 程式碼鏡像：Gitee（`.github/workflows/mirror-gitee.yml`）。Gitee Pages 已於 2024 年停止服務，因此不提供 gitee.io 站點。
- 自訂鏡像域名：`kumoroute.cypilu.cloud`、`kumoroute.cypilu.online`（GET 會被 DNSPod 備案攔截頁接管；騰訊雲 HTTPS 需 ICP 備案。Cloudflare Pages 可免備案但大陸連線不保證）

完整設定步驟見 [docs/deploy.md](docs/deploy.md)。

本機打包（已編譯後）：`python packaging/pack.py`，產物在 `dist/`。

## 安全與測試

```powershell
$env:PATH="$HOME\.cargo\bin;$env:PATH"
cargo test --manifest-path tauri/Cargo.toml -- --test-threads=1
cargo run --manifest-path tauri/Cargo.toml -- --core-self-test
python -m unittest discover -s tests -p "test_*.py" -v
```

下載站排版檢查（無需額外套件，Node 20+ 內建 WebSocket）：

```powershell
python -m http.server 8000 --directory site
# 另一個視窗：Edge 或 Chrome 開著 --headless=new --remote-debugging-port=9333
node scripts/measure.mjs http://127.0.0.1:8000/index.html "JSON.stringify([...document.images].map(i=>[i.currentSrc,i.naturalWidth]))"
VIEWPORT=390x844 OUT=.tmp/shots/mobile.png node scripts/shot.mjs http://127.0.0.1:8000/index.html
node scripts/audit.mjs http://127.0.0.1:8000/index.html mobile   # FCP/LCP/CLS（4x CPU + Slow 4G）
```

CI 會在 Windows、Linux、macOS 執行 Rust 單元測試與實際核心自測；`Dependency security` workflow 會執行 RustSec、pip-audit 與 CycloneDX SBOM。Release 也會附上 SPDX SBOM。

診斷資料只在本機產生；預覽內容會遮蔽 URL、IP、日誌端點及 token／password 等敏感欄位，確認後才寫入檔案。

## 授權

- 客戶端程式碼：[MIT](LICENSE)
- 第三方元件與獨立性聲明：[NOTICE.md](NOTICE.md)
- 隱私政策：[PRIVACY.md](PRIVACY.md)
- 使用條款：[TERMS.md](TERMS.md)
- 內附 mihomo 核心：[GPL-3.0](client/core/LICENSE-GPL3.txt)，版權歸 [MetaCubeX](https://github.com/MetaCubeX/mihomo) 所有
