"""evaluation.dataset の固定Evaluation Setに関するテスト。"""

import pytest

from app.schemas.criteria import Criterion
from evaluation.dataset import EVALUATION_CASES, JUDGE_SAMPLE_CASE_IDS, get_case_by_id


def test_evaluation_set_has_15_cases():
    assert len(EVALUATION_CASES) == 15


def test_case_ids_are_unique():
    ids = [c.case_id for c in EVALUATION_CASES]
    assert len(ids) == len(set(ids))


def test_criteria_count_is_between_1_and_5():
    for case in EVALUATION_CASES:
        assert 1 <= len(case.criteria) <= 5, case.case_id


def test_criteria_values_are_valid_criterion_enum_values():
    valid_values = {c.value for c in Criterion}
    for case in EVALUATION_CASES:
        for criterion in case.criteria:
            assert criterion in valid_values, (case.case_id, criterion)


def test_criteria_have_no_duplicates_within_a_case():
    for case in EVALUATION_CASES:
        assert len(case.criteria) == len(set(case.criteria)), case.case_id


def test_judge_sample_is_subset_of_evaluation_set():
    case_ids = {c.case_id for c in EVALUATION_CASES}
    assert set(JUDGE_SAMPLE_CASE_IDS).issubset(case_ids)


def test_judge_sample_has_5_cases():
    assert len(JUDGE_SAMPLE_CASE_IDS) == 5


def test_get_case_by_id_returns_matching_case():
    case = get_case_by_id("c01")
    assert case.case_id == "c01"


def test_get_case_by_id_raises_for_unknown_id():
    with pytest.raises(KeyError):
        get_case_by_id("does-not-exist")
