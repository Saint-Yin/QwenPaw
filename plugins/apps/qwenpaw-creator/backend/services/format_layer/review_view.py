# -*- coding: utf-8 -*-
"""Review View projection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .errors import ProjectionInputError


def build_review_view(manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(manifest))
    required = (
        "id",
        "transactionId",
        "reviewRevisionId",
        "decisionGroups",
        "operations",
    )
    missing = [field for field in required if field not in value]
    if missing:
        raise ProjectionInputError(
            f"review manifest fields are missing: {missing}",
        )
    blockers = [
        f"REVIEW_OPERATION_LOCATOR_MISSING:{operation.get('id', '')}"
        for operation in value["operations"]
        if not operation.get("uiLocator")
    ]
    return {
        "manifest": value,
        "resolvedRefs": [],
        "relations": [
            {
                "from": f"review-group:{group['id']}",
                "to": operation_id,
                "kind": "contains",
            }
            for group in value["decisionGroups"]
            for operation_id in group.get("operationIds", [])
        ],
        "readiness": {"ready": not blockers},
        "blockers": blockers,
        "targetVersion": str(value.get("manifestToken", value["id"])),
        "uiLocator": {
            "page": "review",
            "transactionId": str(value["transactionId"]),
        },
    }
