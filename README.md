# CareWatch

CareWatch es un sistema de detección de posibles caídas mediante cámara.
Permite enviar alertas por Telegram y registrar información en PostgreSQL.

## Requisitos

- Python de 64 bits, versión 3.10 a 3.12; verificado con Python 3.10.6.
- Docker Desktop con Docker Compose.
- Git.
- Cámara web para detección en tiempo real.
- Internet para instalar dependencias, descargar el modelo y enviar alertas.

## Instalación

Desde PowerShell:

```powershell
git clone https://github.com/ghezdev/sip-uade.git
Set-Location sip-uade
```

Creá y activá un entorno virtual de Python antes de instalar las dependencias:

```powershell
python -m pip install -r requirements.txt
```

Si todavía no está disponible el modelo de MediaPipe, descargalo:

```powershell
python runner.py --download-model
```

## Configuración

Copiá `.env.example` como `.env` y completá:

```dotenv
TELEGRAM_BOT_TOKEN=token_del_bot
TELEGRAM_CHAT_ID=chat_id_del_contacto
```

El token se obtiene de `@BotFather`; el Chat ID corresponde al contacto que recibirá
las alertas. Ese contacto debe abrir el bot y enviar `/start`.

Con Docker Desktop abierto y el entorno virtual activado, prepará PostgreSQL y el contacto:

```powershell
docker compose up -d --wait
python -m alembic upgrade head
python -m database.seed
python -m database.configure_contact
```

## Ejecución

Con el entorno virtual activado:

```powershell
# Cámara
python runner.py --camera 0

# Video
python runner.py --video "videos_prueba\fall-06-cam0.mp4" --crop right
```

Usá `--crop right` cuando necesites recortar el video.

Para detener PostgreSQL:

```powershell
docker compose down
```
