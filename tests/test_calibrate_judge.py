"""Tests for κ and ECE math in scripts/calibrate_judge.py.

Imported via importlib because scripts/ isn't a package.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "calibrate_judge.py"
_spec = importlib.util.spec_from_file_location("calibrate_judge", _SCRIPT)
calib = importlib.util.module_from_spec(_spec)
sys.modules["calibrate_judge"] = calib  # @dataclass needs this for __module__ lookups
_spec.loader.exec_module(calib)


def test_kappa_perfect_agreement_is_one():
    a = [True, False, True, True, False]
    assert calib.cohen_kappa(a, a) == pytest.approx(1.0)


def test_kappa_inverted_is_minus_one():
    a = [True, False, True, False]
    b = [False, True, False, True]
    assert calib.cohen_kappa(a, b) == pytest.approx(-1.0)


def test_kappa_chance_agreement_is_zero():
    """50/50 prevalence with random independent labels → κ ≈ 0."""
    # 4 of each combination: TT, TF, FT, FF — exactly chance.
    a = [True, True, True, True, False, False, False, False]
    b = [True, True, False, False, True, True, False, False]
    assert calib.cohen_kappa(a, b) == pytest.approx(0.0, abs=1e-9)


def test_kappa_above_chance():
    # 8/10 agreement, balanced classes → κ should be 0.6
    a = [True]*5 + [False]*5
    b = [True]*4 + [False] + [True] + [False]*4
    k = calib.cohen_kappa(a, b)
    assert 0.55 < k < 0.65


def test_kappa_length_mismatch():
    with pytest.raises(ValueError):
        calib.cohen_kappa([True], [True, False])


def test_ece_perfectly_calibrated_is_zero():
    """When confidence equals empirical accuracy in every bin, ECE = 0."""
    # All confidences = 1.0, all outcomes = pass → ECE = 0
    confidences = [1.0] * 10
    outcomes = [True] * 10
    assert calib.expected_calibration_error(confidences, outcomes) == pytest.approx(0.0)


def test_ece_unanimous_fail_when_all_pass():
    """Confidence = 1.0 but outcome = fail → ECE = 1.0."""
    confidences = [1.0] * 10
    outcomes = [False] * 10
    assert calib.expected_calibration_error(confidences, outcomes) == pytest.approx(1.0)


def test_ece_partial():
    """Half pass / half fail at confidence 0.5: bin acc = 0.5, conf = 0.5 → ECE = 0."""
    confidences = [0.5] * 10
    outcomes = [True]*5 + [False]*5
    assert calib.expected_calibration_error(confidences, outcomes) == pytest.approx(0.0)


def test_ece_miscalibrated_high_confidence():
    """Confidence 1.0, but only 70% pass → ECE should be 0.3."""
    confidences = [1.0] * 10
    outcomes = [True]*7 + [False]*3
    ece = calib.expected_calibration_error(confidences, outcomes)
    assert ece == pytest.approx(0.3)


def test_ece_thresholds_locked():
    """Match DECISIONS.md #12 exactly."""
    assert calib.ECE_PASS == 0.10
    assert calib.ECE_BADGE == 0.05
    assert calib.KAPPA_PASS == 0.60
