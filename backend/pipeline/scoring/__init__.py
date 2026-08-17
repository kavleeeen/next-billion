"""Turning a model reply into a verdict.

    thesis    the rubric as numbers, kept in step with THESIS.md by a test
    validate  checks a reply before anything trusts it
"""
from __future__ import annotations

from .validate import Problem, repair_message, validate

__all__ = ["Problem", "repair_message", "validate"]
