"""Parses pdflatex/latexmk log output into structured error/warning diagnostics.

LaTeX logs track the currently-processing file via a stack of parentheses:
"(./chapter.tex ... )" wraps everything logged while that file is being read,
including nested package/class loads. We replicate that paren-nesting to
attribute each diagnostic to the file it actually occurred in (relevant for
multi-file projects using \\input/\\include), not just the root document.

This is a heuristic, not a full parser of the log grammar — good enough for
the common cases, not bulletproof against pathological input.
"""

import re
from dataclasses import dataclass

FILE_OPEN_RE = re.compile(r"\((\.?/?[\w./\-]+\.(?:tex|sty|cls|cfg|def|clo|bbl))")
LINE_RE = re.compile(r"^l\.(\d+)")
INPUT_LINE_RE = re.compile(r"on input line (\d+)")
HBOX_LINES_RE = re.compile(r"at lines (\d+)(?:--(\d+))?")


@dataclass
class Diagnostic:
    severity: str  # "error" | "warning"
    file: str | None
    line: int | None
    message: str
    context: str  # the relevant excerpt from the log — not the whole transcript


def _capture_error_context(lines: list[str], start: int, lookahead: int = 15) -> tuple[int | None, str]:
    """From a "! " line, collect just the lines TeX printed for this specific
    error — through the "l.<N> ..." source excerpt and one line past it —
    instead of the whole rest of the transcript. Returns (line number, excerpt)."""
    end = min(start + lookahead, len(lines))
    collected = [lines[start]]
    lineno = None
    for j in range(start + 1, end):
        line = lines[j]
        if line.startswith("! ") :
            break
        collected.append(line)
        match = LINE_RE.match(line)
        if match:
            lineno = int(match.group(1))
            if j + 1 < end:
                collected.append(lines[j + 1])
            break
    return lineno, "\n".join(collected).rstrip()


def _current_file(stack: list[str | None]) -> str | None:
    for entry in reversed(stack):
        if entry is not None:
            return entry
    return None


def _track_parens(line: str, stack: list[str | None]) -> None:
    pos = 0
    while pos < len(line):
        ch = line[pos]
        if ch == "(":
            match = FILE_OPEN_RE.match(line, pos)
            if match:
                raw = match.group(1)
                stack.append(raw[2:] if raw.startswith("./") else raw)
                pos = match.end()
                continue
            stack.append(None)
        elif ch == ")":
            if stack:
                stack.pop()
        pos += 1


def parse_log(log: str) -> list[Diagnostic]:
    lines = log.splitlines()
    diagnostics: list[Diagnostic] = []
    file_stack: list[str | None] = []

    for i, line in enumerate(lines):
        if line.startswith("! "):
            message = line[2:].strip()
            if not message.startswith("=="):
                lineno, context = _capture_error_context(lines, i)
                diagnostics.append(Diagnostic(
                    severity="error",
                    file=_current_file(file_stack),
                    line=lineno,
                    message=message,
                    context=context,
                ))
        elif "Warning:" in line:
            idx = line.index("Warning:")
            prefix = line[:idx].strip()
            msg = line[idx + len("Warning:") :].strip()
            match = INPUT_LINE_RE.search(msg)
            diagnostics.append(Diagnostic(
                severity="warning",
                file=_current_file(file_stack),
                line=int(match.group(1)) if match else None,
                message=f"{prefix}: {msg}" if prefix else msg,
                context=line.strip(),
            ))
        elif line.startswith(("Overfull \\hbox", "Underfull \\hbox", "Overfull \\vbox", "Underfull \\vbox")):
            match = HBOX_LINES_RE.search(line)
            diagnostics.append(Diagnostic(
                severity="warning",
                file=_current_file(file_stack),
                line=int(match.group(1)) if match else None,
                message=line.strip(),
                context=line.strip(),
            ))

        _track_parens(line, file_stack)

    return diagnostics
