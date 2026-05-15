"""
Project registry and marker validation for mcp_terminal.

ProjectRegistry (C-001) scans **watchable parent directories**: each configured
anchor is a host path whose **immediate subdirectories** may be project roots
(``projectid`` marker files, C-002). The anchor directory itself may also
contain ``projectid`` (project root equals the anchor). Runtime resolution
enforces path containment before any mount.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, DefaultDict, Dict, FrozenSet, List, Optional, Sequence, Tuple, Union


@dataclass(frozen=True)
class ProjectMarker:
    """Validated content of a projectid marker file (C-002).

    Constructed only by validate_marker_file(); never directly by callers.
    The directory that contains this marker is not the project identity;
    only the id field is.
    """

    project_id: str
    """UUID4 string from the id field of the marker file."""
    description: str
    """Human-readable project description from the description field."""
    marker_path: Path
    """Absolute path to the projectid marker file (read-only reference)."""
    project_dir: Path
    """Absolute path to the project root directory containing the marker."""


@dataclass(frozen=True)
class MarkerValidationError:
    """Structured rejection reason from validate_marker_file()."""

    path: Path
    """Path of the candidate file that failed validation."""
    reason: str
    """Human-readable description of the validation failure."""
    code: str
    """Short code: invalid_json, missing_id, missing_description, invalid_uuid4,
    not_a_file."""


_UUID4_RE: re.Pattern[str] = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid4(value: str) -> bool:
    """Return True if value matches the UUID4 format."""
    return bool(_UUID4_RE.match(value))


def validate_marker_file(
    candidate: Path,
    *,
    require_uuid4_id: bool = True,
) -> Tuple[Optional[ProjectMarker], Optional[MarkerValidationError]]:
    """Validate a candidate projectid marker file.

    Reads the file, parses JSON, checks required fields, and optionally
    validates UUID4 format on the id field. The file must be named
    "projectid"; callers are responsible for providing only files with
    that name.

    mcp_terminal must never rename, reconfigure, or rewrite the marker file.
    This function is read-only.

    Args:
        candidate: Absolute path to a file named "projectid".
        require_uuid4_id: When True, reject id values that do not match
            UUID4 format.

    Returns:
        A tuple (ProjectMarker, None) on success, or
        (None, MarkerValidationError) on failure.
    """
    if not candidate.is_file():
        return None, MarkerValidationError(
            path=candidate,
            reason="not a regular file",
            code="not_a_file",
        )
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None, MarkerValidationError(
            path=candidate,
            reason="not valid JSON",
            code="invalid_json",
        )
    if not data.get("id"):
        return None, MarkerValidationError(
            path=candidate,
            reason="missing or empty id field",
            code="missing_id",
        )
    if not isinstance(data.get("description"), str):
        return None, MarkerValidationError(
            path=candidate,
            reason="missing or non-string description field",
            code="missing_description",
        )
    if require_uuid4_id and not _is_uuid4(str(data["id"])):
        return None, MarkerValidationError(
            path=candidate,
            reason=f"id {data['id']!r} is not a valid UUID4",
            code="invalid_uuid4",
        )
    return (
        ProjectMarker(
            project_id=str(data["id"]).strip(),
            description=str(data["description"]),
            marker_path=candidate.resolve(),
            project_dir=candidate.resolve().parent,
        ),
        None,
    )


@dataclass
class RegistryEntry:
    """Single entry in the ProjectRegistry index."""

    marker: ProjectMarker
    """Validated marker data for this project."""
    anchor_root: Path
    """Resolved host root under which this project directory was discovered."""
    disabled: bool = False
    """True when the entry is disabled due to a duplicate id conflict."""
    conflict_reason: Optional[str] = None
    """Human-readable reason for disabling, set when disabled=True."""


@dataclass(frozen=True)
class ResolutionResult:
    """Outcome of ProjectRegistry.resolve()."""

    success: bool
    """True when resolution succeeded."""
    project_dir: Optional[Path] = None
    """Verified canonical host path; set only when success=True."""
    error_code: Optional[str] = None
    """Stable ErrorContract code (C-015); set only when success=False."""
    detail: Optional[str] = None
    """Human-readable detail; not stable across versions."""


class ProjectRegistry:
    """In-memory registry of valid mcp_terminal projects (C-001).

    Built from ``projectid`` markers: each configured path is a **parent**
    directory whose immediate subdirectories are candidate project roots
    (``watch_dirs.directories`` plus optional Code Analysis watch directories).
    Provides project_id -> canonical host path resolution with path
    containment enforcement per anchor root.
    """

    MARKER_FILENAME: str = "projectid"  # fixed; never configurable

    def __init__(
        self,
        root_dirs: Union[Path, Sequence[Path]],
        *,
        require_uuid4_id: bool = True,
        allow_nested_projects: bool = False,
    ) -> None:
        """Initialise registry without scanning.

        Args:
            root_dirs: Zero or more host directories; each **contains** project roots
            as its direct subdirectories (each subdir may hold a ``projectid`` file),
            and/or a ``projectid`` file may sit directly in the anchor directory.
            require_uuid4_id: Enforce UUID4 format on marker id field.
            allow_nested_projects: When False, reject markers inside
                subdirectories of other project directories.
        """
        if isinstance(root_dirs, Path):
            seq: Tuple[Path, ...] = (root_dirs.resolve(),)
        else:
            seq = tuple(Path(p).resolve() for p in root_dirs)
        self._root_dirs: Tuple[Path, ...] = seq
        self._require_uuid4_id: bool = require_uuid4_id
        self._allow_nested_projects: bool = allow_nested_projects
        self._entries: Dict[str, RegistryEntry] = {}
        self._logger: logging.Logger = logging.getLogger(__name__)

    @property
    def root_dirs(self) -> Tuple[Path, ...]:
        """Parent directories: each one's direct subdirs (and optionally the anchor
    itself) are scanned for ``projectid``."""
        return self._root_dirs

    def build(self) -> None:
        """Scan parent directories and build the in-memory project index.

        For each parent path in ``root_dirs``, **direct** subdirectories are
        considered; each may contain one project root (``projectid``). If the
        anchor directory itself contains ``projectid``, that project is indexed
        as well.
        Rejects:
        - directories without the marker file
        - invalid markers (invalid JSON, missing fields, UUID4 violations)
        - directories that resolve outside that root
        - nested project markers when allow_nested_projects is False
        On duplicate id detection, disables all conflicting entries.
        """
        self._entries.clear()
        candidates: List[Tuple[Path, ProjectMarker, Path]] = []
        for root_dir in self._root_dirs:
            real_root = root_dir.resolve()
            try:
                subdirs = list(real_root.iterdir())
            except OSError as exc:
                self._logger.warning("Cannot scan project root %s: %s", real_root, exc)
                continue
            anchor_marker = real_root / self.MARKER_FILENAME
            try:
                marker, err = validate_marker_file(
                    anchor_marker, require_uuid4_id=self._require_uuid4_id
                )
            except OSError as exc:
                self._logger.debug("Skipping %s: %s", anchor_marker, exc)
                marker, err = None, None
            if err is None and marker is not None:
                real_project = marker.project_dir.resolve()
                try:
                    real_project.relative_to(real_root)
                except ValueError:
                    self._logger.warning(
                        "Rejecting %s: project path outside root %s", real_project, real_root
                    )
                else:
                    if not self._allow_nested_projects:
                        for existing_path, _, _ in candidates:
                            try:
                                real_project.relative_to(existing_path)
                                self._logger.warning(
                                    "Rejecting nested project %s inside %s",
                                    real_project,
                                    existing_path,
                                )
                                break
                            except ValueError:
                                pass
                        else:
                            candidates.append((real_project, marker, real_root))
                    else:
                        candidates.append((real_project, marker, real_root))
            for subdir in subdirs:
                if not subdir.is_dir():
                    continue
                marker_path = subdir / self.MARKER_FILENAME
                try:
                    marker, err = validate_marker_file(
                        marker_path, require_uuid4_id=self._require_uuid4_id
                    )
                except OSError as exc:
                    self._logger.debug("Skipping %s: %s", marker_path, exc)
                    continue
                if err is not None:
                    self._logger.debug("Skipping %s: %s", marker_path, err.reason)
                    continue
                if marker is None:
                    continue
                real_project = marker.project_dir.resolve()
                try:
                    real_project.relative_to(real_root)
                except ValueError:
                    self._logger.warning(
                        "Rejecting %s: project path outside root %s", real_project, real_root
                    )
                    continue
                if not self._allow_nested_projects:
                    for existing_path, _, _ in candidates:
                        try:
                            real_project.relative_to(existing_path)
                            self._logger.warning(
                                "Rejecting nested project %s inside %s",
                                real_project,
                                existing_path,
                            )
                            break
                        except ValueError:
                            pass
                    else:
                        candidates.append((real_project, marker, real_root))
                else:
                    candidates.append((real_project, marker, real_root))

        seen: Dict[str, List[Tuple[ProjectMarker, Path]]] = {}
        for _, marker, anchor in candidates:
            seen.setdefault(marker.project_id, []).append((marker, anchor))
        for project_id, pairs in seen.items():
            if len(pairs) == 1:
                m, anchor = pairs[0]
                self._entries[project_id] = RegistryEntry(marker=m, anchor_root=anchor)
            else:
                conflict_reason = (
                    f"Duplicate project_id {project_id!r} found in "
                    f"{[str(m.project_dir) for m, _ in pairs]}"
                )
                self._logger.error(conflict_reason)
                for marker, anchor in pairs:
                    self._entries[project_id] = RegistryEntry(
                        marker=marker,
                        anchor_root=anchor,
                        disabled=True,
                        conflict_reason=conflict_reason,
                    )

    @property
    def known_project_ids(self) -> FrozenSet[str]:
        """All project ids in the registry, including disabled entries."""
        return frozenset(self._entries.keys())

    def list_watch_layout(self) -> Dict[str, Any]:
        """Snapshot: each watch anchor directory and projects discovered under it.

        When using the process-wide registry from ``runtime_context``, call only
        via ``registry_list_watch_layout()`` so the read runs under
        ``_project_registry_lock`` together with pointer swaps from refresh.

        ``watch_directories`` follows the order of configured anchor paths
        (``root_dirs``). Each ``projects`` item includes ``disabled`` and optional
        ``conflict_reason`` when duplicate ``project_id`` markers were detected.
        """
        by_anchor: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        for entry in self._entries.values():
            akey = str(entry.anchor_root.resolve())
            by_anchor[akey].append(
                {
                    "project_id": entry.marker.project_id,
                    "description": entry.marker.description,
                    "project_dir": str(entry.marker.project_dir.resolve()),
                    "disabled": entry.disabled,
                    "conflict_reason": entry.conflict_reason,
                }
            )
        for lst in by_anchor.values():
            lst.sort(key=lambda row: row["project_id"])

        watch_directories: List[Dict[str, Any]] = []
        for anchor in self._root_dirs:
            akey = str(anchor.resolve())
            watch_directories.append(
                {"directory": akey, "projects": list(by_anchor.get(akey, []))}
            )

        enabled = sum(1 for e in self._entries.values() if not e.disabled)
        return {
            "watch_directories": watch_directories,
            "totals": {
                "watch_directory_count": len(watch_directories),
                "registry_entry_count": len(self._entries),
                "enabled_project_count": enabled,
            },
        }

    def resolve(self, project_id: str) -> ResolutionResult:
        """Resolve project_id to a verified canonical host path.

        Performs all checks required before any mount operation:
        1. project_id must exist in the registry.
        2. Entry must not be disabled (duplicate conflict).
        3. Canonical path must still exist as a directory.
        4. realpath(project_dir) must lie under the entry's anchor root; when
           allow_nested_projects is False it must be a direct child of that root.
        5. Symlink escapes and relative traversal are rejected.

        Args:
            project_id: Caller-supplied project identifier to resolve.

        Returns:
            ResolutionResult with success=True and project_dir set, or
            success=False with a stable error_code from ErrorContract (C-015).
        """
        entry = self._entries.get(project_id)
        if entry is None:
            return ResolutionResult(
                success=False,
                error_code="PROJECT_NOT_FOUND",
                detail=f"project_id {project_id!r} not found in registry",
            )
        if entry.disabled:
            return ResolutionResult(
                success=False,
                error_code="PROJECT_NOT_FOUND",
                detail=entry.conflict_reason or "project is disabled due to duplicate id",
            )
        project_dir = entry.marker.project_dir
        if not project_dir.is_dir():
            return ResolutionResult(
                success=False,
                error_code="PROJECT_NOT_FOUND",
                detail=f"project directory no longer exists: {project_dir}",
            )
        anchor = entry.anchor_root.resolve()
        real_project = project_dir.resolve()
        try:
            real_project.relative_to(anchor)
        except ValueError:
            self._logger.error(
                "Path containment violation: %s is outside anchor %s",
                real_project,
                anchor,
            )
            return ResolutionResult(
                success=False,
                error_code="PROJECT_PATH_OUT_OF_SCOPE",
                detail="project path is outside the configured projects root",
            )
        if not self._allow_nested_projects:
            is_direct_child = real_project.parent == anchor
            marker_on_anchor = (
                real_project == anchor
                and (anchor / self.MARKER_FILENAME).is_file()
            )
            if not (is_direct_child or marker_on_anchor):
                return ResolutionResult(
                    success=False,
                    error_code="PROJECT_PATH_OUT_OF_SCOPE",
                    detail="nested projects are not allowed",
                )
        return ResolutionResult(success=True, project_dir=real_project)

    def refresh(self) -> None:
        """Re-scan anchor roots and rebuild the registry index.

        Equivalent to calling build() again. Replaces all entries.
        """
        self.build()
