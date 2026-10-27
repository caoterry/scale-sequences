# SPDX-License-Identifier: MIT
"""Repository hygiene: no machine-specific paths in shipped files, public text in English only; the plugin
manifests agree."""
import json
import re

from conftest import REPO

SKIP_DIRS = {"node_modules", "__pycache__", ".venv", ".pytest_cache", ".ruff_cache", ".git"}
TEXT = {".py", ".md", ".json", ".txt", ".mjs", ".ini", ".lock", ".toml", ".cfg", ".yml", ".yaml"}
HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/|\b[A-Za-z]:\\(?:Users)\\")
# CJK radicals through unified ideographs (punctuation, kana, bopomofo, extension A), Hangul, compatibility
# ideographs and forms, full-width forms, ideograph extensions B and later
CJK = re.compile("[\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef\U00020000-\U0003ffff]")


def _shipped_text_files():
    for p in sorted(REPO.rglob("*")):
        rel = p.relative_to(REPO)
        if p.is_file() and not SKIP_DIRS & set(rel.parts) and (p.suffix in TEXT or p.name in {"LICENSE", ".gitignore"}):
            yield p, rel


def test_no_home_directory_paths():
    bad = [f"{rel}:{n}" for p, rel in _shipped_text_files()
           for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1) if HOME_PATH.search(line)]
    assert not bad, "machine-specific paths:\n" + "\n".join(bad)


def test_shipped_text_is_english_only():
    """Public text is English only -- the skill's trigger words included."""
    bad = [f"{rel}:{n}: {line.strip()[:80]}" for p, rel in _shipped_text_files()
           for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1) if CJK.search(line)]
    assert not bad, "non-English text:\n" + "\n".join(bad)


def test_plugin_manifests_agree():
    plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert plugin["name"] == "scale-sequences" and plugin["license"] == "MIT"
    assert [p["name"] for p in market["plugins"]] == [plugin["name"]]
    assert (REPO / "skills" / plugin["name"] / "SKILL.md").is_file()
