from __future__ import annotations

from dataclasses import dataclass

import pytest

from services.workspace.content_store import ContentStore
from services.workspace.entity_reader import EntityReader
from services.workspace.revision_store import RevisionStore
from services.workspace.text_store import TextStore


@dataclass(slots=True)
class WorkspaceStack:
    content: ContentStore
    revisions: RevisionStore
    text: TextStore
    entities: EntityReader


@pytest.fixture()
def workspace_stack(tmp_path) -> WorkspaceStack:
    content = ContentStore(tmp_path / "creator-data")
    revisions = RevisionStore(content)
    text = TextStore(content, revisions)
    return WorkspaceStack(
        content=content,
        revisions=revisions,
        text=text,
        entities=EntityReader(text),
    )
