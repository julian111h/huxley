"""User settings, persisted as JSON under XDG_CONFIG_HOME (~/.config/huxley)."""

import json
import os
from pathlib import Path

DEFAULTS = {
    "ai_base_url": "http://localhost:11434/v1",
    "chat_model": "",
    "autocomplete_model": "",
    "autocomplete_enabled": True,
    "grammar_enabled": True,
    "grammar_language": "en-US",
}


def _config_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "huxley" / "settings.json"


def load_settings() -> dict:
    path = _config_path()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        stored = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    return {**DEFAULTS, **stored}


def save_settings(settings: dict) -> dict:
    merged = {**load_settings(), **settings}
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2))
    return merged
