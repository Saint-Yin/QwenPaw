"""Strict parsers for the documented Text Workspace directory grammar."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from domain.enums import ShotCamera, ShotFraming

from .errors import ProjectionInputError, ProjectionResourceNotFoundError
from .inputs import TextWorkspaceSnapshot

_DURATION_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*s?$", re.IGNORECASE)
_CAMERA_DOCUMENT_RE = re.compile(
    r"^(?P<camera>[^\n]+?)\s*\n+\s*画幅[：:]\s*(?P<framing>[^\n]+?)\s*$"
)


@dataclass(frozen=True, slots=True)
class ParsedShot:
    id: str
    order: int
    description: str
    camera: str
    framing: str
    camera_description: str
    dialogue: str
    duration: float


@dataclass(frozen=True, slots=True)
class ParsedUnit:
    id: str
    order: int
    slug: str
    root: str
    title: str
    route: str
    duration: float
    # Compatibility-only read for projects created before Unit narrative was
    # replaced by the authoritative Shot list. New planners do not write it.
    narrative: str
    continuity: str
    refs: tuple[tuple[str, str], ...]
    shots: tuple[ParsedShot, ...]


@dataclass(frozen=True, slots=True)
class ParsedSection:
    id: str
    order: int
    slug: str
    root: str
    title: str
    # Compatibility-only reads. New Story runs use narrative/script instead.
    summary: str
    narrative: str
    duration_budget: float | None
    pacing: str
    constraints: tuple[str, ...]
    transition: str
    script: str
    units: tuple[ParsedUnit, ...]


def parse_duration(raw: str, *, label: str) -> float:
    match = _DURATION_RE.fullmatch(raw.strip())
    if not match:
        raise ProjectionInputError(f"invalid duration for {label}: {raw!r}")
    try:
        value = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise ProjectionInputError(f"invalid duration for {label}: {raw!r}") from exc
    if value < 0:
        raise ProjectionInputError(f"duration cannot be negative for {label}")
    return float(value)


def parse_reference_duration(raw: str, *, label: str) -> float | None:
    """Best-effort duration parsing for non-authoritative display metadata."""

    if not raw.strip():
        return None
    try:
        return parse_duration(raw, label=label)
    except ProjectionInputError:
        return None


def parse_list(raw: str) -> tuple[str, ...]:
    items: list[str] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text[:2] in {"- ", "* "}:
            text = text[2:].strip()
        if text:
            items.append(text)
    return tuple(items)


def parse_camera_document(raw: str, *, label: str) -> tuple[str, str]:
    match = _CAMERA_DOCUMENT_RE.fullmatch(raw.strip())
    if match is None:
        raise ProjectionInputError(
            f"camera document must include a separate 画幅 line for {label}"
        )
    camera = match.group("camera").strip()
    framing = match.group("framing").strip()
    try:
        camera = ShotCamera(camera).value
        framing = ShotFraming(framing).value
    except ValueError as exc:
        raise ProjectionInputError(
            f"camera/framing is outside the frozen enum for {label}"
        ) from exc
    return camera, framing


def _directory_identity(segment: str, *, label: str) -> tuple[int, str, str]:
    parts = segment.split("--", 2)
    if len(parts) != 3 or not parts[0].isdigit() or not parts[1] or not parts[2]:
        raise ProjectionInputError(f"invalid {label} directory: {segment!r}")
    return int(parts[0]), parts[1], parts[2]


def _shot_directory_identity(segment: str) -> tuple[int, str]:
    parts = segment.split("--", 1)
    if (
        len(parts) != 2
        or len(parts[0]) != 6
        or not parts[0].isdigit()
        or not parts[1]
        or "--" in parts[1]
    ):
        raise ProjectionInputError(f"invalid shot directory: {segment!r}")
    return int(parts[0]), parts[1]


def _child_directories(snapshot: TextWorkspaceSnapshot, prefix: str) -> tuple[str, ...]:
    result = {
        path[len(prefix) :].split("/", 1)[0]
        for path in snapshot.paths(prefix)
        if "/" in path[len(prefix) :]
    }
    return tuple(sorted(result))


def _read_refs(
    snapshot: TextWorkspaceSnapshot, root: str
) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for path in snapshot.paths(root):
        if not path.endswith(".ref"):
            continue
        value = snapshot.text(path, required=True)
        if "\n" in value or not value:
            raise ProjectionInputError(f"reference file must contain one value: {path}")
        result.append((path[len(root) :], value))
    return tuple(sorted(result))


def _parse_shots(
    snapshot: TextWorkspaceSnapshot,
    unit_root: str,
    *,
    route: str,
) -> tuple[ParsedShot, ...]:
    prefix = f"{unit_root}/shots/"
    shots: list[ParsedShot] = []
    for segment in _child_directories(snapshot, prefix):
        order, shot_id = _shot_directory_identity(segment)
        root = f"{prefix}{segment}"
        description = snapshot.text(f"{root}/description.md")
        raw_camera = snapshot.text(f"{root}/camera.md")
        raw_duration = snapshot.text(f"{root}/duration.txt")
        # Agent file actions are individually atomic.  Do not turn the brief
        # create/write window for a new entity into an HTTP 500; the complete
        # entity appears as soon as all required leaves are valid. Camera is a
        # production contract only for R2V. Legacy Edit Shots remain readable
        # as optional editorial beats even when their camera text is missing or
        # predates the frozen enum.
        if not description or not raw_duration or (route == "r2v" and not raw_camera):
            continue
        camera = ""
        framing = ""
        camera_description = raw_camera.strip()
        if route == "r2v":
            camera, framing = parse_camera_document(
                raw_camera,
                label=f"shot {shot_id}",
            )
            camera_description = f"{camera} · {framing}"
        elif raw_camera:
            try:
                camera, framing = parse_camera_document(
                    raw_camera,
                    label=f"shot {shot_id}",
                )
            except ProjectionInputError:
                pass
            else:
                camera_description = f"{camera} · {framing}"
        shots.append(
            ParsedShot(
                id=shot_id,
                order=order,
                description=description,
                camera=camera,
                framing=framing,
                camera_description=camera_description,
                dialogue=snapshot.text(f"{root}/dialogue.md"),
                duration=parse_duration(raw_duration, label=f"shot {shot_id}"),
            )
        )
    return tuple(sorted(shots, key=lambda item: (item.order, item.id)))


def _parse_units(
    snapshot: TextWorkspaceSnapshot, section_root: str
) -> tuple[ParsedUnit, ...]:
    prefix = f"{section_root}/units/"
    units: list[ParsedUnit] = []
    for segment in _child_directories(snapshot, prefix):
        order, unit_id, slug = _directory_identity(segment, label="unit")
        root = f"{prefix}{segment}"
        title = snapshot.text(f"{root}/title.txt")
        route = snapshot.text(f"{root}/route.txt")
        raw_duration = snapshot.text(f"{root}/duration.txt")
        if not title or not route or not raw_duration:
            continue
        if route not in {"r2v", "edit"}:
            raise ProjectionInputError(f"unit route must be r2v or edit: {unit_id}")
        units.append(
            ParsedUnit(
                id=unit_id,
                order=order,
                slug=slug,
                root=root,
                title=title,
                route=route,
                duration=parse_duration(raw_duration, label=f"unit {unit_id}"),
                narrative=snapshot.text(f"{root}/narrative.md"),
                continuity=snapshot.text(f"{root}/continuity.md"),
                refs=_read_refs(snapshot, f"{root}/refs/"),
                shots=_parse_shots(snapshot, root, route=route),
            )
        )
    return tuple(sorted(units, key=lambda item: (item.order, item.id)))


def parse_sections(snapshot: TextWorkspaceSnapshot) -> tuple[ParsedSection, ...]:
    prefix = "story/sections/"
    sections: list[ParsedSection] = []
    for segment in _child_directories(snapshot, prefix):
        order, section_id, slug = _directory_identity(segment, label="section")
        root = f"{prefix}{segment}"
        title = snapshot.text(f"{root}/title.txt")
        if not title:
            continue
        raw_budget = snapshot.text(f"{root}/duration-budget.txt")
        sections.append(
            ParsedSection(
                id=section_id,
                order=order,
                slug=slug,
                root=root,
                title=title,
                summary=snapshot.text(f"{root}/summary.md"),
                narrative=snapshot.text(f"{root}/narrative.md"),
                duration_budget=parse_duration(
                    raw_budget, label=f"section {section_id}"
                )
                if raw_budget
                else None,
                pacing=snapshot.text(f"{root}/pacing.md"),
                constraints=parse_list(snapshot.text(f"{root}/constraints.md")),
                transition=snapshot.text(f"{root}/transition.md"),
                script=snapshot.text(f"{root}/script.md"),
                units=_parse_units(snapshot, root),
            )
        )
    return tuple(sorted(sections, key=lambda item: (item.order, item.id)))


def find_unit(
    sections: tuple[ParsedSection, ...], unit_id: str
) -> tuple[ParsedSection, ParsedUnit]:
    for section in sections:
        for unit in section.units:
            if unit.id == unit_id:
                return section, unit
    raise ProjectionResourceNotFoundError(f"unit not found in snapshot: {unit_id}")
