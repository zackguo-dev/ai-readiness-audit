"""bot_access — AIボットがサイトにアクセスできるかの診断。

2系統で「誤ブロック」を検出する:
1. robots.txt 解析: 主要AIボットUAが Disallow されていないか(サイト所有者の意図的設定)
2. UA別HEADリクエスト: サーバ/CDN/WAFがUAで弾いていないか(401/403。robotsとは別レイヤ)

スコアリング根拠(顧客に説明できること):
- AIに読まれることが集客の前提(GEO)。主要AIボットがアクセスできなければ
  そのAIの検索結果・回答に載る可能性が消える。これは最も影響が大きい項目。
- 8ボットに均等配分(各 12.5点)。robots でブロック or サーバが401/403 で弾く
  ボットの分だけ減点。score = アクセス可能なボット数 / 全体 * 100。
  → 「8つ中いくつのAIが読めるか」をそのまま点数化。透明で説明しやすい。
"""

from __future__ import annotations

import time

import httpx

from ..target import DEFAULT_UA, TargetSite
from .base import CheckResult, Finding, Recommendation, Severity

CHECK_ID = "bot_access"
TITLE = "AIボットのアクセス可否"
WEIGHT = 2.0  # 最重要項目。総合スコアで重く扱う

# v1で検査する主要AIボット(robots.txtに書かれるUAトークン)。
AI_BOTS: list[str] = [
    "GPTBot",  # OpenAI(ChatGPT)
    "ClaudeBot",  # Anthropic(Claude)
    "Claude-Web",  # Anthropic(旧称・併用サイトあり)
    "PerplexityBot",  # Perplexity
    "Google-Extended",  # Google(Gemini学習/参照)
    "CCBot",  # Common Crawl(多くのLLMの基礎データ)
    "Bytespider",  # ByteDance
    "meta-externalagent",  # Meta(Llama関連)
]

# robots取得不可・HEAD失敗時にレポートへ出す補足。
_HEAD_BLOCK_STATUSES = {401, 403}


def _ua_string(bot: str) -> str:
    """HEADプローブ用UA文字列。実ボットのトークンを含める。"""
    return f"{bot} (compatible; ai-audit/0.1 readiness check)"


# --- robots.txt 解析(純粋関数・ネットワーク不要・テスト対象) -----------------


def _parse_groups(robots_txt: str):
    """robots.txtを (user-agentの集合, [(allow, path), ...]) のグループ列に分解。"""
    groups = []
    current_agents: list[str] = []
    current_rules: list[tuple[bool, str]] = []
    started_rules = False
    for raw in robots_txt.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            # 直前にルールが始まっていたら、そこでグループを閉じる
            if started_rules and current_agents:
                groups.append((set(current_agents), current_rules))
                current_agents, current_rules, started_rules = [], [], False
            current_agents.append(value.lower())
        elif field in ("allow", "disallow"):
            started_rules = True
            current_rules.append((field == "allow", value))
    if current_agents:
        groups.append((set(current_agents), current_rules))
    return groups


def _select_group(groups, bot: str):
    """ボットに適用されるルール群を選ぶ。完全一致 > '*' フォールバック。"""
    bot_l = bot.lower()
    star_rules = None
    for agents, rules in groups:
        if bot_l in agents:
            return rules
        if "*" in agents:
            star_rules = rules
    return star_rules if star_rules is not None else []


def _is_blocked(rules, path: str = "/") -> bool:
    """指定パスが Disallow されているか(最長プレフィックス一致。Allow優先)。

    v1の簡略実装: ワイルドカードは最初の '*' まででプレフィックス化して扱う。
    """
    best = None  # (マッチ長, allow_bool)
    for allow, p in rules:
        if p == "":
            # "Disallow:"(値が空)はそのグループに対する全許可。マッチ対象にしない
            continue
        prefix = p.split("*", 1)[0]
        if path.startswith(prefix):
            if best is None or len(prefix) > best[0] or (
                len(prefix) == best[0] and allow
            ):
                best = (len(prefix), allow)
    if best is None:
        return False
    return not best[1]  # Disallowにマッチ = ブロック


def analyze_robots(
    robots_txt: str | None, bots: list[str] | None = None, path: str = "/"
) -> dict[str, bool]:
    """各ボットが robots.txt で path をブロックされているか。

    robots.txt が無い/取得不可なら「ブロックなし」として扱う(誤検出を避ける)。
    """
    bots = bots or AI_BOTS
    if not robots_txt:
        return {b: False for b in bots}
    groups = _parse_groups(robots_txt)
    return {b: _is_blocked(_select_group(groups, b), path) for b in bots}


# --- UA別HEADプローブ(ネットワーク。テストでは monkeypatch する) ----------------


def probe_bot_blocks(
    url: str, bots: list[str] | None = None, *, delay: float = 1.0, timeout: float = 10.0
) -> dict[str, int | None]:
    """各ボットUAでHEADを投げ、ステータスコードを返す(取得不能はNone)。

    リクエスト間は delay(>=1.0)秒あける(対象サイトに負荷をかけない)。
    """
    bots = bots or AI_BOTS
    results: dict[str, int | None] = {}
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        for i, bot in enumerate(bots):
            if i:
                time.sleep(delay)
            try:
                r = client.head(url, headers={"User-Agent": _ua_string(bot)})
                results[bot] = r.status_code
            except httpx.HTTPError:
                results[bot] = None
    return results


# --- 共通IF ------------------------------------------------------------------


def run(target: TargetSite) -> CheckResult:
    robots_blocked = analyze_robots(target.robots_txt, AI_BOTS, target.path)

    # サーバ側のUAブロックをHEADで確認。失敗時は graceful degradation。
    try:
        head_status = probe_bot_blocks(target.final_url or target.url)
    except Exception:  # noqa: BLE001 - 通信系は握りつぶしてrobots結果だけで続行
        head_status = {}

    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    accessible = 0

    for bot in AI_BOTS:
        by_robots = robots_blocked.get(bot, False)
        status = head_status.get(bot)
        by_server = status in _HEAD_BLOCK_STATUSES
        if not by_robots and not by_server:
            accessible += 1
            continue
        if by_robots:
            findings.append(
                Finding(
                    Severity.CRITICAL,
                    f"{bot} が robots.txt でブロックされています",
                    "この設定だと該当AIはページを読み込めません。",
                )
            )
            recommendations.append(
                Recommendation(
                    f"robots.txt の {bot} 向け Disallow を見直し、読ませたいページを許可する",
                    effort="self",
                    priority=90,
                )
            )
        if by_server:
            findings.append(
                Finding(
                    Severity.CRITICAL,
                    f"{bot} がサーバ側で拒否されています(HTTP {status})",
                    "robots.txt以前に、サーバ/CDN/WAFがこのUAを弾いています。",
                )
            )
            recommendations.append(
                Recommendation(
                    f"サーバ・CDN・WAFのアクセス制限で {bot} のUAが弾かれていないか確認する",
                    effort="vendor",
                    cost_hint="設定確認の範囲なら数千〜数万円程度",
                    priority=85,
                )
            )

    score = round(accessible / len(AI_BOTS) * 100)

    if accessible == len(AI_BOTS):
        findings.insert(
            0,
            Finding(
                Severity.INFO,
                f"主要AIボット {len(AI_BOTS)} 種すべてがアクセス可能です",
            ),
        )

    if not target.robots_txt:
        findings.append(
            Finding(
                Severity.INFO,
                "robots.txt が見つかりませんでした",
                "robots.txt(自動プログラム向けの設定ファイル)が無い場合、"
                "既定では全ボットがアクセス可能と判断されます。",
            )
        )

    return CheckResult(
        check_id=CHECK_ID,
        title=TITLE,
        score=score,
        findings=findings,
        recommendations=recommendations,
    )
