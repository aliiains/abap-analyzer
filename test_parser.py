"""
tests/test_parser.py

Unit tests for :mod:`parser`.

Coverage targets
----------------
* Line classification (blank / comment / code)
* Keyword extraction and counting
* Nesting depth tracking
* Magic number detection
* Long-line flagging
* Structure counts (FORM, METHOD, CLASS, FUNCTION, SELECT, etc.)
* Error-handling detection (RAISE / CATCH)
* Comment markers (TODO / FIXME)
* Chain operator detection
* Edge cases: empty input, single line, deeply nested
"""

from __future__ import annotations

import sys
import os

# Ensure the parent directory is on the path so imports work when pytest
# is run from either the project root or the abap-analyzer/ folder.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from parser import AbapParser, AbapParserProtocol, ParseResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def parser() -> AbapParser:
    """Return a default AbapParser instance."""
    return AbapParser()


@pytest.fixture
def strict_parser() -> AbapParser:
    """AbapParser with a tighter long-line limit for testing."""
    return AbapParser(long_line_limit=40)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(source: str) -> ParseResult:
    """Convenience wrapper."""
    return AbapParser().parse(source)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_parser_satisfies_protocol(self, parser: AbapParser) -> None:
        """AbapParser must satisfy AbapParserProtocol structurally."""
        assert isinstance(parser, AbapParserProtocol)

    def test_parse_returns_parse_result(self, parser: AbapParser) -> None:
        result = parser.parse("DATA lv_x TYPE i.")
        assert isinstance(result, ParseResult)


# ---------------------------------------------------------------------------
# Empty / trivial inputs
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_string(self, parser: AbapParser) -> None:
        result = parser.parse("")
        assert result.total_lines == 0
        assert result.code_lines  == 0
        assert result.blank_lines == 0
        assert result.comment_lines == 0

    def test_only_blank_lines(self, parser: AbapParser) -> None:
        result = parser.parse("\n\n\n")
        assert result.total_lines  == 3
        assert result.blank_lines  == 3
        assert result.code_lines   == 0

    def test_single_code_line(self, parser: AbapParser) -> None:
        result = parser.parse("DATA lv_x TYPE i.")
        assert result.total_lines == 1
        assert result.code_lines  == 1
        assert result.blank_lines == 0

    def test_single_comment_line(self, parser: AbapParser) -> None:
        result = parser.parse("* This is a comment")
        assert result.total_lines   == 1
        assert result.comment_lines == 1
        assert result.code_lines    == 0


# ---------------------------------------------------------------------------
# Line classification
# ---------------------------------------------------------------------------

class TestLineClassification:
    def test_star_comment_classified(self) -> None:
        result = _parse("* Full line comment")
        assert result.lines[0].is_comment is True

    def test_blank_line_classified(self) -> None:
        result = _parse("   ")
        assert result.lines[0].is_blank is True

    def test_code_line_classified(self) -> None:
        result = _parse("IF lv_x > 0.")
        assert result.lines[0].is_code is True

    def test_inline_comment_strips_code_part(self) -> None:
        """Line with code + inline comment should be classified as code."""
        result = _parse('DATA lv_y TYPE i.   " inline comment here')
        assert result.lines[0].is_code is True

    def test_mixed_content_counts(self) -> None:
        source = "\n".join([
            "* Comment 1",
            "DATA lv_a TYPE i.",
            "",
            "IF lv_a > 0.",
            "  WRITE: / lv_a.",
            "ENDIF.",
            "* Comment 2",
        ])
        result = _parse(source)
        assert result.total_lines   == 7
        assert result.comment_lines == 2
        assert result.blank_lines   == 1
        assert result.code_lines    == 4


# ---------------------------------------------------------------------------
# Keyword counting
# ---------------------------------------------------------------------------

class TestKeywordCounting:
    def test_data_keyword_counted(self) -> None:
        result = _parse("DATA lv_x TYPE i.")
        assert result.keyword_counts.get("DATA", 0) >= 1

    def test_if_endif_counted(self) -> None:
        source = "IF lv_x > 0.\nENDIF."
        result = _parse(source)
        assert result.keyword_counts.get("IF",    0) == 1
        assert result.keyword_counts.get("ENDIF", 0) == 1

    def test_loop_endloop_counted(self) -> None:
        source = "LOOP AT lt_tab INTO ls_row.\nENDLOOP."
        result = _parse(source)
        assert result.keyword_counts.get("LOOP",    0) == 1
        assert result.keyword_counts.get("ENDLOOP", 0) == 1

    def test_multiple_keyword_occurrences(self) -> None:
        source = "\n".join([
            "IF lv_a > 0.",
            "  IF lv_b > 0.",
            "  ENDIF.",
            "ENDIF.",
        ])
        result = _parse(source)
        assert result.keyword_counts.get("IF",    0) == 2
        assert result.keyword_counts.get("ENDIF", 0) == 2

    def test_select_counted(self) -> None:
        source = "SELECT * FROM mara INTO TABLE lt_data WHERE matnr LIKE 'Z%'."
        result = _parse(source)
        assert result.select_count == 1

    def test_perform_counted(self) -> None:
        result = _parse("PERFORM my_routine.")
        assert result.perform_count == 1

    def test_call_function_counted(self) -> None:
        result = _parse("CALL FUNCTION 'Z_MY_FM'.")
        assert result.call_function_count == 1


# ---------------------------------------------------------------------------
# Nesting depth
# ---------------------------------------------------------------------------

class TestNestingDepth:
    def test_single_if_nesting(self) -> None:
        source = "IF lv_x > 0.\n  WRITE: / 'yes'.\nENDIF."
        result = _parse(source)
        assert result.max_nesting >= 1

    def test_nested_ifs(self) -> None:
        source = "\n".join([
            "IF a.",
            "  IF b.",
            "    IF c.",
            "      WRITE: / 'deep'.",
            "    ENDIF.",
            "  ENDIF.",
            "ENDIF.",
        ])
        result = _parse(source)
        assert result.max_nesting >= 3

    def test_loop_inside_if(self) -> None:
        source = "\n".join([
            "IF lv_flag = 'X'.",
            "  LOOP AT lt_tab INTO ls_row.",
            "    WRITE: / ls_row.",
            "  ENDLOOP.",
            "ENDIF.",
        ])
        result = _parse(source)
        assert result.max_nesting >= 2

    def test_nesting_resets_at_end(self) -> None:
        source = "\n".join([
            "IF a.",
            "  WRITE: / 'a'.",
            "ENDIF.",
            "WRITE: / 'outside'.",
        ])
        result = _parse(source)
        # After ENDIF the depth should drop
        last_depth = result.nesting_history[-1] if result.nesting_history else 0
        assert last_depth == 0

    def test_no_nesting_flat_code(self) -> None:
        source = "\n".join([
            "DATA lv_a TYPE i.",
            "lv_a = 5.",
            "WRITE: / lv_a.",
        ])
        result = _parse(source)
        assert result.max_nesting == 0

    def test_deeply_nested_five_levels(self) -> None:
        source = "\n".join([
            "IF a.",
            "  LOOP AT t1 INTO s1.",
            "    IF b.",
            "      DO 3 TIMES.",
            "        WHILE c.",
            "          WRITE: / 'deep'.",
            "        ENDWHILE.",
            "      ENDDO.",
            "    ENDIF.",
            "  ENDLOOP.",
            "ENDIF.",
        ])
        result = _parse(source)
        assert result.max_nesting >= 5


# ---------------------------------------------------------------------------
# Magic numbers
# ---------------------------------------------------------------------------

class TestMagicNumbers:
    def test_literal_2_is_magic(self) -> None:
        result = _parse("lv_x = 2.")
        assert len(result.all_magic_numbers) >= 1
        assert "2" in result.all_magic_numbers

    def test_zero_is_not_magic(self) -> None:
        result = _parse("lv_x = 0.")
        assert "0" not in result.all_magic_numbers

    def test_one_is_not_magic(self) -> None:
        result = _parse("lv_x = 1.")
        assert "1" not in result.all_magic_numbers

    def test_decimal_magic_number(self) -> None:
        result = _parse("lv_rate = 19.5.")
        assert any("19" in m or "19.5" in m for m in result.all_magic_numbers)

    def test_multiple_magic_numbers(self) -> None:
        result = _parse("lv_x = 42 + 100 - 7.")
        assert len(result.all_magic_numbers) >= 2

    def test_whitelist_extra_number(self) -> None:
        parser = AbapParser(magic_number_whitelist=["42"])
        result = parser.parse("lv_x = 42.")
        assert "42" not in result.all_magic_numbers

    def test_no_magic_in_comment(self) -> None:
        """Numbers in comment lines should NOT be flagged."""
        result = _parse("* value is 99")
        assert len(result.all_magic_numbers) == 0


# ---------------------------------------------------------------------------
# Long lines
# ---------------------------------------------------------------------------

class TestLongLines:
    def test_short_line_not_flagged(self) -> None:
        result = _parse("DATA lv_x TYPE i.")
        assert len(result.long_line_numbers) == 0

    def test_long_line_flagged(self, strict_parser: AbapParser) -> None:
        long_line = "DATA lv_very_long_variable_name_here TYPE string VALUE 'very long default value'."
        result = strict_parser.parse(long_line)
        assert 1 in result.long_line_numbers

    def test_exact_limit_not_flagged(self) -> None:
        parser = AbapParser(long_line_limit=10)
        result = parser.parse("A" * 10)
        # Exactly 10 chars — not > 10, so not flagged
        assert len(result.long_line_numbers) == 0

    def test_over_limit_flagged(self) -> None:
        parser = AbapParser(long_line_limit=10)
        result = parser.parse("A" * 11)
        assert 1 in result.long_line_numbers

    def test_multiple_long_lines(self, strict_parser: AbapParser) -> None:
        source = "\n".join([
            "A" * 5,   # short
            "B" * 50,  # long
            "C" * 50,  # long
        ])
        result = strict_parser.parse(source)
        assert 2 in result.long_line_numbers
        assert 3 in result.long_line_numbers
        assert 1 not in result.long_line_numbers


# ---------------------------------------------------------------------------
# Structure counts
# ---------------------------------------------------------------------------

class TestStructureCounts:
    def test_form_counted(self) -> None:
        source = "FORM my_routine.\nENDFORM."
        result = _parse(source)
        assert result.form_count == 1

    def test_multiple_forms(self) -> None:
        source = "\n".join([
            "FORM routine_a.",
            "ENDFORM.",
            "FORM routine_b.",
            "ENDFORM.",
        ])
        result = _parse(source)
        assert result.form_count == 2

    def test_method_counted(self) -> None:
        source = "METHOD do_something.\nENDMETHOD."
        result = _parse(source)
        assert result.method_count == 1

    def test_class_definition_counted(self) -> None:
        source = "CLASS lcl_helper DEFINITION.\nENDCLASS."
        result = _parse(source)
        assert result.class_count == 1

    def test_function_counted(self) -> None:
        source = "FUNCTION z_my_fm.\nENDFUNCTION."
        result = _parse(source)
        assert result.function_count == 1

    def test_raise_counted(self) -> None:
        result = _parse("RAISE EXCEPTION TYPE cx_no_authority.")
        assert result.raise_count == 1

    def test_catch_counted(self) -> None:
        source = "TRY.\n  lv_x = 1.\nCATCH cx_sy_zerodivide.\nENDTRY."
        result = _parse(source)
        assert result.catch_count == 1


# ---------------------------------------------------------------------------
# Comment markers
# ---------------------------------------------------------------------------

class TestCommentMarkers:
    def test_todo_detected(self) -> None:
        result = _parse("* TODO: fix this later")
        assert result.todo_count == 1

    def test_fixme_detected(self) -> None:
        result = _parse("* FIXME: this is broken")
        assert result.fixme_count == 1

    def test_case_insensitive_todo(self) -> None:
        result = _parse("* todo: lowercase marker")
        assert result.todo_count == 1

    def test_multiple_todos(self) -> None:
        source = "\n".join([
            "* TODO: first",
            "* TODO: second",
            "* FIXME: and this",
        ])
        result = _parse(source)
        assert result.todo_count  == 2
        assert result.fixme_count == 1

    def test_no_markers_in_clean_code(self) -> None:
        source = "DATA lv_x TYPE i.\nlv_x = 42."
        result = _parse(source)
        assert result.todo_count  == 0
        assert result.fixme_count == 0


# ---------------------------------------------------------------------------
# Chain operator
# ---------------------------------------------------------------------------

class TestChainOperator:
    def test_chain_detected(self) -> None:
        result = _parse("DATA: lv_a TYPE i, lv_b TYPE i.")
        assert result.chain_statement_count == 1

    def test_no_chain_without_colon(self) -> None:
        result = _parse("DATA lv_a TYPE i.")
        assert result.chain_statement_count == 0

    def test_multiple_chain_lines(self) -> None:
        source = "\n".join([
            "DATA: lv_a TYPE i,",
            "      lv_b TYPE string.",
            "WRITE: / 'a', lv_a.",
        ])
        result = _parse(source)
        assert result.chain_statement_count >= 1


# ---------------------------------------------------------------------------
# Full-program integration snapshot
# ---------------------------------------------------------------------------

class TestFullProgram:
    """Parse a representative ABAP snippet and assert key aggregate values."""

    SOURCE = "\n".join([
        "* Full program test",
        "REPORT z_test.",
        "",
        "DATA: gv_count TYPE i.",
        "CONSTANTS: gc_max TYPE i VALUE 10.",
        "",
        "FORM run.",
        "  DATA lv_i TYPE i.",
        "  DO 5 TIMES.",
        "    IF lv_i > 3.",
        "      WRITE: / lv_i.",
        "    ENDIF.",
        "    lv_i = lv_i + 1.",
        "  ENDDO.",
        "ENDFORM.",
        "",
        "START-OF-SELECTION.",
        "  PERFORM run.",
    ])

    def test_total_lines(self) -> None:
        result = _parse(self.SOURCE)
        assert result.total_lines == 18

    def test_comment_lines(self) -> None:
        result = _parse(self.SOURCE)
        assert result.comment_lines == 1

    def test_blank_lines(self) -> None:
        result = _parse(self.SOURCE)
        assert result.blank_lines >= 2

    def test_form_count(self) -> None:
        result = _parse(self.SOURCE)
        assert result.form_count == 1

    def test_perform_count(self) -> None:
        result = _parse(self.SOURCE)
        assert result.perform_count == 1

    def test_max_nesting_at_least_2(self) -> None:
        result = _parse(self.SOURCE)
        assert result.max_nesting >= 2

    def test_select_not_present(self) -> None:
        result = _parse(self.SOURCE)
        assert result.select_count == 0

    def test_magic_number_5_detected(self) -> None:
        result = _parse(self.SOURCE)
        assert "5" in result.all_magic_numbers or "3" in result.all_magic_numbers
