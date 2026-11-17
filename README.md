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

Con Docker Desktop abierto, prepará la instalación:

```powershell
.\setup.bat
```

El script prepara el entorno, las dependencias, el modelo y PostgreSQL sin iniciar
el detector. Puede repetirse y conserva los archivos y datos existentes.

## Configuración

Completá `.env`, que `setup.bat` crea desde `.env.example` si falta:

```dotenv
TELEGRAM_BOT_TOKEN=token_del_bot
TELEGRAM_CHAT_ID=chat_id_del_contacto
```

El token se obtiene de `@BotFather`; el Chat ID corresponde al contacto que recibirá
las alertas. Ese contacto debe abrir el bot y enviar `/start`.

Después de completar el Chat ID, volvé a ejecutar el script para registrar el contacto:

```powershell
.\setup.bat
```

## Ejecución

Para iniciar con la cámara 0, con Docker Desktop abierto:

```powershell
.\start.bat
```

Para probar un video desde la terminal:

```powershell
.\.venv\Scripts\python.exe runner.py --video "videos_prueba\fall-06-cam0.mp4" --crop right
```

Usá `--crop right` cuando necesites recortar el video.

Para detener PostgreSQL:

```powershell
docker compose down
```
