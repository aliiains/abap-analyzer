"""
parser.py — ABAP source code parser.

Responsible SOLELY for tokenising and walking ABAP source lines to
produce raw parse data (counts, lists, flags).  No metric calculations
or report logic belong here (Single Responsibility Principle).

Public API
----------
AbapParserProtocol  – structural Protocol so callers can depend on an
                      abstraction rather than the concrete class
                      (Dependency Inversion Principle).
AbapParser          – concrete implementation; can be subclassed or
                      replaced by any class that satisfies the Protocol.
ParseResult         – plain data-class that carries all raw parse data.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Sequence, runtime_checkable


# ---------------------------------------------------------------------------
# Data-classes
# ---------------------------------------------------------------------------

@dataclass
class LineInfo:
    """Metadata for a single source line."""

    number: int
    """1-based line number."""

    raw: str
    """Original text including leading / trailing whitespace."""

    stripped: str
    """Line with leading and trailing whitespace removed."""

    is_blank: bool = False
    is_comment: bool = False
    is_code: bool = False
    indent_level: int = 0
    """Number of leading spaces / 2 (rough indent depth)."""

    tokens: List[str] = field(default_factory=list)
    """Upper-cased ABAP keyword tokens found on the line."""

    has_long_line: bool = False
    """True when len(raw) > 120."""

    magic_numbers: List[str] = field(default_factory=list)
    """Numeric literals that are not 0 or 1."""


@dataclass
class ParseResult:
    """Aggregated result produced by :class:`AbapParser`."""

    # raw line objects
    lines: List[LineInfo] = field(default_factory=list)

    # aggregate counters
    total_lines: int = 0
    blank_lines: int = 0
    comment_lines: int = 0
    code_lines: int = 0

    # keyword / operator counts  {keyword_upper: count}
    keyword_counts: dict = field(default_factory=dict)

    # nesting tracking
    nesting_history: List[int] = field(default_factory=list)
    """Nesting depth at each code line."""

    max_nesting: int = 0

    # structure counts
    form_count: int = 0
    """Number of FORM … procedures found."""

    method_count: int = 0
    """Number of METHOD … definitions found."""

    class_count: int = 0
    """Number of CLASS … DEFINITION blocks found."""

    function_count: int = 0
    """Number of FUNCTION … blocks found."""

    # magic numbers (raw string values)
    all_magic_numbers: List[str] = field(default_factory=list)

    # long lines (1-based line numbers)
    long_line_numbers: List[int] = field(default_factory=list)

    # chains / concatenations
    chain_statement_count: int = 0
    """Lines containing the ABAP chain operator ':'."""

    # select statements
    select_count: int = 0

    # perform / call counts
    perform_count: int = 0
    call_function_count: int = 0
    call_method_count: int = 0

    # error handling
    catch_count: int = 0
    raise_count: int = 0

    # TODO / FIXME markers in comments
    todo_count: int = 0
    fixme_count: int = 0


# ---------------------------------------------------------------------------
# ABAP keyword sets
# ---------------------------------------------------------------------------

# Keywords that OPEN a nesting block
_OPEN_KEYWORDS: frozenset = frozenset({
    "IF", "ELSEIF", "ELSE",
    "LOOP", "DO", "WHILE",
    "CASE", "TRY",
    "FORM", "METHOD", "FUNCTION",
    "CLASS", "INTERFACE",
    "MODULE",
    "AT", "ON",
    "START-OF-SELECTION",
    "END-OF-SELECTION",
})

# Keywords that CLOSE a nesting block
_CLOSE_KEYWORDS: frozenset = frozenset({
    "ENDIF", "ENDLOOP", "ENDDO",
    "ENDWHILE", "ENDCASE",
    "ENDTRY", "ENDFORM",
    "ENDMETHOD", "ENDFUNCTION",
    "ENDCLASS", "ENDINTERFACE",
    "ENDMODULE",
})

# Keywords tracked for raw counts
_TRACKED_KEYWORDS: frozenset = frozenset({
    "DATA", "TYPES", "CONSTANTS", "FIELD-SYMBOLS",
    "IF", "ELSE", "ELSEIF", "ENDIF",
    "LOOP", "ENDLOOP", "DO", "ENDDO",
    "WHILE", "ENDWHILE",
    "CASE", "WHEN", "ENDCASE",
    "CALL", "PERFORM", "FORM", "ENDFORM",
    "FUNCTION", "ENDFUNCTION",
    "METHOD", "ENDMETHOD",
    "CLASS", "ENDCLASS",
    "SELECT", "FROM", "WHERE", "INTO",
    "INSERT", "UPDATE", "DELETE", "MODIFY",
    "WRITE", "MESSAGE",
    "RAISE", "CATCH", "TRY", "ENDTRY",
    "APPEND", "COLLECT", "READ", "MOVE",
    "CLEAR", "REFRESH", "FREE",
    "CHECK", "EXIT", "RETURN", "STOP",
    "DESCRIBE", "TRANSLATE", "CONCATENATE", "SPLIT",
    "SORT", "FIND", "REPLACE",
    "CREATE", "ASSIGN",
    "MODULE", "ENDMODULE",
    "INTERFACE", "ENDINTERFACE",
    "IMPORT", "EXPORT", "RECEIVE",
})

# Regex for numeric magic-number detection (not 0 or 1)
_MAGIC_NUM_RE = re.compile(
    r"""
    (?<!\w)           # not preceded by word char (no variable names)
    (?!0\b)(?!1\b)    # exclude 0 and 1
    \d+(?:\.\d+)?     # integer or decimal
    (?!\w)            # not followed by word char
    """,
    re.VERBOSE,
)

# Regex for chain operator (colon not inside strings)
_CHAIN_RE = re.compile(r"(?<![\"']):")

# Comment pattern: line starts with * or has inline " (ABAP comment styles)
_FULL_COMMENT_RE = re.compile(r"^\*")
_INLINE_COMMENT_RE = re.compile(r'(?<!["\w])"')  # " not inside string


# ---------------------------------------------------------------------------
# Protocol (abstraction for Dependency Inversion)
# ---------------------------------------------------------------------------

@runtime_checkable
class AbapParserProtocol(Protocol):
    """Structural protocol describing the AbapParser interface.

    Any object that implements ``parse(source)`` returning a
    :class:`ParseResult` satisfies this protocol.  Callers (e.g.
    :class:`~metrics.MetricsCalculator`) should type-hint against this
    protocol rather than the concrete class.
    """

    def parse(self, source: str) -> ParseResult:
        """Parse *source* and return raw parse data."""
        ...


# ---------------------------------------------------------------------------
# Abstract base (Open/Closed – extend by sub-classing)
# ---------------------------------------------------------------------------

class BaseAbapParser(ABC):
    """Abstract base that enforces the parse interface.

    Subclasses override :meth:`_post_process` to extend behaviour
    without modifying the base algorithm (Open/Closed Principle).
    """

    @abstractmethod
    def parse(self, source: str) -> ParseResult:
        """Parse *source* ABAP text and return a :class:`ParseResult`."""

    def _post_process(self, result: ParseResult) -> None:
        """Hook for subclasses – called at end of :meth:`parse`."""


# ---------------------------------------------------------------------------
# Concrete implementation
# ---------------------------------------------------------------------------

class AbapParser(BaseAbapParser):
    """Full ABAP source-code parser.

    Parameters
    ----------
    long_line_limit:
        Lines longer than this value are flagged. Default 120.
    magic_number_whitelist:
        Additional numeric strings to treat as *not* magic.
        0 and 1 are always whitelisted.
    """

    def __init__(
        self,
        long_line_limit: int = 120,
        magic_number_whitelist: Optional[Sequence[str]] = None,
    ) -> None:
        self._limit = long_line_limit
        self._extra_whitelist: frozenset = frozenset(
            magic_number_whitelist or []
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def parse(self, source: str) -> ParseResult:
        """Parse *source* and return a fully-populated :class:`ParseResult`.

        The algorithm is O(n) in the number of source lines.

        Parameters
        ----------
        source:
            Raw ABAP source code as a multi-line string.

        Returns
        -------
        ParseResult
            All raw counters and per-line metadata.
        """
        result = ParseResult()
        raw_lines = source.splitlines()
        result.total_lines = len(raw_lines)

        nesting_depth: int = 0

        for idx, raw in enumerate(raw_lines, start=1):
            info = self._classify_line(idx, raw, nesting_depth)
            result.lines.append(info)

            # Aggregate counters
            if info.is_blank:
                result.blank_lines += 1
            elif info.is_comment:
                result.comment_lines += 1
                self._scan_comment_markers(info, result)
            else:
                result.code_lines += 1
                nesting_depth = self._update_nesting(
                    info, nesting_depth, result
                )
                self._count_keywords(info, result)
                self._count_structures(info, result)

            if info.has_long_line:
                result.long_line_numbers.append(idx)

            result.all_magic_numbers.extend(info.magic_numbers)

        result.max_nesting = max(result.nesting_history, default=0)

        self._post_process(result)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _classify_line(
        self, number: int, raw: str, current_nesting: int
    ) -> LineInfo:
        """Build a :class:`LineInfo` for *raw*."""
        stripped = raw.strip()
        info = LineInfo(number=number, raw=raw, stripped=stripped)

        # Blank line
        if not stripped:
            info.is_blank = True
            return info

        # Full-line comment (starts with *)
        if _FULL_COMMENT_RE.match(stripped):
            info.is_comment = True
            return info

        # Inline comment check: text before first unquoted "
        code_part = self._strip_inline_comment(stripped)
        code_stripped = code_part.strip()

        if not code_stripped:
            # Whole line was a comment after stripping
            info.is_comment = True
            return info

        info.is_code = True
        info.indent_level = self._measure_indent(raw)
        info.has_long_line = len(raw.rstrip("\n")) > self._limit
        info.tokens = self._extract_tokens(code_stripped)
        info.magic_numbers = self._find_magic_numbers(code_stripped)

        if _CHAIN_RE.search(code_stripped):
            info.tokens.append("__CHAIN__")

        return info

    @staticmethod
    def _strip_inline_comment(text: str) -> str:
        """Return the portion of *text* before any ABAP inline comment.

        ABAP inline comments begin with an unquoted double-quote character.
        Quoted strings use single quotes in ABAP, so we track those.
        """
        in_string = False
        for i, ch in enumerate(text):
            if ch == "'" :
                in_string = not in_string
            elif ch == '"' and not in_string:
                return text[:i]
        return text

    @staticmethod
    def _measure_indent(raw: str) -> int:
        """Return indent level as number of leading spaces divided by 2."""
        spaces = len(raw) - len(raw.lstrip(" "))
        return spaces // 2

    @staticmethod
    def _extract_tokens(code: str) -> List[str]:
        """Upper-case words from *code* that are in the tracked keyword set."""
        words = re.split(r"[\s\(\)\.,;]+", code.upper())
        return [w for w in words if w in _TRACKED_KEYWORDS]

    def _find_magic_numbers(self, code: str) -> List[str]:
        """Return numeric literals in *code* that qualify as magic numbers."""
        candidates = _MAGIC_NUM_RE.findall(code)
        return [
            c for c in candidates
            if c not in self._extra_whitelist
        ]

    def _update_nesting(
        self,
        info: LineInfo,
        depth: int,
        result: ParseResult,
    ) -> int:
        """Adjust *depth* based on open/close keywords and record it."""
        tokens_upper = [t for t in info.tokens]

        # Close keywords reduce depth BEFORE recording
        for token in tokens_upper:
            if token in _CLOSE_KEYWORDS:
                depth = max(0, depth - 1)

        result.nesting_history.append(depth)

        # Open keywords increase depth AFTER recording
        for token in tokens_upper:
            if token in _OPEN_KEYWORDS:
                depth += 1

        return depth

    @staticmethod
    def _count_keywords(info: LineInfo, result: ParseResult) -> None:
        """Increment per-keyword counters in *result*."""
        for token in info.tokens:
            if token == "__CHAIN__":
                result.chain_statement_count += 1
            else:
                result.keyword_counts[token] = (
                    result.keyword_counts.get(token, 0) + 1
                )

    @staticmethod
    def _count_structures(info: LineInfo, result: ParseResult) -> None:
        """Count high-level structures: FORM, METHOD, CLASS, etc."""
        upper = info.stripped.upper()

        # FORM definition
        if re.match(r"^FORM\b", upper):
            result.form_count += 1

        # METHOD definition (METHOD xxx.)
        if re.match(r"^METHOD\b", upper):
            result.method_count += 1

        # CLASS definition
        if re.match(r"^CLASS\b.*\bDEFINITION\b", upper):
            result.class_count += 1

        # FUNCTION definition
        if re.match(r"^FUNCTION\b", upper) and not re.match(
            r"^FUNCTION-POOL\b", upper
        ):
            result.function_count += 1

        # SELECT
        if re.match(r"^SELECT\b", upper):
            result.select_count += 1

        # PERFORM
        if re.match(r"^PERFORM\b", upper):
            result.perform_count += 1

        # CALL FUNCTION
        if re.match(r"^CALL\s+FUNCTION\b", upper):
            result.call_function_count += 1

        # CALL METHOD
        if re.match(r"^CALL\s+METHOD\b", upper) or "->" in info.stripped:
            result.call_method_count += 1

        # RAISE / CATCH
        if re.match(r"^RAISE\b", upper):
            result.raise_count += 1
        if re.match(r"^CATCH\b", upper):
            result.catch_count += 1

    @staticmethod
    def _scan_comment_markers(info: LineInfo, result: ParseResult) -> None:
        """Detect TODO / FIXME in comment text."""
        upper = info.stripped.upper()
        if "TODO" in upper:
            result.todo_count += 1
        if "FIXME" in upper:
            result.fixme_count += 1
