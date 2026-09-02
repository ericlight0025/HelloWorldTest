import pytest

from main import parse_selection


def test_parse_selection_all() -> None:
    assert parse_selection("all", 4) == [0, 1, 2, 3]


def test_parse_selection_mixed_ranges() -> None:
    assert parse_selection("1,3,5-7", 7) == [0, 2, 4, 5, 6]


def test_parse_selection_removes_duplicates_and_sorts() -> None:
    assert parse_selection("3,1,3,2", 3) == [0, 1, 2]


def test_parse_selection_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        parse_selection("5", 4)


def test_parse_selection_rejects_invalid_range() -> None:
    with pytest.raises(ValueError):
        parse_selection("4-2", 4)
