# CareWatch

CareWatch es un sistema de detección de posibles caídas mediante cámara.
Permite enviar alertas por Telegram y registrar información en PostgreSQL.

## Requisitos

- Python de 64 bits, versión 3.10 a 3.12; verificado con Python 3.10.6.
- Docker Desktop con Docker Compose.
- Git para clonar el repositorio.
- Cámara web para usar el detector en tiempo real.
- Internet para instalar dependencias, descargar el modelo y enviar alertas.

## Instalación

Desde PowerShell:

1. Clonar el repositorio:

   ```powershell
   git clone https://github.com/ghezdev/sip-uade.git
   ```

2. Entrar a la carpeta:

   ```powershell
   Set-Location sip-uade
   ```

3. Crear el entorno virtual usando una versión compatible de Python:

   ```powershell
   python -m venv .venv
   ```

4. Activar el entorno:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   Si PowerShell bloquea la activación, ejecutar lo siguiente y volver a activarlo.
   El cambio se aplica solo a la terminal actual:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
   ```

5. Instalar las dependencias:

   ```powershell
   python -m pip install -r requirements.txt
   ```

6. Descargar el modelo de MediaPipe si no existe `models/pose_landmarker_lite.task`:

   ```powershell
   python runner.py --download-model
   ```

Usar la misma terminal para los pasos siguientes. En una terminal nueva, entrar
a la carpeta del proyecto y volver a activar el entorno.

## Configuración

1. Crear `.env` desde la plantilla. Si ya existe, editarlo sin reemplazarlo:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Completar las variables de Telegram en `.env`:

   ```dotenv
   TELEGRAM_BOT_TOKEN=token_del_bot
   TELEGRAM_CHAT_ID=chat_id_del_contacto
   ```

   Obtener el token con `@BotFather`. El contacto debe abrir el bot y enviar `/start`.
   Para obtener su Chat ID, abrir `https://api.telegram.org/bot<TOKEN>/getUpdates`
   reemplazando `<TOKEN>` por el token del bot. Buscar `message.chat.id` del mensaje
   del contacto en la respuesta de [getUpdates](https://core.telegram.org/bots/api#getupdates).
   Si la lista está vacía, enviar otro mensaje al bot y consultar de nuevo.
   No compartir el token ni subir `.env`. Las variables ya definidas en el entorno
   tienen prioridad sobre `.env`, incluso si están vacías.

3. Abrir Docker Desktop e iniciar PostgreSQL:

   ```powershell
   docker compose up -d
   docker compose ps
   ```

   Esperar a que `postgres` aparezca como `healthy` antes de continuar.
   La conexión local ya está configurada para este Compose.

4. Crear o actualizar las tablas:

   ```powershell
   python -m alembic upgrade head
   ```

5. Crear el usuario de prueba `demo` y su contacto inicial:

   ```powershell
   python -m database.seed
   ```

6. Habilitar el contacto usando `TELEGRAM_CHAT_ID` de `.env` o del entorno:

   ```powershell
   python -m database.configure_contact
   ```

El seed y la configuración pueden repetirse sin duplicar registros. Debe quedar
exactamente un contacto habilitado con Chat ID válido. Si hay otro habilitado,
el comando de configuración rechaza el cambio y pide revisar los contactos.
Para cambiar el destinatario, actualizar el Chat ID, repetir el comando y reiniciar
CareWatch. Sin contactos habilitados, con varios o con Chat ID inválido no se envían
alertas; el Chat ID del entorno solo sirve de respaldo si PostgreSQL no está
disponible al iniciar.

## Ejecución

Con el entorno activado y PostgreSQL iniciado, ejecutar con cámara:

```powershell
python runner.py --camera 0
```

Para otra cámara, probar con `--camera 1`. Para usar un video incluido:

```powershell
python runner.py --video "videos_prueba\fall-06-cam0.mp4" --crop right
```

`--crop right` selecciona la mitad RGB de ese video. Para un video propio completo:

```powershell
python runner.py --video "C:\videos\prueba.mp4"
```

Detener CareWatch con `q`, `Esc`, cerrando la ventana o con `Ctrl+C` en la terminal.
Para detener PostgreSQL sin borrar sus datos:

```powershell
docker compose down
```

## Verificación opcional

Las pruebas no son necesarias para ejecutar CareWatch. `tests/` se conserva
localmente y no se distribuye mediante GitHub; se necesita una copia para ejecutarlas.
Con el entorno activado, el modelo descargado y PostgreSQL iniciado:

```powershell
python -B -m unittest discover -v
```
