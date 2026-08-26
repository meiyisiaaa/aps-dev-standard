"""AI Project Standard CLI."""
from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path


def _read_cli_version() -> str:
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    if version_file.is_file():
        values = {}
        for line in version_file.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key.strip()] = value.strip()
        if values.get("APS_CLI"):
            return values["APS_CLI"]
    try:
        return package_version("ai-project-standard-cli")
    except PackageNotFoundError as exc:
        raise RuntimeError("APS CLI version metadata is unavailable") from exc


def _read_standard_version() -> str:
    manifest = Path(__file__).resolve().parent / "bundle" / "package-manifest.json"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))["version"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError("AI Project Standard manifest is unavailable") from exc
    if not isinstance(value, str) or not value:
        raise RuntimeError("AI Project Standard manifest has no version")
    return value


__version__ = _read_cli_version()
STANDARD_VERSION = _read_standard_version()
