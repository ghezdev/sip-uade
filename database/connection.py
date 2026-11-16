"""Configuración de PostgreSQL para sesiones síncronas."""

import os

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import make_url


DEFAULT_URL = URL.create(
    "postgresql+psycopg", username="carewatch", password="carewatch_dev",
    host="127.0.0.1", port=5433, database="carewatch",
)


def get_database_url() -> URL:
    value = os.environ.get("DATABASE_URL")
    url = make_url(value) if value else DEFAULT_URL
    if url.drivername not in ("postgres", "postgresql", "postgresql+psycopg"):
        raise ValueError("DATABASE_URL debe indicar una conexión PostgreSQL con Psycopg 3")
    return url.set(drivername="postgresql+psycopg")


def create_db_engine(url=None):
    return create_engine(url if url is not None else get_database_url(),
                         pool_pre_ping=True, connect_args={"connect_timeout": 5})
