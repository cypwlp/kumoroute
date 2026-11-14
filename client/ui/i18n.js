(function () {
  const EN = {
    "概覽": "Overview",
    "統計": "Statistics",
    "代理": "Proxies",
    "訂閱": "Subscriptions",
    "日誌": "Logs",
    "設置": "Settings",
    "核心運行中": "Core running",
    "核心未啟動": "Core stopped",
    "核心已停止": "Core stopped",
    "核心已啟動": "Core started",
    "核心已重新啟動": "Core restarted",
    "正在檢查核心狀態…": "Checking core status…",
    "找不到 mihomo 核心": "mihomo core not found",
    "系統代理": "System proxy",
    "系統代理：關": "System proxy: Off",
    "系統代理：開": "System proxy: On",
    "接管 Windows 系統流量": "Route Windows traffic through KumoRoute",
    "代理模式": "Proxy mode",
    "規則": "Rule",
    "全局": "Global",
    "直連": "Direct",
    "下載": "Download",
    "上傳": "Upload",
    "連線數": "Connections",
    "累計下載": "Total download",
    "累計上傳": "Total upload",
    "合計": "Total",
    "當前配置": "Current profile",
    "更新訂閱": "Update subscription",
    "快速上手": "Quick start",
    "到「訂閱」貼上你的 Clash 訂閱連結（或匯入本機 YAML）。": "Open Subscriptions and add a Clash subscription URL or import a local YAML file.",
    "回到概覽，打開「系統代理」。瀏覽器、桌面程式即走代理。": "Return to Overview and enable System proxy. Browser and desktop traffic will use it.",
    "需要換節點時，到「代理」分組裡點選即可。": "To switch nodes, open Proxies and select one from a group.",
    "今日流量": "Today's traffic",
    "最近 7 天": "Last 7 days",
    "近 30 天累計": "30-day total",
    "本次開啟": "This session",
    "峰值速度": "Peak speed",
    "峰值連線": "Peak connections",
    "工作階段計時": "Session time",
    "核心與代理": "Core & proxy",
    "核心啟動": "Core starts",
    "重新啟動": "Restarts",
    "最近啟動": "Last started",
    "系統代理時長": "System proxy time",
    "節點健康度": "Node health",
    "流量歸屬": "Traffic attribution",
    "熱門網域": "Top domains",
    "規則命中": "Rule hits",
    "策略組": "Groups",
    "節點": "Nodes",
    "目前策略組": "Current group",
    "實際出口": "Effective exit",
    "目前": "Current",
    "使用中": "In use",
    "逾時": "Timed out",
    "測速": "Test",
    "測速目前組": "Test current group",
    "測速中…": "Testing…",
    "測速完成": "Test complete",
    "測速失敗": "Test failed",
    "搜尋節點…": "Search nodes…",
    "搜尋日誌…": "Search logs…",
    "只顯示警告／錯誤": "Warnings and errors only",
    "（尚無符合條件的日誌）": "(No matching log entries)",
    "重測": "Retest",
    "重新測試此節點": "Retest this node",
    "節點測試失敗": "Node test failed",
    "已更新節點延遲": "Node latency updated",
    "節點延遲：": "Node latency: ",
    "顯示更多（還剩 ": "Show more (",
    " 個）": " remaining)",
    "全部": "All",
    "找不到符合的節點或策略組。": "No matching node or group.",
    "此策略組沒有可顯示的節點。": "This group has no nodes to display.",
    "再測速幾次即可推薦": "Run a few more tests to get a recommendation",
    "推薦：": "Recommended: ",
    "已套用：": "Applied: ",
    "出口：": "Exit: ",
    "目前：": "Current: ",
    "· 實際出口：": " · Effective exit: ",
    "尚無配置": "No profiles yet",
    "尚無資料": "No data yet",
    "未啟用": "Disabled",
    "尚無事件紀錄": "No events yet",
    "尚無節點測速紀錄。到「代理」頁按一次「測速」後，這裡會開始累積最近 10 次結果。": "No node tests yet. Run Test on the Proxies page to start collecting the latest 10 results.",
    "節點健康度每次測速會保留最近 10 次結果；依成功率、平均延遲與波動推薦較穩定節點。": "Node health keeps the latest 10 tests and recommends stable nodes based on success rate, average latency, and variation.",
    "目前是內建直連配置，流量不經任何代理。到「訂閱」新增你的 Clash 訂閱連結。": "The built-in Direct profile is active. Add your Clash subscription on the Subscriptions page.",
    "未指定配置": "No profile selected",
    "內建": "Built-in",
    "內建配置": "Built-in profile",
    "本機 YAML": "Local YAML",
    "遠端訂閱": "Remote subscription",
    "更新於": "updated",
    "刪除": "Delete",
    "確認刪除？": "Confirm delete?",
    "取消": "Cancel",
    "新增": "Add",
    "更新": "Update",
    "刪除失敗": "Delete failed",
    "已刪除": "Deleted",
    "啟用": "Activate",
    "啟用失敗": "Activation failed",
    "已切換配置": "Profile switched",
    "訂閱已更新": "Subscription updated",
    "已切換節點": "Node switched",
    "切換失敗": "Switch failed",
    "操作失敗": "Operation failed",
    "更新失敗": "Update failed",
    "保存失敗": "Save failed",
    "已複製": "Copied",
    "複製失敗": "Copy failed",
    "已複製去識別化診斷內容": "Sanitized diagnostic content copied",
    "複製內容": "Copy content",
    "複製全部": "Copy all",
    "確認匯出": "Confirm export",
    "預覽／匯出診斷資料": "Preview / export diagnostics",
    "診斷資料預覽": "Diagnostic preview",
    "正在產生去識別化內容…": "Generating sanitized content…",
    "匯出失敗": "Export failed",
    "統計已匯出：": "Statistics exported: ",
    "診斷資料已匯出：": "Diagnostic data exported: ",
    "本機統計已清除": "Local statistics cleared",
    "統計設定已保存": "Statistics settings saved",
    "已保存，核心已重啟": "Saved. Core restarted.",
    "系統代理已開啟": "System proxy enabled",
    "系統代理已關閉": "System proxy disabled",
    "系統代理設定失敗": "Failed to configure system proxy",
    "檢查中…": "Checking…",
    "檢查更新": "Check for updates",
    "檢查更新失敗": "Update check failed",
    "發現新版本 v": "New version available: v",
    "目前已是最新版本": "You are up to date",
    "目前已是最新版本。": "You are up to date.",
    "尚未檢查": "Not checked",
    "查看更新": "View update",
    "立即更新": "Update now",
    "立即更新（": "Update now (",
    "正在下載更新…": "Downloading update…",
    "更新已下載：": "Update downloaded: ",
    "下載更新失敗": "Failed to download update",
    "更新安裝檔已下載，請確認後由系統安裝。": "The update installer has been downloaded. Confirm and install it through your system.",
    "更新安裝檔已下載完成。是否立即啟動安裝程式？\nKumoRoute 會在安裝程式啟動後自動退出。": "The update installer has been downloaded. Start the installer now?\nKumoRoute will exit after the installer starts.",
    "啟動更新安裝檔失敗": "Failed to start the update installer",
    "有新版本 ": "New version ",
    " 可用。可下載並啟動安裝檔，或自行從更新頁安裝。": " available. Download and run the installer, or install it manually from the update page.",
    "可手動下載並安裝新版本；應用程式不會在背景自動執行安裝檔。": "You can download and install updates manually. KumoRoute never runs installers automatically in the background.",
    "管理 Windows 內建 VPN 連線；帳號與密碼由 Windows 保管。": "Manage Windows built-in VPN connections. Windows stores your sign-in credentials.",
    "VPN 連線": "VPN connections",
    "正在讀取 Windows VPN…": "Loading Windows VPN…",
    "重新整理": "Refresh",
    "新增 VPN": "Add VPN",
    "KumoRoute 使用 Windows 認證管理員加密保存 VPN 憑證；首次連線需輸入一次。VPN 與系統代理同時開啟時可能發生路由衝突。": "KumoRoute stores VPN credentials encrypted in Windows Credential Manager. Sign in once for the first connection. VPN and System proxy can conflict when enabled together.",
    "VPN 與系統代理同時開啟，路由可能衝突。建議只保留其中一種接管方式。": "VPN and System proxy are both enabled; routes may conflict. Keep only one traffic takeover method active.",
    "Windows VPN 無法使用。": "Windows VPN is unavailable.",
    "此功能僅支援 Windows 內建 VPN。": "This feature supports Windows built-in VPN only.",
    "讀取 VPN 失敗。": "Failed to load VPN connections.",
    "無法讀取 Windows VPN": "Unable to read Windows VPN",
    "尚未建立 VPN 連線。": "No VPN connections have been created.",
    "目前沒有 VPN 連線。": "No VPN is currently connected.",
    "已連線 VPN：": "Connected VPNs: ",
    "尚未建立 VPN 連線。點「新增 VPN」建立設定。": "No VPN connections yet. Select Add VPN to create one.",
    "斷開": "Disconnect",
    "清除憑證": "Clear credentials",
    "VPN 憑證已清除": "VPN credentials cleared",
    "VPN 連線時自動關閉系統代理": "Turn off System proxy when connecting VPN",
    "VPN 自動代理設定已更新": "VPN auto-proxy setting updated",
    "新增 VPN 連線": "Add VPN connection",
    "編輯 VPN 連線": "Edit VPN connection",
    "建立 Windows 內建 VPN 設定檔；登入密碼會在首次連線時保存到 Windows 認證管理員。": "Create a Windows built-in VPN profile. Sign-in credentials are saved to Windows Credential Manager on first connection.",
    "關閉 VPN 設定視窗": "Close VPN settings dialog",
    "名稱": "Name",
    "伺服器位址": "Server address",
    "VPN 類型": "VPN type",
    "請輸入 VPN 名稱與伺服器位址": "Enter the VPN name and server address",
    "已存在同名 VPN 連線": "A VPN connection with this name already exists",
    "儲存 VPN 失敗": "Failed to save VPN",
    "VPN 已新增": "VPN added",
    "VPN 已更新": "VPN updated",
    "確定刪除 VPN？": "Delete this VPN?",
    "刪除 VPN 失敗": "Failed to delete VPN",
    "VPN 已刪除": "VPN deleted",
    "連線": "Connect",
    "Windows 已記住登入資訊": "Windows has saved sign-in information",
    "Windows 已安全儲存登入資訊": "Windows securely stores sign-in information",
    "首次連線需輸入密碼": "Password required on first connection",
    "VPN 登入資訊": "VPN sign-in",
    "首次連線需要輸入一次；儲存後由 Windows 認證管理員保管。": "Enter your credentials once. Windows Credential Manager stores them securely afterwards.",
    "關閉 VPN 登入視窗": "Close VPN sign-in dialog",
    "使用者名稱": "Username",
    "密碼": "Password",
    "儲存在 Windows 認證管理員": "Save in Windows Credential Manager",
    "KumoRoute 不以明文保存密碼；憑證由 Windows 加密保管，之後可直接連線。": "KumoRoute never stores plaintext passwords. Windows encrypts the credentials so future connections can be direct.",
    "請輸入 VPN 使用者名稱與密碼": "Enter the VPN username and password",
    "VPN 憑證已失效，請重新輸入密碼": "The saved VPN credential is no longer valid. Enter the password again.",
    "VPN 已連線，登入資訊已保存": "VPN connected and sign-in information saved",
    "VPN 已連線，登入資訊未保存": "VPN connected but sign-in information was not saved",
    "已連線，但無法保存 VPN 憑證": "Connected, but the VPN credential could not be saved",
    "保存 Windows VPN 憑證失敗：": "Failed to save the Windows VPN credential: ",
    "讀取 Windows VPN 憑證失敗：": "Failed to read the Windows VPN credential: ",
    "Windows VPN 驗證失敗": "Windows VPN authentication failed",
    "使用者名稱或密碼錯誤": "Incorrect username or password",
    "PPP 連線協商失敗": "PPP negotiation failed",
    "VPN 連線逾時或伺服器無回應": "VPN connection timed out or the server did not respond",
    "找不到 VPN 伺服器": "VPN server not found",
    "VPN 連線失敗（錯誤 ": "VPN connection failed (error ",
    "連線時可能要求登入": "Sign-in may be requested when connecting",
    "VPN 已連線": "VPN connected",
    "VPN 已斷開": "VPN disconnected",
    "正在連線 VPN…": "Connecting VPN…",
    "請在 Windows VPN 視窗完成登入。": "Complete sign-in in the Windows VPN window.",
    "VPN 操作失敗": "VPN operation failed",
    "無法開啟 Windows VPN 設定": "Unable to open Windows VPN settings",
    "DEMO 模式不開啟 Windows VPN 設定": "Windows VPN settings are unavailable in demo mode",
    "Windows VPN 僅支援 Windows": "Windows VPN is only available on Windows",
    "找不到該 VPN 連線": "VPN connection not found",
    "所有 VPN 連線的進階設定": "Advanced settings for all VPN connections",
    "允許透過按流量計費的網路進行 VPN 連線": "Allow VPN over metered networks",
    "允許漫遊時進行 VPN 連線": "Allow VPN while roaming",
    "變更進階設定時，Windows 會要求系統管理員權限。": "Windows requires administrator permission to change advanced settings.",
    "VPN 進階設定已更新": "VPN advanced settings updated",
    "VPN 進階設定已套用": "VPN advanced setting applied",
    "VPN 進階設定未變更（可能取消了 UAC）": "VPN advanced setting was not changed (UAC may have been cancelled)",
    "VPN 進階設定更新失敗": "Failed to update VPN advanced settings",
    "請在 Windows 的 UAC 提示中允許變更。": "Allow the change in the Windows UAC prompt.",
    "無效的 VPN 進階設定": "Invalid VPN advanced setting",
    "更新 VPN 進階設定失敗：": "Failed to update VPN advanced settings: ",
    "VPN 連線名稱無效": "Invalid VPN connection name",
    "讀取 Windows VPN 失敗：": "Failed to read Windows VPN: ",
    "解析 Windows VPN 失敗：": "Failed to parse Windows VPN: ",
    "啟動 VPN 連線視窗失敗：": "Failed to open the VPN connection window: ",
    "啟動 VPN 連線失敗：": "Failed to connect VPN: ",
    "VPN 斷線失敗（代碼 ": "Failed to disconnect VPN (code ",
    "VPN 斷線失敗：": "Failed to disconnect VPN: ",
    "斷線中": "Disconnecting",
    "自動": "Automatic",
    "客戶端版本": "Client version",
    "核心版本": "Core version",
    "資料目錄": "Data directory",
    "今日流量": "Today's traffic",
    "近 7 日流量上限（GB，0 = 關閉）": "7-day traffic limit (GB, 0 = off)",
    "每日流量上限（GB，0 = 關閉）": "Daily traffic limit (GB, 0 = off)",
    "記錄熱門網域與規則命中（僅本機）": "Record top domains and rule hits (local only)",
    "匯出 CSV": "Export CSV",
    "匯出 JSON": "Export JSON",
    "清除統計": "Clear statistics",
    "統計管理": "Statistics management",
    "近 30 天累計": "30-day total",
    "今日流量": "Today's traffic",
    "最近 7 天": "Last 7 days",
    "設定": "Settings",
    "設置": "Settings",
    "新增訂閱": "Add subscription",
    "支援 Clash / mihomo YAML 訂閱連結，或匯入本機配置文件。": "Supports Clash / mihomo YAML subscription URLs or local profile import.",
    "匯入本機 YAML…": "Import local YAML…",
    "已新增的配置": "Saved profiles",
    "請在服務後台選擇「Clash／Mihomo」格式；Base64 節點清單與 ss://、vmess://、trojan:// 原始節點不支援。": "Choose Clash / Mihomo format in your provider. Base64 node lists and raw ss://, vmess://, or trojan:// links are not supported.",
    "日誌": "Logs",
    "mihomo 核心輸出（最近 300 行）。": "mihomo core output (latest 300 lines).",
    "自動滾動到底部": "Auto-scroll to bottom",
    "（尚無日誌）": "(No logs yet)",
    "保存並重啟核心": "Save and restart core",
    "控制 API 埠": "Controller API port",
    "混合代理埠（HTTP/SOCKS）": "Mixed proxy port (HTTP/SOCKS)",
    "連接埠": "Port",
    "連接埠修改後會自動重啟核心。": "Changing a port restarts the core automatically.",
    "開啟資料資料夾": "Open data folder",
    "軟體更新": "Updates",
    "目前版本": "Current version",
    "最新版本": "Latest version",
    "外觀與語言": "Appearance & language",
    "選擇介面主題與顯示語言；切換會立即生效。": "Choose the interface theme and display language. Changes apply immediately.",
    "KumoRoute 僅提供代理工具的圖形化管理，不包含、不販售任何節點或訂閱服務。 請自行準備合法的代理配置，並遵守所在國家與地區的法律法規。": "KumoRoute only provides a graphical interface for proxy tools. It does not include, sell, or resell any nodes or subscriptions. Prepare a lawful configuration and follow local laws and regulations.",
    "啟動時自動檢查更新": "Check for updates on startup",
    "只檢查版本並提示；不會自動下載或執行安裝檔。": "Only checks for versions. It never downloads or runs installers automatically.",
    "關於": "About",
    "隱私政策": "Privacy policy",
    "服務條款": "Terms of service",
    "mihomo 專案（GPL-3.0）": "mihomo project (GPL-3.0)",
    "mihomo 核心": "mihomo core",
    "核心已停止": "Core stopped",
    "搜尋節點…": "Search nodes…",
    "全部": "All",
    "節點": "Nodes",
    "策略組": "Groups",
    "已切換節點": "Node switched",
    "目前使用中": "Currently in use",
    "目前使用": "Currently in use",
    "目前策略組": "Current group",
    "目前出口": "Current exit",
    "切換策略組": "Switch group",
    "還沒有節點": "No nodes yet",
    "連線中": "Connecting",
    "已連線": "Connected",
    "未連線": "Disconnected",
    "電量": "Battery",
    "路由器": "Router",
    "代理節點": "Proxy node",
    "一鍵接管系統流量，規則、全局、直連自由切換。": "Take control of system traffic with one click. Switch freely between Rule, Global, and Direct.",
    "停止核心": "Stop core",
    "累計下載": "Total download",
    "累計上傳": "Total upload",
    "本次開啟期間": "This session",
    "上傳峰值": "Peak upload",
    "只記錄 KumoRoute 開啟期間的流量；資料保存在本機，不會上傳。": "Records traffic only while KumoRoute is open. Data stays on this device and is never uploaded.",
    "依作用中連線的位元組增量估算，可能包含少量重疊或漏計。": "Estimated from byte deltas on active connections; may include minor overlap or missed traffic.",
    "保存統計設定": "Save statistics settings",
    "網域與規則排行預設關閉；啟用後也只保存在本機。": "Domain and rule rankings are off by default and stay local when enabled.",
    "清除統計不會刪除訂閱、設定或日誌。": "Clearing statistics does not delete profiles, settings, or logs.",
    "統計為本機近似值；切換節點、重啟核心或應用程式未開啟期間不會完整計入。": "Statistics are local approximations; traffic during node switches, core restarts, or downtime may be incomplete.",
    "先看上方目前出口，再從左側策略組選擇；測速使用": "Check the effective exit above, then choose a group on the left. Tests use",
    "核心未啟動或配置中沒有策略組。": "The core is stopped or this profile has no proxy groups.",
    "此配置中沒有策略組（proxy-groups）。": "This profile has no proxy groups.",
    "核心未啟動。": "The core is stopped.",
    "新增中…": "Adding…",
    "請輸入 http(s):// 開頭的訂閱連結": "Enter a subscription URL starting with http(s)://",
    "新增失敗": "Add failed",
    "訂閱已新增": "Subscription added",
    "訂閱已新增並啟用": "Subscription added and activated",
    "本機配置已匯入": "Local profile imported",
    "配置已匯入並啟用": "Profile imported and activated",
    "配置已刪除": "Profile deleted",
    "再次點擊確認清除": "Click again to confirm clearing",
    "DEMO 模式不產生診斷資料": "Diagnostics are unavailable in demo mode",
    "產生預覽中…": "Generating preview…",
    "無法產生診斷預覽": "Unable to generate diagnostic preview",
    "匯出中…": "Exporting…",
    "已去識別化：": "Sanitized: ",
    "端點": "Endpoints",
    "敏感欄位": "Sensitive fields",
    "請確認內容後再匯出。": "Review the content before exporting.",
    "流量上限提醒": "Traffic limit alert",
    "今日流量 ": "Today's traffic ",
    "近 7 日流量 ": "7-day traffic ",
    "上限 ": "Limit ",
    "KumoRoute 流量提醒": "KumoRoute traffic alert",
    "偵測到上次未清理的系統代理，已自動恢復原始設定。": "Detected a system proxy left by a previous session and restored the original settings.",
    "已清除過期的代理快照；目前系統代理未被覆蓋。": "Cleared an expired proxy snapshot; the current system proxy was not overridden.",
    "套用": "Apply",
    "普通": "Fair",
    "不穩": "Unstable",
    "穩定": "Stable",
    "已套用推薦節點": "Recommended node applied",
    "事件": "Event",
    "上限": "Limit",
    "核心": "Core",
    "配置": "Profile",
    "遠端訂閱": "Remote subscription",
    "本機配置": "Local profile",
    "更新中…": "Updating…",
    "保存中…": "Saving…",
    "檢查中…": "Checking…",
    "訊息": "Message",
    "核心已啟動": "Core started",
    "核心已重新啟動": "Core restarted",
    "核心已停止": "Core stopped",
    "系統代理已開啟": "System proxy enabled",
    "系統代理已關閉": "System proxy disabled",
    "訂閱已更新": "Subscription updated",
    "訂閱已新增": "Subscription added",
    "本機配置已匯入": "Local profile imported",
    "已切換配置": "Profile switched",
    "已套用推薦節點": "Recommended node applied",
    "DEMO 模式：瀏覽器預覽，未連接客戶端後端": "DEMO MODE: Browser preview without the client backend",
    "啟動 KumoRoute": "Start KumoRoute",
    "· 累計上傳": " · Total upload",
    "每次測速會保留最近 10 次結果；依成功率、平均延遲與波動推薦較穩定節點。": "Each test keeps the latest 10 results; stable nodes are recommended by success rate, average latency, and variation.",
    "名稱（可留空）": "Name (optional)",
    "關閉預覽": "Close preview",
  };
  const EN_PHRASES = [
    ["目前已是最新版本", "You are up to date"],
    ["正在檢查核心狀態…", "Checking core status…"],
    ["正在產生去識別化內容…", "Generating sanitized content…"],
    ["尚無節點測速紀錄。到「代理」頁按一次「測速」後，這裡會開始累積最近 10 次結果。", "No node tests yet. Run Test on the Proxies page to start collecting the latest 10 results."],
    ["請在服務後台選擇「Clash／Mihomo」格式；Base64 節點清單與 ss://、vmess://、trojan:// 原始節點不支援。", "Choose Clash / Mihomo format in your provider. Base64 node lists and raw ss://, vmess://, or trojan:// links are not supported."],
    ["需要換節點時，到「代理」分組裡點選即可。", "To switch nodes, open Proxies and select one from a group."],
    ["回到概覽，打開「系統代理」。瀏覽器、桌面程式即走代理。", "Return to Overview and enable System proxy."],
    ["到「訂閱」貼上你的 Clash 訂閱連結（或匯入本機 YAML）。", "Open Subscriptions and add a Clash subscription URL or local YAML."],
    ["目前是內建直連配置，流量不經任何代理。到「訂閱」新增你的 Clash 訂閱連結。", "The built-in Direct profile is active. Add your Clash subscription."],
    ["已複製去識別化診斷內容", "Sanitized diagnostic content copied"],
    ["統計已匯出：", "Statistics exported: "],
    ["診斷資料已匯出：", "Diagnostic data exported: "],
    ["已套用：", "Applied: "],
    ["已切換節點", "Node switched"],
    ["主題", "Theme"],
    ["語言", "Language"],
    ["跟隨系統", "Follow system"],
    ["深色", "Dark"],
    ["淺色", "Light"],
    ["繁體中文", "Traditional Chinese"],
    ["简体中文", "Simplified Chinese"],
    ["English", "English"],
    ["外觀與語言", "Appearance & language"],
    ["選擇介面主題與顯示語言；切換會立即生效。", "Choose the interface theme and display language. Changes apply immediately."],
  ];
  const PHRASES = [...Object.entries(EN), ...EN_PHRASES]
    .sort((a, b) => b[0].length - a[0].length);
  const SIMP_TERMS = [
    ["资料目录", "数据目录"],
    ["资料夹", "文件夹"],
    ["工作阶段", "会话"],
    ["应用程序", "应用程序"],
    ["伺服器", "服务器"],
    ["连接埠", "端口"],
    ["代理埠", "代理端口"],
    ["埠", "端口"],
    ["本机", "本地"],
    ["远端", "远程"],
    ["软体", "软件"],
    ["专案", "项目"],
    ["安装档", "安装包"],
    ["贩售", "销售"],
    ["讯息", "信息"],
    ["装置", "设备"],
    ["目前", "当前"],
    ["资讯", "信息"],
    ["资料", "数据"],
    ["网域", "域名"],
    ["开启", "打开"],
    ["逾时", "超时"],
    ["连线", "连接"],
    ["连结", "链接"],
    ["程式", "程序"],
    ["介面", "界面"],
    ["选单", "菜单"],
    ["档案", "文件"],
    ["储存", "保存"],
    ["载入", "加载"],
    ["使用者", "用户"],
    ["汇入", "导入"],
    ["汇出", "导出"],
    ["新增", "添加"],
    ["设定", "设置"],
    ["预设", "默认"],
    ["贴上", "粘贴"],
    ["点选", "点击"],
  ];
  const SIMP_CHARS = {"並":"并","來":"来","個":"个","側":"侧","偵":"侦","備":"备","傳":"传","僅":"仅","內":"内","別":"别","刪":"删","則":"则","動":"动","務":"务","匯":"汇","區":"区","協":"协","參":"参","啟":"启","單":"单","國":"国","圖":"图","執":"执","場":"场","夾":"夹","實":"实","專":"专","尋":"寻","屬":"属","幾":"几","彈":"弹","後":"后","從":"从","復":"复","態":"态","應":"应","戶":"户","換":"换","擇":"择","擊":"击","據":"据","敗":"败","數":"数","斷":"断","於":"于","時":"时","書":"书","會":"会","條":"条","業":"业","標":"标","機":"机","檔":"档","檢":"检","欄":"栏","權":"权","歷":"历","歸":"归","氣":"气","沒":"没","淺":"浅","測":"测","準":"准","滾":"滚","瀏":"浏","為":"为","無":"无","熱":"热","狀":"状","獲":"获","現":"现","產":"产","當":"当","疊":"叠","發":"发","確":"确","碼":"码","稱":"称","積":"积","穩":"稳","節":"节","範":"范","簡":"简","籤":"签","紀":"纪","組":"组","結":"结","統":"统","經":"经","網":"网","線":"线","續":"续","與":"与","蓋":"盖","薦":"荐","處":"处","號":"号","裝":"装","裡":"里","製":"制","複":"复","規":"规","覽":"览","觀":"观","訂":"订","計":"计","訊":"讯","記":"记","設":"设","診":"诊","誌":"志","認":"认","語":"语","誤":"误","請":"请","證":"证","識":"识","議":"议","讀":"读","販":"贩","貼":"贴","資":"资","軟":"软","較":"较","載":"载","輸":"输","轉":"转","這":"这","連":"连","運":"运","過":"过","遠":"远","適":"适","遲":"迟","選":"选","還":"还","錄":"录","錯":"错","鍵":"键","鏈":"链","長":"长","門":"门","閉":"闭","開":"开","間":"间","閱":"阅","關":"关","階":"阶","際":"际","隨":"随","險":"险","隱":"隐","雙":"双","電":"电","頁":"页","預":"预","頭":"头","題":"题","顯":"显","風":"风","驗":"验","體":"体","點":"点"};
  let active = "zh-Hant";
  const originals = new WeakMap();
  const rendered = new WeakMap();
  const attrOrigins = new WeakMap();
  function choose(pref) {
    if (pref === "zh-Hant" || pref === "zh-Hans" || pref === "en") return pref;
    const l = String(navigator.language || "zh-Hant").toLowerCase();
    if (l.startsWith("zh-cn") || l.startsWith("zh-sg") || l === "zh-hans") return "zh-Hans";
    if (l.startsWith("zh")) return "zh-Hant";
    return "en";
  }
  function simple(text) {
    let out = Array.from(text).map((ch) => SIMP_CHARS[ch] || ch).join("");
    for (const [from, to] of SIMP_TERMS) out = out.split(from).join(to);
    return out;
  }
  function withSpace(src, out) {
    const m = src.match(/^(\s*)([\s\S]*?)(\s*)$/);
    return m ? m[1] + out + m[3] : out;
  }
  function translate(src, target = active) {
    const text = String(src ?? "");
    if (!text || target === "zh-Hant") return text;
    const lead = text.match(/^(\s*)([\s\S]*?)(\s*)$/);
    if (!lead) return text;
    const body = lead[2];
    if (target === "zh-Hans") return lead[1] + simple(body) + lead[3];
    const hasHan = /[\u3400-\u9fff]/.test(body);
    if (!hasHan) {
      return lead[1] + body
        .replace(/、/g, ", ")
        .replace(/。/g, ".")
        .replace(/；/g, "; ")
        .replace(/：/g, ": ")
        .replace(/（/g, "(")
        .replace(/）/g, ")")
        .replace(/，/g, ", ")
        .replace(/？/g, "?")
        .replace(/！/g, "!")
        .replace(/／/g, "/") + lead[3];
    }
    const normalized = body.replace(/\s+/g, " ").trim();
    let out = EN[body] || EN[normalized];
    if (!out) {
      out = body
        .replace(/(\d+)\s*小時\s*(\d+)\s*分/g, "$1h $2m")
        .replace(/(\d+)\s*分\s*(\d+)\s*秒/g, "$1m $2s")
        .replace(/(\d+(?:\.\d+)?)\s*秒/g, "$1s")
        .replace(/(\d+)\s*分/g, "$1m")
        .replace(/(\d+)\s*次/g, "$1 times")
        .replace(/(\d+(?:\.\d+)?)%\s*逾時/g, "$1% timed out")
        .replace(/穩定\s*(\d+)/g, "Stability $1");
      for (const [from, to] of PHRASES) out = out.split(from).join(to);
      out = out
        .replace(/、/g, ", ")
        .replace(/。/g, ".")
        .replace(/；/g, "; ")
        .replace(/：/g, ": ")
        .replace(/（/g, "(")
        .replace(/）/g, ")")
        .replace(/，/g, ", ")
        .replace(/？/g, "?")
        .replace(/！/g, "!")
        .replace(/／/g, "/");
    }
    return lead[1] + out + lead[3];
  }
  function skipped(el) { return !!(el && el.closest && el.closest("[data-no-i18n]")); }
  function textNode(node) {
    if (!node || skipped(node.parentElement)) return;
    let source = originals.get(node);
    if (source === undefined) {
      if (!node.nodeValue || !/[\u3400-\u9fff]/.test(node.nodeValue)) return;
      source = node.nodeValue;
      originals.set(node, source);
    }
    const value = translate(source);
    if (value !== node.nodeValue) node.nodeValue = value;
    rendered.set(node, value);
  }
  function elementAttrs(el) {
    if (!el || skipped(el) || el.hasAttribute?.("data-no-i18n-attrs")) return;
    let store = attrOrigins.get(el);
    if (!store) { store = {}; attrOrigins.set(el, store); }
    for (const name of ["placeholder", "title", "aria-label", "alt"]) {
      if (!el.hasAttribute || !el.hasAttribute(name)) continue;
      if (!(name in store)) store[name] = el.getAttribute(name);
      const source = store[name];
      const value = translate(source);
      if (value !== el.getAttribute(name)) el.setAttribute(name, value);
    }
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) { textNode(root); return; }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
    if (root.nodeType === Node.ELEMENT_NODE) elementAttrs(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let node = walker.nextNode();
    while (node) {
      if (node.nodeType === Node.TEXT_NODE) textNode(node); else elementAttrs(node);
      node = walker.nextNode();
    }
  }
  function setLanguage(value) {
    active = choose(value);
    document.documentElement.lang = active;
    walk(document.body);
    return active;
  }
  function refresh() {
    if (document.body) walk(document.body);
  }
  function observe() {
    const observer = new MutationObserver((records) => {
      for (const r of records) {
        if (r.type === "characterData") {
          const n = r.target;
          if (rendered.has(n) && n.nodeValue === rendered.get(n)) continue;
          originals.delete(n);
          rendered.delete(n);
          textNode(n);
        } else if (r.type === "attributes") {
          const el = r.target;
          const store = attrOrigins.get(el);
          if (store && store[r.attributeName] && el.getAttribute(r.attributeName) === translate(store[r.attributeName])) continue;
          if (store) delete store[r.attributeName];
          elementAttrs(el);
        } else if (r.type === "childList") {
          for (const n of r.addedNodes) walk(n);
        }
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["placeholder", "title", "aria-label", "alt"] });
  }
  window.KumoI18n = { translate, setLanguage, refresh, observe, choose, get language() { return active; } };
})();