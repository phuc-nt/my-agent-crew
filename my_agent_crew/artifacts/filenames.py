"""The name a canvas is saved under when it leaves the app as a file: its title in any script,
with the extension of its kind. The header that carries it folds a plain fallback from it
(`untrusted_content.disposition`); this is the name a person sees."""

from __future__ import annotations

import re

FILENAME_MAX = 60
FALLBACK_STEM = "canvas"
# Path separators become "-", so the parts of "báo cáo/2026" stay apart. Quotes, wildcards,
# ":", "<", ">", "|" and control characters are refused by some file system, and a quote
# would end the header value the name travels in.
_SEPARATORS = re.compile(r"[/\\]+")
_UNSAFE = re.compile(r'["*:<>?|\x00-\x1f\x7f]+')

# By language, as `clean_language` leaves it. Code in any other language saves as text.
_CODE: dict[str, tuple[str, ...]] = {
    ".py": ("python", "py"),
    ".ts": ("typescript", "ts"),
    ".tsx": ("tsx",),
    ".js": ("javascript", "js"),
    ".jsx": ("jsx",),
    ".json": ("json",),
    ".yaml": ("yaml", "yml"),
    ".toml": ("toml",),
    ".sh": ("bash", "sh", "shell", "zsh"),
    ".sql": ("sql",),
    ".html": ("html",),
    ".css": ("css",),
    ".go": ("go",),
    ".rs": ("rust", "rs"),
    ".java": ("java",),
    ".kt": ("kotlin", "kt"),
    ".swift": ("swift",),
    ".c": ("c",),
    ".cpp": ("c++", "cpp"),
    ".cs": ("c#", "csharp", "cs"),
    ".rb": ("ruby", "rb"),
    ".php": ("php",),
}
CODE_EXTENSIONS = {name: extension for extension, names in _CODE.items() for name in names}


def extension_for(kind: str, language: str = "") -> str:
    if kind == "markdown":
        return ".md"
    if kind == "code":
        return CODE_EXTENSIONS.get(language, ".txt")
    return ".txt"


def filename_for(title: str, kind: str, language: str = "") -> str:
    """Whitespace runs become one space, and a title with nothing left saves as "canvas"."""
    spaced = " ".join(_SEPARATORS.sub("-", title).split())
    stem = " ".join(_UNSAFE.sub("", spaced).split())[:FILENAME_MAX].strip(" .-")
    return (stem or FALLBACK_STEM) + extension_for(kind, language)
