"""Fast, offline repository scanner.

Builds a compact map of PROJECT WOLF (languages, entry points, manifests,
directory tree) without calling any model. The map is used as cached context
for the assistant and is also printed by `wolf map` / the SessionStart hook.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea", ".vscode",
    "target", ".next", ".tox", ".eggs", "coverage",
}

LANGUAGES = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".cpp": "C++", ".cc": "C++", ".c": "C",
    ".h": "C/C++ header", ".swift": "Swift", ".scala": "Scala", ".lua": "Lua",
    ".sh": "Shell", ".sql": "SQL", ".html": "HTML", ".css": "CSS", ".md": "Markdown",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".ipynb": "Notebook",
    ".gd": "GDScript", ".unity": "Unity scene", ".r": "R", ".dart": "Dart",
}

MANIFESTS = {
    "package.json", "pyproject.toml", "requirements.txt", "setup.py", "Pipfile",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile",
    "composer.json", "Makefile", "Dockerfile", "docker-compose.yml", "compose.yaml",
    "CMakeLists.txt", "project.godot", "tsconfig.json", ".github",
}

ENTRY_HINTS = {
    "main.py", "app.py", "__main__.py", "cli.py", "server.py", "manage.py",
    "index.js", "index.ts", "main.ts", "main.go", "main.rs", "lib.rs", "Main.java",
    "Program.cs", "main.c", "main.cpp",
}

# The assistant's own scaffolding; reported separately so it does not drown out WOLF itself.
ASSISTANT_PATHS = ("wolf_assistant", ".claude", "docs/wolf", "tests/test_wolf_assistant.py")


@dataclass
class RepoMap:
    root: Path
    files: list[str] = field(default_factory=list)
    languages: Counter = field(default_factory=Counter)
    manifests: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    total_bytes: int = 0

    @property
    def project_files(self) -> list[str]:
        return [f for f in self.files if not f.startswith(ASSISTANT_PATHS)]

    def render(self, max_tree: int = 300) -> str:
        proj = self.project_files
        lines = [f"# WOLF repository map ({self.root.name})", ""]
        if not proj:
            lines += [
                "PROJECT WOLF has no source files yet (only the assistant scaffolding).",
                "When code is added, re-run `wolf map` or `wolf learn` to update this picture.",
                "",
            ]
        lines.append(f"Files: {len(self.files)} total, {len(proj)} belonging to WOLF itself; "
                     f"{self.total_bytes / 1024:.0f} KiB")
        if self.languages:
            top = ", ".join(f"{lang} ({n})" for lang, n in self.languages.most_common(10))
            lines.append(f"Languages (WOLF files): {top}")
        if self.manifests:
            lines.append("Manifests/config: " + ", ".join(self.manifests[:30]))
        if self.entry_points:
            lines.append("Likely entry points: " + ", ".join(self.entry_points[:30]))
        lines += ["", "## Tree", "```"]
        shown = self.files[:max_tree]
        lines += shown
        if len(self.files) > max_tree:
            lines.append(f"... ({len(self.files) - max_tree} more files)")
        lines.append("```")
        return "\n".join(lines)


def scan(root: str | Path) -> RepoMap:
    root = Path(root).resolve()
    rm = RepoMap(root=root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        rel_dir = Path(dirpath).relative_to(root)
        for name in sorted(filenames):
            rel = (rel_dir / name).as_posix()
            rm.files.append(rel)
            try:
                rm.total_bytes += (Path(dirpath) / name).stat().st_size
            except OSError:
                pass
            is_assistant = rel.startswith(ASSISTANT_PATHS)
            if not is_assistant:
                lang = LANGUAGES.get(Path(name).suffix.lower())
                if lang:
                    rm.languages[lang] += 1
                if name in ENTRY_HINTS:
                    rm.entry_points.append(rel)
            if name in MANIFESTS and not is_assistant:
                rm.manifests.append(rel)
        if rel_dir.as_posix() == ".github" or ".github" in dirnames:
            if ".github" not in rm.manifests and (root / ".github").exists():
                rm.manifests.append(".github")
    return rm


if __name__ == "__main__":  # used by the Claude Code SessionStart hook
    import sys

    print(scan(sys.argv[1] if len(sys.argv) > 1 else ".").render(max_tree=150))
