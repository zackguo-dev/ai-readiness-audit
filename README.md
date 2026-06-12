# ai-readiness-audit

WebサイトがAIクローラーにどれだけ読めるかを診断するCLIツール。  
個人事業「AI可読性診断サービス」の商売道具。**レポート品質=商品品質。**

---

## クイックスタート

```bash
# 診断実行
uv run ai-audit run https://example.com

# レポートをファイルに保存
uv run ai-audit run https://example.com --out report.md

# 結果はJSON形式でも自動保存される
# → results/{ドメイン}/{タイムスタンプ}.json
```

---

## インストール

```bash
git clone https://github.com/kaku101127/ai-readiness-audit
cd ai-readiness-audit
uv sync
uv run playwright install chromium
```

**動作環境:** Python 3.12+ / uv

---

## 診断項目(v1)

| # | チェック名 | 概要 | 重み |
|---|---|---|---|
| 1 | bot_access | 主要AIボット8種のアクセス可否(robots.txt+実HEADリクエスト) | 高 |
| 2 | llms_txt | llms.txt / llms-full.txt の存在とフォーマット | 低 |
| 3 | js_dependency | 静的HTML vs Playwrightレンダリング後のテキスト量比較 | 最高 |
| 4 | structured_data | JSON-LD(Schema.org)の実装状況と必須プロパティ欠落 | 高 |
| 5 | semantic_html | 見出し階層・alt・meta description・OGP | 中 |
| 6 | freshness | 更新日マークアップ・sitemap.xml | 中 |

**監視対象AIボット(bot_access):**
GPTBot / ClaudeBot / Claude-Web / PerplexityBot / Google-Extended / CCBot / Bytespider / meta-externalagent

---

## プロジェクト構成

```
ai_audit/
  cli.py              # typerエントリポイント
  target.py           # TargetSite: 1回フェッチして全checkで使い回す中核オブジェクト
  checks/
    bot_access.py
    llms_txt.py
    js_dependency.py
    structured_data.py
    semantic_html.py
    freshness.py
  report/
    renderer.py       # Jinja2でMarkdown生成
    templates/        # レポートテンプレート
results/              # 診断結果JSON(自動生成)
tests/
  fixtures/           # HTMLフィクスチャ(実サイトに依存しないテスト用)
.claude/agents/       # MasterClaude配下のサブエージェント定義
CLAUDE.md             # 開発憲法(エージェントへの指示を含む)
```

---

## TargetSite 仕様

```python
@dataclass
class TargetSite:
    url: str              # 正規化済み入力URL
    final_url: str        # リダイレクト後URL
    status: int
    headers: dict[str, str]
    html: str             # 静的HTML(httpx GET)
    robots_txt: str|None  # なければNone
    llms_txt: str|None
    llms_full_txt: str|None
    fetched_at: datetime
    errors: list[str]     # 取得失敗の記録

    @cached_property
    def tree(self): ...   # selectolaxで遅延パース

    @classmethod
    def fetch(cls, url, *, timeout=10, retries=2,
              delay=1.0, user_agent="ai-audit/0.1") -> "TargetSite":
        # ページ→robots→llms→llms-full を1秒以上あけて順に取得
        # final_urlとurlが別ドメインの場合はerrors[]に記録してレポートに明記
```

**設計原則:** checkは自分でフェッチしない。取得済みデータだけを参照する。  
例外: bot_access のUA別HEADリクエストのみ、check側が1秒間隔で実行。

---

## CheckResult 仕様

```python
@dataclass
class CheckResult:
    score: int                    # 0-100
    findings: list[str]           # 発見した問題(日本語)
    recommendations: list[dict]   # 改善提案
    # recommendations の各要素:
    # {
    #   "text": "提案内容",
    #   "type": "self" | "professional",  # 自分でできる / 制作会社に依頼
    #   "cost": "費用目安(typeがprofessionalの場合)",
    #   "priority": "high" | "medium" | "low"
    # }
```

---

## エージェント体制(Claude Code)

| エージェント | 役割 | 起動タイミング |
|---|---|---|
| check-builder | 診断モジュール実装 | checks/の実装・変更時 |
| test-guardian | テスト作成・実行 | 実装完了直後(省略禁止) |
| report-craftsman | レポート文言・テンプレート | 日本語出力の変更時 |
| scope-keeper | スコープ監視・セッション管理 | 開始時・終了時・脱線時 |

---

## テスト

```bash
uv run pytest                    # 全テスト
uv run pytest tests/test_bot.py  # 項目を絞る
uv run pytest -v                 # 詳細表示
```

**方針:** 各checkにつき最低3ケース(正常系/問題検出系/壊れた入力)。  
実サイトへのネットワークアクセスは自分のサイト以外で使わない。

---

## バージョン管理・リリース方針

| バージョン | 内容 |
|---|---|
| v1(現在) | 診断6項目・Markdownレポート・JSONログ |
| v2(予定) | LLM APIでのAI言及モニタリング(別リポジトリ) |
| 未定 | PDF納品・GUI・SEO順位チェック |

**スコープ外(v1では追加しない):** 上記「未定」欄のもの。アイデアはBACKLOG.mdへ。

---

## 診断倫理・利用上の注意

- 他者のサイトを診断する前に必ず許可を取ること
- bot_accessのHEADリクエストはUA偽装ではなく正規のクローラーと同じ動作
- レポートで「AIに必ず引用される」等の断定表現を使わないこと(report-craftsmanに組込済み)
- llms.txtの効果は現時点で限定的。顧客への説明時も正直に伝える

---

## 開発ログ

- 2026-06-12: v1完成。全6チェック・JSON保存・MD出力を確認(zenn.dev: 38/100)

---

## ライセンス

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.ja)

個人学習目的の閲覧・利用は自由。サービスとしての再販・商用利用は禁止。
