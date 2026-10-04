"""Phase 5D: Retrieval Quality / Phase 5D-b: Retrieval Rankingで追加した
pure functionの単体テスト。

filter_noise() / chunk_content() は、要約・言い換え・生成を一切行わない
(削除または区切りの位置の操作だけ)。search_technology()のテストは
TavilyClientをfakeに差し替えて行い、実際のTavily API呼び出しは行わない。
"""

import app.services.search_client as search_client_module
from app.schemas.criteria import Criterion, english_search_term_for
from app.services.search_client import (
    _FETCH_RESULTS_PER_QUERY,
    _MAX_QUERY_CRITERIA_CHARS,
    _MAX_QUERY_CRITERIA_CHARS_EN,
    _MAX_QUERY_GOAL_CHARS,
    _OFFICIAL_BONUS_CAP,
    _PROMPT_CONTENT_MAX_LENGTH,
    MAX_RESULTS_PER_QUERY,
    _normalize_tech_name,
    _official_source_bonus,
    _ranking_key,
    build_search_queries,
    chunk_content,
    filter_noise,
    get_source_chunks,
    normalize_url,
    search_technology,
)

# --- filter_noise ------------------------------------------------------------


def _lines(text: str) -> set[str]:
    return {line for line in text.split("\n") if line.strip()}


def test_filter_noise_removes_navigation_fragments_from_medium_like_content():
    """Medium/note.com的なnavigation-heavyな入力: navigation行だけが消え、
    本文(日本語)は一字一句残る。"""
    raw = (
        "Sitemap\n"
        "Open in app\n"
        "Sign in\n"
        "Django公式チュートリアルを解説する\n"
        "久山 和宏 (System Design K2)\n"
        "PythonでWebアプリケーションを作りたくなり、新たにDjangoを使うことを思い立ちました。\n"
        "Write\n"
        "Search\n"
    )

    filtered = filter_noise(raw)

    for nav_word in ("Sitemap", "Open in app", "Sign in", "Write", "Search"):
        assert nav_word not in filtered
    assert "Django公式チュートリアルを解説する" in filtered
    assert "久山 和宏 (System Design K2)" in filtered
    assert "PythonでWebアプリケーションを作りたくなり、新たにDjangoを使うことを思い立ちました。" in filtered
    # 残った行は元テキストの行の部分集合(文字単位で完全一致)。
    assert _lines(filtered) <= _lines(raw)


def test_filter_noise_is_conservative_and_leaves_clean_documentation_untouched():
    """navigationノイズの無い、通常の公式ドキュメント風の入力は一切変更しない
    (保守的であることの確認)。"""
    clean = (
        "FastAPI is a modern, fast web framework for building APIs with Python.\n"
        "It is based on standard Python type hints.\n"
        "Key features include automatic interactive API documentation.\n"
    )

    assert filter_noise(clean) == clean


def test_filter_noise_keeps_japanese_article_body_verbatim():
    text = (
        "チュートリアルは、「投票アプリケーション」を例にとり、これを作るための"
        "実際のコードに沿って説明を展開するスタイルになっています。\n"
        "話が行ったり来たりしているように感じますし、唐突に違う話が出てくるようにも感じます。\n"
    )
    assert filter_noise(text) == text


def test_filter_noise_keeps_english_article_body_verbatim():
    text = (
        "Django is a high-level Python web framework that encourages rapid development.\n"
        "It follows the model-template-views architectural pattern.\n"
    )
    assert filter_noise(text) == text


def test_filter_noise_removes_data_uri_and_svg_garbage():
    """Phase 5C手動E2Eで実際に観測した、URLエンコードされたSVGパスデータの
    混入パターンを削除する。"""
    raw = (
        "久山 和宏 (System Design K2)%22%20d%3D%22M-100-100h300v300h-300z%22%2F%3E%3C%2Fsvg%3E)\n"
        "久山 和宏 (System Design K2)\n"
        "data:image/png;base64,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==\n"
        "本文の続きです。\n"
    )

    filtered = filter_noise(raw)

    assert "%22%20d%3D%22M" not in filtered
    assert "data:image/" not in filtered
    assert "久山 和宏 (System Design K2)" in filtered
    assert "本文の続きです。" in filtered


def test_filter_noise_removes_repeated_short_lines():
    """近接して繰り返される短い行(denylistには無いが、navigationメニュー等の
    重複と見られるもの)は2回目以降を削除する。denylist一致とは別経路の
    ロジックであることを確認するため、denylistに含まれない語を使う。"""
    raw = "Category\nCategory\nCategory\n本文の一節です。\n"

    filtered = filter_noise(raw)

    assert filtered.count("Category") == 1
    assert "本文の一節です。" in filtered


# --- chunk_content -------------------------------------------------------


def test_chunk_content_splits_on_sentence_boundaries_mixed_ja_en():
    text = "FastAPIは高速です。型ヒントを使います。Yes it is. Great tool."
    chunks = chunk_content(text)

    assert chunks  # 何らかのchunkが得られる
    for chunk in chunks:
        assert chunk in text  # verbatim: 必ず元テキストの部分文字列


def test_chunk_content_merges_short_fragments_without_inserting_characters():
    """短い見出し等の断片は隣接するchunkへマージされるが、マージ後の
    chunkはあくまで元テキストの厳密な部分文字列であり続ける
    (空白等の文字を新たに挿入しない)。"""
    text = "API\nGuide\nFastAPI is a modern, fast web framework for building APIs with Python.\n"

    chunks = chunk_content(text)

    assert len(chunks) == 1
    assert chunks[0] in text


def test_chunk_content_does_not_hard_cut_a_long_sentence():
    """soft targetであり、hard cutではない: 句読点の無い長い文を
    機械的な文字数(300文字)で切ることはしない。"""
    long_sentence = "a" * 500  # 句読点を含まない、300文字を超える1つの塊
    chunks = chunk_content(long_sentence)

    assert chunks == [long_sentence]


def test_chunk_content_handles_empty_and_whitespace_only_input():
    assert chunk_content("") == []
    assert chunk_content("   \n\n  \n") == []


# --- chunk_content: Phase 5D-d (Evidence Chunk Boundary) --------------------


def test_chunk_content_does_not_split_on_a_mid_sentence_line_wrap():
    """単なる行折り返し(文末記号の無い改行)では分割しない(Research 56の
    source_id=325(flask.palletsprojects.com)で観測した実際のバグの回帰
    テスト)。"""
    text = (
        "It is designed to make getting started quick and easy, with the ability to scale up to\n"
        "complex applications.\n"
        "Get started with Installation\n"
    )

    chunks = chunk_content(text)

    assert not any(chunk.endswith("scale up to") for chunk in chunks)
    assert (
        "It is designed to make getting started quick and easy, with the ability to scale up to\n"
        "complex applications."
    ) in chunks
    for chunk in chunks:
        assert chunk in text


def test_chunk_content_still_splits_right_after_terminal_punctuation_followed_by_newline():
    """文末記号の直後の改行は、従来どおり区切りとして機能する(回帰)。"""
    text = "First sentence ends here.\nSecond sentence continues after a real period.\n"

    chunks = chunk_content(text)

    assert chunks == [
        "First sentence ends here.",
        "Second sentence continues after a real period.",
    ]


def test_chunk_content_still_splits_each_markdown_table_row():
    """Markdown表の各行(`|`で終わる行)は、改行自体に文末記号が無くても
    引き続き1行=1chunkとして分割される(Research 56のsource_id=331相当、回帰)。"""
    text = (
        "| 学習コスト | 低（シンプルで直感的） | 中（型ヒント・非同期の理解が前提） |\n"
        "| エコシステム成熟度 | ◎（15年以上の実績、拡張多数） | ○（急成長中、主要ライブラリは充実） |\n"
    )

    chunks = chunk_content(text)

    assert len(chunks) == 2
    for chunk in chunks:
        assert chunk.endswith("|")
        assert chunk in text


def test_chunk_content_still_splits_on_paragraph_breaks():
    """空行(2つ以上の連続改行、段落区切り)は引き続き区切りとして機能する
    (修正1が段落区切りまで飲み込んでしまわないことの確認)。"""
    text = "Paragraph one here without a period\n\nParagraph two here also without one"

    chunks = chunk_content(text)

    assert chunks == [
        "Paragraph one here without a period",
        "Paragraph two here also without one",
    ]


def test_get_source_chunks_chain_keeps_each_chunk_verbatim_in_original_when_no_lines_removed():
    """navigationノイズが無い(=filter_noiseが何も削除しない)場合、
    get_source_chunks()を通した各chunkは、元のcontentそのものの
    部分文字列と完全に一致する。"""
    content = (
        "FastAPI is a modern, fast web framework for building APIs with Python.\n"
        "It is based on standard Python type hints.\n"
    )

    for chunk in get_source_chunks(content):
        assert chunk in content


def test_get_source_chunks_each_chunk_is_a_contiguous_substring_of_original_content_with_noise_removed():
    """ノイズ行が削除される場合でも、各chunkは元のSource.content
    (filter_noise適用前のテキスト)の連続した部分文字列であることを保証する。
    フィルタ後テキストに対してverbatimであるだけでは不十分(削除行をまたいで
    前後の断片を結合すると、その結合結果は元のcontent上には存在しない)。"""
    content = (
        "Sitemap\n"
        "Open in app\n"
        "Sign in\n"
        "Django公式チュートリアルを解説する\n"
        "PythonでWebアプリケーションを作りたくなり、新たにDjangoを使うことを思い立ちました。\n"
        "Write\n"
        "Search\n"
    )

    chunks = get_source_chunks(content)

    assert chunks  # 本文chunkが少なくとも1つは得られる
    for chunk in chunks:
        assert chunk in content


def test_get_source_chunks_does_not_merge_short_fragments_across_a_deleted_line():
    """短い断片(見出し等)は隣接断片へマージされるが、そのマージは
    「削除された行をまたがない」範囲に限定される。ノイズ行(ここでは
    "Sign in")を挟んだ前後の断片("Docs"と本文)を1つのchunkに結合すると、
    その結合結果は元のcontent上に存在しない文字列になってしまうため、
    そのようなマージが起きないことを確認する。"""
    content = "Docs\nSign in\nFastAPI is a modern, fast web framework for building APIs with Python.\n"

    chunks = get_source_chunks(content)

    for chunk in chunks:
        assert chunk in content
    assert not any("Docs" in chunk and "FastAPI" in chunk for chunk in chunks)


# --- get_source_chunks: Phase 5D-d (truncation-aware末尾chunk破棄) ----------


def test_get_source_chunks_drops_a_dangling_final_chunk_when_truncation_occurred():
    """`_PROMPT_CONTENT_MAX_LENGTH`超過により実際にtruncationが発生し、
    末尾chunkが文末記号・表の行末のいずれでも終わっていない場合、その1件を
    安全側に倒して除外する(Research 56のsource_id=331で観測した実際の
    バグの回帰テスト)。"""
    unit = "Complete sentence number one ends here.\n"
    head = ""
    while len(head) < _PROMPT_CONTENT_MAX_LENGTH - 50:
        head += unit
    dangling_sentence = "this sentence has no terminal punctuation and keeps going past the cutoff point"
    content = head + dangling_sentence

    # 前提確認: truncationが発生し、かつ切り詰め位置がdangling_sentence内にあること。
    assert len(head) < _PROMPT_CONTENT_MAX_LENGTH < len(content)

    chunks = get_source_chunks(content)

    for chunk in chunks:
        assert chunk in content
    assert not any("this sentence has no terminal punctuation" in chunk for chunk in chunks)
    assert any(chunk == "Complete sentence number one ends here." for chunk in chunks)


def test_get_source_chunks_keeps_a_dangling_final_chunk_when_no_truncation_occurred():
    """contentの全長が`_PROMPT_CONTENT_MAX_LENGTH`以内で、truncationが
    発生していない場合は、句点を伴わない末尾(見出しのみの短いページ等)でも
    正常な終端として残す(修正2の中心的な設計判断の確認)。"""
    content = "Short Page Title Without Any Terminal Punctuation"
    assert len(content) <= _PROMPT_CONTENT_MAX_LENGTH

    chunks = get_source_chunks(content)

    assert chunks == [content]


def test_get_source_chunks_keeps_the_final_chunk_when_truncation_lands_on_a_clean_boundary():
    """truncationは発生しているが、切り詰め位置がたまたま文末記号と一致する
    場合は、末尾chunkを破棄しない(実際に完結しているため)。"""
    exactly_at_cutoff_ending_in_period = "X" * (_PROMPT_CONTENT_MAX_LENGTH - 1) + "."
    content = exactly_at_cutoff_ending_in_period + "\nMore text appears after the cutoff point here."
    assert len(content) > _PROMPT_CONTENT_MAX_LENGTH

    chunks = get_source_chunks(content)

    assert chunks == [exactly_at_cutoff_ending_in_period]


def test_get_source_chunks_can_drop_to_zero_chunks_when_the_only_chunk_is_truncated_mid_sentence():
    """truncationが発生し、かつ生成されるchunkが1件のみで、それが文末記号・
    表の行末のいずれでも終わっていない場合は、その1件も破棄し結果が0件に
    なりうる(Evidence 0件を許容する既存方針との整合性の確認)。"""
    no_punctuation_text = "a" * (_PROMPT_CONTENT_MAX_LENGTH + 50)

    chunks = get_source_chunks(no_punctuation_text)

    assert chunks == []


def test_get_source_chunks_merges_short_fragments_only_when_truly_contiguous_in_original():
    """削除される行が無く、本当に隣接する短い断片同士は従来どおりマージ
    されることを確認する(=保守的すぎて過剰に細切れのchunkを大量生成する
    退行を防ぐ回帰テスト)。"""
    content = "API\nGuide\nFastAPI is a modern, fast web framework for building APIs with Python.\n"

    chunks = get_source_chunks(content)

    assert len(chunks) == 1
    assert chunks[0] in content


# --- build_search_queries (Phase 5D-c: Query Language Strategy) ------------


def test_build_search_queries_returns_exactly_three_regardless_of_criteria_count():
    """criteria件数に比例させない: 1件でも5件でも常に3クエリ(O(1))。"""
    one_criterion = build_search_queries("FastAPI", "Django", ["development_speed"], "AIアプリを作りたい")
    five_criteria = build_search_queries(
        "FastAPI",
        "Django",
        ["development_speed", "learning_curve", "type_safety", "async_support", "cost"],
        "AIアプリを作りたい",
    )

    assert len(one_criterion) == 3
    assert len(five_criteria) == 3


def test_build_search_queries_uses_english_official_retrieval_for_a_and_b():
    """Phase 5D-cから、Query A/Bは英語中心のofficial/primary retrievalを狙う:
    技術名+固定criteriaの英語search term+"official documentation"のみで、
    日本語のgoal・criteria labelの原文は含めない。"""
    queries = build_search_queries(
        "FastAPI", "Django", ["async_support"], "AIアプリのバックエンドを作りたい"
    )
    query_a, query_b, _query_c = queries

    assert "FastAPI" in query_a
    assert "async support" in query_a  # 固定criteriaの英語search term
    assert "official documentation" in query_a
    assert "公式ドキュメント" not in query_a
    assert "AIアプリのバックエンドを作りたい" not in query_a  # 日本語goalは含めない
    assert "非同期処理" not in query_a  # 日本語labelも含めない

    assert "Django" in query_b
    assert "async support" in query_b
    assert "official documentation" in query_b
    assert "AIアプリのバックエンドを作りたい" not in query_b


def test_build_search_queries_keeps_japanese_context_for_c():
    """Query Cは従来どおり(Phase 5D/5D-bから変更なし)、日本語のcriteria
    label・goalを含む、third-party比較記事向けのクエリであり続ける
    (回帰テスト)。"""
    queries = build_search_queries(
        "FastAPI", "Django", ["async_support"], "AIアプリのバックエンドを作りたい"
    )
    _query_a, _query_b, query_c = queries

    assert "FastAPI" in query_c and "Django" in query_c
    assert "vs" in query_c
    assert "非同期処理" in query_c
    assert "AIアプリのバックエンドを作りたい" in query_c
    assert "official documentation" not in query_c
    assert "公式ドキュメント" not in query_c


def test_build_search_queries_excludes_custom_criteria_from_a_and_b_but_keeps_them_in_c():
    """custom criteria(固定候補に無い自由入力、多くは日本語)は、正確な英訳を
    機械的に保証できないためQuery A/Bには含めない。Query Cには引き続き
    日本語labelとして含める(=third-party retrievalでは見捨てない)。"""
    queries = build_search_queries("Flask", "FastAPI", ["独自の比較軸"], "個人開発用")
    query_a, query_b, query_c = queries

    assert "独自の比較軸" not in query_a
    assert "独自の比較軸" not in query_b
    assert "独自の比較軸" in query_c


def test_build_search_queries_caps_english_criteria_terms_for_a_and_b():
    """query_a/bに埋め込む英語criteria termの合計文字数は、過度に長くなら
    ないよう決定論的に切り詰められる。"""
    all_fixed_criteria = [c.value for c in Criterion]  # 10件、合計は80文字を超える
    full_english_terms = " ".join(
        term for term in (english_search_term_for(c) for c in all_fixed_criteria) if term
    )
    assert len(full_english_terms) > _MAX_QUERY_CRITERIA_CHARS_EN  # 前提確認

    query_a, query_b, _query_c = build_search_queries(
        "FastAPI", "Django", all_fixed_criteria, "goal"
    )

    assert full_english_terms not in query_a
    assert full_english_terms not in query_b
    assert len(query_a) < len("FastAPI") + _MAX_QUERY_CRITERIA_CHARS_EN + len(" official documentation") + 10


def test_build_search_queries_caps_japanese_criteria_and_goal_for_c():
    """query_c(日本語)のcriteria/goalは、従来どおり決定論的に切り詰められる
    (Phase 5D/5D-bから変更なし、回帰テスト)。"""
    long_goal = "とても長いuse caseの説明文です。" * 10
    long_criteria = [f"criterion-{i}" for i in range(20)]  # すべてcustom(自由入力)

    _query_a, _query_b, query_c = build_search_queries(
        "FastAPI", "Django", long_criteria, long_goal
    )

    assert long_goal not in query_c
    assert " ".join(long_criteria) not in query_c
    assert len(query_c) < len("FastAPI vs Django") + _MAX_QUERY_CRITERIA_CHARS + _MAX_QUERY_GOAL_CHARS + 10


# --- normalize_url ---------------------------------------------------------


def test_normalize_url_treats_trailing_slash_and_fragment_as_equivalent():
    assert normalize_url("https://example.com/docs/") == normalize_url("https://example.com/docs")
    assert normalize_url("https://example.com/docs#section-1") == normalize_url(
        "https://example.com/docs"
    )


def test_normalize_url_is_case_insensitive():
    assert normalize_url("https://Example.com/Docs") == normalize_url("https://example.com/docs")


# --- _normalize_tech_name ---------------------------------------------------


def test_normalize_tech_name_strips_case_and_non_alnum():
    assert _normalize_tech_name("FastAPI") == "fastapi"
    assert _normalize_tech_name("Next.js") == "nextjs"
    assert _normalize_tech_name("PostgreSQL") == "postgresql"


# --- _official_source_bonus (Phase 5D-b) ------------------------------------


def test_official_source_bonus_matches_official_domain_via_hostname_label():
    """技術名(item_a/item_b)がホスト名のラベルに完全一致する場合、加点される。"""
    assert _official_source_bonus("https://flask.palletsprojects.com/en/3.0.x/", "Flask", "Django") > 0
    assert _official_source_bonus("https://fastapi.tiangolo.com/", "FastAPI", "Flask") > 0


def test_official_source_bonus_matches_partial_hostname_label():
    """"djangoproject"のような、技術名を部分文字列として含むラベルも拾う。"""
    assert _official_source_bonus("https://docs.djangoproject.com/en/5.0/", "Django", "Flask") > 0


def test_official_source_bonus_matches_generic_doc_hosting_pattern_regardless_of_tech_name():
    """readthedocs.io等、技術非依存の汎用パターンは技術名と無関係に加点される。"""
    assert (
        _official_source_bonus("https://someproject.readthedocs.io/en/latest/", "Unrelated", "AlsoUnrelated")
        > 0
    )


def test_official_source_bonus_ignores_tech_name_only_in_url_path_not_hostname():
    """第三者記事のパスに技術名が含まれるだけでは「公式」扱いしない
    (判定対象はホスト名のみ)。"""
    assert _official_source_bonus("https://qiita.com/someone/items/fastapi-tips", "FastAPI", "Flask") == 0.0


def test_official_source_bonus_skips_short_tech_names_for_hostname_match():
    """正規化後3文字未満の技術名は、無関係なドメインへの誤検出リスクが高いため
    ホスト名一致ルールの対象にしない。"""
    assert _official_source_bonus("https://gopherize.me/", "Go", "Rust") == 0.0


def test_official_source_bonus_caps_total_even_when_both_signals_match():
    """技術名一致とdoc-hostingパターンの両方に一致しても、合計は上限を超えない。"""
    bonus = _official_source_bonus("https://docs.flaskproject.readthedocs.io/", "Flask", "Django")
    assert bonus == _OFFICIAL_BONUS_CAP


# --- _ranking_key (Phase 5D-b) ----------------------------------------------


def test_ranking_key_prefers_official_domain_when_relevance_is_close():
    """relevanceが拮抗している場合は、公式ドメインが僅差で優先される。"""
    official = {"score": 0.75, "url": "https://fastapi.tiangolo.com/"}
    third_party = {"score": 0.80, "url": "https://example-blog.com/fastapi-guide"}

    ranked = sorted([third_party, official], key=lambda r: _ranking_key(r, "FastAPI", "Flask"))

    assert ranked[0] is official


def test_ranking_key_does_not_override_a_large_relevance_gap():
    """公式候補のrelevance scoreが大幅に低い場合は、公式というだけで
    高relevanceの第三者sourceを追い越さない(ボーナスはrelevanceを
    置き換える設計になっていないことの回帰テスト)。"""
    official = {"score": 0.3, "url": "https://fastapi.tiangolo.com/"}
    third_party = {"score": 0.9, "url": "https://example-blog.com/fastapi-guide"}

    ranked = sorted([official, third_party], key=lambda r: _ranking_key(r, "FastAPI", "Flask"))

    assert ranked[0] is third_party  # 0.3 + 0.15(上限) = 0.45 < 0.9 のため覆らない


def test_ranking_key_falls_back_to_score_order_when_no_official_domain_present():
    """公式ドメイン候補が1件も無い場合は、現行と同じscore順になる(回帰テスト)。"""
    higher = {"score": 0.6, "url": "https://blog-a.example.com/"}
    lower = {"score": 0.4, "url": "https://blog-b.example.com/"}

    ranked = sorted([lower, higher], key=lambda r: _ranking_key(r, "FastAPI", "Flask"))

    assert ranked == [higher, lower]


def test_ranking_key_reorders_without_dropping_any_result():
    """並べ替えは除外ではないこと(件数・内容の集合が変わらないこと)を確認する。"""
    results = [
        {"score": 0.5, "url": "https://blog.example.com/"},
        {"score": 0.4, "url": "https://fastapi.tiangolo.com/"},
    ]

    ranked = sorted(results, key=lambda r: _ranking_key(r, "FastAPI", "Flask"))

    assert {id(r) for r in ranked} == {id(r) for r in results}


# --- search_technology (Phase 5D-b, Tavilyはfakeに差し替え) -----------------


class _FakeTavilyClient:
    """TavilyClient()の戻り値の代わりに使う、テスト用のfakeクライアント。"""

    def __init__(self, response: dict, captured_kwargs: dict):
        self._response = response
        self._captured_kwargs = captured_kwargs

    def search(self, **kwargs):
        self._captured_kwargs.update(kwargs)
        return self._response


def _raw_result(url: str, score: float, content: str = "本文のダミーです。") -> dict:
    return {"title": url, "url": url, "score": score, "content": content, "raw_content": content}


def test_search_technology_requests_a_wider_candidate_pool_than_it_keeps(monkeypatch):
    """Tavilyへは採用件数(MAX_RESULTS_PER_QUERY)より広い候補プール
    (_FETCH_RESULTS_PER_QUERY)をリクエストする(Tavily呼び出し回数自体は
    1回のまま変わらない)。"""
    captured: dict = {}
    monkeypatch.setattr(
        search_client_module,
        "TavilyClient",
        lambda: _FakeTavilyClient({"results": []}, captured),
    )

    search_technology("FastAPI 公式ドキュメント", item_a="FastAPI", item_b="Flask")

    assert captured["max_results"] == _FETCH_RESULTS_PER_QUERY
    assert _FETCH_RESULTS_PER_QUERY > MAX_RESULTS_PER_QUERY


def test_search_technology_promotes_an_official_domain_that_is_a_close_fourth_place(monkeypatch):
    """生のTavily scoreでは僅差の4位(採用件数の外)だった公式ドメインが、
    候補プールを広げたことと弱いボーナスによって採用件数内に入ること。"""
    raw_results = [
        _raw_result("https://blog-a.example.com/", 0.95),
        _raw_result("https://blog-b.example.com/", 0.90),
        _raw_result("https://blog-c.example.com/", 0.85),
        _raw_result("https://fastapi.tiangolo.com/", 0.80),  # 僅差の4位、公式ドメイン
        _raw_result("https://blog-d.example.com/", 0.50),
    ]
    monkeypatch.setattr(
        search_client_module,
        "TavilyClient",
        lambda: _FakeTavilyClient({"results": raw_results}, {}),
    )

    items = search_technology("FastAPI 公式ドキュメント", item_a="FastAPI", item_b="Flask")

    assert len(items) <= MAX_RESULTS_PER_QUERY
    assert any("fastapi.tiangolo.com" in item.url for item in items)


def test_search_technology_does_not_promote_an_official_domain_with_a_large_relevance_gap(monkeypatch):
    """公式ドメインのrelevance scoreが他候補と大きく(0.15のボーナス上限を
    超えて)離れている場合は、採用件数に入らないこと。"""
    raw_results = [
        _raw_result("https://blog-a.example.com/", 0.95),
        _raw_result("https://blog-b.example.com/", 0.90),
        _raw_result("https://blog-c.example.com/", 0.85),
        _raw_result("https://fastapi.tiangolo.com/", 0.10),  # 大差の最下位、公式ドメイン
    ]
    monkeypatch.setattr(
        search_client_module,
        "TavilyClient",
        lambda: _FakeTavilyClient({"results": raw_results}, {}),
    )

    items = search_technology("FastAPI 公式ドキュメント", item_a="FastAPI", item_b="Flask")

    assert len(items) <= MAX_RESULTS_PER_QUERY
    assert not any("fastapi.tiangolo.com" in item.url for item in items)


def test_search_technology_never_returns_more_than_the_kept_limit(monkeypatch):
    """候補プールを広げても、最終的な返り値はMAX_RESULTS_PER_QUERY件を
    超えない(保存Source数・Geminiプロンプトサイズが変わらないことの保証)。"""
    raw_results = [_raw_result(f"https://blog-{i}.example.com/", 1.0 - i * 0.05) for i in range(8)]
    monkeypatch.setattr(
        search_client_module,
        "TavilyClient",
        lambda: _FakeTavilyClient({"results": raw_results}, {}),
    )

    items = search_technology("FastAPI 公式ドキュメント", item_a="FastAPI", item_b="Flask")

    assert len(items) <= MAX_RESULTS_PER_QUERY
