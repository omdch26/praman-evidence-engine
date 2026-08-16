"""
Database connection and initialization.

Responsibility
    Create SQLAlchemy engine and session factory.
    Run migrations on startup.
    Provide database connection pool.

Must not
    Contain business logic.
    Be imported by domain/ or ports/.
    Make queries directly (use repositories).
"""

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from praman.config import settings
from praman.persistence.models import Base
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def create_db_engine():
    """
    Create SQLAlchemy engine with connection pooling.

    Uses NullPool for Render free tier (ephemeral connections).
    """
    engine = create_engine(
        settings.database_url,
        poolclass=NullPool,  # No connection pooling on free tier
        echo=settings.db_echo,
        connect_args={"connect_timeout": 10},
    )
    return engine


def run_migrations():
    """
    Run SQL migrations from praman/persistence/migrations/*.sql

    Executed at application startup.
    Migrations are idempotent (can be run multiple times safely).
    """
    engine = create_db_engine()

    migrations_dir = Path(__file__).parent / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        logger.warning("No migrations found in %s", migrations_dir)
        return

    logger.info(f"Running {len(migration_files)} migration(s)...")

    with engine.connect() as conn:
        for migration_file in migration_files:
            logger.info(f"Executing {migration_file.name}...")
            sql = migration_file.read_text()
            conn.execute(text(sql))
            conn.commit()

    logger.info("✅ All migrations completed")
    engine.dispose()


def init_database():
    """
    Initialize the database:
    1. Create engine
    2. Run migrations
    3. Create session factory

    Called from main.py at startup.
    """
    try:
        run_migrations()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise


# Session factory (for dependency injection in FastAPI routes)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=create_db_engine())


def get_db() -> Session:
    """
    Dependency injection for database session.

    Usage in FastAPI routes:
        @app.get("/events")
        async def get_events(db: Session = Depends(get_db)):
            return db.query(Event).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
