# AI Readiness Audit — プロジェクト憲法

## この環境について（足場メモ）
- 単独プロジェクト。Nova Vault（`C:\Users\Tkaku\projects`）の**外**に置いてある（auto-commitフックの干渉を避けるため）。場所：`C:\Users\Tkaku\Product\dev\ai-readiness-audit`
- パッケージ管理は **uv**。実行は `uv run ai-audit ...` / テストは `uv run pytest`
- `.claude/agents/` のサブエージェントは**このディレクトリで `claude` を起動したときに有効**になる。委譲を効かせたいセッションは必ずここで起動すること

## 目的
WebサイトがAIクローラーにどれだけ読めるかを診断するCLI。個人事業
「AI可読性診断サービス」(診断3〜5万円/実装10〜30万円/月次)の商売道具。
レポート品質=商品品質。

## 経緯(なぜ作るか・何を作らないか)
- AI検索の普及で「AIに引用される」ことが集客の前提になった(GEO)
- ただし llms.txt 単体は主要AIクローラーがほぼ参照せず効果薄。本ツールは
  llms.txt屋ではなく、HTMLが実際にAIに読めるかの技術診断(JS依存度が本丸)
- 「効果不明な施策を効くと言わない誠実さ」が事業の差別化軸。レポート文言にも反映
  (llms.txtは「低コストな将来投資」と正直に書く)
- フェーズ1=本CLI開発 → フェーズ2=開発者自身のブログで実証 → フェーズ3=Zenn事例記事

## アーキテクチャ原則
- 各診断項目は checks/ 配下の独立モジュール。共通IF:
  run(target: TargetSite) -> CheckResult(score, findings, recommendations)
- TargetSiteは一度フェッチした内容を全checkで使い回す(同一URLを何度も叩かない)
- 対象サイトに負荷をかけない:リクエスト間1秒以上、robots.txt遵守、UA明示
- ネットワークは必ずタイムアウト・リトライ付き

## 診断項目(v1スコープ・これで固定)
1. bot_access: robots.txt解析+主要AIボットUA(GPTBot/ClaudeBot/Claude-Web/
   PerplexityBot/Google-Extended/CCBot/Bytespider/meta-externalagent)での
   HEADリクエストで誤ブロック検出
2. llms_txt: llms.txt/llms-full.txt の存在とフォーマット妥当性
3. js_dependency: 静的HTML vs Playwrightレンダリング後のテキスト量比較。
   JS依存率=(後-前)/後。30%超警告、60%超重大。Playwright失敗時は
   graceful degradation(「動的検証不可」とレポートに明記)
4. structured_data: JSON-LD抽出、Schema.orgタイプ列挙、必須プロパティ欠落
   (Organization/Article/Product/FAQPage)
5. semantic_html: 見出し階層(h1重複・スキップ)、表の画像化、alt、
   meta description、OGP
6. freshness: lastmod/公開日マークアップ、sitemap.xml

## 出力
- `ai-audit run https://example.com --out report.md`（uv経由なら `uv run ai-audit run ...`）
- 日本語レポート。読者は技術者でない中小企業のマーケ担当者
- 構成:総合スコア(100点)→最も効果が大きい改善3つ→項目別評価→
  優先度付き改善提案(「自分でできる(無料)」/「制作会社に依頼(費用目安)」区分)
- スコアリング根拠はコードコメントに明記(顧客に説明できること)

## やらないこと(v1・変更不可)
- SEO順位チェック、コンテンツ品質評価、GUI/Web化、PDF納品
- LLM APIでのAI回答取得(可視性チェッカーはフェーズ2・別リポジトリ)

## 開発プロトコル(最重要)
開発者は「計画を磨き続けて実装が止まる」癖を自己申告している。よって:
- スコープ拡張の提案は禁止。「あれも測れます」は実装完了後に回す
- 1セッション=動くものが1つ増えて終わる。設計議論でセッションを使い切らない
- 完璧な設計より、6項目中2項目でも動く暫定版を先に出す
- セッション終了時は必ず: pytest通過 → 実URLで動作確認 → git commit

## コミュニケーション
- 結論から・短く。お世辞不要。設計上の欠陥は率直に指摘してよい
- 開発者はPython/TypeScript/Reactが使える。専門用語はそのままでよい

## エージェント委任ルール(MasterClaude用)
- セッション開始 → scope-keeper でゴール確定
- checks/の実装 → check-builder
- 実装完了直後 → test-guardian(自動で続けて呼ぶ。省略禁止)
- レポート文言・テンプレート → report-craftsman
- スコープ外の話題が出た → scope-keeper
- セッション終了前 → scope-keeper のチェックリスト
- MasterClaude自身は統合・コミット・進捗報告のみ。実装の細部に手を出さない
