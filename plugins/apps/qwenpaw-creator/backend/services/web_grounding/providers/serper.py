# -*- coding: utf-8 -*-
"""Serper (google.serper.dev) provider boundary.

The adapter implementation remains private to the pipeline, mirroring the
Tavily extraction; this module defines the ownership boundary for
provider-specific endpoint constants and response parsing.
"""

SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_IMAGES_URL = "https://google.serper.dev/images"
