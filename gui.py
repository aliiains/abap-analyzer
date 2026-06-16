"""
gui.py — Graphical User Interface (Tkinter).

Single responsibility: build and wire up the application window.
No parsing, metric calculation, or report formatting logic lives here.

The ``App`` class depends on injected collaborators
(``AbapParserProtocol``, ``MetricCalculatorProtocol``,
``ReportFormatterProtocol``) — Dependency Inversion Principle.

Layout
------
┌──────────────────────────────────────────────────────────────┐
│  ABAP Code Analyser                    [toolbar]             │
├─────────────────────────────┬────────────────────────────────┤
│  Input pane (Text widget)   │  Output / Report pane          │
│  [ABAP source code here]    │  [metrics + recommendations]   │
│                             │                                │
├─────────────────────────────┴────────────────────────────────┤
│  Status bar                                                  │
└──────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Optional

from metrics import MetricCalculatorProtocol, MetricsCalculator, MetricsReport
from parser import AbapParser, AbapParserProtocol, ParseResult
from report import ReportFormatterProtocol, TextReportFormatter

# ---------------------------------------------------------------------------
# Colour palette (Catppuccin-inspired dark theme)
# ---------------------------------------------------------------------------

_PALETTE = {
    "bg":           "#1e1e2e",
    "bg_surface":   "#181825",
    "bg_overlay":   "#313244",
    "text":         "#cdd6f4",
    "text_dim":     "#a6adc8",
    "accent":       "#89b4fa",
    "accent2":      "#cba6f7",
    "ok":           "#a6e3a1",
    "warning":      "#f9e2af",
    "critical":     "#f38ba8",
    "border":       "#45475a",
    "selection_bg": "#45475a",
    "cursor":       "#f5e0dc",
    "btn_bg":       "#313244",
    "btn_active":   "#45475a",
}

_FONT_CODE   = ("Consolas", 11)
_FONT_UI     = ("Segoe UI", 10)
_FONT_TITLE  = ("Segoe UI", 13, "bold")
_FONT_SMALL  = ("Segoe UI", 9)

# ABAP keyword list for syntax highlighting
_ABAP_KEYWORDS = [
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
    "WRITE", "MESSAGE", "RAISE", "CATCH",
    "TRY", "ENDTRY", "APPEND", "READ",
    "CLEAR", "REFRESH", "CHECK", "EXIT",
    "RETURN", "STOP", "MOVE", "COLLECT",
    "DESCRIBE", "TRANSLATE", "CONCATENATE", "SPLIT",
    "SORT", "FIND", "REPLACE", "CREATE", "ASSIGN",
    "INTERFACE", "ENDINTERFACE", "MODULE", "ENDMODULE",
    "IMPORT", "EXPORT", "AT", "TABLES",
]

# ---------------------------------------------------------------------------
# Heatmap colour table
# ---------------------------------------------------------------------------
# Each entry maps a nesting depth (0-based) to a background hex colour.
# Depth 0  = no colouring (code at the outermost level).
# Depths 1+ progress from a warm amber to a deep crimson so hotspots
# stand out while text remains readable.

_HEATMAP_COLOURS: list = [
    None,       # depth 0  — no background
    "#27201a",  # depth 1  — very subtle warm
    "#321e10",  # depth 2  — soft amber
    "#3e1a08",  # depth 3  — orange-brown
    "#4d1205",  # depth 4  — burnt orange-red
    "#5d0a04",  # depth 5  — deep red
    "#6e0505",  # depth 6  — crimson
    "#7a0303",  # depth 7+ — dark crimson (capped)
]
_HEATMAP_MAX_DEPTH = len(_HEATMAP_COLOURS) - 1


# ---------------------------------------------------------------------------
# Syntax highlighter helper
# ---------------------------------------------------------------------------

class SyntaxHighlighter:
    """Applies ABAP syntax colouring to a Tkinter Text widget.

    Responsible only for colouring – nothing else.
    """

    def __init__(self, text_widget: tk.Text) -> None:
        self._widget = text_widget
        self._configure_tags()

    def _configure_tags(self) -> None:
        w = self._widget
        w.tag_configure("keyword",  foreground=_PALETTE["accent"],  font=(*_FONT_CODE[:2], "bold"))
        w.tag_configure("comment",  foreground=_PALETTE["text_dim"], font=_FONT_CODE)
        w.tag_configure("string",   foreground=_PALETTE["ok"])
        w.tag_configure("number",   foreground=_PALETTE["warning"])
        w.tag_configure("longline", background="#3d1010")

    def highlight(self) -> None:
        """Re-highlight the entire widget content."""
        w = self._widget
        # Remove previous tags
        for tag in ("keyword", "comment", "string", "number", "longline"):
            w.tag_remove(tag, "1.0", tk.END)

        content = w.get("1.0", tk.END)
        lines = content.split("\n")

        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Full-line comment
            if stripped.startswith("*") or stripped.startswith('"'):
                start = f"{lineno}.0"
                end   = f"{lineno}.end"
                w.tag_add("comment", start, end)
                continue

            # Long line background
            if len(line.rstrip("\n")) > 120:
                w.tag_add("longline", f"{lineno}.0", f"{lineno}.end")

            # Strings (single-quoted)
            col = 0
            in_str = False
            str_start = 0
            for ci, ch in enumerate(line):
                if ch == "'":
                    if not in_str:
                        in_str = True
                        str_start = ci
                    else:
                        in_str = False
                        w.tag_add("string", f"{lineno}.{str_start}", f"{lineno}.{ci + 1}")

            # Keywords
            words = line.upper().split()
            search_start = 0
            for word_upper in words:
                clean = word_upper.strip(".,;:()")
                if clean in _ABAP_KEYWORDS:
                    # find position in original line
                    idx = line.upper().find(clean, search_start)
                    if idx >= 0:
                        w.tag_add("keyword", f"{lineno}.{idx}", f"{lineno}.{idx + len(clean)}")
                        search_start = idx + len(clean)

            # Numbers
            import re
            for m in re.finditer(r"\b\d+(?:\.\d+)?\b", line):
                w.tag_add("number", f"{lineno}.{m.start()}", f"{lineno}.{m.end()}")

    def clear(self) -> None:
        """Remove all syntax-highlighting tags from the widget."""
        for tag in ("keyword", "comment", "string", "number", "longline"):
            self._widget.tag_remove(tag, "1.0", tk.END)


# ---------------------------------------------------------------------------
# Heatmap painter helper
# ---------------------------------------------------------------------------

class HeatmapPainter:
    """Paints line-background colours on a Tkinter Text widget by nesting depth.

    Single Responsibility: only responsible for applying and removing
    heatmap background tags.  Knows nothing about parsing or metrics.

    Usage
    -----
    After obtaining a :class:`~parser.ParseResult`, call
    :meth:`paint` with the per-line depth list.  Call :meth:`clear` to
    remove all heatmap colouring.

    The painter is deliberately separate from :class:`SyntaxHighlighter`
    so both can be toggled independently (Open/Closed Principle).
    """

    # Tag name prefix — one tag per depth level
    _TAG_PREFIX = "heatmap_depth_"

    def __init__(self, text_widget: tk.Text) -> None:
        self._widget = text_widget
        self._active_tags: list = []
        self._configure_tags()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def paint(self, depth_per_line: list) -> None:
        """Apply heatmap background to all lines in *depth_per_line*.

        Parameters
        ----------
        depth_per_line:
            List whose i-th element is the nesting depth (int) of
            source line i+1 (1-based).  Blank / comment lines should
            carry depth 0.
        """
        self.clear()
        w = self._widget

        for lineno, depth in enumerate(depth_per_line, start=1):
            capped = min(depth, _HEATMAP_MAX_DEPTH)
            if capped == 0:
                continue  # depth-0 lines keep the default background
            tag = f"{self._TAG_PREFIX}{capped}"
            w.tag_add(tag, f"{lineno}.0", f"{lineno}.end+1c")

    def clear(self) -> None:
        """Remove all heatmap background tags from the widget."""
        w = self._widget
        for depth in range(1, _HEATMAP_MAX_DEPTH + 1):
            tag = f"{self._TAG_PREFIX}{depth}"
            w.tag_remove(tag, "1.0", tk.END)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _configure_tags(self) -> None:
        """Register one Tk tag per depth level with its background colour."""
        w = self._widget
        for depth in range(1, _HEATMAP_MAX_DEPTH + 1):
            colour = _HEATMAP_COLOURS[depth]
            tag = f"{self._TAG_PREFIX}{depth}"
            w.tag_configure(
                tag,
                background=colour,
                # Keep foreground bright so text stays readable on dark bg
                foreground=_PALETTE["text"],
            )
            # Heatmap tags sit BELOW syntax tags (lower priority = added first)
            # Raise syntax tags above heatmap so keywords still colour correctly.
            # We lower heatmap tags in the stack so syntax fg wins.
            w.tag_lower(tag)

    @staticmethod
    def depth_list_from_parse_result(result) -> list:
        """Build a per-line depth list from a :class:`~parser.ParseResult`.

        Blank and comment lines receive depth 0 because they are not
        execution hotspots.

        Parameters
        ----------
        result:
            A fully-populated :class:`~parser.ParseResult`.

        Returns
        -------
        list[int]
            One integer per source line (1-based index → list[index-1]).
        """
        depths: list = []
        nesting_iter = iter(result.nesting_history)

        for line_info in result.lines:
            if line_info.is_code:
                try:
                    depth = next(nesting_iter)
                except StopIteration:
                    depth = 0
            else:
                depth = 0
            depths.append(depth)

        return depths


# ---------------------------------------------------------------------------
# Main application class
# ---------------------------------------------------------------------------

class App:
    """Root application window.

    Parameters
    ----------
    root:
        The Tk root window.
    parser:
        Any object satisfying :class:`~parser.AbapParserProtocol`.
        Defaults to :class:`~parser.AbapParser`.
    calculator:
        Any object satisfying :class:`~metrics.MetricCalculatorProtocol`.
        Defaults to :class:`~metrics.MetricsCalculator`.
    formatter:
        Any object satisfying :class:`~report.ReportFormatterProtocol`.
        Defaults to :class:`~report.TextReportFormatter`.
    """

    def __init__(
        self,
        root: tk.Tk,
        parser: Optional[AbapParserProtocol] = None,
        calculator: Optional[MetricCalculatorProtocol] = None,
        formatter: Optional[ReportFormatterProtocol] = None,
    ) -> None:
        self._root = root
        self._parser:    AbapParserProtocol      = parser     or AbapParser()
        self._calculator: MetricCalculatorProtocol = calculator or MetricsCalculator()
        self._formatter: ReportFormatterProtocol = formatter  or TextReportFormatter()

        # State
        self._last_report_text: str = ""
        self._last_metrics: Optional[MetricsReport] = None
        self._last_result: Optional[ParseResult] = None

        # Heatmap state
        self._heatmap_active: bool = True
        self._highlight_active: bool = True
        self._heatmap_painter: Optional[HeatmapPainter] = None  # set in _build_panes

        self._build_window()
        self._build_menu()
        self._build_toolbar()
        self._build_panes()
        self._build_statusbar()
        self._apply_theme()
        self._load_sample_code()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        """Configure the root window geometry and title."""
        self._root.title("ABAP Code Analyser")
        self._root.geometry("1280x800")
        self._root.minsize(900, 600)
        self._root.configure(bg=_PALETTE["bg"])
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self) -> None:
        """Create the menu bar."""
        menubar = tk.Menu(
            self._root,
            bg=_PALETTE["bg_overlay"],
            fg=_PALETTE["text"],
            activebackground=_PALETTE["btn_active"],
            activeforeground=_PALETTE["text"],
            relief=tk.FLAT,
            border=0,
        )
        self._root.configure(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=False,
                            bg=_PALETTE["bg_overlay"], fg=_PALETTE["text"],
                            activebackground=_PALETTE["btn_active"])
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Открыть ABAP файл…", command=self._open_file)
        file_menu.add_command(label="Сохранить отчёт…",   command=self._save_report)
        file_menu.add_separator()
        file_menu.add_command(label="Выход",               command=self._on_close)

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=False,
                            bg=_PALETTE["bg_overlay"], fg=_PALETTE["text"],
                            activebackground=_PALETTE["btn_active"])
        menubar.add_cascade(label="Правка", menu=edit_menu)
        edit_menu.add_command(label="Очистить ввод", command=self._clear_input)
        edit_menu.add_command(label="Загрузить пример", command=self._load_sample_code)

        # Analysis menu
        analysis_menu = tk.Menu(menubar, tearoff=False,
                                bg=_PALETTE["bg_overlay"], fg=_PALETTE["text"],
                                activebackground=_PALETTE["btn_active"])
        menubar.add_cascade(label="Анализ", menu=analysis_menu)
        analysis_menu.add_command(label="Анализировать  Ctrl+Enter", command=self._analyse)
        analysis_menu.add_command(label="Подсветка синтаксиса вкл/выкл", command=self._toggle_highlight)
        analysis_menu.add_command(label="Тепловая карта вкл/выкл",   command=self._toggle_heatmap)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=False,
                            bg=_PALETTE["bg_overlay"], fg=_PALETTE["text"],
                            activebackground=_PALETTE["btn_active"])
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", command=self._show_about)

    def _build_toolbar(self) -> None:
        """Create the top toolbar with action buttons."""
        self._toolbar = tk.Frame(self._root, bg=_PALETTE["bg_surface"], pady=6, padx=8)
        self._toolbar.pack(side=tk.TOP, fill=tk.X)

        btn_style = dict(
            bg=_PALETTE["btn_bg"],
            fg=_PALETTE["text"],
            activebackground=_PALETTE["btn_active"],
            activeforeground=_PALETTE["text"],
            relief=tk.FLAT,
            cursor="hand2",
            padx=14,
            pady=4,
            font=_FONT_UI,
            border=0,
        )

        self._btn_analyse = tk.Button(
            self._toolbar, text="▶  Анализировать",
            command=self._analyse, **btn_style
        )
        self._btn_analyse.pack(side=tk.LEFT, padx=(0, 6))

        self._btn_clear = tk.Button(
            self._toolbar, text="✕  Очистить",
            command=self._clear_input, **btn_style
        )
        self._btn_clear.pack(side=tk.LEFT, padx=(0, 6))

        self._btn_open = tk.Button(
            self._toolbar, text="📂  Открыть файл",
            command=self._open_file, **btn_style
        )
        self._btn_open.pack(side=tk.LEFT, padx=(0, 6))

        self._btn_save = tk.Button(
            self._toolbar, text="💾  Скачать результат",
            command=self._save_report, **btn_style,
            state=tk.DISABLED,
        )
        self._btn_save.pack(side=tk.LEFT, padx=(0, 6))

        self._btn_highlight = tk.Button(
            self._toolbar, text="🎨  Подсветка: ВКЛ",
            command=self._toggle_highlight, **btn_style
        )
        self._btn_highlight.pack(side=tk.LEFT, padx=(0, 6))

        self._btn_heatmap = tk.Button(
            self._toolbar, text="🌡  Тепловая карта: ВКЛ",
            command=self._toggle_heatmap,
            bg=_PALETTE["btn_bg"],
            fg=_PALETTE["warning"],
            activebackground=_PALETTE["btn_active"],
            activeforeground=_PALETTE["warning"],
            relief=tk.FLAT,
            cursor="hand2",
            padx=14, pady=4,
            font=_FONT_UI,
            border=0,
        )
        self._btn_heatmap.pack(side=tk.LEFT, padx=(0, 6))

        # Title label on right
        tk.Label(
            self._toolbar,
            text="ABAP Code Analyser",
            bg=_PALETTE["bg_surface"],
            fg=_PALETTE["accent"],
            font=_FONT_TITLE,
        ).pack(side=tk.RIGHT, padx=10)

    def _build_panes(self) -> None:
        """Create the horizontal split pane with input and output areas."""
        pane_container = tk.Frame(self._root, bg=_PALETTE["bg"])
        pane_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))

        self._paned = tk.PanedWindow(
            pane_container,
            orient=tk.HORIZONTAL,
            sashwidth=6,
            sashrelief=tk.FLAT,
            bg=_PALETTE["border"],
        )
        self._paned.pack(fill=tk.BOTH, expand=True)

        # Left pane — input
        left_frame = tk.Frame(self._paned, bg=_PALETTE["bg"])
        self._paned.add(left_frame, minsize=350)

        tk.Label(
            left_frame, text="  Исходный код ABAP",
            bg=_PALETTE["bg_surface"], fg=_PALETTE["accent"],
            font=_FONT_UI, anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 2))

        self._input_text = tk.Text(
            left_frame,
            wrap=tk.NONE,
            font=_FONT_CODE,
            bg=_PALETTE["bg_surface"],
            fg=_PALETTE["text"],
            insertbackground=_PALETTE["cursor"],
            selectbackground=_PALETTE["selection_bg"],
            selectforeground=_PALETTE["text"],
            relief=tk.FLAT,
            padx=8, pady=8,
            undo=True,
            maxundo=50,
        )
        self._input_text.pack(fill=tk.BOTH, expand=True)

        # Scrollbars for input
        input_vsb = tk.Scrollbar(left_frame, orient=tk.VERTICAL,
                                  command=self._input_text.yview,
                                  bg=_PALETTE["bg_overlay"], troughcolor=_PALETTE["bg"])
        input_hsb = tk.Scrollbar(left_frame, orient=tk.HORIZONTAL,
                                  command=self._input_text.xview,
                                  bg=_PALETTE["bg_overlay"], troughcolor=_PALETTE["bg"])
        input_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        input_hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._input_text.configure(yscrollcommand=input_vsb.set,
                                    xscrollcommand=input_hsb.set)

        self._highlighter    = SyntaxHighlighter(self._input_text)
        self._heatmap_painter = HeatmapPainter(self._input_text)

        # Legend strip — colour swatches with depth labels
        self._legend_frame = tk.Frame(left_frame, bg=_PALETTE["bg_surface"], pady=3)
        self._legend_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self._build_heatmap_legend(self._legend_frame)

        # Bind Ctrl+Enter to analyse
        self._input_text.bind("<Control-Return>", lambda _e: self._analyse())
        self._input_text.bind("<KeyRelease>", self._on_input_key)

        # Explicit paste bindings — ensures Ctrl+V works on all platforms/themes
        self._input_text.bind("<Control-v>", self._paste)
        self._input_text.bind("<Control-V>", self._paste)  # Caps Lock safety
        # macOS uses Command key
        self._input_text.bind("<Command-v>", self._paste)
        self._input_text.bind("<Command-V>", self._paste)

        # Right pane — output (notebook with two tabs)
        right_frame = tk.Frame(self._paned, bg=_PALETTE["bg"])
        self._paned.add(right_frame, minsize=350)

        # Tab notebook for report / raw details
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "TNotebook",
            background=_PALETTE["bg"],
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            background=_PALETTE["bg_overlay"],
            foreground=_PALETTE["text"],
            padding=[10, 4],
            font=_FONT_UI,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", _PALETTE["bg_surface"])],
            foreground=[("selected", _PALETTE["accent"])],
        )

        self._notebook = ttk.Notebook(right_frame)
        self._notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1 — Metrics report
        report_frame = tk.Frame(self._notebook, bg=_PALETTE["bg_surface"])
        self._notebook.add(report_frame, text=" 📊  Отчёт ")

        self._output_text = tk.Text(
            report_frame,
            wrap=tk.WORD,
            font=_FONT_CODE,
            bg=_PALETTE["bg_surface"],
            fg=_PALETTE["text"],
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=10, pady=10,
        )
        self._output_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        out_vsb = tk.Scrollbar(report_frame, orient=tk.VERTICAL,
                                command=self._output_text.yview,
                                bg=_PALETTE["bg_overlay"], troughcolor=_PALETTE["bg"])
        out_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._output_text.configure(yscrollcommand=out_vsb.set)

        # Configure output text tags for coloured severity
        self._output_text.tag_configure("ok",       foreground=_PALETTE["ok"])
        self._output_text.tag_configure("warning",  foreground=_PALETTE["warning"])
        self._output_text.tag_configure("critical", foreground=_PALETTE["critical"])
        self._output_text.tag_configure("header",   foreground=_PALETTE["accent"],
                                        font=(*_FONT_CODE[:2], "bold"))
        self._output_text.tag_configure("subheader", foreground=_PALETTE["accent2"])
        self._output_text.tag_configure("dim",      foreground=_PALETTE["text_dim"])

        # Tab 2 — Metrics table
        table_frame = tk.Frame(self._notebook, bg=_PALETTE["bg_surface"])
        self._notebook.add(table_frame, text=" 📋  Таблица метрик ")

        style.configure(
            "Treeview",
            background=_PALETTE["bg_surface"],
            fieldbackground=_PALETTE["bg_surface"],
            foreground=_PALETTE["text"],
            rowheight=24,
            font=_FONT_UI,
        )
        style.configure(
            "Treeview.Heading",
            background=_PALETTE["bg_overlay"],
            foreground=_PALETTE["accent"],
            font=(*_FONT_UI[:2], "bold"),
        )
        style.map("Treeview", background=[("selected", _PALETTE["selection_bg"])])

        self._tree = ttk.Treeview(
            table_frame,
            columns=("label", "value", "unit", "severity"),
            show="headings",
        )
        self._tree.heading("label",    text="Метрика")
        self._tree.heading("value",    text="Значение")
        self._tree.heading("unit",     text="Единица")
        self._tree.heading("severity", text="Статус")
        self._tree.column("label",    width=300, anchor=tk.W)
        self._tree.column("value",    width=80,  anchor=tk.E)
        self._tree.column("unit",     width=80,  anchor=tk.W)
        self._tree.column("severity", width=80,  anchor=tk.CENTER)
        self._tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        tree_vsb = tk.Scrollbar(table_frame, orient=tk.VERTICAL,
                                 command=self._tree.yview,
                                 bg=_PALETTE["bg_overlay"])
        tree_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.configure(yscrollcommand=tree_vsb.set)

        # Row tags for severity colouring
        self._tree.tag_configure("ok",       foreground=_PALETTE["ok"])
        self._tree.tag_configure("warning",  foreground=_PALETTE["warning"])
        self._tree.tag_configure("critical", foreground=_PALETTE["critical"])

    def _build_statusbar(self) -> None:
        """Create the bottom status bar."""
        self._statusbar = tk.Frame(self._root, bg=_PALETTE["bg_overlay"], height=26)
        self._statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        self._statusbar.pack_propagate(False)

        self._status_label = tk.Label(
            self._statusbar,
            text="  Готово. Вставьте код и нажмите «Анализировать».",
            bg=_PALETTE["bg_overlay"],
            fg=_PALETTE["text_dim"],
            font=_FONT_SMALL,
            anchor=tk.W,
        )
        self._status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._lines_label = tk.Label(
            self._statusbar,
            text="",
            bg=_PALETTE["bg_overlay"],
            fg=_PALETTE["text_dim"],
            font=_FONT_SMALL,
        )
        self._lines_label.pack(side=tk.RIGHT, padx=12)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        """Apply global widget theme settings."""
        self._root.option_add("*tearOff", False)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _analyse(self) -> None:
        """Run the analysis pipeline and display results."""
        source = self._input_text.get("1.0", tk.END)
        if not source.strip():
            self._set_status("⚠  Введите код ABAP для анализа.", "warning")
            return

        self._set_status("⏳  Анализирую…")
        self._root.update_idletasks()

        try:
            parse_result   = self._parser.parse(source)
            metrics_report = self._calculator.calculate(parse_result)
            report_text    = self._formatter.format_report(
                metrics_report,
                parse_result,
                title="Отчёт анализа ABAP-кода",
            )
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Ошибка анализа", str(exc))
            self._set_status("✖  Ошибка анализа.", "critical")
            return

        self._last_report_text = report_text
        self._last_metrics = metrics_report
        self._last_result  = parse_result

        self._display_report(report_text, metrics_report)
        self._populate_table(metrics_report)
        self._btn_save.configure(state=tk.NORMAL)

        # Apply heatmap if active
        if self._heatmap_active:
            self._apply_heatmap(parse_result)

        summary = self._formatter.format_summary(metrics_report)
        self._set_status(f"✔  Анализ завершён. {summary}")
        loc = parse_result.code_lines
        total = parse_result.total_lines
        self._lines_label.configure(text=f"LOC: {loc} / {total}")

    def _display_report(self, text: str, metrics: MetricsReport) -> None:
        """Render *text* in the output widget with coloured severity marks."""
        self._output_text.configure(state=tk.NORMAL)
        self._output_text.delete("1.0", tk.END)

        for line in text.splitlines(keepends=True):
            tag = self._line_tag(line, metrics)
            self._output_text.insert(tk.END, line, tag)

        self._output_text.configure(state=tk.DISABLED)
        self._output_text.see("1.0")

    @staticmethod
    def _line_tag(line: str, metrics: MetricsReport) -> str:
        """Determine the display tag for a report line."""
        if "✖" in line or "[CRIT]" in line:
            return "critical"
        if "⚠" in line or "[WARN]" in line:
            return "warning"
        if "✔" in line or "[OK]" in line:
            return "ok"
        if line.startswith("="):
            return "header"
        if line.startswith("-") or line.startswith("  ─"):
            return "subheader"
        return ""

    def _populate_table(self, metrics: MetricsReport) -> None:
        """Fill the metrics Treeview table."""
        for row in self._tree.get_children():
            self._tree.delete(row)

        sev_labels = {"ok": "✔ OK", "warning": "⚠ Предупр.", "critical": "✖ Крит."}
        for m in metrics.metrics:
            tag = m.severity
            self._tree.insert(
                "",
                tk.END,
                values=(m.label, m.value, m.unit, sev_labels.get(m.severity, m.severity)),
                tags=(tag,),
            )

    def _save_report(self) -> None:
        """Save the last report to a file chosen by the user."""
        if not self._last_report_text:
            messagebox.showinfo("Нет данных", "Сначала выполните анализ.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Текстовый файл", "*.txt"),
                ("Все файлы", "*.*"),
            ],
            title="Сохранить отчёт",
            initialfile="abap_report.txt",
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._last_report_text)
            self._set_status(f"✔  Отчёт сохранён: {path}")
        except OSError as exc:  # pragma: no cover
            messagebox.showerror("Ошибка сохранения", str(exc))

    def _open_file(self) -> None:
        """Open an ABAP source file and load it into the input area."""
        path = filedialog.askopenfilename(
            filetypes=[
                ("ABAP файлы", "*.abap *.txt *.prog"),
                ("Все файлы", "*.*"),
            ],
            title="Открыть ABAP файл",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError as exc:  # pragma: no cover
            messagebox.showerror("Ошибка чтения", str(exc))
            return

        self._input_text.delete("1.0", tk.END)
        self._input_text.insert("1.0", content)
        self._refresh_highlight()
        self._set_status(f"📂  Файл загружен: {path}")

    def _clear_input(self) -> None:
        """Clear both the input and output areas."""
        self._input_text.delete("1.0", tk.END)
        self._output_text.configure(state=tk.NORMAL)
        self._output_text.delete("1.0", tk.END)
        self._output_text.configure(state=tk.DISABLED)
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._last_report_text = ""
        self._last_metrics = None
        self._last_result  = None
        self._btn_save.configure(state=tk.DISABLED)
        self._lines_label.configure(text="")
        self._clear_heatmap()
        self._set_status("  Очищено.")

    def _refresh_highlight(self) -> None:
        """Re-run syntax highlighting only if it is currently active."""
        if self._highlight_active:
            self._highlighter.highlight()

    def _toggle_highlight(self) -> None:
        """Toggle syntax highlighting on or off."""
        self._highlight_active = not self._highlight_active
        self._update_highlight_button()
        if self._highlight_active:
            self._highlighter.highlight()
            self._set_status("🎨  Подсветка синтаксиса включена.")
        else:
            self._highlighter.clear()
            self._set_status("🎨  Подсветка синтаксиса выключена.")

    def _update_highlight_button(self) -> None:
        """Sync the toolbar button label with current highlight state."""
        if self._highlight_active:
            self._btn_highlight.configure(
                text="🎨  Подсветка: ВКЛ",
                fg=_PALETTE["text"],
            )
        else:
            self._btn_highlight.configure(
                text="🎨  Подсветка: ВЫКЛ",
                fg=_PALETTE["text_dim"],
            )

    def _on_input_key(self, _event: tk.Event) -> None:
        """Update line/char counter in the status bar on each keystroke."""
        content = self._input_text.get("1.0", tk.END)
        lines = content.count("\n")
        self._lines_label.configure(text=f"Строк: {lines}")

    def _paste(self, event: tk.Event) -> str:
        """Handle Ctrl+V / Command+V paste explicitly.

        Tkinter's default paste can be swallowed on some platforms or
        themes. This handler guarantees the clipboard text is inserted
        at the cursor, replacing any active selection, and then
        refreshes the syntax highlighting and line counter.

        Returns ``"break"`` to stop Tkinter from triggering its own
        default paste handler (which would otherwise insert the text a
        second time).
        """
        try:
            clipboard_text = self._root.clipboard_get()
        except tk.TclError:
            # Clipboard is empty or contains non-text content
            return "break"

        widget = self._input_text

        # Delete selected text first (if any)
        try:
            sel_start = widget.index(tk.SEL_FIRST)
            sel_end   = widget.index(tk.SEL_LAST)
            widget.delete(sel_start, sel_end)
        except tk.TclError:
            pass  # No selection — that's fine

        # Insert at current cursor position
        widget.insert(tk.INSERT, clipboard_text)

        # Scroll so the insertion point is visible
        widget.see(tk.INSERT)

        # Refresh counters and highlighting
        self._on_input_key(event)
        self._refresh_highlight()

        return "break"  # prevent double-paste from default binding

    def _load_sample_code(self) -> None:
        """Insert a sample ABAP snippet for demonstration."""
        sample = _SAMPLE_ABAP_CODE
        self._input_text.delete("1.0", tk.END)
        self._input_text.insert("1.0", sample)
        self._refresh_highlight()
        self._set_status("📝  Пример кода загружен. Нажмите «Анализировать».")

    def _show_about(self) -> None:
        """Show the About dialog."""
        messagebox.showinfo(
            "О программе",
            "ABAP Code Analyser\n"
            "Версия 1.0\n\n"
            "Анализатор качества ABAP-кода.\n"
            "Принципы SOLID, модульная архитектура.\n\n"
            "Запуск: python main.py\n"
            "Тесты:  pytest tests/",
        )

    def _on_close(self) -> None:
        """Handle window close request."""
        self._root.destroy()

    # ------------------------------------------------------------------
    # Heatmap methods
    # ------------------------------------------------------------------

    def _build_heatmap_legend(self, parent: tk.Frame) -> None:
        """Build the colour-swatch legend strip inside *parent*.

        The legend is always visible so users understand what depth
        each colour represents even before running an analysis.
        """
        tk.Label(
            parent,
            text="  Вложенность: ",
            bg=_PALETTE["bg_surface"],
            fg=_PALETTE["text_dim"],
            font=_FONT_SMALL,
        ).pack(side=tk.LEFT)

        labels = [
            (0, _PALETTE["bg_surface"], "0"),
            (1, _HEATMAP_COLOURS[1], "1"),
            (2, _HEATMAP_COLOURS[2], "2"),
            (3, _HEATMAP_COLOURS[3], "3"),
            (4, _HEATMAP_COLOURS[4], "4"),
            (5, _HEATMAP_COLOURS[5], "5"),
            (6, _HEATMAP_COLOURS[6], "6"),
            (7, _HEATMAP_COLOURS[7], "7+"),
        ]

        for _depth, colour, label_text in labels:
            swatch = tk.Label(
                parent,
                text=f" {label_text} ",
                bg=colour,
                fg=_PALETTE["text"],
                font=_FONT_SMALL,
                relief=tk.FLAT,
                padx=4,
                pady=1,
            )
            swatch.pack(side=tk.LEFT, padx=1)

        tk.Label(
            parent,
            text="  (уровни)",
            bg=_PALETTE["bg_surface"],
            fg=_PALETTE["text_dim"],
            font=_FONT_SMALL,
        ).pack(side=tk.LEFT)

    def _apply_heatmap(self, result: ParseResult) -> None:
        """Paint the heatmap onto the input editor from *result*.

        Delegates actual painting to :class:`HeatmapPainter`, keeping
        App free of tag-management logic (Single Responsibility).
        """
        if self._heatmap_painter is None:
            return
        depths = HeatmapPainter.depth_list_from_parse_result(result)
        self._heatmap_painter.paint(depths)
        # Ensure syntax highlighting tags stay on top of heatmap backgrounds
        self._highlighter.highlight()

    def _clear_heatmap(self) -> None:
        """Remove all heatmap background colouring from the editor."""
        if self._heatmap_painter is not None:
            self._heatmap_painter.clear()

    def _toggle_heatmap(self) -> None:
        """Toggle heatmap on or off and update the button label."""
        self._heatmap_active = not self._heatmap_active
        self._update_heatmap_button()

        if self._heatmap_active:
            # Re-apply immediately if we have a prior parse result
            if self._last_result is not None:
                self._apply_heatmap(self._last_result)
            self._set_status("🌡  Тепловая карта вложенности включена.")
        else:
            self._clear_heatmap()
            self._set_status("🌡  Тепловая карта вложенности выключена.")

    def _update_heatmap_button(self) -> None:
        """Sync the toolbar button label and colour with current state."""
        if self._heatmap_active:
            self._btn_heatmap.configure(
                text="🌡  Тепловая карта: ВКЛ",
                fg=_PALETTE["warning"],
            )
        else:
            self._btn_heatmap.configure(
                text="🌡  Тепловая карта: ВЫКЛ",
                fg=_PALETTE["text_dim"],
            )

    # ------------------------------------------------------------------
    # Status bar helper
    # ------------------------------------------------------------------

    def _set_status(self, text: str, level: str = "ok") -> None:
        """Update the status bar label."""
        colour_map = {
            "ok":       _PALETTE["text_dim"],
            "warning":  _PALETTE["warning"],
            "critical": _PALETTE["critical"],
        }
        colour = colour_map.get(level, _PALETTE["text_dim"])
        self._status_label.configure(text=f"  {text}", fg=colour)


# ---------------------------------------------------------------------------
# Sample ABAP code (used as default content)
# ---------------------------------------------------------------------------

_SAMPLE_ABAP_CODE = """\
*---------------------------------------------------------------------*
* Program: Z_EXAMPLE                                                   *
* Author:  Example Developer                                           *
* Purpose: ABAP Code Analyser demonstration sample                     *
*---------------------------------------------------------------------*
REPORT z_example.

* --- Global data declarations ---
DATA: gv_count    TYPE i,
      gv_max      TYPE i VALUE 100,       " TODO: make configurable
      gv_name     TYPE string,
      gt_orders   TYPE TABLE OF string,
      gs_order    LIKE LINE OF gt_orders.

CONSTANTS: gc_limit   TYPE i VALUE 50,
           gc_prefix  TYPE string VALUE 'ORD'.

* =====================================================================
* FORM: process_orders
* Description: Main processing routine for order data
* =====================================================================
FORM process_orders
  USING    iv_max   TYPE i
  CHANGING ev_count TYPE i.

  DATA: lv_index   TYPE i,
        lv_item    TYPE string,
        lv_status  TYPE char1,
        lv_value   TYPE p DECIMALS 2.

  ev_count = 0.

  LOOP AT gt_orders INTO gs_order.
    lv_index = sy-tabix.

    IF lv_index > iv_max.
      EXIT.
    ENDIF.

    IF gs_order IS INITIAL.
      CONTINUE.
    ENDIF.

    " Process each order
    IF lv_index > 10.
      IF lv_index > 25.
        IF lv_index > 40.
          " Deep nesting — should trigger warning
          lv_status = 'X'.
          WRITE: / 'Deep level:', lv_index.
        ELSE.
          lv_status = 'B'.
        ENDIF.
      ELSE.
        lv_status = 'A'.
      ENDIF.
    ELSE.
      lv_status = 'N'.
    ENDIF.

    ev_count = ev_count + 1.
  ENDLOOP.

ENDFORM.

* =====================================================================
* FORM: load_data
* Description: Loads data from the database
* =====================================================================
FORM load_data.
  DATA: lv_key   TYPE string,
        lt_data  TYPE TABLE OF string.

  " Select data from database
  SELECT * FROM mara
    INTO TABLE lt_data
    WHERE matnr LIKE 'Z%'.

  IF sy-subrc <> 0.
    MESSAGE 'No records found' TYPE 'I'.
    RETURN.
  ENDIF.

  SELECT COUNT(*) FROM ekko
    INTO gv_count
    WHERE bukrs = '1000'.   " FIXME: hardcoded company code = magic number

  PERFORM process_orders USING 99 CHANGING gv_count.

ENDFORM.

* =====================================================================
* FORM: calculate_totals
* Description: Aggregates totals across orders
* =====================================================================
FORM calculate_totals
  USING    it_items TYPE TABLE OF string
  CHANGING ev_total TYPE p.

  DATA: lv_amount TYPE p DECIMALS 2,
        lv_tax    TYPE p DECIMALS 2,
        lv_line   TYPE string.

  ev_total = 0.

  LOOP AT it_items INTO lv_line.
    CASE lv_line(1).
      WHEN 'A'.
        lv_amount = 123.45.    " magic number
        lv_tax    = lv_amount * 20 / 100. " magic numbers 20, 100
      WHEN 'B'.
        lv_amount = 250.
        lv_tax    = 0.
      WHEN OTHERS.
        lv_amount = 0.
        lv_tax    = 0.
    ENDCASE.

    ev_total = ev_total + lv_amount + lv_tax.
  ENDLOOP.

ENDFORM.

* Start of selection
START-OF-SELECTION.
  PERFORM load_data.
  WRITE: / 'Processing complete. Count:', gv_count.
"""
