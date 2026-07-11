"""latexmk wrapper: compiles a .tex file and reports success/failure + log."""

import asyncio
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompileResult:
    success: bool
    pdf_path: Path | None
    log: str


async def compile_tex(tex_path: Path, engine: str = "pdflatex") -> CompileResult:
    """Run latexmk on tex_path, writing artifacts to a build/ subdir next to it."""
    tex_path = tex_path.resolve()
    build_dir = tex_path.parent / "build"
    build_dir.mkdir(exist_ok=True)

    engine_flag = {
        "pdflatex": "-pdf",
        "lualatex": "-lualatex",
        "xelatex": "-xelatex",
    }[engine]

    proc = await asyncio.create_subprocess_exec(
        "latexmk",
        engine_flag,
        "-synctex=1",
        "-interaction=nonstopmode",
        "-halt-on-error",
        # Force a real rerun every time. Without this, if two compiles get
        # triggered back-to-back for the same save (the file watcher and an
        # explicit Compile click both fire), latexmk decides the second one
        # is a no-op and returns a terse "Nothing to do" log with none of the
        # actual diagnostics — which then overwrites the correct error list
        # in the UI with an empty one.
        "-g",
        f"-outdir={build_dir}",
        tex_path.name,
        cwd=tex_path.parent,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    log = stdout.decode("utf-8", errors="replace")

    pdf_path = build_dir / f"{tex_path.stem}.pdf"
    success = proc.returncode == 0 and pdf_path.exists()
    return CompileResult(success=success, pdf_path=pdf_path if success else None, log=log)
