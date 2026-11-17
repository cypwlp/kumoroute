"""Generate the three localized feedback pages.

The site has no backend by design. These pages collect nothing themselves: they
explain what to include in a report and deep-link into GitHub Issues with the
template prefilled. Sensitive issues are routed to private security advisories.

  python scripts/gen_feedback_pages.py
  python scripts/gen_feedback_pages.py --check   # CI guard

Edit the strings below, rerun the generator, then run scripts/inline_css.py.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from urllib.parse import quote, urlencode

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
REPO = "https://github.com/cypwlp/kumoroute"
BASE = "https://cypwlp.github.io/kumoroute/"
CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; "
    "script-src 'self'; connect-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'none'"
)


def issue_url(title: str, body: str, label: str) -> str:
    return REPO + "/issues/new?" + urlencode(
        {"title": title, "body": body, "labels": label}, quote_via=quote
    )


CONFIG = {
    "": {
        "lang": "zh-Hant",
        "prefix": "",
        "skip": "跳至主要內容",
        "title": "回報問題或留言 — KumoRoute",
        "desc": "回報 KumoRoute 的問題或提出建議。送出前請先移除訂閱連結、IP 與敏感資訊；內容會寫入公開的 GitHub Issues。",
        "h1": "回報問題或留言",
        "intro": "KumoRoute 沒有帳號或客服系統。問題與建議會直接寫到公開的 GitHub Issues —— 除了你主動貼上的內容，本站不會上傳任何資料。",
        "note": "請先移除訂閱連結、節點網址、IP 位址、VPN 憑證與完整日誌。安全性漏洞請改用下面的「安全性問題」私下回報，不要公開張貼。",
        "nav": "主導覽",
        "download": "下載",
        "faq": "常見問題",
        "feedback": "回報問題",
        "lang_label": "語言",
        "home": "首頁",
        "privacy": "隱私政策",
        "terms": "服務條款",
        "steps_heading": "送出前，先準備這些資訊",
        "steps": [
            '先看一下 <a href="./#faq">常見問題</a>，說不定已有解答。',
            "記下設定頁顯示的版本號、作業系統與裝置型號。",
            "寫下重現步驟、預期結果與實際結果；有截圖會更好。",
            "若要附診斷檔，請先用程式內的匯出功能（會自動移除訂閱網址、IP 與敏感端點）。",
        ],
        "ways_heading": "選擇回報方式",
        "bug": ("回報錯誤", "自動帶入錯誤回報範本並標記為 bug", "🐞"),
        "idea": ("功能建議", "自動帶入建議範本並標記為 enhancement", "💡"),
        "security": ("安全性問題", "私下回報漏洞，不會公開細節", "🔒"),
        "bug_title": "[Bug] ",
        "idea_title": "[建議] ",
        "template_heading": "回報範本",
        "template_note": "下方文字可自行選取複製，再貼到任何你方便使用的管道；按鈕會嘗試自動複製。",
        "copy": "複製範本",
        "copied": "已複製",
        "select": "已選取，請按 Ctrl+C",
        "disclaimer": "KumoRoute 為獨立開源專案，不提供任何代理節點或訂閱服務。",
        "template": """【不要在公開 Issue 貼上訂閱連結、節點網址、IP、VPN 憑證或完整日誌】

**版本**
- KumoRoute：（設定頁顯示的版本號）
- 系統：（Windows 11 / Ubuntu 24.04 / macOS 15 ...）

**發生什麼**

**重現步驟**
1.
2.
3.

**預期結果**

**實際結果**

**已嘗試過的方法**

**診斷資訊**
（若已匯出診斷檔，確認已去識別化後再附上；也可只貼相關片段）

**附加檔案**
（截圖 / 去識別化日誌）""",
    },
    "en/": {
        "lang": "en",
        "prefix": "../",
        "skip": "Skip to main content",
        "title": "Feedback & bug reports — KumoRoute",
        "desc": "Report a KumoRoute problem or suggest a feature. Remove subscription URLs, IPs and sensitive data first; reports go to public GitHub Issues.",
        "h1": "Feedback & bug reports",
        "intro": "KumoRoute has no account or support desk. Reports go straight to public GitHub Issues — the site itself uploads nothing beyond what you choose to paste.",
        "note": "Remove subscription URLs, node addresses, IP addresses, VPN credentials and full logs first. For security vulnerabilities use the private “Security issue” link below instead of a public issue.",
        "nav": "Main",
        "download": "Download",
        "faq": "FAQ",
        "feedback": "Feedback",
        "lang_label": "Language",
        "home": "Home",
        "privacy": "Privacy policy",
        "terms": "Terms of service",
        "steps_heading": "Before you send",
        "steps": [
            'Check the <a href="./#faq">FAQ</a> first — your question may already be answered.',
            "Note the version shown in Settings, your OS and device model.",
            "Write down the steps to reproduce, what you expected and what happened; a screenshot helps.",
            "For diagnostics, use the in-app export (it strips subscription URLs, IPs and sensitive endpoints).",
        ],
        "ways_heading": "Choose where to send it",
        "bug": ("Report a bug", "Opens a prefilled issue labelled bug", "🐞"),
        "idea": ("Suggest a feature", "Opens a prefilled issue labelled enhancement", "💡"),
        "security": ("Security issue", "Report privately, no public details", "🔒"),
        "bug_title": "[Bug] ",
        "idea_title": "[Idea] ",
        "template_heading": "Report template",
        "template_note": "The text below can be selected and copied manually; the button tries to copy it for you.",
        "copy": "Copy template",
        "copied": "Copied",
        "select": "Selected — press Ctrl+C",
        "disclaimer": "KumoRoute is an independent open-source project and provides no proxy nodes or subscription services.",
        "template": """DO NOT paste subscription URLs, node addresses, IPs, VPN credentials or full logs into a public issue.

**Version**
- KumoRoute: (version shown in Settings)
- OS: (Windows 11 / Ubuntu 24.04 / macOS 15 ...)

**What happened**

**Steps to reproduce**
1.
2.
3.

**Expected result**

**Actual result**

**What you already tried**

**Diagnostics**
(If you exported a bundle, verify it is redacted first; relevant excerpts are fine)

**Attachments**
(screenshots / redacted logs)""",
    },
    "zh-cn/": {
        "lang": "zh-Hans",
        "prefix": "../",
        "skip": "跳至主要内容",
        "title": "反馈与问题回报 — KumoRoute",
        "desc": "回报 KumoRoute 问题或提出建议。送出前请先移除订阅链接、IP 与敏感资讯；内容会写入公开的 GitHub Issues。",
        "h1": "反馈与问题回报",
        "intro": "KumoRoute 没有账号或客服系统。问题与建议会直接写到公开的 GitHub Issues —— 除了你主动贴上的内容，本站不会上传任何资料。",
        "note": "请先移除订阅链接、节点网址、IP 地址、VPN 凭据与完整日志。安全性漏洞请改用下方的“安全性问题”私下回报，不要公开张贴。",
        "nav": "主导航",
        "download": "下载",
        "faq": "常见问题",
        "feedback": "问题回报",
        "lang_label": "语言",
        "home": "首页",
        "privacy": "隐私政策",
        "terms": "服务条款",
        "steps_heading": "送出前，先准备这些信息",
        "steps": [
            '先看一下 <a href="./#faq">常见问题</a>，说不定已有解答。',
            "记下设置页显示的版本号、操作系统与设备型号。",
            "写下重现步骤、预期结果与实际结果；有截图更好。",
            "若要附诊断档，请先用程序内的导出功能（会自动移除订阅网址、IP 与敏感端点）。",
        ],
        "ways_heading": "选择回报方式",
        "bug": ("回报错误", "自动带入错误回报范本并标记为 bug", "🐞"),
        "idea": ("功能建议", "自动带入建议范本并标记为 enhancement", "💡"),
        "security": ("安全性问题", "私下回报漏洞，不公开细节", "🔒"),
        "bug_title": "[Bug] ",
        "idea_title": "[建议] ",
        "template_heading": "回报范本",
        "template_note": "下方文字可自行选取复制，再贴到你方便使用的管道；按钮会尝试自动复制。",
        "copy": "复制范本",
        "copied": "已复制",
        "select": "已选取，请按 Ctrl+C",
        "disclaimer": "KumoRoute 为独立开源项目，不提供任何代理节点或订阅服务。",
        "template": """【不要在公开 Issue 贴上订阅链接、节点网址、IP、VPN 凭据或完整日志】

**版本**
- KumoRoute：（设置页显示的版本号）
- 系统：（Windows 11 / Ubuntu 24.04 / macOS 15 ...）

**发生了什么**

**重现步骤**
1.
2.
3.

**预期结果**

**实际结果**

**已尝试过的方法**

**诊断信息**
（若已导出诊断档，确认已去识别化后再附上；也可只贴相关片段）

**附加文件**
（截图 / 去识别化日志）""",
    },
}

ALTERNATES = {
    "": ("zh-Hant", "feedback.html"),
    "en/": ("en", "en/feedback.html"),
    "zh-cn/": ("zh-Hans", "zh-cn/feedback.html"),
}


def page(key: str, c: dict) -> str:
    prefix = c["prefix"]
    alternates = "\n".join(
        f'<link rel="alternate" hreflang="{lang}" href="{BASE}{url}">'
        for lang, url in ALTERNATES.values()
    )
    xdefault = f'<link rel="alternate" hreflang="x-default" href="{BASE}feedback.html">'
    steps = "".join(f"<li>{s}</li>" for s in c["steps"])

    def card(label: str, desc: str, icon: str, href: str) -> str:
        return (
            f'<a class="feedback-card" href="{html.escape(href, quote=True)}" '
            'target="_blank" rel="noopener">'
            f'<span class="feature-icon">{icon}</span><b>{label}</b><span>{desc}</span></a>'
        )

    bug_url = issue_url(c["bug_title"], c["template"], "bug")
    idea_url = issue_url(c["idea_title"], c["template"], "enhancement")

    return f"""<!DOCTYPE html>
<html lang="{c['lang']}">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#070a10">
<title>{c['title']}</title>
<meta name="description" content="{c['desc']}">
<link rel="canonical" href="{BASE}{ALTERNATES[key][1]}">
{alternates}
{xdefault}
<link rel="icon" href="{prefix}assets/icon.png">
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<a class="skip" href="#main">{c['skip']}</a>
<header class="nav"><div class="nav-inner"><a class="brand" href="./"><img src="{prefix}assets/icon.png" alt="KumoRoute" width="256" height="256" decoding="async"><span>KumoRoute</span></a><nav class="nav-links" aria-label="{c['nav']}"><a href="./#download">{c['download']}</a><a href="./#faq">{c['faq']}</a><a href="./feedback.html" aria-current="page">{c['feedback']}</a></nav><nav class="lang-switch" aria-label="{c['lang_label']}"><a href="{prefix}feedback.html" hreflang="zh-Hant" lang="zh-Hant" aria-current="{str(key == '').lower()}">繁中</a><a href="{prefix}zh-cn/feedback.html" hreflang="zh-Hans" lang="zh-Hans" aria-current="{str(key == 'zh-cn/').lower()}">简中</a><a href="{prefix}en/feedback.html" hreflang="en" lang="en" aria-current="{str(key == 'en/').lower()}">EN</a></nav></div></header>
<main class="legal-page" id="main" tabindex="-1">
<h1>{c['h1']}</h1>
<p class="lead">{c['intro']}</p>
<p class="legal-note">{c['note']}</p>
<h2>{c['steps_heading']}</h2>
<ol class="feedback-steps">{steps}</ol>
<h2>{c['ways_heading']}</h2>
<div class="feedback-grid">
{card(*c['bug'], bug_url)}
{card(*c['idea'], idea_url)}
{card(*c['security'], REPO + '/security/advisories/new')}
</div>
<h2>{c['template_heading']}</h2>
<p>{c['template_note']}</p>
<textarea id="report-template" class="report-template" rows="16" spellcheck="false" readonly>{html.escape(c['template'])}</textarea>
<div class="feedback-actions"><button class="btn ghost small" id="copy-template" type="button" data-copied="{c['copied']}" data-select="{c['select']}">{c['copy']}</button><span class="copy-status" id="copy-status" role="status" aria-live="polite"></span></div>
</main>
<footer><div class="foot-inner"><div class="foot-brand"><img src="{prefix}assets/icon.png" alt="" width="256" height="256" decoding="async"><span>KumoRoute</span></div><p class="disclaimer">{c['disclaimer']}</p><p class="foot-links"><a href="./">{c['home']}</a><a href="{prefix}privacy.html">{c['privacy']}</a><a href="{prefix}terms.html">{c['terms']}</a><a href="{prefix}feedback.html">{c['feedback']}</a><a href="{REPO}">GitHub</a></p></div></footer>
<script src="{prefix}app.js"></script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    paths = {key: SITE / key / "feedback.html" if key else SITE / "feedback.html" for key in CONFIG}

    # Compare against the fully inlined/CSP-pinned output, which is what
    # actually ships, so --check stays valid after inline_css.py has run.
    sys.path.insert(0, str(Path(__file__).parent))
    import inline_css

    expected = {key: inline_css.inline_page(page(key, CONFIG[key])) for key in CONFIG}
    if args.check:
        bad = [str(p.relative_to(ROOT)) for key, p in paths.items() if p.read_text(encoding="utf-8") != expected[key]]
        if bad:
            print("feedback pages out of date:", *bad, sep="\n  ")
            return 1
        print("feedback pages up to date")
        return 0
    for key, path in paths.items():
        path.write_text(expected[key], encoding="utf-8", newline="\n")
        print("wrote", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
