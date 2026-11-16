# 部署與鏡像

下載站 `site/` 是純靜態檔案，同一份內容可同時發佈到多個主機。GitHub Pages 是主站，
其餘為備援；所有工作流在缺少 secrets 時會自動跳過，fork 不用改任何東西。

| 站點 | 觸發 | 需要的設定 | 備註 |
|---|---|---|---|
| GitHub Pages → https://cypwlp.github.io/kumoroute/ | push `main`（`site/**`） | 無（Settings → Pages → Source: GitHub Actions） | 主站，`<meta http-equiv>` 形式的 CSP |
| Cloudflare Pages | push `main`（`site/**`） | `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`，選用 `CLOUDFLARE_PROJECT` | 真正的 HTTP 標頭（`site/_headers`），可自訂域名 |
| 騰訊雲裸 IP → http://129.204.149.106/ | 手動 | SSH 金鑰 | `bash packaging/deploy-tencent.sh` |
| Gitee → 僅程式碼鏡像 | push `main` / tag | `GITEE_SSH_KEY`、`GITEE_REPO`，選用 `GITEE_SSH_KNOWN_HOSTS` | **不含網站**（見下） |

## Gitee Pages 已停止服務

Gitee Pages（含 Pro）於 2024 年停止對外服務，現在無法再開通或續用，因此本專案
不再提供 gitee.io 站點。Gitee 只作為**原始碼鏡像**，讓大陸使用者能讀取程式碼與
Release 說明；下載與網站仍走 GitHub Pages／Cloudflare Pages／騰訊雲鏡像。

## Cloudflare Pages（建議的中國大陸友善備援）

1. Cloudflare Dashboard → Pages → Create → Connect to Git，選這個 repo。
2. Build command 留空，Build output directory 填 `site`，Framework preset 選 `None`。
3. 部署後在 Custom domains 綁 `kumoroute.cypilu.cloud`（免費、自動簽發憑證，不需要 ICP 備案）。
4. 想改由 Actions 部署（而非 Git 整合）時，建立 API Token（權限 `Pages:Edit`），
   把 `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID` 加進 repo secrets；
   `.github/workflows/deploy-cloudflare.yml` 會自動接手，並套用 `site/_headers` 的
   快取與安全標頭（GitHub Pages 無法送出這些 response header）。

同一個 Pages 專案可綁多個自訂域名；若走 GitHub 整合方式，就不要同時啟用 Actions 部署，
避免兩邊互相覆蓋。

## Gitee 程式碼鏡像

1. 在 Gitee 建立空 repo（不要初始化 README）。
2. 該 repo → Settings → Deploy Keys → 新增一把金鑰並勾選 write 權限；
   私鑰存進 GitHub secret `GITEE_SSH_KEY`，主機指紋存進 `GITEE_SSH_KNOWN_HOSTS`
   （`ssh-keyscan gitee.com` 的輸出）。
3. 新增 repository variable `GITEE_REPO`，例如 `git@gitee.com:cypwlp/kumoroute.git`。
4. 之後每次 push `main` 或建立 `v*` tag，`.github/workflows/mirror-gitee.yml` 會同步
   所有分支與 tag（`git push --prune`，Gitee 上已刪除的分支也會被清掉）。

另一個做法是用 Gitee 的「倉庫鏡像管理」主動拉 GitHub，設定更少，但同步方向只能
GitHub → Gitee，且無法鏡像刪除。

## 騰訊雲裸 IP 鏡像

- 同步：`bash packaging/deploy-tencent.sh`（SSH 到 `ubuntu@129.204.149.106`，上傳 `site/` 到 `/var/www/kumoroute`）
- nginx 站點：`/etc/nginx/sites-available/kumoroute`；Let's Encrypt 憑證已配置，待域名可合規對外服務後啟用
- 只有 HTTP，適合當最後一道備援；不建議在此站直接提供大檔案下載
