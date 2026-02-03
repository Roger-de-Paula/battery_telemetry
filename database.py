from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from pydantic_settings import BaseSettings

from models import Base

# Default URL for local development; override with DATABASE_URL env or .env
class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/battery_telemetry"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


engine = None
async_session_factory = None


def init_db() -> None:
    global engine, async_session_factory
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        echo=False,
    )
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if async_session_factory is None:
        init_db()
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    if engine is None:
        init_db()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
