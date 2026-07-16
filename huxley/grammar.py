"""Grammar checking via a local LanguageTool server (language_tool_python spawns
and manages one on first use — downloads LanguageTool itself the first time,
then reuses the running local Java process for every check after that).

LaTeX source is masked before checking: markup is blanked out to whitespace of
the *same length* so LanguageTool's returned offsets stay valid positions in
the original, unmodified text — no separate offset-mapping table needed.
"""

import asyncio
import re

import language_tool_python

_tools: dict[str, language_tool_python.LanguageTool] = {}

_MATH_ENV_RE = re.compile(
    r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?|displaymath)\}.*?\\end\{\1\}",
    re.DOTALL,
)
_INLINE_MATH_RE = re.compile(r"\$\$.*?\$\$|\$[^$]*\$|\\\[.*?\\\]|\\\(.*?\\\)", re.DOTALL)
_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_ESCAPED_CHAR_RE = re.compile(r"\\[%&_#${}]")

# Commands whose argument is a technical identifier (package/file/label name,
# not prose) — blank the whole call, argument included, not just the command
# name, so e.g. "amsmath" in \usepackage{amsmath} isn't checked as a word.
# Covers both document-preamble commands and package/class-authoring commands
# (.sty/.cls files consist almost entirely of these).
_TECHNICAL_COMMAND_RE = re.compile(
    r"\\(usepackage|documentclass|input|include|includegraphics|label|ref|eqref|pageref|"
    r"cite\w*|bibliography\w*|bibliographystyle|url|href|newcommand|renewcommand|"
    r"newenvironment|renewenvironment|providecommand|"
    r"ProvidesPackage|ProvidesClass|ProvidesFile|NeedsTeXFormat|RequirePackage|"
    r"DeclareOption|ProcessOptions|ExecuteOptions|"
    r"pagestyle|thispagestyle|newcounter|setcounter|usecounter|"
    r"newlength|setlength|addtolength|"
    r"definecolor|colorlet|graphicspath|hypersetup|geometry|"
    r"counterwithin\*?|numberwithin)\*?"
    r"(\[[^\]]*\])?(\{[^{}]*\})?(\{[^{}]*\})?(\[[^\]]*\])?",
)
_COMMAND_RE = re.compile(r"\\[a-zA-Z]+\*?")
_BRACKET_RE = re.compile(r"[{}\[\]]")


def strip_latex_preserve_offsets(text: str) -> tuple[str, list[bool]]:
    """Returns the masked text plus a same-length "was this character part of
    blanked-out markup" array, so callers can tell a real prose match from one
    that only exists because e.g. a blanked comment reads as a run of spaces."""
    masked = [False] * len(text)

    def blank(pattern: re.Pattern, s: str) -> str:
        def repl(m: re.Match) -> str:
            for i in range(m.start(), m.end()):
                masked[i] = True
            return " " * len(m.group(0))
        return pattern.sub(repl, s)

    text = blank(_MATH_ENV_RE, text)
    text = blank(_INLINE_MATH_RE, text)
    text = blank(_COMMENT_RE, text)
    text = blank(_ESCAPED_CHAR_RE, text)
    text = blank(_TECHNICAL_COMMAND_RE, text)
    text = blank(_COMMAND_RE, text)
    text = blank(_BRACKET_RE, text)
    return text, masked


def _get_tool(language: str) -> language_tool_python.LanguageTool:
    if language not in _tools:
        _tools[language] = language_tool_python.LanguageTool(language)
    return _tools[language]


def _check_sync(text: str, language: str) -> list[dict]:
    stripped, masked = strip_latex_preserve_offsets(text)
    matches = _get_tool(language).check(stripped)
    results = []
    for m in matches:
        start, end = m.offset, m.offset + m.error_length
        # Skip matches that fall (even partially) inside blanked-out markup —
        # e.g. a long blanked comment reading as "repeated whitespace" to
        # LanguageTool. That's a masking artifact, not a real prose issue.
        if any(masked[start:end]):
            continue
        results.append({
            "offset": m.offset,
            "length": m.error_length,
            "message": m.message,
            "replacements": m.replacements[:5],
            "rule_id": m.rule_id,
        })
    return results


async def check_text(text: str, language: str) -> list[dict]:
    return await asyncio.to_thread(_check_sync, text, language)
