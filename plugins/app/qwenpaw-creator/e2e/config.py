# -*- coding: utf-8 -*-
"""Creator browser acceptance configuration.

The suite drives the Vite UI and reaches the unique Creator API through the
same proxy as the browser.  It never calls removed v1 ``/ai`` or ``/agent``
routes and it never reads provider secrets.
"""
from __future__ import annotations

import os

UI_HOST = os.getenv("QWENPAW_UI_HOST", "127.0.0.1")
UI_PORT = os.getenv("QWENPAW_UI_PORT", "5173")
BASE_URL = os.getenv("CREATOR_E2E_BASE_URL", f"http://{UI_HOST}:{UI_PORT}")
API_PREFIX = "/api/creator"
STRICT = os.getenv("CREATOR_E2E_STRICT", "0") == "1"

# Deterministic all-project cutover rehearsal fixtures.  Override these when
# validating a different rehearsal without changing the source suite.
R2V_PROJECT_ID = os.getenv("CREATOR_E2E_R2V_PROJECT_ID", "creator-974986b728b6")
R2V_UNIT_ID = os.getenv("CREATOR_E2E_R2V_UNIT_ID", "gen-1783342430520-0-seg-1")
R2V_SECTION_ID = os.getenv("CREATOR_E2E_R2V_SECTION_ID", "gen-1783342430520-0")
EDIT_PROJECT_ID = os.getenv("CREATOR_E2E_EDIT_PROJECT_ID", "creator-b2b3414f6fc8")
EDIT_UNIT_ID = os.getenv("CREATOR_E2E_EDIT_UNIT_ID", "edit-e2e-long-highlight")
ASSET_PROJECT_ID = os.getenv("CREATOR_E2E_ASSET_PROJECT_ID", "creator-023d115f301a")

# A PENDING_REVIEW fixture cannot be created deterministically by a public
# administrative endpoint: it must be produced by the normal Creator flow and
# seal boundary.  Release acceptance may pin that public fixture explicitly;
# otherwise the suite discovers a suitable project through GET /projects.
PENDING_PROJECT_ID = os.getenv("CREATOR_E2E_PENDING_PROJECT_ID", "").strip()
PENDING_TRANSACTION_ID = os.getenv("CREATOR_E2E_PENDING_TRANSACTION_ID", "").strip()
# Optional data-root snapshot containing the same naturally sealed public
# fixture.  The restart test APFS-clones this root and mutates only the clone.
PENDING_SNAPSHOT_ROOT = os.getenv("CREATOR_E2E_PENDING_SNAPSHOT_ROOT", "").strip()
RUN_PROVIDER_SEALING = os.getenv("CREATOR_E2E_RUN_PROVIDER_SEALING", "0") == "1"
PROVIDER_SEALING_TIMEOUT = int(
    os.getenv("CREATOR_E2E_PROVIDER_SEALING_TIMEOUT", "3600")
)
SEALING_RESUME_PROJECT_ID = os.getenv(
    "CREATOR_E2E_SEALING_RESUME_PROJECT_ID", ""
).strip()

# Explicit paid scenario 12 fixture.  The snapshot must contain one real WAN
# provider Task in RUNNING with its providerTaskId already durably bound.
RUN_LATE_MEDIA = os.getenv("CREATOR_E2E_RUN_LATE_MEDIA", "0") == "1"
LATE_MEDIA_IN_PLACE = os.getenv("CREATOR_E2E_LATE_MEDIA_IN_PLACE", "0") == "1"
LATE_MEDIA_SNAPSHOT_ROOT = os.getenv(
    "CREATOR_E2E_LATE_MEDIA_SNAPSHOT_ROOT", ""
).strip()
LATE_MEDIA_PROJECT_ID = os.getenv("CREATOR_E2E_LATE_MEDIA_PROJECT_ID", "").strip()
LATE_MEDIA_TRANSACTION_ID = os.getenv(
    "CREATOR_E2E_LATE_MEDIA_TRANSACTION_ID", ""
).strip()
LATE_MEDIA_TASK_ID = os.getenv("CREATOR_E2E_LATE_MEDIA_TASK_ID", "").strip()
LATE_MEDIA_PROVIDER_TASK_ID = os.getenv(
    "CREATOR_E2E_LATE_MEDIA_PROVIDER_TASK_ID", ""
).strip()
LATE_MEDIA_DELETE_UNIT_ID = os.getenv(
    "CREATOR_E2E_LATE_MEDIA_DELETE_UNIT_ID", ""
).strip()
LATE_MEDIA_TIMEOUT = int(os.getenv("CREATOR_E2E_LATE_MEDIA_TIMEOUT", "3600"))
