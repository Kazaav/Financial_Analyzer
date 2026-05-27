"""Minimal multi-language support (D4).

Scope: UI chrome only. Financial labels (売上高, 営業利益 etc.) intentionally
stay in Japanese because the source documents are 有価証券報告書.

Default language: Japanese. Switchable via cookie `fa_lang=ja|en|zh`.
"""
from __future__ import annotations

from fastapi import Request

SUPPORTED = ("ja", "en", "zh")
DEFAULT = "ja"
COOKIE_NAME = "fa_lang"


TRANSLATIONS: dict[str, dict[str, str]] = {
    "ja": {
        # Landing
        "landing.eyebrow": "日本上場企業 · 有価証券報告書",
        "landing.headline.line1": "財務データを、",
        "landing.headline.line2": "もっと素直に読む。",
        "landing.sub": "有価証券報告書 PDF から13項目の主要指標を自動抽出し、企業間・年度間で比較・可視化するツール。研究と実務の両方で「ただ素直に数字を並べる」体験を目指して作りました。",
        "landing.cta.samples": "サンプルを見る",
        "landing.cta.login": "ログインしてアップロード",
        "landing.section.samples": "サンプル分析 / Sample Analyses",
        "landing.section.capabilities": "機能 / Capabilities",
        "landing.cap1.title": "PDF 構造解析",
        "landing.cap1.desc": "主要な経営指標等の推移・連結 B/S・P/L・C/F の各セクションをページ単位で識別し抽出します。",
        "landing.cap2.title": "13指標 × 派生12指標",
        "landing.cap2.desc": "売上高・利益・資産・CF を自動抽出し、ROA・ROE・自己資本比率などを計算式とともに表示。",
        "landing.cap3.title": "3つの比較モード",
        "landing.cap3.desc": "多社同年度・同一企業時系列・カスタム選択。証券コード/EDINETによる企業同一性判定。",
        "landing.cap4.title": "レポート出力",
        "landing.cap4.desc": "分析結果を CSS 埋め込みのスタンドアロン HTML として出力可能。",
        "landing.demo.view": "View analysis →",
        # Nav
        "nav.github": "GitHub",
        "nav.login": "ログイン",
        "nav.logout": "ログアウト",
        "nav.app": "アプリへ",
        "nav.home": "トップ",
        "nav.new": "新規",
        # Tabs
        "tab.overview": "概要",
        "tab.metrics": "指標比較",
        "tab.charts": "チャート",
        "tab.manage": "管理",
        # Sidebar
        "sidebar.mode": "分析モード",
        "sidebar.export": "エクスポート",
        "sidebar.print": "印刷 / PDF 出力",
        "sidebar.report": "レポート生成",
        # Login
        "login.title": "ログイン",
        "login.username": "ユーザー名",
        "login.password": "パスワード",
        "login.submit": "ログイン",
        "login.back": "← トップに戻る",
        # Language names
        "lang.ja": "日本語",
        "lang.en": "English",
        "lang.zh": "中文",
    },
    "en": {
        "landing.eyebrow": "Japan-listed companies · Annual Securities Reports",
        "landing.headline.line1": "Read financial data",
        "landing.headline.line2": "the way it was filed.",
        "landing.sub": "Auto-extract 13 key indicators from Japanese 有価証券報告書 PDFs and compare them across companies and years. Built to make raw numbers speak — for research and practical analysis.",
        "landing.cta.samples": "View samples",
        "landing.cta.login": "Log in to upload",
        "landing.section.samples": "Sample Analyses",
        "landing.section.capabilities": "Capabilities",
        "landing.cap1.title": "PDF Structural Parsing",
        "landing.cap1.desc": "Locates 主要な経営指標等の推移, consolidated B/S, P/L and C/F sections page-by-page and extracts numbers in context.",
        "landing.cap2.title": "13 raw × 12 derived metrics",
        "landing.cap2.desc": "Sales, profit, assets and cash flow are auto-extracted. ROA, ROE, equity ratio and others are shown with their formulas.",
        "landing.cap3.title": "Three comparison modes",
        "landing.cap3.desc": "Cross-company same-year, single-company time-series, and custom selection. Companies are unified by securities code / EDINET.",
        "landing.cap4.title": "Report export",
        "landing.cap4.desc": "Analyses can be exported as standalone HTML, CSV, Excel and JSON.",
        "landing.demo.view": "View analysis →",
        "nav.github": "GitHub",
        "nav.login": "Log in",
        "nav.logout": "Log out",
        "nav.app": "Open app",
        "nav.home": "Home",
        "nav.new": "New",
        "tab.overview": "Overview",
        "tab.metrics": "Metrics",
        "tab.charts": "Charts",
        "tab.manage": "Manage",
        "sidebar.mode": "Analysis mode",
        "sidebar.export": "Export",
        "sidebar.print": "Print / Save as PDF",
        "sidebar.report": "Generate report",
        "login.title": "Sign in",
        "login.username": "Username",
        "login.password": "Password",
        "login.submit": "Sign in",
        "login.back": "← Back to home",
        "lang.ja": "日本語",
        "lang.en": "English",
        "lang.zh": "中文",
    },
    "zh": {
        "landing.eyebrow": "日本上市公司 · 有价证券报告书",
        "landing.headline.line1": "把财报数据，",
        "landing.headline.line2": "直白地读出来。",
        "landing.sub": "从有价证券报告书 PDF 自动抽取 13 个核心指标，支持多公司同年度、同公司多年度、自定义三种比较方式。为研究与实务而设计，让数字本身说话。",
        "landing.cta.samples": "查看示例",
        "landing.cta.login": "登录并上传",
        "landing.section.samples": "示例分析 / Sample Analyses",
        "landing.section.capabilities": "功能 / Capabilities",
        "landing.cap1.title": "PDF 结构解析",
        "landing.cap1.desc": "定位「主要な経営指標等の推移」、合并资产负债表、损益表与现金流量表，按页抽出数据并保留来源。",
        "landing.cap2.title": "13 原始 × 12 派生指标",
        "landing.cap2.desc": "自动提取销售额、利润、资产、现金流；ROA、ROE、自有资本比率等派生指标附带公式说明。",
        "landing.cap3.title": "三种比较模式",
        "landing.cap3.desc": "多公司同年度、同公司时系列、自定义自由组合。基于证券代码 / EDINET 的企业归一识别。",
        "landing.cap4.title": "报告导出",
        "landing.cap4.desc": "分析结果可导出为独立 HTML、CSV、Excel 与 JSON。",
        "landing.demo.view": "查看分析 →",
        "nav.github": "GitHub",
        "nav.login": "登录",
        "nav.logout": "退出",
        "nav.app": "进入应用",
        "nav.home": "首页",
        "nav.new": "新建",
        "tab.overview": "概要",
        "tab.metrics": "指标比较",
        "tab.charts": "图表",
        "tab.manage": "管理",
        "sidebar.mode": "分析模式",
        "sidebar.export": "导出",
        "sidebar.print": "打印 / 保存为 PDF",
        "sidebar.report": "生成报告",
        "login.title": "登录",
        "login.username": "用户名",
        "login.password": "密码",
        "login.submit": "登录",
        "login.back": "← 返回首页",
        "lang.ja": "日本語",
        "lang.en": "English",
        "lang.zh": "中文",
    },
}


def get_lang(request: Request) -> str:
    val = request.cookies.get(COOKIE_NAME, "")
    if val in SUPPORTED:
        return val
    return DEFAULT


def translator(lang: str):
    """Return a callable t(key, default=None) bound to a language."""
    fallback = TRANSLATIONS[DEFAULT]
    chosen = TRANSLATIONS.get(lang, fallback)

    def t(key: str, default: str | None = None) -> str:
        return chosen.get(key) or fallback.get(key) or (default if default is not None else key)

    return t
