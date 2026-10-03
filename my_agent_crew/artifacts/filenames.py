"""The name a canvas is saved under when it leaves the app as a file: its title in any script,
with the extension of its kind. The header that carries it folds a plain fallback from it
(`untrusted_content.disposition`); this is the name a person sees."""

from __future__ import annotations

import re

from my_agent_crew.artifacts.kinds import sniff_image

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
_BY_KIND = {"markdown": ".md", "html": ".html", "svg": ".svg", "mermaid": ".mmd"}
# A browser runs the scripts in these when the file is opened, with the reach of a local file,
# and a canvas can hold whatever an agent copied from a web page: they download as text.
_BROWSER_RUNS = {".html", ".svg"}


def extension_for(kind: str, language: str = "", data: bytes | None = None) -> str:
    """A picture's extension is the one its bytes give, `.bin` when they give none. Every other
    kind ignores `data`, and only code looks at `language`."""
    if kind == "code":
        return CODE_EXTENSIONS.get(language, ".txt")
    if kind == "image":
        return sniff_image(data) or ".bin"
    return _BY_KIND.get(kind, ".txt")


def filename_for(title: str, kind: str, language: str = "", data: bytes | None = None) -> str:
    """Whitespace runs become one space, and a title with nothing left saves as "canvas". A page,
    a drawing or code a browser would run keeps its extension before `.txt`, so opening the file
    shows the text."""
    spaced = " ".join(_SEPARATORS.sub("-", title).split())
    stem = " ".join(_UNSAFE.sub("", spaced).split())[:FILENAME_MAX].strip(" .-")
    extension = extension_for(kind, language, data)
    if extension in _BROWSER_RUNS:
        extension += ".txt"
    return (stem or FALLBACK_STEM) + extension
