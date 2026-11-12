KumoRoute v0.5.0 — 輕量 Mihomo 桌面客戶端（Windows x64 免安裝版，Rust/Tauri；相容 Clash 配置）

使用方法
1. 解壓縮到任意資料夾（請保持 KumoRoute.exe、core\、與程式同層）
2. 雙擊 KumoRoute.exe
3. 到「訂閱」貼上你的 Clash 訂閱連結（或匯入本機 YAML）
4. 回「概覽」打開「系統代理」

提示
- 首次執行可能出現 Windows SmartScreen 提示：更多資訊 → 仍要執行（本程式未簽名）。
- 關閉視窗會最小化到托盤，從托盤選單可退出。
- 若系統代理開關打開後又被關掉，是其他安全軟體在守護代理設定，請關閉其代理守護。
- 統計資料只保存在本機；可在「統計」頁匯出 CSV／JSON 或清除。
- 設定頁可檢查更新；未簽名版本不會自動下載或執行安裝檔。
- 當機紀錄保存在本機 logs 目錄，設定頁可匯出去識別化診斷資料。
- 設定目錄：%APPDATA%\KumoRoute
- 從舊版 MyClash 升級時，首次啟動會自動沿用並遷移原有設定。

內置說明
- 已內置 GeoIP/GeoSite 資料庫（geoip.metadb、geosite.dat），導入訂閱即可使用，無需聯網下載 geodata。
- 核心若異常退出會自動重啟（60 秒內最多 5 次）；core.log 超過 2MB 自動輪轉為 core.1.log。

授權
- 客戶端程式碼 MIT（見 LICENSE）；第三方元件聲明見 NOTICE.md。
- 內附 mihomo 核心為 GPL-3.0（見 core\LICENSE-GPL3.txt）。
- 本軟體不含任何節點或訂閱服務，請自備合法的 Clash 配置並遵守當地法律法規。
