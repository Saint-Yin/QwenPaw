# -*- coding: utf-8 -*-
"""Serper (google.serper.dev) provider boundary.

The adapter implementation remains private to the pipeline, mirroring the
Tavily extraction; this module defines the ownership boundary for
provider-specific endpoint constants and response parsing.
"""

SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_IMAGES_URL = "https://google.serper.dev/images"
SERPER_LENS_URL = "https://google.serper.dev/lens"
SERPER_SCRAPE_URL = "https://google.serper.dev/scrape"

SERPER_SEARCH_MAX_ATTEMPTS = 10
SERPER_LENS_MAX_ATTEMPTS = 10
SERPER_SCRAPE_MAX_ATTEMPTS = 3
SERPER_RETRY_BACKOFF_CAP_SECONDS = 10.0
