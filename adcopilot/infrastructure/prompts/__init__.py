"""Versioned LLM prompt templates for the Campaign Intelligence Engine.

The canonical prompt text lives here as the authoritative source and is seeded
into the ``prompt_versions`` table by Alembic migrations (per the prompt-
versioning rule). Adapters read the DB version at runtime and fall back to the
code constant when a key is not yet seeded.
"""
