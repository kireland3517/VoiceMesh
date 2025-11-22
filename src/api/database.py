"""Database connection and session management."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
import structlog

from src.api.config import settings

logger = structlog.get_logger()

# Create async engine
# Use SQLite for local development if DATABASE_URL is not set
if settings.DATABASE_URL:
    # Convert postgres:// to postgresql+asyncpg:// for async support
    database_url = settings.DATABASE_URL.replace("postgres://", "postgresql+asyncpg://").replace("postgresql://", "postgresql+asyncpg://")

    # asyncpg doesn't accept sslmode parameter, need to remove it
    # and configure SSL through connect_args instead
    if "?sslmode=" in database_url or "&sslmode=" in database_url:
        # Remove sslmode from URL (asyncpg doesn't accept it)
        import re
        database_url = re.sub(r'[?&]sslmode=[^&]*', '', database_url)
        # Clean up any leftover ? or &
        database_url = re.sub(r'\?&', '?', database_url)
        database_url = re.sub(r'\?$', '', database_url)
else:
    # Use SQLite for local development
    database_url = "sqlite+aiosqlite:///./voicemesh.db"
    logger.info("using_sqlite_for_local_development")

# Configure connection args for Fly.io Postgres
# For internal Fly.io connections (.internal hostname), disable SSL
# SSL on internal network causes ConnectionResetError with asyncpg
connect_args = {}

engine = create_async_engine(
    database_url,
    echo=not settings.is_production,  # Log SQL queries in development
    pool_pre_ping=True if settings.DATABASE_URL else False,  # Only for Postgres
    pool_size=5 if settings.DATABASE_URL else 0,  # SQLite doesn't use connection pooling
    max_overflow=10 if settings.DATABASE_URL else 0,
    connect_args=connect_args,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Create declarative base for models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get database session.

    Yields:
        AsyncSession: Database session

    Example:
        @app.get("/customers")
        async def get_customers(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Customer))
            return result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("database_session_error", error=str(e))
            raise
        finally:
            await session.close()


async def init_db():
    """
    Initialize database tables.

    Creates all tables defined in models.
    This should only be used in development.
    In production, use Alembic migrations instead.
    """
    # Import all models here to ensure they're registered
    from src.api.models import Customer, Function, Call

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("database_tables_created")


async def close_db():
    """Close database connections."""
    await engine.dispose()
    logger.info("database_connections_closed")
