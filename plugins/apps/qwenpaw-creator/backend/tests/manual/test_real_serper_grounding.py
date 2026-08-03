# -*- coding: utf-8 -*-
# pylint: disable=protected-access
"""Manual real-provider acceptance for Serper grounding.

This opt-in entry point exercises the real Serper ``/search``, ``/images`` and
``/lens`` endpoints and therefore consumes real quota. Every test skips unless
``SERPER_API_KEY`` is exported, so the module stays collectable-but-inert in CI
and in the default local suite.

Run manually::

    SERPER_API_KEY=... pytest tests/manual/test_real_serper_grounding.py -q

``SERPER_LENS_IMAGE_URL`` may override the public reference image used for
the reverse image search case.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from services.web_grounding.providers import adapters

pytestmark = pytest.mark.manual_real

requires_serper_key = pytest.mark.skipif(
    not os.environ.get("SERPER_API_KEY"),
    reason="SERPER_API_KEY not configured; manual real-provider run only",
)

DEFAULT_LENS_IMAGE_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/a/a8/"
    "Tour_Eiffel_Wikimedia_Commons.jpg"
)


def _run(coroutine_factory):
    async def runner():
        async with httpx.AsyncClient(timeout=60.0) as client:
            return await coroutine_factory(client)

    return asyncio.run(runner())


@requires_serper_key
def test_real_serper_text_search_returns_relevant_sources():
    results = _run(
        lambda client: adapters._search_serper(
            client,
            "Eiffel Tower construction year",
            3,
        ),
    )

    assert results, "real /search returned no organic results"
    for source in results:
        assert source["provider"] == "serper"
        assert source["url"].startswith(("http://", "https://"))
        assert source["title"]


@requires_serper_key
def test_real_serper_image_search_returns_image_urls():
    results = _run(
        lambda client: adapters._search_serper_visuals(
            client,
            "Eiffel Tower at dusk",
            3,
        ),
    )

    assert results, "real /images returned no image results"
    for source in results:
        assert source["provider"] == "serper"
        assert source["url"].startswith(("http://", "https://"))


@requires_serper_key
def test_real_serper_lens_reverse_image_search():
    image_url = os.environ.get(
        "SERPER_LENS_IMAGE_URL",
        DEFAULT_LENS_IMAGE_URL,
    )
    results = _run(
        lambda client: adapters._search_serper_lens(
            client,
            image_url,
            5,
            query="manual lens acceptance",
        ),
    )

    # Lens recall depends on the reference image; require a well-formed
    # response rather than a minimum match count.
    assert isinstance(results, list)
    for source in results:
        assert source["provider"] == "serper_lens"
        assert source["url"].startswith(("http://", "https://"))
