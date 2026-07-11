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
_TECHNICAL_COMMAND_RE = re.compile(
    r"\\(usepackage|documentclass|input|include|includegraphics|label|ref|eqref|pageref|"
    r"cite\w*|bibliography\w*|url|href|newcommand|renewcommand)\*?"
    r"(\[[^\]]*\])?(\{[^{}]*\})?(\[[^\]]*\])?",
)
_COMMAND_RE = re.compile(r"\\[a-zA-Z]+\*?")
_BRACKET_RE = re.compile(r"[{}\[\]]")


def _blank(match: re.Match) -> str:
    return " " * len(match.group(0))


def strip_latex_preserve_offsets(text: str) -> str:
    text = _MATH_ENV_RE.sub(_blank, text)
    text = _INLINE_MATH_RE.sub(_blank, text)
    text = _COMMENT_RE.sub(_blank, text)
    text = _ESCAPED_CHAR_RE.sub(_blank, text)
    text = _TECHNICAL_COMMAND_RE.sub(_blank, text)
    text = _COMMAND_RE.sub(_blank, text)
    text = _BRACKET_RE.sub(" ", text)
    return text


def _get_tool(language: str) -> language_tool_python.LanguageTool:
    if language not in _tools:
        _tools[language] = language_tool_python.LanguageTool(language)
    return _tools[language]


_LATEX_CONTROL_CHARS = set("\\{}[]$")


def _check_sync(text: str, language: str) -> list[dict]:
    stripped = strip_latex_preserve_offsets(text)
    matches = _get_tool(language).check(stripped)
    results = []
    for m in matches:
        span = text[m.offset : m.offset + m.error_length]
        # Skip matches against blanked-out markup (e.g. "repeated whitespace"
        # where a command name used to be) — an artifact of the masking, not
        # a real prose issue.
        if any(ch in _LATEX_CONTROL_CHARS for ch in span):
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
