"""Tavily APIを使ったWeb検索(Phase 3)と、Evidence用のchunk抽出(Phase 5D)。

コスト・複雑さを抑えるための方針:
- search_depth="basic"を明示し、auto_parameters=Falseにする。
  auto_parametersを有効にすると、Tavilyが意図せずsearch_depthを
  "advanced"(2クレジット消費)へ昇格させることがあるため、
  明示的に"basic"(1クレジット)へ固定している。
- Tavilyへは候補プールとして`_FETCH_RESULTS_PER_QUERY`件をリクエストするが、
  実際に採用・保存するのは並べ替え後の上位`MAX_RESULTS_PER_QUERY`件のみ
  (Phase 5D-b。詳細は下記)。Tavily API呼び出し自体は1クエリ=1回のまま
  変更しない(max_resultsを増やしても呼び出し回数・crediting単位には
  影響しないという前提。README参照)。
- include_raw_content="text"で、ページの実際の本文(プレーンテキスト)を
  取得する。これはLLMに自由に引用文を生成させず、Evidence Viewerで
  表示する根拠本文を「実際にWeb上にあったテキスト」にするため。

Phase 5D: Retrieval Quality
- クエリは技術名だけでなく、criteria(比較軸)・goal(利用目的)も反映する
  (build_search_queries())。criteria件数に比例させず、1 researchあたり
  常に3クエリ(item_a向け・item_b向け・比較記事向け)に固定する
  (5criteria×2technologies=10回のような設計にはしない)。
- Evidenceに保存する根拠本文を「Source全文」から「claimを実際に支える
  verbatim excerpt」に変える準備として、filter_noise() / chunk_content()
  という2つの独立したpure functionを追加する。どちらも本文の要約・
  言い換え・生成は一切行わず、削除または分割だけを行う。
- get_source_chunks()が最終的に返す各chunkは、単にfilter_noise()の出力
  (ノイズ除去後のテキスト)の部分文字列であることに留まらず、**元の
  Source.content(切り詰め前と同じ文字列)の連続した部分文字列**である
  ことを保証する。ノイズ行(削除される行)を挟んで前後の短い断片を
  1つのchunkにマージすることはしない(マージすると、削除された行を
  またいだ、元のcontent上には存在しない結合になってしまうため)。

Phase 5D-b: Retrieval Ranking(公式/一次情報の優先度向上)
- 実API smoke test(Flask vs FastAPI)で、クエリに「公式ドキュメント」と
  入れているにもかかわらず、取得したSourceに公式ドキュメントが1件も
  含まれないことが確認された。原因は、Tavilyへのリクエスト自体が
  `max_results=MAX_RESULTS_PER_QUERY`(=採用件数と同じ3件)だったため、
  rankingで並べ替えても「候補プールの外」にある公式ドキュメントを
  拾い上げる余地が最初から無かったこと。
- 対策として、Tavilyへリクエストする候補件数(`_FETCH_RESULTS_PER_QUERY`)
  と、実際に採用する件数(`MAX_RESULTS_PER_QUERY`)を分離した。Tavily
  API呼び出し回数(3回/research)・採用件数(=保存Source数・Gemini
  プロンプトサイズ)はいずれも変更しない。
- `_official_source_bonus()`により、(a)技術名(item_a/item_b)がURLの
  ホスト名に含まれるか、(b)技術非依存の汎用的なドキュメントホスティング
  パターン(readthedocs.io等)に一致するか、の2種類のみを加点対象にする。
  技術ごとの公式ドメインを事前登録するテーブルは作らない。
- このボーナスは**Tavily自身のrelevance scoreを置き換えるものではない**
  (上限0.15程度の弱いsignalとして、relevanceが拮抗している候補同士の
  中でのみ公式/一次情報を優先する。relevanceの差が大きい場合、公式で
  あっても高relevanceの第三者ソースを追い越さない)。第三者の比較記事・
  解説記事のハード除外は行わない。

Phase 5D-c: Query Language Strategy(候補プールに公式ドキュメントを
入りやすくする)
- Phase 5D-b実装後の実API smoke testで、`fastapi.tiangolo.com`はrerankingで
  正しく昇格した一方、`flask.palletsprojects.com`は候補プール(8件)に
  1件も入らなかった。切り分け実験の結果、原因はrerankingではなく、
  **日本語のcriteria/goalを含む長いクエリが、英語中心の公式ドキュメントの
  candidate retrieval自体を阻害していること**だと判明した(同じ内容を
  英語化したクエリ、または`"Flask official documentation"`のような短い
  英語クエリでは、いずれも`flask.palletsprojects.com`が1位で返ってきた)。
- 対策として、3クエリの役割を分担する: query[0]/query[1](item_a/b向け)
  は**英語中心**にし、official/primary retrievalを狙う(技術名+固定
  criteriaの英語search term+`"official documentation"`。日本語のgoal・
  custom criteriaは含めない)。query[2](比較記事向け)は**従来どおり
  日本語**のままにし、third-party比較記事のretrieval役を維持する。
  「Technology × Use Case × Comparison Pointを検索意図に反映する」という
  Phase 5Dの原則は、個々のクエリ単位ではなく3クエリ全体として満たす。
- 固定criteria(`app/schemas/criteria.py::Criterion`)にのみ、英語
  search termの対訳表(`CRITERION_ENGLISH_SEARCH_TERMS`)を用意する。
  各criterionにつき1語/1フレーズの直訳のみとし、関連語への拡張は
  行わない(query languageの効果とcriteria keyword拡張の効果を混同
  しないため)。custom criteria(自由入力)は正確な英訳を機械的に保証
  できないため、query[0]/query[1]には含めない(query[2]には引き続き
  日本語labelとして含める)。
- Tavily呼び出し回数(3回/research)・Gemini呼び出し回数(1回/research)
  はいずれも変更しない。query翻訳のための追加LLM呼び出しも行わない。
  Phase 5D-bのreranking(`_FETCH_RESULTS_PER_QUERY`/`MAX_RESULTS_PER_QUERY`/
  `_official_source_bonus()`/`_ranking_key()`)は変更しない
  (retrieval層の改善とranking層の改善は独立に積み重なる)。

Phase 5D-d: Evidence Chunk Boundary(文途中で終わるEvidenceの修正)
- 実API full pipeline smoke testで、保存されたEvidenceが文の途中(例:
  `"...with the ability to scale up to"`)や表の行の途中(例:
  `"...急成長中、主要ライブ"`)で終わっていることが確認された。いずれも
  `evidence_text`自体は`Source.content`のverbatim substringだが、
  「自然なsentence/newline boundaryでchunk化する」設計意図に反していた。
- 原因1: 旧`_BOUNDARY_CHAR_PATTERN`が単独の改行(`\n`)を文末記号と同列の
  区切りとして扱っていたため、ページ内で長い文が単に行折り返しされている
  だけの箇所(文末記号を伴わない`\n`)で文が分断されていた。対策として
  `_CHUNK_BOUNDARY_PATTERN`は、文末記号の直後・Markdown表の行末(`|`)の
  直後の改行・2つ以上連続する改行(段落区切り)のみを区切りとして扱い、
  単なる行折り返しの単独改行では区切らない。
- 原因2: `_PROMPT_CONTENT_MAX_LENGTH`(800文字)による機械的な末尾切り
  詰めが、文や表の行の途中で`Source.content`を寸断することがあり、
  `chunk_content()`はその切れ端を無条件に「完結したchunk」として返して
  いた。対策として`get_source_chunks()`が、実際にtruncationが発生した
  場合のみ、末尾chunkが文末記号/表の行末のいずれでも終わっていなければ
  その1件を除外する(`_ends_with_chunk_terminal_marker()`)。truncationが
  発生していない場合(contentが元々`_PROMPT_CONTENT_MAX_LENGTH`以内)は、
  見出し・箇条書き・コード等で末尾が文末記号を伴わなくても、ページ全体を
  見た上での正常な終端として除外しない(「Evidence 0件を許容する一方、
  不完全でも何かあった方がよいとは考えない」という方針による)。
- `chunk_content()`自体の契約(soft target、hard cutしない、1件しか
  chunkが無ければ破棄しない)は変更しない。`_PROMPT_CONTENT_MAX_LENGTH`
  の値・Tavily/Gemini呼び出し回数・DB schemaもいずれも変更しない。
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from tavily import TavilyClient

from app.schemas.criteria import english_search_term_for, label_for

# ranking後に実際に採用する件数(=保存するSource数・Geminiプロンプトに
# 入るchunk数の上限に直結する)。Phase 5D-b以前からの値を維持する。
MAX_RESULTS_PER_QUERY = 3

# Tavilyへ候補プールとしてリクエストする件数(Phase 5D-b)。採用件数
# (MAX_RESULTS_PER_QUERY)より広めに取得することで、rankingが「候補にすら
# 入っていない公式ドキュメント」を拾えない、という問題を防ぐ。Tavily API
# 呼び出し回数(1クエリ=1回)には影響しない。
_FETCH_RESULTS_PER_QUERY = 8

# DBに保存する本文の長さの上限(ページ全体を無制限に保存しないため)。
_CONTENT_MAX_LENGTH = 3000

# プロンプトに含める(≒chunkに分割してLLMに提示する)本文の長さの上限。
# LLMが実際に「見た」範囲を超えてEvidenceを作らないよう、
# get_source_chunks()はこの上限を超えた部分を最初から対象にしない
# (llm_client.py側でのプロンプト構築・research_runner.py側でのcitation
# 解決の両方が、必ずこの同じ範囲に対してchunkを計算するため、chunk_indexの
# ずれは起きない)。
_PROMPT_CONTENT_MAX_LENGTH = 800

# 検索クエリに埋め込むcriteria/goalの文字数上限(クエリが過度に長くならない
# ようにするための決定論的なcap。LLMによるquery生成は行わない)。
# query[2](比較記事向け、日本語)で使う。
_MAX_QUERY_CRITERIA_CHARS = 60
_MAX_QUERY_GOAL_CHARS = 80

# query[0]/query[1](item_a/b向け、英語中心)で使うcriteria英語termの
# 文字数上限(Phase 5D-c)。英語termは日本語ラベルより1語あたりの文字数が
# 長くなりやすいため、JP側のcapとは別の値にしている。
_MAX_QUERY_CRITERIA_CHARS_EN = 80

# noise filteringで「短い行」とみなす閾値。これより長い行はdenylistに
# 一致しても(本文の可能性が高いため)保守的に残す。
_SHORT_LINE_MAX_CHARS = 24

# 明らかにnavigation/UI起因と判断できる短い行のdenylist(小文字比較)。
# 「短い」かつ「一致」の両方を満たす行だけを削除対象にすることで、
# 通常の本文(見出し等)を誤って消すリスクを抑える(保守的な設計)。
_NAVIGATION_LINE_DENYLIST = {
    "sitemap",
    "open in app",
    "sign in",
    "sign up",
    "log in",
    "login",
    "write",
    "search",
    "menu",
    "home",
    "about",
    "contact",
    "subscribe",
    "follow",
    "share",
    "skip to content",
    "cookie",
    "cookies",
    "privacy policy",
    "terms of service",
    "all rights reserved",
}

# data URI(data:image/..., data:application/...)や、URLエンコードされた
# SVGパスデータ等、機械的なノイズと判断できるパターン
# (Phase 5C手動E2Eで実際に観測した破損データを含む)。
_DATA_URI_PATTERN = re.compile(r"data:(image|application)/", re.IGNORECASE)
_SVG_PATTERN = re.compile(r"</?svg|%3Csvg|%2Fsvg", re.IGNORECASE)
_URLENCODED_PATH_PATTERN = re.compile(r"%22%20?d%3D%22|%[0-9A-Fa-f]{2}%[0-9A-Fa-f]{2}%[0-9A-Fa-f]{2}")

# chunkがこれより短い場合は、隣接する断片へマージする(見出しの断片等が
# 単独のchunkにならないようにするため)。上限側は設けない: 自然な区切り
# (文・改行)を優先し、長い文を意味の途中で機械的に切ることはしない
# (soft target。目安はおよそ20〜300文字程度)。
_CHUNK_SOFT_MIN_CHARS = 20

# chunkの区切り候補とみなす位置(直後で区切る)。Phase 5D-d: 単独の改行
# (単なる行折り返しの可能性が高い)は区切りにしない。以下の3パターンの
# いずれかのみを区切りとして扱う:
#   1. 文の終端記号(日本語の全角句点・感嘆符・疑問符、英語のピリオド等)
#      の直後。
#   2. Markdown表の行末(`|`)の直後の改行(表の1行を1単位として扱う)。
#   3. 2つ以上連続する改行(空行=段落区切り)の直後。
# (1)〜(3)のいずれにも該当しない単独の`\n`(例: ページ内で長い文が単に
# 行折り返しされているだけのもの)は区切り候補にしない。これにより、
# 文末記号の無い改行でEvidenceが文の途中で分断されることを防ぐ
# (Phase 5D full pipeline smoke testで観測した実際のバグの修正)。
_CHUNK_BOUNDARY_PATTERN = re.compile(r"[。！？!?.]|\|\n|\n{2,}")

# chunkの末尾が「完結している」とみなせる文字の集合(Phase 5D-d)。
# _CHUNK_BOUNDARY_PATTERNの文末記号・表の行末(|)と同じ基準を共有する。
# get_source_chunks()が、truncationで寸断された可能性のある末尾chunkを
# 安全側に判定する際に使う。
_CHUNK_TERMINAL_MARKERS = "。！？!?.|"


def _ends_with_chunk_terminal_marker(chunk: str) -> bool:
    """chunkの末尾(空白除去後の最終文字)が、文末記号または表の行末(|)で
    終わっているかを判定する(Phase 5D-d、get_source_chunks()専用)。"""
    return bool(chunk) and chunk[-1] in _CHUNK_TERMINAL_MARKERS


@dataclass
class SearchResultItem:
    title: str
    url: str
    content: str


def _cap_text(text: str, max_chars: int) -> str:
    """検索クエリに埋め込む前に、文字数を上限までtrimする(単純な切り詰め)。"""
    trimmed = text.strip()
    return trimmed[:max_chars]


def build_search_queries(
    item_a: str,
    item_b: str,
    criteria: list[str],
    goal: str,
) -> list[str]:
    """Technology × Use Case × Comparison Pointを反映した3クエリを組み立てる。

    LLMによるquery生成は行わない(文字列結合・切り詰めだけの決定論的な
    処理)。criteria件数に関わらず常に3クエリを返す(O(1)。5criteria×
    2technologies=10クエリのような設計にはしない)。

    Phase 5D-cから、3クエリは役割分担する(モジュールdocstring
    「Phase 5D-c」参照):
    - query[0]: item_a向け。英語中心でofficial/primary retrievalを狙う
      (技術名+固定criteriaの英語search term+"official documentation"。
      日本語のgoal・custom criteriaの原文は含めない)。
    - query[1]: item_b向け(同上)。
    - query[2]: item_a/bを直接比較した記事向け。Phase 5D/5D-bから変更なし
      (日本語のcriteria label・goalを含む、third-party比較記事向け)。

    `criteria`は生のcriterion文字列のリスト(固定候補のkeyまたは自由入力)
    を受け取る(表示用に解決済みのJP labelではない)。
    """
    english_terms = [term for term in (english_search_term_for(c) for c in criteria) if term]
    english_criteria_text = _cap_text(" ".join(english_terms), _MAX_QUERY_CRITERIA_CHARS_EN)

    query_a = " ".join(
        part for part in (item_a, english_criteria_text, "official documentation") if part
    )
    query_b = " ".join(
        part for part in (item_b, english_criteria_text, "official documentation") if part
    )

    jp_criteria_text = _cap_text(" ".join(label_for(c) for c in criteria), _MAX_QUERY_CRITERIA_CHARS)
    goal_text = _cap_text(goal, _MAX_QUERY_GOAL_CHARS)
    jp_context = " ".join(part for part in (jp_criteria_text, goal_text) if part)
    query_c = " ".join(part for part in (f"{item_a} vs {item_b}", jp_context) if part)

    return [query_a, query_b, query_c]


# 個人ブログ・記事集約プラットフォームのように、navigationノイズが混入
# しやすい一方で技術によっては唯一の情報源になりうるドメイン。
# 除外はせず、Tavilyのscoreが同程度の場合の並び順だけを後ろにする
# (hard excludeにしない=保守的な優先度付けに留める)。
_SOFT_DEPRIORITIZED_DOMAINS = (
    "note.com",
    "qiita.com",
    "zenn.dev",
    "hatenablog.com",
    "medium.com",
)

# 公式/一次情報らしさへのボーナス(Phase 5D-b)。技術ごとのドメインを
# 事前登録するのではなく、(a)技術名がURLのホスト名に含まれるか、
# (b)技術に依存しない汎用的なドキュメントホスティングのパターンに一致するか
# の2種類のみを加点対象にする。値はいずれも小さく抑え、Tavily自身の
# relevance score(概ね0〜1)を置き換えない「弱いsignal」として扱う
# (=relevanceが拮抗している候補同士の中でのみ効く。relevanceの差が
# 大きい場合、公式であっても高relevanceの第三者ソースを追い越さない)。
_OFFICIAL_NAME_MATCH_BONUS = 0.12
_DOC_HOSTING_PATTERN_BONUS = 0.04
_OFFICIAL_BONUS_CAP = 0.15

# 技術名の正規化後の長さがこれ未満なら、(a)のホスト名一致判定は行わない
# (短い技術名ほど無関係なドメインへの誤検出リスクが高いため)。
_MIN_TECH_NAME_LENGTH_FOR_MATCH = 3

_NON_ALNUM_PATTERN = re.compile(r"[^0-9a-z]+")

# 技術に依存しない、汎用的な「ドキュメントホスティング」の命名規約。
# 特定の技術のドメインではなく、多数の技術で共通して使われる配信基盤・
# 命名パターンのみを対象にする(_SOFT_DEPRIORITIZED_DOMAINSと対になる、
# 技術非依存で保守コストが技術数に比例しないリスト)。
_DOC_HOSTING_HOST_SUFFIXES = ("readthedocs.io", "readthedocs.org", "github.io")
_DOC_HOSTING_HOST_PREFIXES = ("docs.", "documentation.")
_DOC_HOSTING_PATH_MARKERS = ("/docs/", "/documentation/")


def _normalize_tech_name(name: str) -> str:
    """技術名を比較用に正規化する(小文字化、英数字以外を除去)。

    例: "FastAPI"→"fastapi"、"Next.js"→"nextjs"、"PostgreSQL"→"postgresql"。
    """
    return _NON_ALNUM_PATTERN.sub("", name.lower())


def _has_tech_name_in_hostname(hostname: str, tech_name: str) -> bool:
    """正規化した技術名が、ホスト名のいずれかのラベル(ドット区切り区間)に
    部分文字列として含まれるかを判定する。

    ホスト名のみを対象にし、パスやクエリ文字列は見ない(第三者記事の
    パスに技術名が含まれるだけで「公式」扱いしないため)。判定は
    item_a/item_bという入力から都度計算するため、技術ごとのドメインを
    事前登録する必要はない。
    """
    normalized = _normalize_tech_name(tech_name)
    if len(normalized) < _MIN_TECH_NAME_LENGTH_FOR_MATCH:
        return False
    return any(normalized in label for label in hostname.split(".") if label)


def _is_doc_hosting_url(hostname: str, path: str) -> bool:
    """技術に依存しない、汎用的なドキュメントホスティングのパターンに
    一致するかを判定する(readthedocs.io等のホスティング基盤、または
    `docs.`のようなホスト名の命名規約、`/docs/`のようなパスの慣習)。"""
    if hostname.endswith(_DOC_HOSTING_HOST_SUFFIXES):
        return True
    if hostname.startswith(_DOC_HOSTING_HOST_PREFIXES):
        return True
    return any(marker in path for marker in _DOC_HOSTING_PATH_MARKERS)


def _official_source_bonus(url: str, item_a: str, item_b: str) -> float:
    """公式/一次情報らしさを示す弱いsignal(0.0〜_OFFICIAL_BONUS_CAP)を返す。

    ハードなフィルタではなく、_ranking_key()でTavily自身のrelevance score
    に加算するための小さなボーナスとして使う(モジュールdocstring
    「Phase 5D-b」参照)。
    """
    lowered = url.lower()
    parsed = urlparse(lowered if "://" in lowered else f"//{lowered}")
    hostname = parsed.hostname or ""
    path = parsed.path or ""
    if not hostname:
        return 0.0

    bonus = 0.0
    if _has_tech_name_in_hostname(hostname, item_a) or _has_tech_name_in_hostname(hostname, item_b):
        bonus += _OFFICIAL_NAME_MATCH_BONUS
    if _is_doc_hosting_url(hostname, path):
        bonus += _DOC_HOSTING_PATTERN_BONUS

    return min(bonus, _OFFICIAL_BONUS_CAP)


def _ranking_key(result: dict, item_a: str, item_b: str) -> tuple[float]:
    """Tavilyの`score`を主キーに、(a)既知の集約系ドメインをわずかに
    後順位へ回すpenaltyと、(b)公式/一次情報らしさへの小さなbonusを加味した
    並び替えキーを返す(いずれも除外ではなく弱い優先度付けに留める)。"""
    score = result.get("score") or 0.0
    url = (result.get("url") or "").lower()
    penalty = 0.01 if any(domain in url for domain in _SOFT_DEPRIORITIZED_DOMAINS) else 0.0
    bonus = _official_source_bonus(url, item_a, item_b)
    return (-(score + bonus - penalty),)


def search_technology(query: str, item_a: str, item_b: str) -> list[SearchResultItem]:
    """指定したクエリ文字列でTavily検索し、公式/一次情報を弱く優先しつつ
    上位数件の情報源を返す。

    Phase 5Dから、呼び出し側(research_runner.py)が`build_search_queries()`
    で組み立てた完成済みのクエリ文字列を渡す(この関数自体はクエリを
    組み立てない)。TAVILY_API_KEY環境変数からキーを自動取得する
    (TavilyClient()のデフォルト挙動)。

    Phase 5D-bから、Tavilyへは候補プールとして`_FETCH_RESULTS_PER_QUERY`件
    をリクエストし(呼び出し回数はこれまでどおり1クエリ=1回)、
    `_ranking_key()`で並べ替えた上位`MAX_RESULTS_PER_QUERY`件だけを採用する。
    item_a/item_bは、_official_source_bonus()での公式/一次情報らしさの
    判定にのみ使う。
    """
    client = TavilyClient()

    response = client.search(
        query=query,
        search_depth="basic",
        auto_parameters=False,
        max_results=_FETCH_RESULTS_PER_QUERY,
        include_raw_content="text",
    )

    results = sorted(
        response.get("results", []),
        key=lambda result: _ranking_key(result, item_a, item_b),
    )

    items: list[SearchResultItem] = []
    for result in results:
        if len(items) >= MAX_RESULTS_PER_QUERY:
            break
        content = (result.get("raw_content") or result.get("content") or "").strip()
        if not content:
            continue
        items.append(
            SearchResultItem(
                title=result.get("title") or result.get("url", ""),
                url=result.get("url", ""),
                content=content[:_CONTENT_MAX_LENGTH],
            )
        )
    return items


def normalize_url(url: str) -> str:
    """重複排除用にURLを軽く正規化する(末尾スラッシュ・フラグメントの違いを吸収)。

    完全な正規化(クエリパラメータの並び替え等)は行わない、簡易的なもの。
    """
    trimmed = url.strip()
    trimmed = trimmed.split("#", 1)[0]  # フラグメントを除去
    if trimmed.endswith("/"):
        trimmed = trimmed[:-1]
    return trimmed.lower()


def _kept_line_spans(raw_text: str) -> list[tuple[int, int]]:
    """行単位のノイズ判定を行い、削除しない行の(start, end)をraw_text上の
    文字位置で返す(各spanは改行文字を含まない、その行自体の範囲)。

    filter_noise()とget_source_chunks()の両方がこの関数を共有する。
    位置情報(span)をraw_text座標のまま保持することで、chunk_contentへ
    渡す前に「削除された行をまたいでいないか」を判定できるようにする
    (get_source_chunks側で使用。詳細はそちらのdocstring参照)。
    """
    kept: list[tuple[int, int]] = []
    recent_short_lines: list[str] = []
    pos = 0

    for line in raw_text.split("\n"):
        line_start = pos
        line_end = pos + len(line)
        pos = line_end + 1  # 次の行の開始位置("\n"の1文字分を進める)

        stripped = line.strip()
        lowered = stripped.lower()

        if _DATA_URI_PATTERN.search(stripped) or _SVG_PATTERN.search(stripped):
            continue
        if _URLENCODED_PATH_PATTERN.search(stripped):
            continue

        is_short = 0 < len(stripped) <= _SHORT_LINE_MAX_CHARS
        if is_short and lowered in _NAVIGATION_LINE_DENYLIST:
            continue

        if is_short and stripped:
            if stripped in recent_short_lines:
                continue  # 直近数行以内に出た同一の短い行(navigation反復)は削除する
            recent_short_lines.append(stripped)
            recent_short_lines = recent_short_lines[-5:]

        kept.append((line_start, line_end))

    return kept


def filter_noise(raw_text: str) -> str:
    """行単位で、明らかにノイズと判断できる行だけを削除する。

    保守的な設計: 要約・言い換え・本文の書き換えは一切行わない。削除する
    行以外は元のraw_textと文字単位で完全に同じ(verbatim)であることを
    常に維持する(この関数の出力はraw_textの行の部分集合の結合)。

    削除対象(いずれも「短い行」かつdenylist一致、または明確な機械的
    ノイズパターンに一致する場合のみ。疑わしい場合は残す):
    - navigation断片("Sitemap" "Sign in" "Write" "Search"等)
    - data URI / SVGのURLエンコード片(Phase 5C手動E2Eで観測した破損データ)
    - 近接して繰り返される短い行(navigationメニューの重複等)

    注意: この関数が返す文字列は表示・単体テスト用の便宜的な結合であり、
    削除した行をまたぐ場合は"\\n"で単純に再結合するため、raw_text全体の
    単一の連続した部分文字列ではなくなりうる。Evidence用のchunk抽出
    (get_source_chunks())はこの関数を経由せず、_kept_line_spans()の
    span情報をraw_text上でそのまま使うため、その制約の影響を受けない。
    """
    spans = _kept_line_spans(raw_text)
    return "\n".join(raw_text[start:end] for start, end in spans)


def chunk_content(filtered_text: str) -> list[str]:
    """文・改行など自然なboundaryで、Evidence用のchunkに分割する。

    20〜300文字程度をsoft targetとするが、hard cutではない: 文の途中や
    意味の途中で機械的に切ることはしない。短すぎる断片(見出しの断片等)は
    隣接する断片へマージし、長い文はそのまま1つのchunkとして残す
    (単語や句点の位置を無視した強制分割はしない)。

    Phase 5D-d: 区切り候補は`_CHUNK_BOUNDARY_PATTERN`(文末記号/表の行末+
    改行/連続した改行)のみとし、単なる行折り返しの単独改行では区切らない
    (そのdocstring参照)。

    実装上の注意(verbatim性の担保): 分割・マージは常にfiltered_text上の
    文字位置(start, end)の操作として行い、文字列の切り貼りによる結合
    (別々の断片を空白等でつなぎ直すこと)はしない。これにより、マージで
    短い断片同士をまとめた場合でも、出力される各chunkはfiltered_textの
    厳密な部分文字列(=1文字も足さず・減らさず・変えない)であり続ける。
    """
    if not filtered_text.strip():
        return []

    # 文の終端記号・表の行末・段落区切りの直後を、chunk候補の区切り位置
    # (boundary)とする(単なる行折り返しの単独改行は区切りにしない)。
    boundaries = [m.end() for m in _CHUNK_BOUNDARY_PATTERN.finditer(filtered_text)]
    if not boundaries or boundaries[-1] != len(filtered_text):
        boundaries.append(len(filtered_text))

    # 空白のみの候補区間(例: 連続した改行の間)は捨てる。
    candidate_spans: list[tuple[int, int]] = []
    start = 0
    for end in boundaries:
        if filtered_text[start:end].strip():
            candidate_spans.append((start, end))
        start = end

    # 短すぎる断片は、区切り位置を無かったことにして次の候補区間へ
    # 吸収させる(=区間の終端を伸ばすだけで、文字の追加・削除はしない)。
    merged_spans: list[tuple[int, int]] = []
    pending_start: int | None = None
    for span_start, span_end in candidate_spans:
        if pending_start is None:
            pending_start = span_start
        if len(filtered_text[pending_start:span_end].strip()) < _CHUNK_SOFT_MIN_CHARS:
            continue
        merged_spans.append((pending_start, span_end))
        pending_start = None

    if pending_start is not None:
        # 末尾に短い断片が残った場合は、直前のchunkの区間を伸ばして吸収する
        # (無ければ、短いままでも単独のchunkとして残す)。
        if merged_spans:
            last_start, _ = merged_spans[-1]
            merged_spans[-1] = (last_start, len(filtered_text))
        else:
            merged_spans.append((pending_start, len(filtered_text)))

    return [
        filtered_text[s:e].strip()
        for s, e in merged_spans
        if filtered_text[s:e].strip()
    ]


def _merge_contiguous_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """隣接するkept-line-spanのうち、元のテキスト上で本当に連続している
    (間に削除された行を挟まない = ちょうど改行1文字分の間隔しかない)
    ものだけを1つの区間にまとめる。

    ノイズ行を挟んで前後の行を1つの区間にまとめることはしない。これにより
    後段のchunk_content()が短い断片同士をマージする際も、削除された行を
    またいだ結合が起きなくなり、生成される各chunkが常に元テキストの
    「連続した」部分文字列であることを保証できる。
    """
    if not spans:
        return []
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start - last_end == 1:  # 間は元テキストの改行1文字だけ(=間に削除された行が無い)
            merged[-1] = (last_start, end)
        else:
            merged.append((start, end))
    return merged


def get_source_chunks(content: str) -> list[str]:
    """Source.contentから、Evidence citation用のchunk一覧を計算する。

    verbatim性の保証範囲: 各chunkは、単に「ノイズ除去後のテキスト」の
    部分文字列であることに留まらず、**元のSource.content(切り詰め前と
    同じ文字列の範囲)の連続した部分文字列**であることを保証する。

    そのため、"\\n"で結合した単一の文字列に対してchunk_content()を適用する
    のではなく、以下の手順を取る:
    1. `content[:_PROMPT_CONTENT_MAX_LENGTH]`で切り詰める(truncated)。
    2. `_kept_line_spans()`でノイズ行を除いた行のspan(truncated上の位置)
       を求める。
    3. `_merge_contiguous_spans()`で、削除された行を挟まずtruncated上で
       本当に連続しているspanだけをまとめ、「連続run」の区間を作る。
    4. 各runについて、`truncated[start:end]`(=truncatedの連続した部分
       文字列)を`chunk_content()`に渡してchunkへ分割する。runをまたいだ
       短い断片のマージは行わない(=削除行をまたいだ結合を防ぐ)。

    `truncated[start:end]`は必ず`content`の連続した部分文字列であり、
    `chunk_content()`自体もindex-spanベースで動作し文字の挿入・削除を
    行わないため、最終的に得られる各chunkは常に`chunk in content`を
    満たす。

    Phase 5D-d: `content`が`_PROMPT_CONTENT_MAX_LENGTH`を超えており
    実際にtruncationが発生した場合のみ、末尾のchunkが文末記号・表の行末
    (`_ends_with_chunk_terminal_marker()`参照)のいずれでも終わっていなければ、
    「truncationによって途中で寸断された可能性がある未完了chunk」とみなし、
    安全側に倒してその1件を結果から除外する(結果が0件になることもある。
    Evidence 0件を許容する既存方針と整合する)。truncationが発生していない
    場合(contentが元々`_PROMPT_CONTENT_MAX_LENGTH`以内)は、見出し・
    箇条書き・コード等で末尾が文末記号を伴わなくても、ページ全体を見た
    上での正常な終端として除外しない。この判断は`chunk_content()`自体
    (純粋関数、無変更)ではなく、`content`の全長を知るこの関数でのみ行う。

    llm_client.py(プロンプト構築)とresearch_runner.py(citation解決)の
    両方が、この関数を同じcontentに対して呼べば必ず同じchunk一覧が得られる
    (決定論的、状態を持たない)ため、chunk_indexのずれは起きない。DBには
    保存しない(都度計算)。
    """
    truncated = content[:_PROMPT_CONTENT_MAX_LENGTH]
    was_truncated = len(content) > len(truncated)

    kept_spans = _kept_line_spans(truncated)
    runs = _merge_contiguous_spans(kept_spans)

    chunks: list[str] = []
    for start, end in runs:
        chunks.extend(chunk_content(truncated[start:end]))

    if was_truncated and chunks and not _ends_with_chunk_terminal_marker(chunks[-1]):
        chunks = chunks[:-1]

    return chunks
