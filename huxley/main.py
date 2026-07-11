"""Entry point: starts the FastAPI backend in a thread, then opens the pywebview window."""

import os
import sys
import threading
from pathlib import Path

# WebKitGTK's DMA-BUF renderer crashes the compositor connection on some Wayland
# setups (Hyprland included) with "Error 71 (Protocol error)". Must be set before
# WebKit's process launches.
os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

# Sets WM_CLASS (X11) / app_id (Wayland) so compositor rules (e.g. Hyprland) can match this window.
GLib.set_prgname("huxley")

import uvicorn
import webview

from huxley import server

HOST = "127.0.0.1"
PORT = 8471


class Api:
    """Methods exposed to the frontend as window.pywebview.api.* — native dialogs
    have to go through pywebview since the webview process can't show its own."""

    def open_folder(self):
        result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent / "sample"


def run():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else _default_root()
    if not root.is_dir():
        raise SystemExit(f"No such directory: {root}")
    server.state["root"] = root

    config = uvicorn.Config(server.app, host=HOST, port=PORT, log_level="warning")
    uv_server = uvicorn.Server(config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()

    webview.create_window(
        "Huxley",
        f"http://{HOST}:{PORT}/",
        width=1400,
        height=900,
        background_color="#0a0f19",
        js_api=Api(),
    )
    webview.start()


if __name__ == "__main__":
    run()
