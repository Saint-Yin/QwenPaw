# -*- coding: utf-8 -*-
"""Structured readers over immutable/working Text Workspace snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import re

from domain.errors import NotFoundError, ValidationError
from domain.refs import validate_workspace_ref

from .mutations import safe_storage_segment, safe_workspace_path
from .text_store import TextStore


_ORDERED_ENTITY_DIR_RE = re.compile(
    r"^(?P<order>\d{6})--(?P<id>[^/]+?)(?:--(?P<slug>.+))?$",
)
_PLAIN_ENTITY_DIR_RE = re.compile(r"^(?P<id>[^/]+?)(?:--(?P<slug>.+))?$")


@dataclass(frozen=True, slots=True)
class EntityFile:
    path: str
    relative_path: str
    text: str
    blob_hash: str
    content_type: str


@dataclass(frozen=True, slots=True)
class WorkspaceEntity:
    id: str
    directory: str
    order: int | None
    slug: str | None
    files: tuple[EntityFile, ...]

    def file_map(self) -> dict[str, EntityFile]:
        return {item.relative_path: item for item in self.files}


class EntityReader:
    def __init__(self, text_store: TextStore) -> None:
        self.text_store = text_store

    @staticmethod
    def _selector(
        *,
        branch_id: str | None,
        revision_id: str | None,
    ) -> dict[str, str | None]:
        if (branch_id is None) == (revision_id is None):
            raise ValidationError("必须且只能指定 branch_id 或 revision_id")
        return {"branch_id": branch_id, "revision_id": revision_id}

    def read_text(
        self,
        project_id: str,
        path: str,
        *,
        branch_id: str | None = None,
        revision_id: str | None = None,
    ) -> str:
        selector = self._selector(branch_id=branch_id, revision_id=revision_id)
        return self.text_store.read_text(
            project_id,
            safe_workspace_path(path),
            **selector,
        )

    def read_ref(
        self,
        project_id: str,
        path: str,
        *,
        branch_id: str | None = None,
        revision_id: str | None = None,
    ) -> str:
        normalized = safe_workspace_path(path)
        if not normalized.endswith(".ref"):
            raise ValidationError("read_ref 只接受 .ref 路径")
        value = self.read_text(
            project_id,
            normalized,
            branch_id=branch_id,
            revision_id=revision_id,
        )
        return validate_workspace_ref(value)

    def read_directory(
        self,
        project_id: str,
        directory: str,
        *,
        branch_id: str | None = None,
        revision_id: str | None = None,
    ) -> tuple[EntityFile, ...]:
        normalized = safe_workspace_path(directory)
        selector = self._selector(branch_id=branch_id, revision_id=revision_id)
        entries = self.text_store.list_entries(
            project_id,
            prefix=normalized,
            **selector,
        )
        prefix = f"{normalized}/"
        files: list[EntityFile] = []
        for entry in entries:
            if entry.path == normalized:
                relative = entry.path.rsplit("/", 1)[-1]
            elif entry.path.startswith(prefix):
                relative = entry.path[len(prefix) :]
            else:  # defensive for custom TextStore implementations
                continue
            files.append(
                EntityFile(
                    path=entry.path,
                    relative_path=relative,
                    text=self.text_store.read_text(
                        project_id,
                        entry.path,
                        **selector,
                    ),
                    blob_hash=entry.blob_hash,
                    content_type=entry.content_type,
                ),
            )
        return tuple(files)

    def list_entities(
        self,
        project_id: str,
        root: str,
        *,
        ordered: bool,
        branch_id: str | None = None,
        revision_id: str | None = None,
    ) -> tuple[WorkspaceEntity, ...]:
        normalized_root = safe_workspace_path(root)
        selector = self._selector(branch_id=branch_id, revision_id=revision_id)
        entries = self.text_store.list_entries(
            project_id,
            prefix=normalized_root,
            **selector,
        )
        prefix = f"{normalized_root}/"
        directory_names: set[str] = set()
        for entry in entries:
            if not entry.path.startswith(prefix):
                continue
            remainder = entry.path[len(prefix) :]
            if "/" in remainder:
                directory_names.add(remainder.split("/", 1)[0])

        pattern = _ORDERED_ENTITY_DIR_RE if ordered else _PLAIN_ENTITY_DIR_RE
        entities: list[WorkspaceEntity] = []
        for directory_name in sorted(directory_names):
            match = pattern.fullmatch(directory_name)
            if not match:
                raise ValidationError(
                    "entity directory 不符合稳定 ID 命名规则",
                    details={
                        "root": normalized_root,
                        "directory": directory_name,
                    },
                )
            entity_id = safe_storage_segment(
                match.group("id"),
                label="entity id",
            )
            order_text = match.groupdict().get("order")
            directory = f"{normalized_root}/{directory_name}"
            entities.append(
                WorkspaceEntity(
                    id=entity_id,
                    directory=directory,
                    order=int(order_text) if order_text is not None else None,
                    slug=match.groupdict().get("slug"),
                    files=self.read_directory(
                        project_id,
                        directory,
                        **selector,
                    ),
                ),
            )
        return tuple(
            sorted(
                entities,
                key=lambda item: (
                    item.order if item.order is not None else 0,
                    item.directory,
                ),
            ),
        )

    def read_entity(
        self,
        project_id: str,
        root: str,
        entity_id: str,
        *,
        ordered: bool,
        branch_id: str | None = None,
        revision_id: str | None = None,
    ) -> WorkspaceEntity:
        normalized_id = safe_storage_segment(entity_id, label="entity id")
        matches = [
            item
            for item in self.list_entities(
                project_id,
                root,
                ordered=ordered,
                branch_id=branch_id,
                revision_id=revision_id,
            )
            if item.id == normalized_id
        ]
        if not matches:
            raise NotFoundError(
                "Workspace entity 不存在",
                details={"root": root, "entityId": normalized_id},
            )
        if len(matches) > 1:
            raise ValidationError(
                "同一稳定 ID 对应多个 entity directory",
                details={"root": root, "entityId": normalized_id},
            )
        return matches[0]
