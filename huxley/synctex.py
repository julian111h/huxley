"""Wraps the `synctex` CLI for forward (source -> PDF) and inverse (PDF -> source) search.

Coordinates are PDF points (1/72in), origin at the page's top-left, matching
both `synctex`'s own convention and PDF.js's viewport convention at scale=1 —
so the frontend only needs to divide/multiply by its render scale, no axis flips.
"""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ForwardResult:
    page: int
    x: float
    y: float
    width: float
    height: float


@dataclass
class InverseResult:
    file: Path
    line: int


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "synctex", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode("utf-8", errors="replace")


async def forward_search(source: Path, line: int, pdf: Path) -> ForwardResult | None:
    output = await _run("view", "-i", f"{line}:0:{source}", "-o", str(pdf))
    for block in output.split("Output:"):
        page = re.search(r"Page:(\d+)", block)
        x = re.search(r"^x:([\d.\-]+)", block, re.MULTILINE)
        y = re.search(r"^y:([\d.\-]+)", block, re.MULTILINE)
        w = re.search(r"^W:([\d.\-]+)", block, re.MULTILINE)
        h = re.search(r"^H:([\d.\-]+)", block, re.MULTILINE)
        if page and x and y:
            return ForwardResult(
                page=int(page.group(1)),
                x=float(x.group(1)),
                y=float(y.group(1)),
                width=float(w.group(1)) if w else 0.0,
                height=float(h.group(1)) if h else 12.0,
            )
    return None


async def inverse_search(page: int, x: float, y: float, pdf: Path) -> InverseResult | None:
    output = await _run("edit", "-o", f"{page}:{x}:{y}:{pdf}")
    input_match = re.search(r"^Input:(.+)$", output, re.MULTILINE)
    line_match = re.search(r"^Line:(\d+)", output, re.MULTILINE)
    if not input_match or not line_match:
        return None
    return InverseResult(file=Path(input_match.group(1).strip()), line=int(line_match.group(1)))
