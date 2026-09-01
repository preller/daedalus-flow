"""Unit tests for the assert_golden_json_approx helper.

A last-digit perturbation passes; every other kind of drift fails.
"""

import json
from pathlib import Path

import pytest

from tests._helpers import assert_golden_json_approx

BENIGN_PERTURBATION = 1e-13
REAL_CHANGE = 1e-3


def _write(tmp_path: Path, name: str, obj: object) -> Path:
    """Write ``obj`` as indent-2 JSON (matching the module write style)."""
    path = tmp_path / name
    path.write_text(json.dumps(obj, indent=2))
    return path


def _pair(tmp_path: Path, produced: object, expected: object) -> tuple[Path, Path]:
    """Stage a produced/expected JSON pair under ``tmp_path``."""
    return (
        _write(tmp_path, "produced.json", produced),
        _write(tmp_path, "expected.json", expected),
    )


def test_benign_last_ulp_perturbation_passes(tmp_path: Path) -> None:
    base = 0.014159271239341
    produced, expected = _pair(tmp_path, {"x": base + BENIGN_PERTURBATION}, {"x": base})
    assert_golden_json_approx(produced, expected)


def test_real_float_change_fails(tmp_path: Path) -> None:
    base = 0.5
    produced, expected = _pair(tmp_path, {"x": base + REAL_CHANGE}, {"x": base})
    with pytest.raises(AssertionError, match="float mismatch"):
        assert_golden_json_approx(produced, expected)


def test_key_set_difference_fails(tmp_path: Path) -> None:
    produced, expected = _pair(tmp_path, {"a": 1.0, "b": 2.0}, {"a": 1.0, "c": 2.0})
    with pytest.raises(AssertionError, match="key-set mismatch"):
        assert_golden_json_approx(produced, expected)


def test_list_length_difference_fails(tmp_path: Path) -> None:
    produced, expected = _pair(tmp_path, {"xs": [1.0, 2.0]}, {"xs": [1.0, 2.0, 3.0]})
    with pytest.raises(AssertionError, match="list-length mismatch"):
        assert_golden_json_approx(produced, expected)


def test_int_leaf_change_fails(tmp_path: Path) -> None:
    # int leaves must match; a count drift is a regression.
    produced, expected = _pair(tmp_path, {"n": 3}, {"n": 4})
    with pytest.raises(AssertionError, match="int mismatch"):
        assert_golden_json_approx(produced, expected)


def test_string_leaf_change_fails(tmp_path: Path) -> None:
    produced, expected = _pair(tmp_path, {"name": "mcmc"}, {"name": "nested"})
    with pytest.raises(AssertionError, match="value mismatch"):
        assert_golden_json_approx(produced, expected)


def test_bool_vs_int_leaf_fails(tmp_path: Path) -> None:
    # bool is an int subclass; True must not compare equal to 1.
    produced, expected = _pair(tmp_path, {"flag": True}, {"flag": 1})
    with pytest.raises(AssertionError, match="bool mismatch"):
        assert_golden_json_approx(produced, expected)


def test_nan_equals_nan_passes(tmp_path: Path) -> None:
    # json.dumps emits NaN as the bare token NaN, which json.loads reads back.
    produced, expected = _pair(tmp_path, {"x": float("nan")}, {"x": float("nan")})
    assert_golden_json_approx(produced, expected)
