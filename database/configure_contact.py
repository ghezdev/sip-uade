"""Configura el contacto local de demo sin enviar mensajes."""

import os
import sys

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from alerts.telegram import load_env, TelegramError
from .connection import create_db_engine
from services.contacts import configure_contact


def main():
    engine = None
    try:
        load_env()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        engine = create_db_engine()
        with Session(engine) as session, session.begin():
            configure_contact(session, chat_id)
    except (ValueError, TelegramError) as exc:
        print(f"No se configuró el contacto: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("No se configuró el contacto. Revisá PostgreSQL y las migraciones.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print("Contacto de demo configurado y habilitado. No se enviaron mensajes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
