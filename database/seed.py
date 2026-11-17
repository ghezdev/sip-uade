"""Datos locales de prueba, sin episodios ni envíos a Telegram."""

import sys
from uuid import uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .connection import create_db_engine
from .models import TrustedContact, User


def seed_demo(session: Session) -> User:
    session.execute(insert(User).values(id=uuid4(), code="demo", name="Persona de prueba")
                    .on_conflict_do_nothing(index_elements=[User.code]))
    user = session.scalar(select(User).where(User.code == "demo"))
    # Un ID estable evita duplicados aunque el contacto todavía no tenga Chat ID.
    contact_id = uuid5(user.id, "demo-contact")
    session.execute(insert(TrustedContact).values(
        id=contact_id, user_id=user.id, name="Contacto de prueba",
        telegram_chat_id=None, notifications_enabled=False,
    ).on_conflict_do_nothing(index_elements=[TrustedContact.id]))
    return user


def main() -> int:
    engine = None
    try:
        engine = create_db_engine()
        with Session(engine) as session, session.begin():
            seed_demo(session)
    except (SQLAlchemyError, ValueError):
        print("No se pudieron cargar los datos de prueba. Revisá PostgreSQL, DATABASE_URL y las migraciones.",
              file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print("Usuario demo y contacto de prueba disponibles.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
