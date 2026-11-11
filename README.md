# MyClash

輕量的 Windows 桌面 Clash 客戶端，內建 [mihomo](https://github.com/MetaCubeX/mihomo) 核心。

正式客戶端為 **Rust / Tauri 2**（`tauri/`），圖形介面與 Python 後備版（`client/`）共用同一套 HTML/CSS/JS。

- 一鍵系統代理（退出自動還原）
- Clash 訂閱管理（遠端訂閱 / 本機 YAML）
- 節點選擇、整組測速、模式切換（規則 / 全局 / 直連）
- 即時上下行速度、連線數、日誌
- 托盤常駐、關窗不退出、單實例

> MyClash 只提供客戶端，不包含、不販售任何節點或訂閱服務。

## 專案結構

```
tauri/                  正式客戶端（Rust / Tauri 2）
  src/                  後端：核心管理、訂閱、系統代理、托盤、commands
  tauri.conf.json       frontendDist 指向 ../client/ui
  .cargo/config.toml    crates 鏡像＋target 目錄
client/                 共用 UI＋Python 後備版
  ui/                   HTML/CSS/JS（pywebview / Tauri / DEMO 三模式）
  app.py                Python 後備後端
  core/                 mihomo.exe（不提交）與 GPL-3.0 授權文本
  tools/                fetch_core / make_icon
site/                   下載站（GitHub Pages）
.github/workflows/      Pages 部署工作流
```

## 建置 Rust 正式版

```powershell
cd tauri
cargo build --release
# 產物 target\release\myclash.exe；把 client\core\ 複製到 exe 同層\core\ 即可運行
```

Windows 上實測 GNU toolchain 亦可鏈接；若遇連結問題可改用 MSVC（`rustup default stable-x86_64-pc-windows-msvc`＋VS C++ 工作負載）。

## 本機開發（Python 後備）

```powershell
cd client
python -m pip install -r requirements.txt
python tools\fetch_core.py
python app.py
```

## 發佈

1. 將 `myclash.exe`＋`core\`（mihomo.exe、GPL-3.0）＋README 壓成 `MyClash-win-x64.zip`。
2. GitHub Release（如 `v0.1.0`）上傳該 zip；下載站按鈕指向 `releases/latest/download/MyClash-win-x64.zip`（見 `site/app.js`）。
3. Pages：Settings → Pages → Source 選「GitHub Actions」，推送後自動部署 `site/`。

## 授權

- 客戶端程式碼：[MIT](LICENSE)
- 內附 mihomo 核心：[GPL-3.0](client/core/LICENSE-GPL3.txt)，版權歸 [MetaCubeX](https://github.com/MetaCubeX/mihomo) 所有
