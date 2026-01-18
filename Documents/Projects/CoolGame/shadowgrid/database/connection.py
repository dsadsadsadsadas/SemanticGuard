"""
ShadowGrid Database Connection

Async SQLAlchemy connection handling with SQLite for development.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy import event

from .models import Base


# Database URL from environment or default to SQLite
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./shadowgrid.db"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=os.environ.get("DEBUG", "false").lower() == "true",
    future=True
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database initialized")


async def drop_db() -> None:
    """Drop all tables (for testing)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get database session.
    
    Usage:
        @app.get("/players")
        async def get_players(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class DatabaseManager:
    """
    High-level database operations manager.
    """
    
    def __init__(self):
        self.session_factory = AsyncSessionLocal
    
    async def get_session(self) -> AsyncSession:
        """Get a new database session."""
        return self.session_factory()
    
    async def initialize(self) -> None:
        """Initialize database."""
        await init_db()


# Global instance
db_manager = DatabaseManager()
