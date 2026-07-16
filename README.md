# Huxley.

A local, desktop LaTeX editor built as a replacement for Overleaf — no compile
timeouts, no cloud, no telemetry. Everything runs on your machine, including
the optional AI features, which talk only to a local model server you point
it at (e.g. [Ollama](https://ollama.com)).

![Screenshot](huxley/samples/figures/20260711_155419.png)

## Features

- **Editor** — CodeMirror 6 with LaTeX syntax highlighting, a file tree
  sidebar (create/rename/delete files and folders via right-click), and a
  draggable split between the editor and PDF preview.
- **Compile** — runs `latexmk` on clicking "compile" or on
  save (Ctrl+S), no timeout. Compile artifacts go to a `build/`
  subdirectory, kept out of your source tree.
- **Diagnostics** — compile errors and warnings are parsed out of the log
  into a clickable list (jump straight to the offending line, even across
  `\input`/`\include`d files), plus the full raw log in a copyable text box
  for pasting into a search engine.
- **SyncTeX** — click a line in the source to jump to that spot in the
  rendered PDF (Ctrl+Click), or click the PDF to jump back to the source.
- **AI (optional, fully local)** — point Huxley at any OpenAI-compatible
  endpoint (Ollama, llama.cpp server, etc.) and it will:
  - explain a compile error in plain language,
  - offer inline ghost-text autocomplete as you type (toggle in Settings;
    use a small, fast, non-reasoning model for this one),
  - rewrite a selected paragraph on request, with a diff-style preview
    before anything is applied.
- **Grammar checking** — prose is checked locally via
  [LanguageTool](https://languagetool.org/); issues get a
  wavy underline with one-click suggestions. LaTeX markup is stripped out
  before checking so package names and commands aren't flagged as typos.

No feature here calls out to the network except to whatever local AI
endpoint you configure in Settings.

## Requirements

Huxley shells out to a few external tools rather than bundling them:

| Tool | Used for | Install |
|---|---|---|
| Python 3.10+ | running Huxley itself | — |
| A TeX distribution (`latexmk`, `pdflatex`, `synctex`) | compiling and SyncTeX | TeX Live / MacTeX / MiKTeX |
| Java | LanguageTool's local grammar server (auto-downloaded on first use) | any recent JRE |
| [Ollama](https://ollama.com) or another local OpenAI-compatible server | AI features (optional — everything else works without it) | — |

On Fedora: `sudo dnf install latexmk synctex java-latest-openjdk`.

Huxley currently targets **Linux** (developed against Hyprland/Wayland +
WebKitGTK, via [pywebview](https://pywebview.flowrl.com/)). The only
Linux-specific code is a small window-class hint in `huxley/main.py` used for
compositor window rules — pywebview itself supports macOS and Windows, so
porting should mostly be a matter of guarding that one import.

## Install

```bash
git clone https://github.com/julian111h/huxley.git
cd huxley
uv venv .venv --system-site-packages   # --system-site-packages picks up system PyGObject/GTK
uv pip install -e . --python .venv/bin/python
```

(`--system-site-packages` matters because `pywebview`'s GTK backend needs
`PyGObject`, which is easiest to get from your distro's package manager
rather than pip.)

## Usage

```bash
.venv/bin/huxley                 # opens the sample project
.venv/bin/huxley path/to/project # opens a specific folder
```

Or use **Open Folder…** in the sidebar to switch projects without
restarting. A project is just a directory — Huxley looks for `main.tex` at
the top level, falling back to the first `.tex` file it finds, and treats
that as the compile target (marked with a ★ in the file tree) regardless of
which file you're currently viewing.

**Shortcuts**

| Action | Shortcut |
|---|---|
| Save + compile | Ctrl+S, or the Compile button |
| Jump source → PDF | Ctrl+Click a line in the editor |
| Jump PDF → source | Click text in the PDF |
| Accept ghost-text suggestion | Tab |
| Dismiss ghost-text suggestion | Esc |

Settings (AI endpoint, model selection, autocomplete/grammar toggles) live
behind the gear icon in the top bar and persist to
`~/.config/huxley/settings.json`.

## Architecture

```
huxley/
├── huxley/
│   ├── main.py       # entry point: FastAPI (background thread) + pywebview window
│   ├── server.py      # routes: files, compile, synctex, settings, AI, grammar; WebSocket status
│   ├── compiler.py    # latexmk wrapper
│   ├── log_parser.py  # latexmk/pdflatex log -> structured diagnostics
│   ├── synctex.py     # wraps the `synctex` CLI for forward/inverse search
│   ├── ai.py           # thin OpenAI-compatible client
│   ├── grammar.py     # LanguageTool wrapper + LaTeX-aware text stripping
│   └── settings.py    # settings persistence (~/.config/huxley)
├── web/                # plain HTML/CSS/JS frontend (CodeMirror 6 + PDF.js, vendored — no CDN)
└── sample/             # a small multi-file LaTeX project, opened by default
```

The backend is FastAPI running in-process alongside the pywebview window; the
frontend is plain JS talking to it over HTTP + a WebSocket for compile
status. No build step for the frontend — the CodeMirror bundle in
`web/vendor/` is pre-built with esbuild and checked in.


## License

[MIT](LICENSE)
