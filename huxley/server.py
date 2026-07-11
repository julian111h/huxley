"""FastAPI app: project tree, file read/save, compile, websocket status, and static UI serving."""

import asyncio
import shutil
from dataclasses import asdict
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from watchfiles import DefaultFilter, awatch

from huxley import ai
from huxley import settings as settings_store
from huxley.compiler import compile_tex
from huxley.grammar import check_text
from huxley.log_parser import Diagnostic, parse_log
from huxley.synctex import forward_search, inverse_search

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Source extensions that should trigger a recompile when changed on disk.
SOURCE_EXTENSIONS = {".tex", ".bib", ".sty", ".cls", ".bst"}

app = FastAPI()
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

# Populated by main.py (and /api/open-folder) before/while the server runs.
# main_file is the compile target (the project's root .tex document) — it only
# changes when the project root changes, never just from browsing/viewing a file.
state: dict[str, Path | None] = {"root": None, "main_file": None}

_watch_task: asyncio.Task | None = None
_compile_lock = asyncio.Lock()
_sockets: set[WebSocket] = set()


class WatchFilter(DefaultFilter):
    def __init__(self):
        super().__init__(ignore_dirs=(*DefaultFilter.ignore_dirs, "build"))


def _resolve_in_root(rel_path: str) -> Path:
    root = state["root"]
    candidate = (root / rel_path).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(400, "Path escapes project root")
    return candidate


def find_initial_tex(root: Path) -> Path | None:
    top_level = root / "main.tex"
    if top_level.exists():
        return top_level
    matches = sorted(root.rglob("*.tex"))
    return matches[0] if matches else None


async def _broadcast(message: dict):
    dead = set()
    for ws in _sockets:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    _sockets.difference_update(dead)


def _relativize(diagnostic: Diagnostic, compile_dir: Path, root: Path) -> Diagnostic:
    if diagnostic.file is None:
        return diagnostic
    try:
        relative = (compile_dir / diagnostic.file).resolve().relative_to(root)
    except ValueError:
        return Diagnostic(diagnostic.severity, None, diagnostic.line, diagnostic.message)
    return Diagnostic(diagnostic.severity, str(relative), diagnostic.line, diagnostic.message)


async def _compile_and_broadcast():
    tex_path = state["main_file"]
    if tex_path is None or tex_path.suffix != ".tex":
        return
    async with _compile_lock:
        await _broadcast({"status": "compiling"})
        result = await compile_tex(tex_path)
        diagnostics = [
            _relativize(d, tex_path.parent, state["root"])
            for d in parse_log(result.log)
        ]
        await _broadcast({
            "status": "ok" if result.success else "error",
            "log": result.log,
            "diagnostics": [asdict(d) for d in diagnostics],
        })


async def _watch_root(root: Path):
    async for changes in awatch(root, watch_filter=WatchFilter(), debounce=400):
        if any(Path(path).suffix in SOURCE_EXTENSIONS for _change, path in changes):
            await _compile_and_broadcast()


def set_root(root: Path):
    global _watch_task
    state["root"] = root
    state["main_file"] = find_initial_tex(root)
    if _watch_task is not None:
        _watch_task.cancel()
    _watch_task = asyncio.get_running_loop().create_task(_watch_root(root))


@app.on_event("startup")
async def _on_startup():
    if state["root"] is not None:
        set_root(state["root"])
    # LanguageTool's first check spins up a local Java server (a few seconds) —
    # do that now in the background so the user's first keystroke isn't the one
    # that pays for it.
    language = settings_store.load_settings()["grammar_language"]
    asyncio.get_running_loop().create_task(check_text("", language))


class SaveBody(BaseModel):
    path: str
    content: str


class OpenFolderBody(BaseModel):
    path: str


class ForwardSearchBody(BaseModel):
    path: str
    line: int


class InverseSearchBody(BaseModel):
    page: int
    x: float
    y: float


class SettingsBody(BaseModel):
    ai_base_url: str | None = None
    chat_model: str | None = None
    autocomplete_model: str | None = None
    autocomplete_enabled: bool | None = None
    grammar_enabled: bool | None = None
    grammar_language: str | None = None


class ExplainBody(BaseModel):
    message: str
    log: str = ""


class CompleteBody(BaseModel):
    prefix: str
    suffix: str = ""


class GrammarCheckBody(BaseModel):
    text: str


class RenameBody(BaseModel):
    path: str
    new_name: str


class CreateFileBody(BaseModel):
    path: str


class DeleteFileBody(BaseModel):
    path: str


class ImproveBody(BaseModel):
    text: str


def _pdf_path() -> Path:
    tex_path = state["main_file"]
    if tex_path is None:
        raise HTTPException(404, "No file open")
    pdf_path = tex_path.parent / "build" / f"{tex_path.stem}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "PDF not compiled yet")
    return pdf_path


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


def _build_tree(dir_path: Path) -> list[dict]:
    entries = []
    for child in sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if child.name.startswith(".") or child.name in ("build", "__pycache__"):
            continue
        entries.append({
            "name": child.name,
            "path": str(child.relative_to(state["root"])),
            "type": "dir" if child.is_dir() else "file",
        })
    return entries


@app.get("/api/tree")
def get_tree(path: str = ""):
    dir_path = _resolve_in_root(path) if path else state["root"]
    if not dir_path.is_dir():
        raise HTTPException(404, "Not a directory")
    return _build_tree(dir_path)


@app.get("/api/status")
def get_status():
    main_file = state["main_file"]
    return {
        "root": str(state["root"]),
        "main_file": str(main_file.relative_to(state["root"])) if main_file else None,
    }


@app.get("/api/file")
def get_file(path: str):
    file_path = _resolve_in_root(path)
    if not file_path.is_file():
        raise HTTPException(404, "No such file")
    try:
        content = file_path.read_text()
    except UnicodeDecodeError:
        raise HTTPException(415, "Not a text file")
    return {"path": path, "content": content}


@app.post("/api/save")
def save_file(body: SaveBody):
    file_path = _resolve_in_root(body.path)
    file_path.write_text(body.content)
    return {"ok": True}


@app.post("/api/file/create")
def create_file(body: CreateFileBody):
    new_path = _resolve_in_root(body.path)
    if new_path.exists():
        raise HTTPException(409, "A file with that name already exists")
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.touch()
    return {"path": body.path}


@app.post("/api/file/rename")
def rename_file(body: RenameBody):
    new_name = body.new_name.strip()
    if not new_name or "/" in new_name or "\\" in new_name:
        raise HTTPException(400, "Invalid name")
    old_path = _resolve_in_root(body.path)
    if not old_path.exists():
        raise HTTPException(404, "No such file or folder")
    new_path = old_path.parent / new_name
    if new_path.exists():
        raise HTTPException(409, "A file or folder with that name already exists")
    old_path.rename(new_path)

    main_file = state["main_file"]
    if main_file is not None:
        if main_file == old_path:
            state["main_file"] = new_path
        elif old_path in main_file.parents:
            state["main_file"] = new_path / main_file.relative_to(old_path)

    return {"path": str(new_path.relative_to(state["root"])), "type": "dir" if new_path.is_dir() else "file"}


@app.post("/api/file/delete")
def delete_file(body: DeleteFileBody):
    target = _resolve_in_root(body.path)
    if not target.exists():
        raise HTTPException(404, "No such file or folder")

    main_file = state["main_file"]
    main_file_affected = main_file is not None and (main_file == target or target in main_file.parents)

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    if main_file_affected:
        state["main_file"] = find_initial_tex(state["root"])
    return {"ok": True}


@app.post("/api/compile")
async def compile_current():
    await _compile_and_broadcast()
    return {"ok": True}


@app.get("/api/pdf")
def get_pdf():
    return FileResponse(_pdf_path(), media_type="application/pdf")


@app.post("/api/synctex/forward")
async def synctex_forward(body: ForwardSearchBody):
    source_path = _resolve_in_root(body.path)
    result = await forward_search(source_path, body.line, _pdf_path())
    if result is None:
        raise HTTPException(404, "No SyncTeX match for that location")
    return {"page": result.page, "x": result.x, "y": result.y, "width": result.width, "height": result.height}


@app.post("/api/synctex/inverse")
async def synctex_inverse(body: InverseSearchBody):
    result = await inverse_search(body.page, body.x, body.y, _pdf_path())
    if result is None:
        raise HTTPException(404, "No SyncTeX match for that location")
    try:
        relative = result.file.resolve().relative_to(state["root"])
    except ValueError:
        raise HTTPException(404, "Matched file is outside the project root")
    return {"path": str(relative), "line": result.line}


@app.post("/api/open-folder")
async def open_folder(body: OpenFolderBody):
    root = Path(body.path).resolve()
    if not root.is_dir():
        raise HTTPException(400, "Not a directory")
    set_root(root)
    return {"ok": True}


@app.get("/api/settings")
def get_settings():
    return settings_store.load_settings()


@app.post("/api/settings")
def update_settings(body: SettingsBody):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    return settings_store.save_settings(updates)


@app.get("/api/ai/models")
async def ai_models():
    base_url = settings_store.load_settings()["ai_base_url"]
    try:
        return {"models": await ai.list_models(base_url)}
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Could not reach {base_url}: {exc}")


@app.post("/api/ai/explain")
async def ai_explain(body: ExplainBody):
    settings = settings_store.load_settings()
    model = settings["chat_model"]
    if not model:
        raise HTTPException(400, "No chat model configured — set one in Settings")
    try:
        explanation = await ai.explain_error(settings["ai_base_url"], model, body.message, body.log)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"AI request failed: {exc}")
    return {"explanation": explanation}


@app.post("/api/ai/complete")
async def ai_complete(body: CompleteBody):
    settings = settings_store.load_settings()
    if not settings["autocomplete_enabled"]:
        return {"completion": ""}
    model = settings["autocomplete_model"] or settings["chat_model"]
    if not model:
        return {"completion": ""}
    try:
        completion = await ai.ghost_completion(settings["ai_base_url"], model, body.prefix, body.suffix)
    except httpx.HTTPError:
        return {"completion": ""}
    return {"completion": completion}


@app.post("/api/ai/improve")
async def ai_improve(body: ImproveBody):
    settings = settings_store.load_settings()
    model = settings["chat_model"]
    if not model:
        raise HTTPException(400, "No chat model configured — set one in Settings")
    try:
        improved = await ai.improve_text(settings["ai_base_url"], model, body.text)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"AI request failed: {exc}")
    return {"improved": improved}


@app.post("/api/grammar/check")
async def grammar_check(body: GrammarCheckBody):
    settings = settings_store.load_settings()
    if not settings["grammar_enabled"]:
        return {"matches": []}
    matches = await check_text(body.text, settings["grammar_language"])
    return {"matches": matches}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _sockets.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _sockets.discard(websocket)
