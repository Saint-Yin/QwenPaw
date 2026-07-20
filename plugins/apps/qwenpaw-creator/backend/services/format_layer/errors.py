# -*- coding: utf-8 -*-
"""Failures raised for incomplete or inconsistent projection inputs."""

from __future__ import annotations


class ProjectionInputError(ValueError):
    """An authoritative input cannot be projected without inventing data."""


class ProjectionResourceNotFoundError(ProjectionInputError):
    """A requested page resource is absent from the authoritative snapshot."""


class UnsupportedViewError(ProjectionInputError):
    """The requested page is not defined by the current product contract."""
