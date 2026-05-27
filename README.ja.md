# Financial Analyzer

[English](README.md) | **[日本語]**

> 有価証券報告書（PDF）から財務データを自動抽出・比較・可視化するWebツール

EDINET形式のPDFレポートから連結財務データを直接読み取り、比較可能なダッシュボードとして表示します。大学院研究で数十本の有報を読み込む作業を効率化するために開発し、同様の作業をしている方が使えるよう公開しました。

GitHub: **<https://github.com/Kazaav/Financial_Analyzer>**  
Live: **<https://fin.zekkx.icu>**

---

## 機能

- **構造解析PDF読み取り** — 「主要な経営指標等の推移」「連結貸借対照表 / 連結財政状態計算書」「連結損益計算書」「連結キャッシュ・フロー計算書」の各セクションをページ単位で特定。日本基準（JGAAP）・IFRS両対応、同義語解決付き（売上高 ⇆ 売上収益、親会社株主に帰属する当期純利益 ⇆ 親会社の所有者に帰属する当期利益、純資産 ⇆ 資本合計 等）
- **生指標13項目 + 派生指標12項目** — 売上高・純利益・総資産・キャッシュフローをPDFから直接抽出；ROA・ROE・自己資本比率・各種利益率・成長率は計算式とともに表示
- **3つの分析モード**
  - **多社同年度** — 複数企業を同一年度で横断比較
  - **同一企業時系列** — 1社の複数年度推移を追跡
  - **カスタム** — 任意のPDFを自由に組み合わせて比較
- **出典トレーサビリティ** — 抽出した数値にはページバッジが付き、クリックするとPDF原文ページをインライン表示
- **インタラクティブチャート** — ECharts（ダークテーマ）；モードに応じて折れ線 / 棒 / 散布図を自動選択
- **エクスポート** — CSV（UTF-8 BOM、Excelでそのまま開ける）・Excel（3シート構成、抽出元情報付き）・JSON（完全構造化）・印刷品質HTMLレポート・ブラウザPDF印刷
- **3言語UI** — 日本語 / 英語 / 中国語（財務用語は原文書に合わせて日本語のまま）
- **パブリックデモ** — ランディングページに3件のサンプル分析をプリセット；ログイン不要で閲覧可能

---

## 技術スタック

- **バックエンド**: Python 3.11+、FastAPI、uvicorn
- **PDF解析**: PyMuPDF (fitz)
- **チャート**: ECharts 5（CDN）
- **Excelエクスポート**: openpyxl
- **テンプレート**: Jinja2
- **フロントエンド**: バニラHTML/CSS/JS — ビルドステップなし
- **可観測性**: prometheus_client、JSONラインログ
- **リバースプロキシ（本番）**: Caddy（自動HTTPS）
- **プロセス管理**: systemd

JavaScriptフレームワーク不使用、バンドラー不要、Docker不要。`uvicorn` 1コマンドで起動します。

---

## アーキテクチャ

```
┌────────────────────────────────────────────────────────────────┐
│                          ブラウザ                                │
│  ランディング · デモ · 分析ダッシュボード · ECharts · 原文モーダル  │
└──────────────────────────────┬─────────────────────────────────┘
                               │ HTTPS
                       ┌───────▼────────┐
                       │     Caddy      │   （自動TLS、gzip/zstd圧縮）
                       └───────┬────────┘
                               │ HTTP 127.0.0.1:8010
                  ┌────────────▼────────────┐
                  │      FastAPI アプリ      │
                  │  ┌──────────────────┐   │
                  │  │ 認証 + i18n + クリーンアップ ミドルウェア │
                  │  │ メトリクス ミドルウェア │
                  │  └────────┬─────────┘   │
                  │           │             │
                  │  ┌────────▼─────────┐   │
                  │  │ pdf_parser.py    │   │  PyMuPDF テキスト抽出
                  │  │ analysis.py      │   │  同義語解決
                  │  │ export.py        │   │  派生指標計算
                  │  │ reporting.py     │   │  CSV/XLSX/JSON エクスポート
                  │  └────────┬─────────┘   │
                  │           │             │
                  │  ┌────────▼─────────┐   │
                  │  │  ストレージ（JSON）│  │  /var/lib/financial-analyzer/
                  │  └──────────────────┘   │
                  └─────────────────────────┘
```

ストレージはディスク上のプレーンJSONファイル — 個人ツール用途では十分で、バックアップも簡単です。

---

## クイックスタート

### 前提条件
- Python 3.11 以上
- venv + 依存パッケージ用に約100MBの空き容量

### ローカル実行

```bash
git clone https://github.com/Kazaav/Financial_Analyzer.git
cd Financial_Analyzer
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -e ".[dev]"

# 任意：ストレージ先を変更する場合
export FINANCIAL_ANALYZER_STORAGE=/tmp/fa-storage

# 任意：デフォルトユーザーを変更する場合（admin / guest001）
#   形式: username:role:pbkdf2_sha256$iterations$salt$hash
# export FINANCIAL_ANALYZER_USERS="me:admin:pbkdf2_sha256$..."

uvicorn app.main:app --reload --port 8010
```

<http://localhost:8010> をブラウザで開く。デフォルト認証情報: `admin` / `guest001`

### テスト実行

```bash
pytest                              # 全テスト
pytest tests/test_pdf_parser.py     # パーサー単体テストのみ
ruff check .                        # リント
mypy app                            # 型チェック（非strict）
```

---

## 設定

| 環境変数 | デフォルト | 用途 |
| --- | --- | --- |
| `FINANCIAL_ANALYZER_STORAGE` | `./storage` | 分析JSON・アップロード・レポートの保存先 |
| `FINANCIAL_ANALYZER_USERS` | `admin:admin:pbkdf2_sha256$...` | セミコロン区切りの `username:role:hash` 形式のユーザー一覧 |
| `FINANCIAL_ANALYZER_SESSION_SECRET` | プロセス起動時にランダム生成 | セッションCookieのHMACシークレット（本番では必ず設定） |
| `FINANCIAL_ANALYZER_SESSION_MAX_AGE_SECONDS` | 43200（12時間） | ログイン持続時間 |
| `FINANCIAL_ANALYZER_COOKIE_SECURE` | `0` | HTTPS環境では `1` に設定（CookieをHTTPS専用にする） |
| `FINANCIAL_ANALYZER_RETENTION_DAYS` | `7` | アップロード・レポートの保持日数；`0` でクリーンアップ無効 |

デモレコード（分析ID が `demo-` で始まるもの）はクリーンアップ対象外です。

パスワードのハッシュ生成:

```python
import hashlib, base64, secrets
salt = base64.urlsafe_b64encode(secrets.token_bytes(16)).decode().rstrip("=")
digest = hashlib.pbkdf2_hmac("sha256", b"yourpassword", salt.encode(), 260000)
print("pbkdf2_sha256$260000$" + salt + "$" + base64.urlsafe_b64encode(digest).decode().rstrip("="))
```

---

## APIエンドポイント

主要なエンドポイント一覧：

```
GET  /                                          # パブリック ランディングページ
GET  /demo/{slug}                               # パブリック デモ（読み取り専用）
GET  /app                                       # 認証済み アップロードページ
GET  /analysis/{id}                             # 分析ダッシュボード
GET  /analysis/{id}/export.{csv,xlsx,json}      # エクスポート
GET  /source-page/{analysis}/{doc}/{page}.png   # PDF原文ページ（原文ビューア用）
GET  /set-lang/{ja|en|zh}                       # UI言語切り替え
GET  /metrics                                   # Prometheus メトリクス
GET  /healthz                                   # ヘルスチェック
```

`/analysis/demo-*` パスはパブリック公開 — デモ閲覧者がモード切り替えをしてもログインリダイレクトされません。

---

## パーサーについて

日本の有価証券報告書は外見上は統一されていますが、テキスト構造は報告書によって大きく異なります。パーサーは以下の3点でロバスト性を確保しています：

1. **ページ番号ではなくセクションアンカーで位置を特定**。「主要な経営指標等の推移」「連結損益計算書」「連結財政状態計算書」等の見出しをマッチさせ、対象ページ範囲内のみをスキャン。

2. **指標ごとの同義語ラダー**。各指標（売上高、純利益、純資産等）に優先度付きのラベルパターンリストを持ち、IFRSラベルを先に試してからJGAAPを試すことで、移行年度（IFRS表とJGAAP表が共存する報告書）でも正しい列を取得。

3. **括弧付き注記ガード**。従業員数の後に続く `(27)` のような副行（= 平均臨時従業員数）を検出してコレクションを終了させつつ、キャッシュフロー行の `△N`（通常の負値）は引き続き収集。

これまでに対応した実績エッジケース: TIS、アバントグループ、野村総合研究所（JGAAP→IFRS移行、千円 vs 百万円の単位差、親会社単体 vs 連結の指標テーブル混在）。追加サンプルのPRを歓迎します。

---

## ライセンス

[MIT](LICENSE)
