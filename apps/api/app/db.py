from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import redis.asyncio as redis

from app.config import settings
from app.models import Base


engine: Engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
    add_missing_columns()


def add_missing_columns() -> None:
    """Keep the MVP dev database usable until Alembic migrations are introduced."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if not existing_tables:
        return

    table_columns = {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in existing_tables
    }

    additions: dict[str, dict[str, str]] = {
        "github_installations": {
            "user_id": "INTEGER NULL REFERENCES user_accounts(id)",
        },
        "webhook_events": {
            "installation_id": "INTEGER NULL REFERENCES github_installations(id)",
            "sender_login": "VARCHAR(255) NOT NULL DEFAULT ''",
        },
        "agent_runs": {
            "user_id": "INTEGER NULL REFERENCES user_accounts(id)",
            "issue_title": "VARCHAR(512) NOT NULL DEFAULT ''",
            "issue_url": "VARCHAR(1024) NOT NULL DEFAULT ''",
            "comment_url": "VARCHAR(1024) NOT NULL DEFAULT ''",
            "pull_request_url": "VARCHAR(1024) NOT NULL DEFAULT ''",
            "provider": "VARCHAR(64) NULL",
            "model_name": "VARCHAR(255) NULL",
        },
    }

    with engine.begin() as connection:
        for table_name, columns in additions.items():
            if table_name not in table_columns:
                continue
            for column_name, definition in columns.items():
                if column_name not in table_columns[table_name]:
                    connection.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
                    )


def get_session() -> Generator[Session]:
    with SessionLocal() as session:
        yield session


def check_postgres() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


async def check_redis() -> None:
    client = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    try:
        await client.ping()
    finally:
        await client.aclose()
