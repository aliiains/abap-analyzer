"""
report.py — Report formatting layer.

Transforms a :class:`~metrics.MetricsReport` (and optionally the raw
:class:`~parser.ParseResult`) into human-readable text for display in
the GUI and for saving to disk.

Design notes
------------
* ``ReportFormatterProtocol`` – abstraction for callers
  (Dependency Inversion Principle).
* ``BaseReportFormatter`` – extension hook via :meth:`extra_sections`
  (Open/Closed Principle).
* ``TextReportFormatter`` – plain-text / UTF-8 implementation.
* ``SummaryFormatter`` – lightweight short summary for status bars.
* Each method formats exactly one section (Single Responsibility).
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, runtime_checkable

from metrics import Metric, MetricsReport
from parser import ParseResult


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEPARATOR_WIDE = "=" * 70
_SEPARATOR_THIN = "-" * 70
_SEVERITY_LABELS = {
    "ok": "✔",
    "warning": "⚠",
    "critical": "✖",
}
_SEVERITY_LABELS_ASCII = {
    "ok": "[OK]",
    "warning": "[WARN]",
    "critical": "[CRIT]",
}


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ReportFormatterProtocol(Protocol):
    """Structural protocol for report formatters."""

    def format_report(
        self,
        metrics_report: MetricsReport,
        parse_result: Optional[ParseResult] = None,
        title: str = "Отчёт анализа ABAP",
    ) -> str:
        """Return the full report as a single string."""
        ...

    def format_summary(self, metrics_report: MetricsReport) -> str:
        """Return a one-liner status summary."""
        ...


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseReportFormatter(ABC):
    """Abstract base formatter with the Open/Closed extension hook.

    Concrete subclasses override :meth:`extra_sections` to append
    custom sections without modifying the base algorithm.
    """

    def format_report(
        self,
        metrics_report: MetricsReport,
        parse_result: Optional[ParseResult] = None,
        title: str = "Отчёт анализа ABAP",
    ) -> str:
        """Compose and return the full report."""
        parts: List[str] = [
            self._header(title),
            self._summary_section(metrics_report),
            self._metrics_section(metrics_report),
            self._recommendations_section(metrics_report),
        ]
        if parse_result is not None:
            parts.append(self._details_section(parse_result))
        parts.extend(self.extra_sections(metrics_report, parse_result))
        parts.append(self._footer())
        return "\n".join(parts)

    @abstractmethod
    def _header(self, title: str) -> str:
        """Format report header."""

    @abstractmethod
    def _summary_section(self, report: MetricsReport) -> str:
        """Format high-level summary."""

    @abstractmethod
    def _metrics_section(self, report: MetricsReport) -> str:
        """Format all metrics."""

    @abstractmethod
    def _recommendations_section(self, report: MetricsReport) -> str:
        """Format actionable recommendations."""

    @abstractmethod
    def _details_section(self, result: ParseResult) -> str:
        """Format low-level parse details."""

    @abstractmethod
    def _footer(self) -> str:
        """Format report footer."""

    def format_summary(self, metrics_report: MetricsReport) -> str:
        """One-liner status string."""
        crits = len(metrics_report.criticals)
        warns = len(metrics_report.warnings)
        if crits:
            return f"Критических: {crits} | Предупреждений: {warns}"
        if warns:
            return f"Предупреждений: {warns} — проверьте рекомендации"
        return "Код в норме — критических замечаний нет"

    def extra_sections(
        self,
        report: MetricsReport,
        result: Optional[ParseResult],
    ) -> List[str]:
        """Extension hook – returns [] by default."""
        return []


# ---------------------------------------------------------------------------
# Plain-text formatter
# ---------------------------------------------------------------------------

class TextReportFormatter(BaseReportFormatter):
    """Produces UTF-8 plain-text reports.

    Parameters
    ----------
    use_unicode_symbols:
        When ``True``, uses ✔ / ⚠ / ✖ severity markers.
        When ``False``, uses ASCII alternatives [OK] / [WARN] / [CRIT].
    include_timestamp:
        Embed timestamp in header/footer.
    """

    def __init__(
        self,
        use_unicode_symbols: bool = True,
        include_timestamp: bool = True,
    ) -> None:
        self._unicode = use_unicode_symbols
        self._timestamp = include_timestamp

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sev(self, severity: str) -> str:
        if self._unicode:
            return _SEVERITY_LABELS.get(severity, "?")
        return _SEVERITY_LABELS_ASCII.get(severity, "?")

    def _now(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # Section implementations
    # ------------------------------------------------------------------

    def _header(self, title: str) -> str:
        lines: List[str] = [
            _SEPARATOR_WIDE,
            f"  {title}",
        ]
        if self._timestamp:
            lines.append(f"  Дата/время: {self._now()}")
        lines.append(_SEPARATOR_WIDE)
        return "\n".join(lines)

    def _summary_section(self, report: MetricsReport) -> str:
        crits = len(report.criticals)
        warns = len(report.warnings)
        oks = len(report.ok_metrics)
        lines: List[str] = [
            "",
            "ИТОГОВАЯ СВОДКА",
            _SEPARATOR_THIN,
            f"  {self._sev('ok')}  В норме:          {oks}",
            f"  {self._sev('warning')}  Предупреждения:   {warns}",
            f"  {self._sev('critical')}  Критические:      {crits}",
        ]
        if crits == 0 and warns == 0:
            lines.append("")
            lines.append("  Код соответствует базовым стандартам качества.")
        elif crits > 0:
            lines.append("")
            lines.append(
                f"  ВНИМАНИЕ: Обнаружено {crits} критических проблем. "
                "Требуется рефакторинг."
            )
        return "\n".join(lines)

    def _metrics_section(self, report: MetricsReport) -> str:
        lines: List[str] = [
            "",
            "МЕТРИКИ КОДА",
            _SEPARATOR_THIN,
        ]
        for metric in report.metrics:
            sev_mark = self._sev(metric.severity)
            value_str = (
                f"{metric.value} {metric.unit}".strip()
            )
            line = f"  {sev_mark}  {metric.label:<45} {value_str}"
            lines.append(line)
        return "\n".join(lines)

    def _recommendations_section(self, report: MetricsReport) -> str:
        issues = report.criticals + report.warnings
        if not issues:
            return (
                "\n"
                "РЕКОМЕНДАЦИИ\n"
                + _SEPARATOR_THIN + "\n"
                "  Замечаний нет. Отличная работа!"
            )

        lines: List[str] = [
            "",
            "РЕКОМЕНДАЦИИ",
            _SEPARATOR_THIN,
        ]
        for i, metric in enumerate(issues, start=1):
            sev_mark = self._sev(metric.severity)
            lines.append(f"  {i}. {sev_mark} [{metric.label}]")
            if metric.recommendation:
                # Wrap recommendation at ~65 chars
                wrapped = self._wrap(metric.recommendation, 65, indent="     ")
                lines.append(wrapped)
            lines.append("")
        return "\n".join(lines)

    def _details_section(self, result: ParseResult) -> str:
        lines: List[str] = [
            "ДЕТАЛИ АНАЛИЗА",
            _SEPARATOR_THIN,
        ]

        # Keyword counts table
        if result.keyword_counts:
            lines.append("  Частота ключевых слов:")
            sorted_kw = sorted(
                result.keyword_counts.items(),
                key=lambda kv: kv[1],
                reverse=True,
            )
            for kw, cnt in sorted_kw[:20]:
                lines.append(f"    {kw:<30} {cnt:>5}")

        # Long lines
        if result.long_line_numbers:
            lines.append("")
            lines.append("  Строки > 120 символов:")
            for lineno in result.long_line_numbers[:20]:
                lines.append(f"    Строка {lineno}")
            if len(result.long_line_numbers) > 20:
                lines.append(
                    f"    … и ещё {len(result.long_line_numbers) - 20}"
                )

        # Magic numbers
        if result.all_magic_numbers:
            lines.append("")
            preview = ", ".join(result.all_magic_numbers[:15])
            if len(result.all_magic_numbers) > 15:
                preview += f" … +{len(result.all_magic_numbers) - 15}"
            lines.append(f"  Магические числа: {preview}")

        # Nesting distribution
        if result.nesting_history:
            from collections import Counter
            dist = Counter(result.nesting_history)
            lines.append("")
            lines.append("  Распределение уровней вложенности:")
            for depth in sorted(dist):
                bar = "█" * min(dist[depth], 40)
                lines.append(f"    {depth:>2}  {bar} ({dist[depth]})")

        lines.append(_SEPARATOR_THIN)
        return "\n".join(lines)

    def _footer(self) -> str:
        lines: List[str] = [
            _SEPARATOR_WIDE,
            "  ABAP Code Analyser — конец отчёта",
        ]
        if self._timestamp:
            lines.append(f"  Сформировано: {self._now()}")
        lines.append(_SEPARATOR_WIDE)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap(text: str, width: int, indent: str = "") -> str:
        """Simple word-wrap that respects *width* and prepends *indent*."""
        words = text.split()
        current_line: List[str] = []
        result_lines: List[str] = []
        current_len = len(indent)

        for word in words:
            if current_len + len(word) + 1 > width and current_line:
                result_lines.append(indent + " ".join(current_line))
                current_line = [word]
                current_len = len(indent) + len(word)
            else:
                current_line.append(word)
                current_len += len(word) + 1

        if current_line:
            result_lines.append(indent + " ".join(current_line))

        return "\n".join(result_lines)


# ---------------------------------------------------------------------------
# HTML formatter (Open/Closed — extends without modifying TextReportFormatter)
# ---------------------------------------------------------------------------

class HtmlReportFormatter(BaseReportFormatter):
    """Minimal HTML report formatter.

    Produces a standalone HTML snippet that can be embedded in a
    webview or saved as an ``.html`` file.
    """

    _CSS = """
    body { font-family: Consolas, monospace; background: #1e1e2e; color: #cdd6f4; padding: 2em; }
    h1   { color: #89b4fa; }
    h2   { color: #89dceb; border-bottom: 1px solid #45475a; }
    table { border-collapse: collapse; width: 100%; }
    th, td { padding: 4px 10px; text-align: left; }
    tr:nth-child(even) { background: #313244; }
    .ok   { color: #a6e3a1; }
    .warn { color: #f9e2af; }
    .crit { color: #f38ba8; }
    .rec  { margin: 4px 0 4px 20px; color: #fab387; }
    """

    def _header(self, title: str) -> str:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"<html><head><style>{self._CSS}</style></head><body>"
            f"<h1>{title}</h1><p>Дата/время: {ts}</p>"
        )

    def _summary_section(self, report: MetricsReport) -> str:
        crits = len(report.criticals)
        warns = len(report.warnings)
        oks = len(report.ok_metrics)
        return (
            "<h2>Итоговая сводка</h2>"
            f"<p class='ok'>В норме: {oks}</p>"
            f"<p class='warn'>Предупреждения: {warns}</p>"
            f"<p class='crit'>Критические: {crits}</p>"
        )

    def _metrics_section(self, report: MetricsReport) -> str:
        rows: List[str] = ["<h2>Метрики</h2><table><tr><th>Метрика</th><th>Значение</th><th>Статус</th></tr>"]
        for m in report.metrics:
            css = {"ok": "ok", "warning": "warn", "critical": "crit"}.get(m.severity, "ok")
            rows.append(
                f"<tr class='{css}'>"
                f"<td>{m.label}</td>"
                f"<td>{m.value} {m.unit}</td>"
                f"<td>{m.severity.upper()}</td>"
                "</tr>"
            )
        rows.append("</table>")
        return "\n".join(rows)

    def _recommendations_section(self, report: MetricsReport) -> str:
        issues = report.criticals + report.warnings
        if not issues:
            return "<h2>Рекомендации</h2><p class='ok'>Замечаний нет.</p>"
        parts = ["<h2>Рекомендации</h2><ol>"]
        for m in issues:
            css = "crit" if m.severity == "critical" else "warn"
            parts.append(f"<li class='{css}'><strong>{m.label}</strong>")
            if m.recommendation:
                parts.append(f"<p class='rec'>{m.recommendation}</p>")
            parts.append("</li>")
        parts.append("</ol>")
        return "\n".join(parts)

    def _details_section(self, result: ParseResult) -> str:
        lines = ["<h2>Детали анализа</h2>"]
        if result.long_line_numbers:
            lines.append(
                f"<p>Строки &gt; 120 символов: "
                + ", ".join(str(n) for n in result.long_line_numbers[:20])
                + "</p>"
            )
        return "\n".join(lines)

    def _footer(self) -> str:
        return "<hr/><p>ABAP Code Analyser — конец отчёта</p></body></html>"

    def format_summary(self, report: MetricsReport) -> str:
        crits = len(report.criticals)
        warns = len(report.warnings)
        if crits:
            return f"Критических: {crits}, предупреждений: {warns}"
        if warns:
            return f"Предупреждений: {warns}"
        return "Всё в норме"


# ---------------------------------------------------------------------------
# Summary-only formatter (lightweight)
# ---------------------------------------------------------------------------

class SummaryFormatter:
    """Produces only a compact multi-line summary string.

    Useful for status bars and notification areas where a full report
    is too verbose.

    This class intentionally does NOT extend ``BaseReportFormatter``
    because it has a different, simpler interface.
    """

    def format_summary(self, report: MetricsReport) -> str:
        """Return a compact multi-line summary."""
        loc_m = report.by_name("loc")
        nesting_m = report.by_name("max_nesting")
        cc_m = report.by_name("cyclomatic_complexity")
        crits = len(report.criticals)
        warns = len(report.warnings)

        parts: List[str] = []
        if loc_m:
            parts.append(f"LOC: {int(loc_m.value)}")
        if nesting_m:
            parts.append(f"Вложенность: {int(nesting_m.value)}")
        if cc_m:
            parts.append(f"Сложность: {int(cc_m.value)}")
        parts.append(f"Критических: {crits} | Предупреждений: {warns}")
        return " | ".join(parts)
