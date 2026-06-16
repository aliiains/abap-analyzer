"""
tests/test_report.py

Unit tests for :mod:`report`.

Coverage targets
----------------
* TextReportFormatter.format_report returns a non-empty string
* All sections present: header, summary, metrics, recommendations, footer
* Severity markers appear for warning / critical metrics
* format_summary returns a one-liner
* SummaryFormatter.format_summary
* HtmlReportFormatter produces HTML
* BaseReportFormatter.extra_sections hook
* Word-wrap helper
* Unicode vs ASCII symbol mode
* Timestamp inclusion / exclusion
* ReportFormatterProtocol compliance
* Report contains metric labels
* Recommendations omitted when all OK
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from parser import AbapParser, ParseResult
from metrics import (
    AnalysisThresholds,
    Metric,
    MetricsCalculator,
    MetricsReport,
)
from report import (
    BaseReportFormatter,
    HtmlReportFormatter,
    ReportFormatterProtocol,
    SummaryFormatter,
    TextReportFormatter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(source: str) -> ParseResult:
    return AbapParser().parse(source)


def _metrics(source: str, thresholds: AnalysisThresholds | None = None) -> MetricsReport:
    calc = MetricsCalculator(thresholds=thresholds)
    return calc.calculate(_parse(source))


def _make_metrics_with_issues() -> MetricsReport:
    """Return a MetricsReport that includes warning and critical metrics."""
    metrics = [
        Metric(name="loc",        label="Строк кода (LOC)",       value=600,  severity="warning",
               recommendation="Файл слишком большой."),
        Metric(name="max_nesting", label="Глубина вложенности",   value=7,    severity="critical",
               recommendation="Необходим рефакторинг."),
        Metric(name="comment_ratio", label="Доля комментариев",   value=2.0,  severity="warning",
               recommendation="Добавьте комментарии."),
        Metric(name="total_lines", label="Всего строк",           value=800,  severity="ok"),
    ]
    return MetricsReport(metrics=metrics)


def _make_clean_metrics() -> MetricsReport:
    """Return a MetricsReport with all OK metrics."""
    metrics = [
        Metric(name="loc",        label="Строк кода (LOC)",  value=50, severity="ok"),
        Metric(name="total_lines", label="Всего строк",       value=60, severity="ok"),
    ]
    return MetricsReport(metrics=metrics)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_text_formatter_satisfies_protocol(self) -> None:
        fmt = TextReportFormatter()
        assert isinstance(fmt, ReportFormatterProtocol)

    def test_html_formatter_satisfies_protocol(self) -> None:
        fmt = HtmlReportFormatter()
        assert isinstance(fmt, ReportFormatterProtocol)

    def test_format_report_returns_string(self) -> None:
        fmt = TextReportFormatter()
        report = fmt.format_report(_make_clean_metrics())
        assert isinstance(report, str)
        assert len(report) > 0

    def test_format_summary_returns_string(self) -> None:
        fmt = TextReportFormatter()
        summary = fmt.format_summary(_make_clean_metrics())
        assert isinstance(summary, str)


# ---------------------------------------------------------------------------
# TextReportFormatter – structure
# ---------------------------------------------------------------------------

class TestTextReportFormatterStructure:
    def test_header_separator_present(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_clean_metrics(), title="Тест")
        assert "=" * 10 in text  # separator present

    def test_title_in_output(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_clean_metrics(), title="МойОтчёт")
        assert "МойОтчёт" in text

    def test_summary_section_present(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "ИТОГОВАЯ СВОДКА" in text

    def test_metrics_section_present(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "МЕТРИКИ КОДА" in text

    def test_recommendations_section_present(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "РЕКОМЕНДАЦИИ" in text

    def test_footer_present(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "конец отчёта" in text.lower()

    def test_details_section_included_when_parse_result_given(self) -> None:
        fmt = TextReportFormatter()
        pr = _parse("DATA lv_x TYPE i.")
        mr = _metrics("DATA lv_x TYPE i.")
        text = fmt.format_report(mr, parse_result=pr)
        assert "ДЕТАЛИ АНАЛИЗА" in text

    def test_details_section_absent_when_no_parse_result(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_clean_metrics(), parse_result=None)
        assert "ДЕТАЛИ АНАЛИЗА" not in text


# ---------------------------------------------------------------------------
# Severity markers
# ---------------------------------------------------------------------------

class TestSeverityMarkers:
    def test_unicode_warning_marker_present(self) -> None:
        fmt = TextReportFormatter(use_unicode_symbols=True)
        text = fmt.format_report(_make_metrics_with_issues())
        assert "⚠" in text

    def test_unicode_critical_marker_present(self) -> None:
        fmt = TextReportFormatter(use_unicode_symbols=True)
        text = fmt.format_report(_make_metrics_with_issues())
        assert "✖" in text

    def test_unicode_ok_marker_present(self) -> None:
        fmt = TextReportFormatter(use_unicode_symbols=True)
        text = fmt.format_report(_make_clean_metrics())
        assert "✔" in text

    def test_ascii_warning_marker_when_unicode_disabled(self) -> None:
        fmt = TextReportFormatter(use_unicode_symbols=False)
        text = fmt.format_report(_make_metrics_with_issues())
        assert "[WARN]" in text

    def test_ascii_critical_marker_when_unicode_disabled(self) -> None:
        fmt = TextReportFormatter(use_unicode_symbols=False)
        text = fmt.format_report(_make_metrics_with_issues())
        assert "[CRIT]" in text

    def test_ascii_ok_marker_when_unicode_disabled(self) -> None:
        fmt = TextReportFormatter(use_unicode_symbols=False)
        text = fmt.format_report(_make_clean_metrics())
        assert "[OK]" in text


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_recommendations_included_for_issues(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_metrics_with_issues())
        assert "Необходим рефакторинг" in text

    def test_no_issues_message_when_all_ok(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "Замечаний нет" in text

    def test_multiple_recommendations_numbered(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_metrics_with_issues())
        assert "1." in text
        assert "2." in text

    def test_recommendation_text_in_report(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_metrics_with_issues())
        assert "Файл слишком большой" in text


# ---------------------------------------------------------------------------
# Metric labels
# ---------------------------------------------------------------------------

class TestMetricLabels:
    def test_metric_label_in_output(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "Строк кода (LOC)" in text

    def test_metric_value_in_output(self) -> None:
        fmt = TextReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "50" in text  # LOC value

    def test_all_metric_labels_present(self) -> None:
        fmt = TextReportFormatter()
        mr = _make_metrics_with_issues()
        text = fmt.format_report(mr)
        for m in mr.metrics:
            assert m.label in text, f"Label '{m.label}' missing from report"


# ---------------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------------

class TestTimestamp:
    def test_timestamp_present_by_default(self) -> None:
        fmt = TextReportFormatter(include_timestamp=True)
        text = fmt.format_report(_make_clean_metrics())
        # Year 2024/2025/2026 should appear
        import datetime
        year = str(datetime.datetime.now().year)
        assert year in text

    def test_timestamp_absent_when_disabled(self) -> None:
        fmt = TextReportFormatter(include_timestamp=False)
        text = fmt.format_report(_make_clean_metrics())
        import datetime
        year = str(datetime.datetime.now().year)
        # Year string may or may not appear in metric values — just check
        # that "Дата/время:" is not present
        assert "Дата/время:" not in text


# ---------------------------------------------------------------------------
# format_summary
# ---------------------------------------------------------------------------

class TestFormatSummary:
    def test_summary_mentions_criticals(self) -> None:
        fmt = TextReportFormatter()
        mr = _make_metrics_with_issues()
        summary = fmt.format_summary(mr)
        assert "Критических" in summary or "критических" in summary.lower()

    def test_summary_mentions_warnings(self) -> None:
        fmt = TextReportFormatter()
        mr = _make_metrics_with_issues()
        summary = fmt.format_summary(mr)
        assert "Предупреждений" in summary or "предупреждений" in summary.lower()

    def test_summary_ok_message_for_clean_code(self) -> None:
        fmt = TextReportFormatter()
        summary = fmt.format_summary(_make_clean_metrics())
        assert len(summary) > 0

    def test_summary_is_single_line(self) -> None:
        fmt = TextReportFormatter()
        summary = fmt.format_summary(_make_clean_metrics())
        assert "\n" not in summary


# ---------------------------------------------------------------------------
# SummaryFormatter
# ---------------------------------------------------------------------------

class TestSummaryFormatter:
    def test_format_summary_returns_string(self) -> None:
        sf = SummaryFormatter()
        result = sf.format_summary(_make_clean_metrics())
        assert isinstance(result, str)

    def test_summary_contains_loc(self) -> None:
        sf = SummaryFormatter()
        mr = _metrics("DATA lv_x TYPE i.")
        result = sf.format_summary(mr)
        assert "LOC" in result

    def test_summary_contains_nesting(self) -> None:
        sf = SummaryFormatter()
        mr = _metrics("IF a. ENDIF.")
        result = sf.format_summary(mr)
        assert "Вложенность" in result

    def test_summary_contains_complexity(self) -> None:
        sf = SummaryFormatter()
        mr = _metrics("IF a. ENDIF.")
        result = sf.format_summary(mr)
        assert "Сложность" in result

    def test_summary_contains_critical_count(self) -> None:
        sf = SummaryFormatter()
        result = sf.format_summary(_make_metrics_with_issues())
        assert "Критических" in result


# ---------------------------------------------------------------------------
# HtmlReportFormatter
# ---------------------------------------------------------------------------

class TestHtmlReportFormatter:
    def test_format_report_returns_html_string(self) -> None:
        fmt = HtmlReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "<html>" in text
        assert "</html>" in text

    def test_html_contains_metrics(self) -> None:
        fmt = HtmlReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "Строк кода (LOC)" in text

    def test_html_contains_table(self) -> None:
        fmt = HtmlReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "<table>" in text

    def test_html_summary_format(self) -> None:
        fmt = HtmlReportFormatter()
        summary = fmt.format_summary(_make_metrics_with_issues())
        assert isinstance(summary, str)

    def test_html_footer_present(self) -> None:
        fmt = HtmlReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "</html>" in text

    def test_html_recommendations_for_issues(self) -> None:
        fmt = HtmlReportFormatter()
        text = fmt.format_report(_make_metrics_with_issues())
        assert "<ol>" in text or "Рекомендации" in text

    def test_html_no_issues_message(self) -> None:
        fmt = HtmlReportFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "Замечаний нет" in text


# ---------------------------------------------------------------------------
# Word-wrap helper
# ---------------------------------------------------------------------------

class TestWordWrap:
    def test_short_text_not_wrapped(self) -> None:
        result = TextReportFormatter._wrap("Hello world", width=80, indent="  ")
        assert "Hello world" in result

    def test_long_text_wrapped(self) -> None:
        long_text = "word " * 30
        result = TextReportFormatter._wrap(long_text.strip(), width=40, indent="")
        lines = result.splitlines()
        assert len(lines) > 1

    def test_indent_applied(self) -> None:
        result = TextReportFormatter._wrap("Hello world", width=80, indent="   ")
        assert result.startswith("   ")

    def test_empty_text(self) -> None:
        result = TextReportFormatter._wrap("", width=80, indent="")
        assert result == ""

    def test_single_word_longer_than_width(self) -> None:
        """Single long word must not crash — lands on its own line."""
        result = TextReportFormatter._wrap("averylongwordthatexceedswidth", width=10, indent="")
        assert "averylongwordthatexceedswidth" in result


# ---------------------------------------------------------------------------
# Extra sections hook (Open/Closed)
# ---------------------------------------------------------------------------

class TestExtraSectionsHook:
    def test_subclass_can_add_extra_section(self) -> None:
        class MyFormatter(TextReportFormatter):
            def extra_sections(self, report, result):
                return ["\nEXTRA SECTION\nCustom content here."]

        fmt = MyFormatter()
        text = fmt.format_report(_make_clean_metrics())
        assert "EXTRA SECTION" in text
        assert "Custom content here." in text

    def test_base_extra_sections_returns_empty(self) -> None:
        fmt = TextReportFormatter()
        result = fmt.extra_sections(_make_clean_metrics(), None)
        assert result == []


# ---------------------------------------------------------------------------
# Integration: parser → metrics → report pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    SOURCE = "\n".join([
        "* ABAP program with intentional issues",
        "REPORT z_test.",
        "",
        "DATA: gv_count TYPE i.",
        "",
        "FORM run.",
        "  DO 5 TIMES.",           # magic number 5
        "    IF sy-index > 3.",    # magic number 3
        "      IF sy-index > 4.",  # magic number 4, nesting 3
        "        WRITE: / sy-index.",
        "      ENDIF.",
        "    ENDIF.",
        "  ENDDO.",
        "ENDFORM.",
        "",
        "START-OF-SELECTION.",
        "  PERFORM run.",
    ])

    def test_pipeline_produces_report_string(self) -> None:
        pr  = _parse(self.SOURCE)
        mr  = MetricsCalculator().calculate(pr)
        fmt = TextReportFormatter()
        text = fmt.format_report(mr, parse_result=pr)
        assert len(text) > 100

    def test_pipeline_report_contains_loc(self) -> None:
        pr  = _parse(self.SOURCE)
        mr  = MetricsCalculator().calculate(pr)
        fmt = TextReportFormatter()
        text = fmt.format_report(mr, parse_result=pr)
        assert "LOC" in text or "Строк кода" in text

    def test_pipeline_details_contains_keyword_table(self) -> None:
        pr  = _parse(self.SOURCE)
        mr  = MetricsCalculator().calculate(pr)
        fmt = TextReportFormatter()
        text = fmt.format_report(mr, parse_result=pr)
        # At least one ABAP keyword should appear in the keyword table section
        assert "FORM" in text or "DATA" in text or "IF" in text

    def test_pipeline_magic_numbers_in_details(self) -> None:
        pr  = _parse(self.SOURCE)
        mr  = MetricsCalculator().calculate(pr)
        fmt = TextReportFormatter()
        text = fmt.format_report(mr, parse_result=pr)
        assert "Магические числа" in text

    def test_pipeline_recommendations_for_nesting(self) -> None:
        # Deep nesting threshold set very low to guarantee recommendation
        th = AnalysisThresholds(max_nesting_warning=1)
        pr  = _parse(self.SOURCE)
        mr  = MetricsCalculator(thresholds=th).calculate(pr)
        fmt = TextReportFormatter()
        text = fmt.format_report(mr, parse_result=pr)
        assert "РЕКОМЕНДАЦИИ" in text

    def test_save_to_string_unicode(self) -> None:
        """Report must be encodable as UTF-8 (for file saving)."""
        pr   = _parse(self.SOURCE)
        mr   = MetricsCalculator().calculate(pr)
        fmt  = TextReportFormatter()
        text = fmt.format_report(mr, parse_result=pr)
        encoded = text.encode("utf-8")
        assert len(encoded) > 0
