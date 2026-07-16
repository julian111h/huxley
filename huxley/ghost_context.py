"""Builds a focused prompt for ghost-text autocomplete.

Rather than sending the whole document (slow, and drowns the model in
irrelevant text), pull out just what's relevant: the project's preamble
(packages/macros) and title/abstract from the root document, plus the
current section heading and the last few paragraphs from wherever the user
is actually typing. Keeps the prompt to a few thousand characters regardless
of how large the surrounding document is.
"""

import re
from dataclasses import dataclass

_TITLE_RE = re.compile(r"\\title\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)
_SECTION_RE = re.compile(r"\\(chapter|section|subsection|subsubsection)\*?\{([^{}]*)\}")
_MACRO_LINE_RE = re.compile(r"^\s*\\(usepackage|newcommand|renewcommand|DeclareMathOperator)\b")

PREAMBLE_CHAR_LIMIT = 2000
PARAGRAPH_CHAR_LIMIT = 2000
SUFFIX_CHAR_LIMIT = 500
PREVIOUS_PARAGRAPH_COUNT = 3


@dataclass
class GhostContext:
    preamble: str
    title: str
    abstract: str
    section: str
    previous_paragraphs: str
    current_paragraph: str
    suffix: str


def _extract_preamble_bits(main_text: str) -> tuple[str, str, str]:
    body_start = main_text.find(r"\begin{document}")
    preamble = main_text[:body_start] if body_start != -1 else main_text

    title_match = _TITLE_RE.search(main_text)
    title = title_match.group(1).strip() if title_match else ""

    abstract_match = _ABSTRACT_RE.search(main_text)
    abstract = abstract_match.group(1).strip() if abstract_match else ""

    if len(preamble) > PREAMBLE_CHAR_LIMIT:
        # Too big to send whole — keep just the lines that actually define
        # packages/macros, which is what a completion needs to stay consistent.
        macro_lines = [line for line in preamble.splitlines() if _MACRO_LINE_RE.match(line)]
        preamble = "\n".join(macro_lines)[:PREAMBLE_CHAR_LIMIT]

    return preamble, title, abstract


def _last_section_heading(prefix: str) -> str:
    matches = list(_SECTION_RE.finditer(prefix))
    return matches[-1].group(2).strip() if matches else ""


def _split_paragraphs(prefix: str) -> tuple[str, str]:
    """(previous paragraphs, current paragraph) — current is whatever's
    after the last blank line, i.e. a possibly-unfinished sentence."""
    parts = re.split(r"\n\s*\n", prefix)
    current = parts[-1] if parts else ""
    previous = parts[max(0, len(parts) - 1 - PREVIOUS_PARAGRAPH_COUNT) : -1]
    previous_text = "\n\n".join(previous)
    if len(previous_text) > PARAGRAPH_CHAR_LIMIT:
        previous_text = previous_text[-PARAGRAPH_CHAR_LIMIT:]
    return previous_text, current


def build_context(main_text: str | None, prefix: str, suffix: str) -> GhostContext:
    preamble, title, abstract = _extract_preamble_bits(main_text) if main_text else ("", "", "")
    previous_paragraphs, current_paragraph = _split_paragraphs(prefix)
    return GhostContext(
        preamble=preamble,
        title=title,
        abstract=abstract,
        section=_last_section_heading(prefix),
        previous_paragraphs=previous_paragraphs,
        current_paragraph=current_paragraph,
        suffix=suffix[:SUFFIX_CHAR_LIMIT],
    )


def build_prompt(context: GhostContext, use_suffix: bool = True) -> str:
    """The only place that knows about prefix-only vs. fill-in-the-middle —
    everything upstream (context building) and downstream (the actual model
    call) is unaffected by which mode is active here."""
    parts = []
    if context.preamble:
        parts.append(f"Document preamble:\n{context.preamble}")
    if context.title:
        parts.append(f"Title: {context.title}")
    if context.abstract:
        parts.append(f"Abstract: {context.abstract}")
    if context.section:
        parts.append(f"Current section: {context.section}")
    if context.previous_paragraphs:
        parts.append(f"Preceding text:\n{context.previous_paragraphs}")

    if use_suffix and context.suffix:
        parts.append(f"Text so far in this paragraph (continue at <CURSOR>):\n{context.current_paragraph}<CURSOR>{context.suffix}")
    else:
        parts.append(f"Text so far in this paragraph:\n{context.current_paragraph}<CURSOR>")

    return "\n\n".join(parts)
