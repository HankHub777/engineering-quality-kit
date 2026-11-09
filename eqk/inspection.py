"""`eqk inspect`: read-only detection of languages, existing quality config, CI and tools."""

from __future__ import annotations

import configparser
import json
from fnmatch import fnmatch
from pathlib import Path

from . import profiles as profiles_mod
from .util import git_state, resolve_tool, walk_files

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.9/3.10 fallback
    tomllib = None  # type: ignore[assignment]


def _toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    if tomllib is not None:
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return {"__unparseable__": True}
    # Fallback: only detect table headers we care about.
    tool: dict = {}
    for line in text.splitlines():
        s = line.strip()
        for key in ("ruff", "mypy", "pytest"):
            if s.startswith(f"[tool.{key}"):
                tool.setdefault(key, {})
    return {"tool": tool}


def _ini_has(path: Path, section: str) -> bool:
    if not path.is_file():
        return False
    cp = configparser.ConfigParser()
    try:
        cp.read(path, encoding="utf-8")
    except configparser.Error:
        return False
    return cp.has_section(section)


def _any(files: list[str], *patterns: str) -> list[str]:
    return [f for f in files if any(fnmatch(f, p) or fnmatch(Path(f).name, p) for p in patterns)]


def detect(root: Path) -> dict:
    files = walk_files(root)
    top = {f for f in files if "/" not in f}
    pyproject = _toml(root / "pyproject.toml")
    tool_tbl = pyproject.get("tool", {}) if isinstance(pyproject.get("tool"), dict) else {}

    pkg: dict = {}
    if (root / "package.json").is_file():
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pkg = {"__unparseable__": True}
    scripts = pkg.get("scripts", {}) if isinstance(pkg.get("scripts"), dict) else {}
    npm_test = scripts.get("test", "")

    py_files = _any(files, "*.py")
    ts_files = [f for f in _any(files, "*.ts", "*.tsx") if not f.endswith(".d.ts")]
    md_files = _any(files, "*.md", "*.mdx")

    languages = []
    if py_files:
        languages.append("python")
    if ts_files or "tsconfig.json" in top:
        languages.append("typescript")
    if "package.json" in top:
        languages.append("javascript")
    if md_files:
        languages.append("docs")

    configs = {
        "ruff_config": sorted(
            [f for f in ("ruff.toml", ".ruff.toml") if (root / f).is_file()]
            + (["pyproject.toml [tool.ruff]"] if "ruff" in tool_tbl else [])
        ),
        "mypy_config": sorted(
            [f for f in ("mypy.ini", ".mypy.ini") if (root / f).is_file()]
            + (["pyproject.toml [tool.mypy]"] if "mypy" in tool_tbl else [])
            + (["setup.cfg [mypy]"] if _ini_has(root / "setup.cfg", "mypy") else [])
        ),
        "pytest_config": sorted(
            [f for f in ("pytest.ini", "conftest.py") if (root / f).is_file()]
            + (["pyproject.toml [tool.pytest.ini_options]"] if "pytest" in tool_tbl else [])
            + (["setup.cfg [tool:pytest]"] if _ini_has(root / "setup.cfg", "tool:pytest") else [])
            + (["tox.ini [pytest]"] if _ini_has(root / "tox.ini", "pytest") else [])
        ),
        "python_tests": sorted(_any(files, "test_*.py", "*_test.py"))[:20],
        "tsconfig": ["tsconfig.json"] if "tsconfig.json" in top else [],
        "eslint_config": sorted(_any(list(top), "eslint.config.*", ".eslintrc*")),
        "npm_test_script": [f"package.json scripts.test = {npm_test!r}"]
        if npm_test and "no test specified" not in npm_test
        else [],
        "markdownlint_config": sorted(_any(list(top), ".markdownlint*")),
        "vale_config": [".vale.ini"] if ".vale.ini" in top else [],
        "pre_commit": [".pre-commit-config.yaml"] if ".pre-commit-config.yaml" in top else [],
        "ci": sorted(
            _any(files, ".github/workflows/*.yml", ".github/workflows/*.yaml")
            + [f for f in (".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile") if f in top]
        ),
        "eqk": [".quality/eqk.json"] if (root / ".quality/eqk.json").is_file() else [],
    }
    if pyproject.get("__unparseable__"):
        configs["warnings"] = ["pyproject.toml could not be parsed; config detection may be incomplete"]

    return {
        "languages": languages,
        "file_counts": {
            "python": len(py_files),
            "typescript": len(ts_files),
            "markdown": len(md_files),
            "total_scanned": len(files),
        },
        "configs": configs,
        "git": git_state(root),
    }


def tool_availability(root: Path) -> dict:
    names = sorted({c["tool"] for p in profiles_mod.list_ids() for c in profiles_mod.load(p)["checks"]})
    out = {}
    for name in names:
        path, source = resolve_tool(name, root)
        out[name] = {"available": path is not None, "source": source}
    return out


def suggest_profile(info: dict) -> tuple[str, str]:
    langs = [lang for lang in info["languages"] if lang != "javascript"]
    code_langs = [lang for lang in langs if lang != "docs"]
    if len(code_langs) > 1:
        return "minimal", "more than one code language detected; start with the smallest shared gate"
    if code_langs == ["python"]:
        return "python-data", "Python project"
    if code_langs == ["typescript"]:
        return "typescript-web", "TypeScript project"
    if "javascript" in info["languages"]:
        return "minimal", "JavaScript project (no dedicated profile yet)"
    if langs == ["docs"]:
        return "docs", "only Markdown content detected"
    return "minimal", "no known language detected"


def inspect_repo(root: Path) -> dict:
    info = detect(root)
    info["tools"] = tool_availability(root)
    prof, why = suggest_profile(info)
    info["suggested_profile"] = {"id": prof, "reason": why}
    info["modified_files"] = []  # inspect is read-only by contract; tests assert this.
    return info


def render(info: dict) -> str:
    lines = ["# eqk inspect (read-only; nothing was changed)", ""]
    lines.append("Languages: " + (", ".join(info["languages"]) or "none detected"))
    g = info["git"]
    lines.append(
        f"Git: {'repo' if g['is_repo'] else 'not a git repo'}"
        + (
            f", HEAD {g['commit'][:10] if g['commit'] else '(no commits)'}, {'dirty' if g['dirty'] else 'clean'}"
            if g["is_repo"]
            else ""
        )
    )
    lines.append("")
    lines.append("Existing quality setup (will be preserved):")
    for key, val in info["configs"].items():
        if val:
            lines.append(f"  - {key}: {', '.join(val[:5])}{' …' if len(val) > 5 else ''}")
    lines.append("")
    lines.append("Tools:")
    for name, t in info["tools"].items():
        lines.append(f"  - {name}: {'found (' + t['source'] + ')' if t['available'] else 'NOT FOUND'}")
    sp = info["suggested_profile"]
    lines += ["", f"Suggested profile: {sp['id']} ({sp['reason']})", f"Next: eqk plan --profile {sp['id']}"]
    return "\n".join(lines)
