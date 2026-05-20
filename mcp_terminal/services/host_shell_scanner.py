"""
Shell-string parsing and forbidden-pattern scanning for host execution policy (C-018).

Parses shell chains, quotes, redirections, heredocs, and here-strings.
Scans extracted fragments for forbidden substrings.
Imported exclusively by mcp_terminal/services/host_execution_config.py validators.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import FrozenSet, List, Optional

_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Aligned with ``SandboxPolicy._FORBIDDEN_OPTIONS`` plus host subshell/redirect risks.
HOST_FORBIDDEN_SUBSTRINGS: FrozenSet[str] = frozenset(
    {
        "--privileged",
        "--pid=host",
        "--pid host",
        "--network=host",
        "--network host",
        "--ipc=host",
        "--ipc host",
        "--uts=host",
        "--uts host",
        "--cap-add=SYS_ADMIN",
        "--cap-add SYS_ADMIN",
        "/var/run/docker.sock",
        "$(",  # command substitution
        "${",  # parameter expansion
        "`",  # backtick substitution
        "\x00",
    }
)

# Always blocked on the host path even if listed in ``allowed_commands`` (C-018).
HOST_FORBIDDEN_EXECUTABLES: FrozenSet[str] = frozenset(
    {
        "docker",
        "podman",
        "kubectl",
        "helm",
        "sudo",
        "su",
        "doas",
        "mount",
        "umount",
        "nsenter",
        "chroot",
        "systemctl",
        "service",
        "iptables",
        "nft",
        "ip",
        "ifconfig",
        "tcpdump",
        "nmap",
        "socat",
        "nc",
        "netcat",
    }
)


def decompose_shell_command(command: str) -> List[str]:
    """Split a shell string on ``&&``, ``||``, ``;``, ``|`` outside quotes."""
    text = command.strip()
    if not text:
        return []

    segments: List[str] = []
    buf: List[str] = []
    i = 0
    n = len(text)
    in_squote = False
    in_dquote = False

    def flush() -> None:
        seg = "".join(buf).strip()
        buf.clear()
        if seg:
            segments.append(seg)

    while i < n:
        ch = text[i]
        if in_squote:
            buf.append(ch)
            if ch == "'":
                in_squote = False
            i += 1
            continue
        if in_dquote:
            if ch == "\\" and i + 1 < n:
                buf.append(ch)
                buf.append(text[i + 1])
                i += 2
                continue
            buf.append(ch)
            if ch == '"':
                in_dquote = False
            i += 1
            continue
        if ch == "'":
            in_squote = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_dquote = True
            buf.append(ch)
            i += 1
            continue
        if text.startswith("&&", i):
            flush()
            i += 2
            continue
        if text.startswith("||", i):
            flush()
            i += 2
            continue
        if ch in ";|":
            flush()
            i += 1
            continue
        buf.append(ch)
        i += 1

    flush()
    return segments


def shell_command_has_chain(command: str) -> bool:
    """True when ``command`` contains a chain operator outside quotes."""
    return len(decompose_shell_command(command)) > 1


def segment_executable_name(segment: str) -> Optional[str]:
    """First non-assignment token basename in one shell segment."""
    try:
        parts = shlex.split(segment.strip())
    except ValueError:
        return None
    for part in parts:
        if _ENV_ASSIGN_RE.match(part):
            continue
        return Path(part).name or None
    return None


def command_executable_name(
    execution_kind: str,
    command: Optional[str],
    argv: Optional[List[str]],
) -> Optional[str]:
    """Basename of the executable for argv or the first shell token."""
    if execution_kind == "argv" and argv:
        return Path(str(argv[0])).name or None
    if execution_kind == "shell" and command and command.strip():
        return segment_executable_name(command.strip())
    return None


def find_forbidden_substring(text: str) -> Optional[str]:
    """Return the first forbidden substring found in ``text``, if any."""
    for forbidden in HOST_FORBIDDEN_SUBSTRINGS:
        if forbidden in text:
            return forbidden
    return None


def _advance_quote(
    ch: str, i: int, text: str, in_squote: bool, in_dquote: bool
) -> tuple[bool, bool, int]:
    """Update quote state and index for one character."""
    if in_squote:
        if ch == "'":
            in_squote = False
        return in_squote, in_dquote, i + 1
    if in_dquote:
        if ch == "\\" and i + 1 < len(text):
            return in_squote, in_dquote, i + 2
        if ch == '"':
            in_dquote = False
        return in_squote, in_dquote, i + 1
    if ch == "'":
        return True, in_dquote, i + 1
    if ch == '"':
        return in_squote, True, i + 1
    return in_squote, in_dquote, i + 1


def _read_shell_word(text: str, i: int) -> tuple[str, int]:
    """Read one shell word (quoted or unquoted) starting at ``i``; returns word and new index."""
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n:
        return "", i

    in_squote = False
    in_dquote = False
    buf: List[str] = []
    start = i

    while i < n:
        ch = text[i]
        if in_squote:
            buf.append(ch)
            if ch == "'":
                in_squote = False
            i += 1
            continue
        if in_dquote:
            if ch == "\\" and i + 1 < n:
                buf.append(ch)
                buf.append(text[i + 1])
                i += 2
                continue
            buf.append(ch)
            if ch == '"':
                in_dquote = False
            i += 1
            continue
        if ch == "'":
            in_squote = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_dquote = True
            buf.append(ch)
            i += 1
            continue
        if ch.isspace():
            break
        buf.append(ch)
        i += 1

    if not buf:
        return "", start
    word = "".join(buf)
    try:
        parts = shlex.split(word)
        if len(parts) == 1:
            return parts[0], i
    except ValueError:
        pass
    return word.strip("'\""), i


def _read_heredoc_delimiter(text: str, i: int) -> tuple[str, int]:
    """Parse delimiter after ``<<`` / ``<<-``; returns delimiter line text and index after it."""
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    delim, i = _read_shell_word(text, i)
    return delim, i


def extract_heredoc_bodies(text: str) -> List[str]:
    """Extract heredoc / here-string bodies from a (possibly multiline) shell command."""
    bodies: List[str] = []
    n = len(text)
    i = 0
    in_squote = False
    in_dquote = False

    while i < n:
        ch = text[i]
        if in_squote or in_dquote:
            in_squote, in_dquote, i = _advance_quote(ch, i, text, in_squote, in_dquote)
            continue

        if text.startswith("<<<", i):
            i += 3
            word, i = _read_shell_word(text, i)
            if word:
                bodies.append(word)
            continue

        if text.startswith("<<", i):
            i += 2
            if i < n and text[i] == "-":
                i += 1
            delim, i = _read_heredoc_delimiter(text, i)
            if not delim:
                continue

            line_start = i
            while line_start < n and text[line_start] != "\n":
                line_start += 1
            if line_start < n:
                i = line_start + 1

            buf: List[str] = []
            while i < n:
                line_end = text.find("\n", i)
                if line_end == -1:
                    line_end = n
                line = text[i:line_end]
                stripped = line.strip()
                if stripped == delim:
                    bodies.append("\n".join(buf))
                    i = line_end + 1 if line_end < n else line_end
                    break
                buf.append(line)
                i = line_end + 1 if line_end < n else line_end
            continue

        in_squote, in_dquote, i = _advance_quote(ch, i, text, in_squote, in_dquote)

    return bodies


def _extract_here_string_words(segment: str) -> List[str]:
    """Words after ``<<<`` in one segment."""
    words: List[str] = []
    n = len(segment)
    i = 0
    in_squote = False
    in_dquote = False
    while i < n:
        ch = segment[i]
        if in_squote or in_dquote:
            in_squote, in_dquote, i = _advance_quote(ch, i, segment, in_squote, in_dquote)
            continue
        if segment.startswith("<<<", i):
            i += 3
            word, i = _read_shell_word(segment, i)
            if word:
                words.append(word)
            continue
        in_squote, in_dquote, i = _advance_quote(ch, i, segment, in_squote, in_dquote)
    return words


def extract_redirection_targets(segment: str) -> List[str]:
    """Extract redirect destination paths / here-string words from one shell segment."""
    targets: List[str] = []
    n = len(segment)
    i = 0
    in_squote = False
    in_dquote = False

    while i < n:
        ch = segment[i]
        if in_squote or in_dquote:
            in_squote, in_dquote, i = _advance_quote(ch, i, segment, in_squote, in_dquote)
            continue

        if segment.startswith("<<<", i):
            i += 3
            _, i = _read_shell_word(segment, i)
            continue

        if segment.startswith("<<", i):
            i += 2
            if i < n and segment[i] == "-":
                i += 1
            _, i = _read_heredoc_delimiter(segment, i)
            continue

        redirect_kind: Optional[str] = None
        if i + 1 < n and segment[i : i + 2] == ">>":
            redirect_kind = ">>"
            i += 2
        elif i + 1 < n and segment[i : i + 2] == ">&":
            redirect_kind = ">&"
            i += 2
        elif ch == ">":
            redirect_kind = ">"
            i += 1
        elif ch == "<":
            redirect_kind = "<"
            i += 1
        elif ch.isdigit() and i + 1 < n and segment[i + 1] in "><":
            redirect_kind = segment[i + 1]
            i += 2
            if i < n and segment[i] in ">&" and redirect_kind == ">":
                i += 1

        if redirect_kind:
            while i < n and segment[i].isspace():
                i += 1
            if i < n and segment[i] == "&":
                i += 1
                while i < n and segment[i].isdigit():
                    i += 1
                continue
            word, i = _read_shell_word(segment, i)
            if word and not word.isdigit():
                targets.append(word)
            continue

        in_squote, in_dquote, i = _advance_quote(ch, i, segment, in_squote, in_dquote)

    return targets


def iter_shell_scan_fragments(command: str) -> List[tuple[str, str]]:
    """Labeled fragments to scan; specific targets before whole segments."""
    items: List[tuple[str, str]] = []
    for body in extract_heredoc_bodies(command):
        items.append((body, "heredoc"))
    segments = decompose_shell_command(command)
    for segment in segments:
        for target in extract_redirection_targets(segment):
            items.append((target, "redirect"))
        for word in _extract_here_string_words(segment):
            items.append((word, "here-string"))
    for segment in segments:
        items.append((segment, "segment"))
    items.append((command, "command"))
    return items


def collect_shell_scan_texts(command: str) -> List[str]:
    """All command fragments to scan for forbidden patterns (segments, redirects, heredocs)."""
    return [fragment for fragment, _label in iter_shell_scan_fragments(command)]


def find_forbidden_in_shell_command(command: str) -> Optional[tuple[str, str]]:
    """Return ``(forbidden, context)`` when any scan fragment contains a forbidden pattern."""
    for fragment, label in iter_shell_scan_fragments(command):
        hit = find_forbidden_substring(fragment)
        if hit is not None:
            return hit, label
    return None
