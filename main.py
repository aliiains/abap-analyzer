"""
main.py — Application entry point.

Wires up all collaborators (parser, calculator, formatter) and starts
the Tkinter event loop.  Follows Dependency Inversion: App receives
injected collaborators — no hard-coded imports inside App itself.

Usage
-----
    python main.py
"""

from __future__ import annotations

import sys
import tkinter as tk


def main() -> None:
    """Create the root Tk window, inject dependencies, and start the loop."""

    # Import collaborators here so main.py owns the wiring
    from gui import App
    from metrics import ExtendedMetricsCalculator
    from parser import AbapParser
    from report import TextReportFormatter

    root = tk.Tk()

    # Dependency injection — swap any component without touching App
    parser     = AbapParser(long_line_limit=120)
    calculator = ExtendedMetricsCalculator()   # includes extra metrics
    formatter  = TextReportFormatter(
        use_unicode_symbols=True,
        include_timestamp=True,
    )

    app = App(
        root=root,
        parser=parser,
        calculator=calculator,
        formatter=formatter,
    )

    # Centre the window on screen
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.mainloop()


if __name__ == "__main__":
    main()
