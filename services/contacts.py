"""Reglas para seleccionar y configurar contactos, sin envíos ni hilos."""

import re
from uuid import uuid5

from database import repositories


def valid_chat_id(value):
    return isinstance(value, str) and re.fullmatch(r"-?[1-9][0-9]*", value.strip()) is not None


def select_contact(session, user_id):
    contacts = repositories.get_enabled_contacts(session, user_id)
    if not contacts:
        return None, "No hay contactos habilitados; notificaciones deshabilitadas"
    if len(contacts) > 1:
        return None, "Hay varios contactos habilitados; notificaciones deshabilitadas"
    contact = contacts[0]
    if not valid_chat_id(contact.telegram_chat_id):
        return None, "El contacto habilitado tiene un Chat ID inválido; notificaciones deshabilitadas"
    return contact, "Destinatario seleccionado desde PostgreSQL"


def configure_contact(session, chat_id):
    if not valid_chat_id(chat_id):
        raise ValueError("TELEGRAM_CHAT_ID debe ser un identificador numérico distinto de cero")
    chat_id = chat_id.strip()
    user = repositories.get_user_by_code(session, "demo", for_update=True)
    if user is None:
        raise ValueError("No existe demo. Ejecutá primero python -m database.seed")
    contact = repositories.get_contact_by_chat_id(session, user.id, chat_id)
    if contact is None:
        contact = repositories.get_contact(session, uuid5(user.id, "demo-contact"))
    active_ids = repositories.get_enabled_contact_ids(session, user.id)
    contact_id = contact.id if contact is not None else None
    if any(identifier != contact_id for identifier in active_ids):
        raise ValueError("Ya hay otro contacto habilitado para demo; revisá la configuración antes de cambiarlo")
    if contact is None:
        contact = repositories.add_contact(session, user.id, "Contacto de confianza")
    contact.telegram_chat_id = chat_id
    contact.notifications_enabled = True
    session.flush()
    return contact
