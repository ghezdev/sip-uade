"""Envío de mensajes a Telegram, independiente del detector."""

import argparse
import json
import os
from math import isfinite
from http.client import HTTPException
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
TEST_MESSAGE = "Mensaje de prueba de CareWatch. La conexión con Telegram funciona."


class TelegramError(RuntimeError):
    """No se pudo configurar o completar el envío a Telegram."""

    def __init__(self, message, *, retry_after=None, uncertain=False):
        super().__init__(message)
        self.retry_after = retry_after
        self.uncertain = uncertain


def is_configured(*, require_chat=True) -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
                and (not require_chat or os.environ.get("TELEGRAM_CHAT_ID", "").strip()))


def load_env(path: Path = ENV_FILE) -> None:
    """Carga las dos variables de Telegram sin reemplazar las del entorno."""
    try:
        content = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return
    except (OSError, UnicodeError):
        raise TelegramError("No se pudo leer el archivo .env; revisá sus permisos y codificación UTF-8.") from None

    for line_number, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name = name.strip()
        if name not in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            continue
        value = value.strip()
        if not separator or (value.startswith(("'", '"')) and
                             (len(value) < 2 or value[-1] != value[0])):
            raise TelegramError(f"Revisá el formato de .env en la línea {line_number}: usá VARIABLE=valor.")
        if value.startswith(("'", '"')):
            value = value[1:-1]
        os.environ.setdefault(name, value)


def _api_error(code: int | str, retry_after=None) -> TelegramError:
    if code in (401, 404):
        return TelegramError("Telegram rechazó el token. Revisá TELEGRAM_BOT_TOKEN con BotFather.")
    if code == 400:
        return TelegramError("Telegram rechazó el mensaje. Revisá TELEGRAM_CHAT_ID y que el contacto haya iniciado el bot.")
    if code == 403:
        return TelegramError("El bot no tiene permiso para escribir en ese chat; revisá si está bloqueado.")
    if code == 429:
        if (isinstance(retry_after, bool) or not isinstance(retry_after, (int, float))
                or not isfinite(retry_after) or retry_after < 0):
            retry_after = 5.0
        return TelegramError(
            "Telegram recibió demasiadas solicitudes. Esperá antes de intentar otra vez.",
            retry_after=retry_after,
        )
    return TelegramError(
        f"Telegram no pudo confirmar el envío (código {code}). Revisá el chat antes de intentar más tarde.",
        uncertain=True,
    )


def send_message(text: str, *, chat_id=None) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID", "") if chat_id is None else chat_id).strip()
    if not token or not chat_id:
        raise TelegramError("Configurá TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en el entorno o en .env.")
    if not isinstance(text, str) or not text.strip() or len(text) > 4096:
        raise TelegramError("El mensaje debe tener entre 1 y 4096 caracteres y no puede estar vacío.")

    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    try:
        request = Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
    except HTTPError as exc:
        retry_after = None
        try:
            if exc.code == 429:
                error_body = json.loads(exc.read())
                if isinstance(error_body, dict) and isinstance(error_body.get("parameters"), dict):
                    retry_after = error_body["parameters"].get("retry_after")
        except (ValueError, OSError, HTTPException):
            pass
        finally:
            exc.close()
        raise _api_error(exc.code, retry_after) from None
    except (URLError, OSError, HTTPException):
        raise TelegramError(
            "No se pudo completar la conexión con Telegram. Revisá internet. "
            "Comprobá el chat antes de repetir: el mensaje podría haber llegado.", uncertain=True,
        ) from None
    except ValueError:
        raise TelegramError(
            "No se pudo procesar la solicitud o la respuesta de Telegram. Revisá el token y el chat.",
            uncertain=True,
        ) from None

    if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
        raise TelegramError("Telegram devolvió una respuesta con un formato inesperado.", uncertain=True)
    if not payload["ok"]:
        parameters = payload.get("parameters")
        retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
        raise _api_error(payload.get("error_code", "desconocido"), retry_after)
    if not isinstance(payload.get("result"), dict):
        raise TelegramError("Telegram no devolvió la confirmación del mensaje.", uncertain=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Enviar un mensaje de prueba de CareWatch a Telegram")
    parser.add_argument("--message", default=TEST_MESSAGE, help="Texto del mensaje de prueba")
    args = parser.parse_args(argv)
    try:
        load_env()
        send_message(args.message)
    except TelegramError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("Mensaje enviado a Telegram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
