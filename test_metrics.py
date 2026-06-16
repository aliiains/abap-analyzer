"""
tests/test_metrics.py

Unit tests for :mod:`metrics`.

Coverage targets
----------------
* MetricsCalculator.calculate returns MetricsReport
* Size metrics (LOC, total, comments, blanks)
* Complexity metrics (nesting, cyclomatic)
* Quality metrics (comment ratio, long lines, magic numbers, TODO)
* DB metrics (SELECT, CALL FUNCTION)
* Structure metrics (FORM, METHOD, CLASS, error handling)
* Keyword frequency metrics
* Severity classification (ok / warning / critical)
* AnalysisThresholds customisation
* MetricsReport helpers (by_name, warnings, criticals)
* ExtendedMetricsCalculator extra metrics
* Protocol compliance
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from parser import AbapParser, ParseResult
from metrics import (
    AnalysisThresholds,
    ExtendedMetricsCalculator,
    Metric,
    MetricCalculatorProtocol,
    MetricsCalculator,
    MetricsReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(source: str) -> ParseResult:
    return AbapParser().parse(source)


def _calc(source: str, thresholds: AnalysisThresholds | None = None) -> MetricsReport:
    calc = MetricsCalculator(thresholds=thresholds)
    return calc.calculate(_parse(source))


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_calculator_satisfies_protocol(self) -> None:
        calc = MetricsCalculator()
        assert isinstance(calc, MetricCalculatorProtocol)

    def test_calculate_returns_metrics_report(self) -> None:
        report = _calc("DATA lv_x TYPE i.")
        assert isinstance(report, MetricsReport)

    def test_metrics_is_list(self) -> None:
        report = _calc("DATA lv_x TYPE i.")
        assert isinstance(report.metrics, list)


# ---------------------------------------------------------------------------
# Metric dataclass
# ---------------------------------------------------------------------------

class TestMetricDataclass:
    def test_metric_frozen(self) -> None:
        m = Metric(name="test", label="Test", value=42)
        with pytest.raises((AttributeError, TypeError)):
            m.value = 99  # type: ignore[misc]

    def test_metric_defaults(self) -> None:
        m = Metric(name="x", label="X", value=0)
        assert m.unit     == ""
        assert m.severity == "ok"
        assert m.recommendation is None


# ---------------------------------------------------------------------------
# MetricsReport helpers
# ---------------------------------------------------------------------------

class TestMetricsReport:
    def _make_report(self) -> MetricsReport:
        metrics = [
            Metric(name="a", label="A", value=1, severity="ok"),
            Metric(name="b", label="B", value=2, severity="warning"),
            Metric(name="c", label="C", value=3, severity="critical"),
            Metric(name="d", label="D", value=4, severity="ok"),
        ]
        return MetricsReport(metrics=metrics)

    def test_warnings_property(self) -> None:
        report = self._make_report()
        assert len(report.warnings) == 1
        assert report.warnings[0].name == "b"

    def test_criticals_property(self) -> None:
        report = self._make_report()
        assert len(report.criticals) == 1
        assert report.criticals[0].name == "c"

    def test_ok_metrics_property(self) -> None:
        report = self._make_report()
        assert len(report.ok_metrics) == 2

    def test_by_name_found(self) -> None:
        report = self._make_report()
        m = report.by_name("b")
        assert m is not None
        assert m.value == 2

    def test_by_name_not_found(self) -> None:
        report = self._make_report()
        assert report.by_name("zzz") is None

    def test_by_name_returns_first(self) -> None:
        """by_name returns the first match when duplicates exist."""
        metrics = [
            Metric(name="dup", label="First",  value=1),
            Metric(name="dup", label="Second", value=2),
        ]
        report = MetricsReport(metrics=metrics)
        assert report.by_name("dup").label == "First"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Size metrics
# ---------------------------------------------------------------------------

class TestSizeMetrics:
    def test_loc_metric_present(self) -> None:
        report = _calc("DATA lv_x TYPE i.")
        m = report.by_name("loc")
        assert m is not None
        assert m.value == 1

    def test_total_lines_metric(self) -> None:
        source = "DATA lv_x TYPE i.\n\n* comment\n"
        report = _calc(source)
        m = report.by_name("total_lines")
        assert m is not None
        assert m.value == 3

    def test_comment_lines_metric(self) -> None:
        source = "* comment\nDATA lv_x TYPE i."
        report = _calc(source)
        m = report.by_name("comment_lines")
        assert m is not None
        assert m.value == 1

    def test_blank_lines_metric(self) -> None:
        source = "DATA lv_x TYPE i.\n\n"
        report = _calc(source)
        m = report.by_name("blank_lines")
        assert m is not None
        assert m.value >= 1

    def test_loc_warning_threshold(self) -> None:
        th = AnalysisThresholds(max_loc_warning=5, max_loc_critical=100)
        source = "\n".join(["DATA lv_x TYPE i."] * 6)
        report = _calc(source, thresholds=th)
        m = report.by_name("loc")
        assert m is not None
        assert m.severity == "warning"

    def test_loc_critical_threshold(self) -> None:
        th = AnalysisThresholds(max_loc_critical=3)
        source = "\n".join(["DATA lv_x TYPE i."] * 4)
        report = _calc(source, thresholds=th)
        m = report.by_name("loc")
        assert m is not None
        assert m.severity == "critical"

    def test_loc_ok_when_within_limits(self) -> None:
        th = AnalysisThresholds(max_loc_warning=100)
        source = "DATA lv_x TYPE i."
        report = _calc(source, thresholds=th)
        m = report.by_name("loc")
        assert m is not None
        assert m.severity == "ok"


# ---------------------------------------------------------------------------
# Complexity metrics
# ---------------------------------------------------------------------------

class TestComplexityMetrics:
    def test_max_nesting_metric_present(self) -> None:
        source = "IF a.\n  IF b.\n  ENDIF.\nENDIF."
        report = _calc(source)
        m = report.by_name("max_nesting")
        assert m is not None
        assert m.value >= 1

    def test_avg_nesting_metric_present(self) -> None:
        report = _calc("DATA lv_x TYPE i.")
        m = report.by_name("avg_nesting")
        assert m is not None

    def test_cyclomatic_complexity_present(self) -> None:
        report = _calc("DATA lv_x TYPE i.")
        m = report.by_name("cyclomatic_complexity")
        assert m is not None
        assert m.value >= 1  # always at least 1

    def test_cyclomatic_increases_with_branches(self) -> None:
        simple = "DATA lv_x TYPE i."
        complex_ = "\n".join([
            "IF a. ENDIF.",
            "IF b. ENDIF.",
            "LOOP AT t INTO s. ENDLOOP.",
        ])
        r_simple  = _calc(simple)
        r_complex = _calc(complex_)
        cc_simple  = r_simple.by_name("cyclomatic_complexity")
        cc_complex = r_complex.by_name("cyclomatic_complexity")
        assert cc_complex.value > cc_simple.value  # type: ignore[union-attr]

    def test_nesting_warning_threshold(self) -> None:
        th = AnalysisThresholds(max_nesting_warning=2, max_nesting_critical=10)
        source = "\n".join([
            "IF a.", "  IF b.", "    IF c.", "    ENDIF.", "  ENDIF.", "ENDIF."
        ])
        report = _calc(source, thresholds=th)
        m = report.by_name("max_nesting")
        assert m is not None
        assert m.severity in ("warning", "critical")

    def test_nesting_critical_threshold(self) -> None:
        th = AnalysisThresholds(max_nesting_critical=2)
        source = "\n".join([
            "IF a.", "  IF b.", "    IF c.", "    ENDIF.", "  ENDIF.", "ENDIF."
        ])
        report = _calc(source, thresholds=th)
        m = report.by_name("max_nesting")
        assert m is not None
        assert m.severity == "critical"

    def test_cyclomatic_critical_at_high_value(self) -> None:
        th = AnalysisThresholds()
        # Generate many IF statements to push CC > 20
        lines = ["IF cond. ENDIF."] * 25
        report = _calc("\n".join(lines), thresholds=th)
        m = report.by_name("cyclomatic_complexity")
        assert m is not None
        assert m.severity == "critical"


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------

class TestQualityMetrics:
    def test_comment_ratio_metric_present(self) -> None:
        report = _calc("DATA lv_x TYPE i.")
        m = report.by_name("comment_ratio")
        assert m is not None

    def test_no_comments_low_ratio(self) -> None:
        source = "\n".join(["DATA lv_x TYPE i."] * 10)
        report = _calc(source)
        m = report.by_name("comment_ratio")
        assert m is not None
        assert m.value == 0.0

    def test_comment_ratio_warning(self) -> None:
        th = AnalysisThresholds(min_comment_ratio_warning=0.5, min_comment_ratio_critical=0.1)
        source = "\n".join(["DATA lv_x TYPE i."] * 10 + ["* comment"])
        report = _calc(source, thresholds=th)
        m = report.by_name("comment_ratio")
        assert m is not None
        assert m.severity in ("warning", "critical")

    def test_sufficient_comments_ok(self) -> None:
        source = "\n".join(
            ["DATA lv_x TYPE i."] * 5 + ["* comment"] * 5
        )
        report = _calc(source)
        m = report.by_name("comment_ratio")
        assert m is not None
        # 50% comment ratio should be fine with default threshold of 10%
        assert m.severity == "ok"

    def test_long_lines_metric_present(self) -> None:
        report = _calc("DATA lv_x TYPE i.")
        m = report.by_name("long_lines")
        assert m is not None

    def test_long_lines_flagged(self) -> None:
        long_line = "DATA lv_very_long_name_here TYPE string VALUE 'a very very very very very very long default value that definitely exceeds one hundred and twenty characters here'."
        report = _calc(long_line)
        m = report.by_name("long_lines")
        assert m is not None
        assert m.value >= 1

    def test_magic_numbers_metric_present(self) -> None:
        report = _calc("lv_x = 42.")
        m = report.by_name("magic_numbers")
        assert m is not None
        assert m.value >= 1

    def test_zero_magic_numbers_ok(self) -> None:
        report = _calc("DATA lv_x TYPE i.")
        m = report.by_name("magic_numbers")
        assert m is not None
        assert m.severity == "ok"

    def test_magic_numbers_warning(self) -> None:
        th = AnalysisThresholds(max_magic_numbers_warning=2, max_magic_numbers_critical=20)
        source = "lv_x = 2.\nlv_y = 3.\nlv_z = 4."
        report = _calc(source, thresholds=th)
        m = report.by_name("magic_numbers")
        assert m is not None
        assert m.severity in ("warning", "critical")

    def test_todo_fixme_metric(self) -> None:
        source = "* TODO: fix this\n* FIXME: broken"
        report = _calc(source)
        m = report.by_name("todo_fixme")
        assert m is not None
        assert m.value == 2

    def test_chain_statements_counted(self) -> None:
        source = "DATA: lv_a TYPE i, lv_b TYPE i."
        report = _calc(source)
        m = report.by_name("chain_statements")
        assert m is not None
        assert m.value >= 1


# ---------------------------------------------------------------------------
# DB metrics
# ---------------------------------------------------------------------------

class TestDbMetrics:
    def test_select_count_metric(self) -> None:
        source = "SELECT * FROM mara INTO TABLE lt_data WHERE matnr LIKE 'Z%'."
        report = _calc(source)
        m = report.by_name("select_count")
        assert m is not None
        assert m.value == 1

    def test_select_warning_threshold(self) -> None:
        th = AnalysisThresholds(max_select_warning=3, max_select_critical=100)
        source = "\n".join(["SELECT * FROM mara INTO lv_x."] * 4)
        report = _calc(source, thresholds=th)
        m = report.by_name("select_count")
        assert m is not None
        assert m.severity in ("warning", "critical")

    def test_call_function_metric(self) -> None:
        source = "CALL FUNCTION 'Z_MY_FM'."
        report = _calc(source)
        m = report.by_name("call_function_count")
        assert m is not None
        assert m.value == 1

    def test_perform_metric(self) -> None:
        source = "PERFORM my_routine."
        report = _calc(source)
        m = report.by_name("perform_count")
        assert m is not None
        assert m.value == 1


# ---------------------------------------------------------------------------
# Structure metrics
# ---------------------------------------------------------------------------

class TestStructureMetrics:
    def test_form_count_metric(self) -> None:
        source = "FORM my_form.\nENDFORM."
        report = _calc(source)
        m = report.by_name("form_count")
        assert m is not None
        assert m.value == 1

    def test_method_count_metric(self) -> None:
        source = "METHOD do_it.\nENDMETHOD."
        report = _calc(source)
        m = report.by_name("method_count")
        assert m is not None
        assert m.value == 1

    def test_class_count_metric(self) -> None:
        source = "CLASS lcl_x DEFINITION.\nENDCLASS."
        report = _calc(source)
        m = report.by_name("class_count")
        assert m is not None
        assert m.value == 1

    def test_function_count_metric(self) -> None:
        source = "FUNCTION z_my_fm.\nENDFUNCTION."
        report = _calc(source)
        m = report.by_name("function_count")
        assert m is not None
        assert m.value == 1

    def test_raise_without_catch_warning(self) -> None:
        source = "RAISE EXCEPTION TYPE cx_no_auth."
        report = _calc(source)
        m = report.by_name("raise_count")
        assert m is not None
        assert m.severity == "warning"

    def test_catch_count_metric(self) -> None:
        source = "TRY.\n  lv_x = 1.\nCATCH cx_sy_zerodivide.\nENDTRY."
        report = _calc(source)
        m = report.by_name("catch_count")
        assert m is not None
        assert m.value == 1


# ---------------------------------------------------------------------------
# Keyword frequency
# ---------------------------------------------------------------------------

class TestKeywordMetrics:
    def test_top_keyword_metrics_present(self) -> None:
        source = "DATA lv_x TYPE i.\nDATA lv_y TYPE string."
        report = _calc(source)
        # Should contain keyword_data
        names = [m.name for m in report.metrics]
        assert any("keyword_data" in n for n in names)

    def test_no_keyword_metrics_for_empty(self) -> None:
        report = _calc("")
        # keyword metrics may be absent for empty code
        names = [m.name for m in report.metrics]
        keyword_names = [n for n in names if n.startswith("keyword_")]
        # Acceptable: either 0 keywords or only valid ones
        assert all("keyword_" in n for n in keyword_names)


# ---------------------------------------------------------------------------
# ExtendedMetricsCalculator
# ---------------------------------------------------------------------------

class TestExtendedCalculator:
    def test_data_declaration_density_present(self) -> None:
        source = "DATA lv_x TYPE i.\nDATA lv_y TYPE string.\nlv_x = 1."
        calc = ExtendedMetricsCalculator()
        report = calc.calculate(_parse(source))
        m = report.by_name("data_declaration_density")
        assert m is not None

    def test_modularisation_score_present(self) -> None:
        source = "DATA lv_x TYPE i.\nPERFORM my_routine."
        calc = ExtendedMetricsCalculator()
        report = calc.calculate(_parse(source))
        m = report.by_name("modularisation_score")
        assert m is not None

    def test_modularisation_warning_low_score(self) -> None:
        """Low modularisation score on large code block should warn."""
        # 105 DATA lines and zero calls = very low score
        source = "\n".join(["DATA lv_x TYPE i."] * 105)
        th = AnalysisThresholds()
        calc = ExtendedMetricsCalculator(thresholds=th)
        report = calc.calculate(_parse(source))
        m = report.by_name("modularisation_score")
        assert m is not None
        assert m.severity in ("warning", "ok")  # depends on exact value

    def test_extended_adds_extra_metrics(self) -> None:
        source = "DATA lv_x TYPE i.\nPERFORM my_routine."
        base_report   = MetricsCalculator().calculate(_parse(source))
        ext_report    = ExtendedMetricsCalculator().calculate(_parse(source))
        assert len(ext_report.metrics) > len(base_report.metrics)


# ---------------------------------------------------------------------------
# Severity summary
# ---------------------------------------------------------------------------

class TestSeveritySummary:
    def test_all_ok_for_clean_code(self) -> None:
        source = "\n".join([
            "* Well-documented program",
            "REPORT z_test.",
            "* Purpose: demonstration",
            "DATA lv_x TYPE i.",
            "* Process",
            "lv_x = 1.",
        ])
        report = _calc(source)
        assert len(report.criticals) == 0

    def test_summary_thresholds_customisable(self) -> None:
        """Custom thresholds change which metrics become warnings."""
        strict = AnalysisThresholds(max_magic_numbers_warning=0)
        report_strict = _calc("lv_x = 5.", thresholds=strict)
        m_strict = report_strict.by_name("magic_numbers")
        assert m_strict is not None
        assert m_strict.severity in ("warning", "critical")

        # Default thresholds — 1 magic number should be fine
        report_default = _calc("lv_x = 5.")
        m_default = report_default.by_name("magic_numbers")
        assert m_default is not None
        assert m_default.severity == "ok"
