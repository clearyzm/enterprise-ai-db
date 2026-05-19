"""SQLAlchemy declarative base for ORM models.

Phase 1: Only Base is defined; actual ORM models will be added in Phase 2+.
migrations/env.py imports Base.metadata for autogenerate support.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# Phase 2+ will import all model modules here to ensure they register on Base.metadata:
# from app.models.tenant import Tenant  # noqa: F401
# from app.models.user import User  # noqa: F401
# ...
