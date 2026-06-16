"""
metrics.py — Metric calculation layer.

Transforms raw :class:`~parser.ParseResult` data into named, typed
metric objects with human-readable labels and optional recommendations.

Design decisions
----------------
* ``Metric`` is a frozen dataclass – immutable value object.
* ``MetricCalculatorProtocol`` lets callers depend on an abstraction
  (Dependency Inversion Principle).
* ``BaseMetricCalculator`` provides the extension hook
  :meth:`extra_metrics` (Open/Closed Principle).
* Each metric type is its own tiny class (Single Responsibility).
* New metric families are added by implementing
  ``MetricCalculatorProtocol`` without touching existing code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Protocol, runtime_checkable

from parser import ParseResult


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Metric:
    """A single computed metric.

    Attributes
    ----------
    name:
        Short machine-friendly name (e.g. ``"loc"``).
    label:
        Human-readable display label.
    value:
        Numeric value of the metric.
    unit:
        Optional unit string (e.g. ``"lines"``, ``"%"``).
    description:
        Longer description of what is measured.
    recommendation:
        Optional actionable recommendation text.  ``None`` means the
        metric is within acceptable bounds.
    severity:
        ``"ok"``, ``"warning"``, or ``"critical"``.
    """

    name: str
    label: str
    value: float
    unit: str = ""
    description: str = ""
    recommendation: Optional[str] = None
    severity: str = "ok"


@dataclass(frozen=True)
class MetricsReport:
    """Collection of all computed metrics for one analysis run."""

    metrics: List[Metric]

    @property
    def warnings(self) -> List[Metric]:
        """Metrics with severity ``'warning'``."""
        return [m for m in self.metrics if m.severity == "warning"]

    @property
    def criticals(self) -> List[Metric]:
        """Metrics with severity ``'critical'``."""
        return [m for m in self.metrics if m.severity == "critical"]

    @property
    def ok_metrics(self) -> List[Metric]:
        """Metrics with severity ``'ok'``."""
        return [m for m in self.metrics if m.severity == "ok"]

    def by_name(self, name: str) -> Optional[Metric]:
        """Return first metric matching *name*, or ``None``."""
        for m in self.metrics:
            if m.name == name:
                return m
        return None


# ---------------------------------------------------------------------------
# Thresholds (configurable, centralised)
# ---------------------------------------------------------------------------

@dataclass
class AnalysisThresholds:
    """Thresholds used to classify metric severity.

    All attributes have sensible ABAP-specific defaults and can be
    overridden at construction time.
    """

    max_nesting_warning: int = 3
    """Nesting depth that triggers a *warning*."""

    max_nesting_critical: int = 5
    """Nesting depth that triggers a *critical* flag."""

    min_comment_ratio_warning: float = 0.10
    """Comment-to-code ratio below which a warning is raised."""

    min_comment_ratio_critical: float = 0.05
    """Comment-to-code ratio below which a critical is raised."""

    max_long_lines_warning: int = 5
    """Number of long lines that triggers a warning."""

    max_long_lines_critical: int = 15
    """Number of long lines that triggers a critical."""

    max_magic_numbers_warning: int = 3
    """Magic-number occurrences that trigger a warning."""

    max_magic_numbers_critical: int = 10
    """Magic-number occurrences that trigger a critical."""

    max_forms_warning: int = 20
    """Number of FORM subroutines that triggers a warning."""

    max_select_warning: int = 5
    """SELECT statements that trigger a warning."""

    max_select_critical: int = 15
    """SELECT statements that trigger a critical."""

    max_loc_warning: int = 500
    """Lines of code (LOC) that trigger a warning."""

    max_loc_critical: int = 1000
    """Lines of code that trigger a critical."""

    max_call_function_warning: int = 10
    """CALL FUNCTION statements that trigger a warning."""

    max_todo_warning: int = 5
    """TODO comment markers that trigger a warning."""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class MetricCalculatorProtocol(Protocol):
    """Structural protocol for metric calculators."""

    def calculate(self, result: ParseResult) -> MetricsReport:
        """Compute all metrics from *result* and return a report."""
        ...


# ---------------------------------------------------------------------------
# Abstract base (Open/Closed extension hook)
# ---------------------------------------------------------------------------

class BaseMetricCalculator(ABC):
    """Abstract base calculator with the Open/Closed extension hook.

    Subclasses that want additional metrics override
    :meth:`extra_metrics` – they never touch the core computation.
    """

    def calculate(self, result: ParseResult) -> MetricsReport:
        """Run all metric families and return a :class:`MetricsReport`."""
        metrics: List[Metric] = []
        metrics.extend(self._size_metrics(result))
        metrics.extend(self._complexity_metrics(result))
        metrics.extend(self._quality_metrics(result))
        metrics.extend(self._db_metrics(result))
        metrics.extend(self._structure_metrics(result))
        metrics.extend(self._keyword_metrics(result))
        metrics.extend(self.extra_metrics(result))
        return MetricsReport(metrics=metrics)

    @abstractmethod
    def _thresholds(self) -> AnalysisThresholds:
        """Return thresholds used by all metric families."""

    def extra_metrics(self, result: ParseResult) -> List[Metric]:
        """Extension hook for subclasses – returns [] by default."""
        return []

    # ------------------------------------------------------------------
    # Metric families
    # ------------------------------------------------------------------

    def _size_metrics(self, result: ParseResult) -> List[Metric]:
        """Lines-of-code family."""
        th = self._thresholds()
        metrics: List[Metric] = []

        # Total lines
        metrics.append(Metric(
            name="total_lines",
            label="Всего строк",
            value=result.total_lines,
            unit="строк",
            description="Общее количество строк исходного кода.",
        ))

        # LOC (code only)
        loc = result.code_lines
        loc_severity = "ok"
        loc_rec: Optional[str] = None
        if loc >= th.max_loc_critical:
            loc_severity = "critical"
            loc_rec = (
                f"Файл содержит {loc} строк кода — критически большой. "
                "Рекомендуется разбить на несколько модулей."
            )
        elif loc >= th.max_loc_warning:
            loc_severity = "warning"
            loc_rec = (
                f"Файл содержит {loc} строк кода. "
                "Рассмотрите возможность декомпозиции."
            )
        metrics.append(Metric(
            name="loc",
            label="Строк кода (LOC)",
            value=loc,
            unit="строк",
            description="Строки, содержащие исполняемый код (не пустые и не комментарии).",
            recommendation=loc_rec,
            severity=loc_severity,
        ))

        # Comment lines
        metrics.append(Metric(
            name="comment_lines",
            label="Строк комментариев",
            value=result.comment_lines,
            unit="строк",
            description="Строки, начинающиеся с '*' или содержащие только комментарий.",
        ))

        # Blank lines
        metrics.append(Metric(
            name="blank_lines",
            label="Пустых строк",
            value=result.blank_lines,
            unit="строк",
            description="Строки, не содержащие никакого текста.",
        ))

        return metrics

    def _complexity_metrics(self, result: ParseResult) -> List[Metric]:
        """Nesting / cyclomatic-complexity family."""
        th = self._thresholds()
        metrics: List[Metric] = []

        # Max nesting
        nesting = result.max_nesting
        nest_severity = "ok"
        nest_rec: Optional[str] = None
        if nesting >= th.max_nesting_critical:
            nest_severity = "critical"
            nest_rec = (
                f"Максимальная глубина вложенности {nesting} — критическая. "
                "Необходим немедленный рефакторинг: выделите логические блоки "
                "в отдельные FORM/METHOD."
            )
        elif nesting >= th.max_nesting_warning:
            nest_severity = "warning"
            nest_rec = (
                f"Глубина вложенности {nesting} превышает рекомендуемое значение {th.max_nesting_warning}. "
                "Рекомендуется рефакторинг."
            )
        metrics.append(Metric(
            name="max_nesting",
            label="Максимальная глубина вложенности",
            value=nesting,
            unit="уровней",
            description=(
                "Максимальное количество вложенных блоков "
                "(IF, LOOP, DO, WHILE, CASE и т.д.)."
            ),
            recommendation=nest_rec,
            severity=nest_severity,
        ))

        # Average nesting
        avg_nesting = (
            sum(result.nesting_history) / len(result.nesting_history)
            if result.nesting_history
            else 0.0
        )
        metrics.append(Metric(
            name="avg_nesting",
            label="Средняя глубина вложенности",
            value=round(avg_nesting, 2),
            unit="уровней",
            description="Среднее значение глубины вложенности по всем строкам кода.",
        ))

        # Approximated cyclomatic complexity
        # CC ≈ decision points + 1
        decision_keywords = {"IF", "ELSEIF", "WHEN", "LOOP", "DO", "WHILE"}
        decision_count = sum(
            result.keyword_counts.get(kw, 0) for kw in decision_keywords
        )
        cc = decision_count + 1
        cc_severity = "ok"
        cc_rec: Optional[str] = None
        if cc > 20:
            cc_severity = "critical"
            cc_rec = (
                f"Цикломатическая сложность ≈ {cc} — очень высокая. "
                "Код трудно тестировать и сопровождать."
            )
        elif cc > 10:
            cc_severity = "warning"
            cc_rec = (
                f"Цикломатическая сложность ≈ {cc}. "
                "Рекомендуется упростить логику."
            )
        metrics.append(Metric(
            name="cyclomatic_complexity",
            label="Цикломатическая сложность (оценка)",
            value=cc,
            description=(
                "Приближённая цикломатическая сложность: "
                "число точек ветвления + 1."
            ),
            recommendation=cc_rec,
            severity=cc_severity,
        ))

        return metrics

    def _quality_metrics(self, result: ParseResult) -> List[Metric]:
        """Code-quality family."""
        th = self._thresholds()
        metrics: List[Metric] = []

        # Comment ratio
        total_meaningful = result.code_lines + result.comment_lines
        ratio = (
            result.comment_lines / total_meaningful
            if total_meaningful > 0
            else 0.0
        )
        ratio_pct = round(ratio * 100, 1)
        ratio_severity = "ok"
        ratio_rec: Optional[str] = None
        if ratio < th.min_comment_ratio_critical:
            ratio_severity = "critical"
            ratio_rec = (
                f"Доля комментариев {ratio_pct}% — критически низкая. "
                "Добавьте документирующие комментарии к блокам и процедурам."
            )
        elif ratio < th.min_comment_ratio_warning:
            ratio_severity = "warning"
            ratio_rec = (
                f"Доля комментариев {ratio_pct}% — ниже рекомендуемых 10%. "
                "Недостаточно документирования."
            )
        metrics.append(Metric(
            name="comment_ratio",
            label="Доля комментариев",
            value=ratio_pct,
            unit="%",
            description="Процент комментариев от суммы строк кода и комментариев.",
            recommendation=ratio_rec,
            severity=ratio_severity,
        ))

        # Long lines
        long_cnt = len(result.long_line_numbers)
        long_severity = "ok"
        long_rec: Optional[str] = None
        if long_cnt >= th.max_long_lines_critical:
            long_severity = "critical"
            long_rec = (
                f"{long_cnt} строк превышают 120 символов. "
                "Разбейте длинные выражения на несколько строк."
            )
        elif long_cnt >= th.max_long_lines_warning:
            long_severity = "warning"
            long_rec = (
                f"{long_cnt} строк превышают 120 символов. "
                "Рекомендуется разбить для улучшения читаемости."
            )
        metrics.append(Metric(
            name="long_lines",
            label="Строк > 120 символов",
            value=long_cnt,
            unit="строк",
            description="Строки, длина которых превышает 120 символов.",
            recommendation=long_rec,
            severity=long_severity,
        ))

        # Magic numbers
        magic_cnt = len(result.all_magic_numbers)
        magic_severity = "ok"
        magic_rec: Optional[str] = None
        if magic_cnt >= th.max_magic_numbers_critical:
            magic_severity = "critical"
            magic_rec = (
                f"Обнаружено {magic_cnt} магических чисел. "
                "Замените на именованные константы (CONSTANTS)."
            )
        elif magic_cnt >= th.max_magic_numbers_warning:
            magic_severity = "warning"
            magic_rec = (
                f"Обнаружено {magic_cnt} магических чисел. "
                "Рекомендуется использовать CONSTANTS."
            )
        metrics.append(Metric(
            name="magic_numbers",
            label="Магических чисел",
            value=magic_cnt,
            description=(
                "Числовые литералы (кроме 0 и 1), "
                "которые следует заменить именованными константами."
            ),
            recommendation=magic_rec,
            severity=magic_severity,
        ))

        # TODO / FIXME
        todo_total = result.todo_count + result.fixme_count
        todo_severity = "ok"
        todo_rec: Optional[str] = None
        if todo_total >= th.max_todo_warning:
            todo_severity = "warning"
            todo_rec = (
                f"Найдено {todo_total} меток TODO/FIXME. "
                "Устраните технический долг."
            )
        metrics.append(Metric(
            name="todo_fixme",
            label="Метки TODO / FIXME",
            value=todo_total,
            description="Количество незавершённых замечаний в комментариях.",
            recommendation=todo_rec,
            severity=todo_severity,
        ))

        # Chain statements
        metrics.append(Metric(
            name="chain_statements",
            label="Цепочечных операторов (':')",
            value=result.chain_statement_count,
            description="Строки, использующие синтаксис цепочки ABAP ':'.",
        ))

        return metrics

    def _db_metrics(self, result: ParseResult) -> List[Metric]:
        """Database-access family."""
        th = self._thresholds()
        metrics: List[Metric] = []

        # SELECT count
        sel = result.select_count
        sel_severity = "ok"
        sel_rec: Optional[str] = None
        if sel >= th.max_select_critical:
            sel_severity = "critical"
            sel_rec = (
                f"{sel} операторов SELECT — критически много. "
                "Объедините запросы или используйте внутренние таблицы."
            )
        elif sel >= th.max_select_warning:
            sel_severity = "warning"
            sel_rec = (
                f"{sel} операторов SELECT. "
                "Рассмотрите буферизацию и оптимизацию запросов."
            )
        metrics.append(Metric(
            name="select_count",
            label="Операторов SELECT",
            value=sel,
            description="Количество операторов SELECT (обращений к БД).",
            recommendation=sel_rec,
            severity=sel_severity,
        ))

        # CALL FUNCTION
        cf = result.call_function_count
        cf_severity = "ok"
        cf_rec: Optional[str] = None
        if cf >= th.max_call_function_warning:
            cf_severity = "warning"
            cf_rec = (
                f"{cf} вызовов CALL FUNCTION. "
                "Рассмотрите использование методов классов."
            )
        metrics.append(Metric(
            name="call_function_count",
            label="Вызовов CALL FUNCTION",
            value=cf,
            description="Количество вызовов RFC / function-module.",
            recommendation=cf_rec,
            severity=cf_severity,
        ))

        # PERFORM
        metrics.append(Metric(
            name="perform_count",
            label="Вызовов PERFORM",
            value=result.perform_count,
            description="Количество вызовов FORM-подпрограмм через PERFORM.",
        ))

        return metrics

    def _structure_metrics(self, result: ParseResult) -> List[Metric]:
        """Program-structure family."""
        th = self._thresholds()
        metrics: List[Metric] = []

        # FORM count
        form_cnt = result.form_count
        form_severity = "ok"
        form_rec: Optional[str] = None
        if form_cnt >= th.max_forms_warning:
            form_severity = "warning"
            form_rec = (
                f"Определено {form_cnt} FORM-подпрограмм. "
                "Рассмотрите переход к классам (OOP)."
            )
        metrics.append(Metric(
            name="form_count",
            label="Подпрограмм FORM",
            value=form_cnt,
            description="Количество FORM ... ENDFORM определений.",
            recommendation=form_rec,
            severity=form_severity,
        ))

        metrics.append(Metric(
            name="method_count",
            label="Методов (METHOD)",
            value=result.method_count,
            description="Количество METHOD ... ENDMETHOD определений.",
        ))

        metrics.append(Metric(
            name="class_count",
            label="Классов (CLASS DEFINITION)",
            value=result.class_count,
            description="Количество CLASS ... DEFINITION блоков.",
        ))

        metrics.append(Metric(
            name="function_count",
            label="Function Modules (FUNCTION)",
            value=result.function_count,
            description="Количество FUNCTION ... ENDFUNCTION блоков.",
        ))

        # Error handling
        if result.raise_count > 0 and result.catch_count == 0:
            eh_rec: Optional[str] = (
                "Обнаружены RAISE без CATCH. "
                "Добавьте обработку исключений через TRY/CATCH."
            )
            eh_sev = "warning"
        else:
            eh_rec = None
            eh_sev = "ok"
        metrics.append(Metric(
            name="raise_count",
            label="Исключений RAISE",
            value=result.raise_count,
            description="Количество операторов RAISE.",
            recommendation=eh_rec,
            severity=eh_sev,
        ))
        metrics.append(Metric(
            name="catch_count",
            label="Блоков CATCH",
            value=result.catch_count,
            description="Количество блоков CATCH (обработка исключений).",
        ))

        return metrics

    def _keyword_metrics(self, result: ParseResult) -> List[Metric]:
        """Top-N keyword-frequency metrics."""
        metrics: List[Metric] = []
        top_keywords = sorted(
            result.keyword_counts.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )[:10]
        for kw, cnt in top_keywords:
            metrics.append(Metric(
                name=f"keyword_{kw.lower()}",
                label=f"Ключевое слово: {kw}",
                value=cnt,
                unit="раз",
                description=f"Количество вхождений ключевого слова {kw}.",
            ))
        return metrics


# ---------------------------------------------------------------------------
# Default concrete implementation
# ---------------------------------------------------------------------------

class MetricsCalculator(BaseMetricCalculator):
    """Default metric calculator.

    Parameters
    ----------
    thresholds:
        Optional custom thresholds. Defaults to :class:`AnalysisThresholds`.
    """

    def __init__(
        self, thresholds: Optional[AnalysisThresholds] = None
    ) -> None:
        self._th = thresholds or AnalysisThresholds()

    def _thresholds(self) -> AnalysisThresholds:
        return self._th


# ---------------------------------------------------------------------------
# Extended calculator example (Open/Closed in action)
# ---------------------------------------------------------------------------

class ExtendedMetricsCalculator(MetricsCalculator):
    """Adds module-coupling and data-definition density metrics.

    Demonstrates extending the calculator without modifying base code.
    """

    def extra_metrics(self, result: ParseResult) -> List[Metric]:
        metrics: List[Metric] = []

        # Data declaration density
        data_kw = result.keyword_counts.get("DATA", 0)
        data_density = (
            round(data_kw / result.code_lines * 100, 1)
            if result.code_lines > 0
            else 0.0
        )
        metrics.append(Metric(
            name="data_declaration_density",
            label="Плотность объявлений DATA",
            value=data_density,
            unit="%",
            description=(
                "Доля строк с объявлением DATA от общего числа строк кода. "
                "Высокое значение может указывать на избыточное использование глобальных данных."
            ),
        ))

        # Modularisation score (ratio of procedure calls vs code lines)
        calls = result.perform_count + result.call_function_count + result.call_method_count
        mod_score = round(calls / result.code_lines * 100, 1) if result.code_lines > 0 else 0.0
        mod_rec: Optional[str] = None
        mod_sev = "ok"
        if mod_score < 5 and result.code_lines > 100:
            mod_sev = "warning"
            mod_rec = (
                f"Коэффициент модульности {mod_score}% — низкий. "
                "Разбейте код на подпрограммы или методы."
            )
        metrics.append(Metric(
            name="modularisation_score",
            label="Коэффициент модульности",
            value=mod_score,
            unit="%",
            description=(
                "Отношение вызовов процедур (PERFORM, CALL FUNCTION, CALL METHOD) "
                "к общему числу строк кода."
            ),
            recommendation=mod_rec,
            severity=mod_sev,
        ))

        return metrics
