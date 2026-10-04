"""Phase 5D-c: Query Language Strategyで追加した
`CRITERION_ENGLISH_SEARCH_TERMS` / `english_search_term_for()` の単体テスト。
"""

from app.schemas.criteria import (
    Criterion,
    CRITERION_ENGLISH_SEARCH_TERMS,
    english_search_term_for,
)


def test_criterion_english_search_terms_covers_every_fixed_criterion():
    """固定候補(Criterion)の全メンバーに対応する英語termが存在する
    (将来criteriaが追加された際の抜け漏れを防ぐ回帰テスト)。"""
    assert set(CRITERION_ENGLISH_SEARCH_TERMS.keys()) == set(Criterion)


def test_english_search_term_for_returns_the_mapped_term_for_fixed_criteria():
    assert english_search_term_for("learning_curve") == "learning curve"
    assert english_search_term_for("ecosystem") == "ecosystem"


def test_english_search_term_for_returns_none_for_custom_criteria():
    """自由入力(固定候補に無い文字列)は、正確な英訳を機械的に保証できない
    ため、label_for()のような原文フォールバックはせずNoneを返す。"""
    assert english_search_term_for("独自の比較軸") is None
    assert english_search_term_for("some custom criterion") is None


def test_criterion_english_search_terms_are_single_concise_terms_without_expansion():
    """各termは1語/1フレーズの直訳のみで、関連語への拡張(カンマ区切り等)が
    紛れ込んでいないことを確認する(Phase 5D-c設計時の明示的な方針の回帰
    テスト: query languageの効果とcriteria keyword拡張の効果を混同しない
    ため)。"""
    for term in CRITERION_ENGLISH_SEARCH_TERMS.values():
        assert "," not in term
        assert "/" not in term
        assert len(term) <= 20
