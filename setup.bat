@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

pushd "%~dp0"
if errorlevel 1 (
    echo ERROR: No se pudo acceder a la carpeta de CareWatch.
    pause
    exit /b 1
)

echo Preparando CareWatch...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: No se encontró Python. Instalá Python de 64 bits y agregalo al PATH.
    goto :error
)

docker compose version >nul 2>&1
if errorlevel 1 (
    echo ERROR: No se encontró Docker Compose. Instalá Docker Desktop.
    goto :error
)
docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker no está disponible. Abrí Docker Desktop y volvé a intentar.
    goto :error
)

if not exist ".venv" (
    echo Creando el entorno virtual...
    python -m venv ".venv"
    if errorlevel 1 (
        echo ERROR: No se pudo crear el entorno virtual.
        goto :error
    )
)

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo ERROR: El entorno .venv está incompleto. Revisalo antes de continuar.
    goto :error
)
"%PYTHON%" -c "import sys, struct; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: .venv debe usar Python de 64 bits, versión 3.10 a 3.12.
    goto :error
)

echo Comprobando e instalando las dependencias necesarias...
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: No se pudieron instalar las dependencias. Revisá la conexión y requirements.txt.
    goto :error
)

if not exist "models\pose_landmarker_lite.task" (
    echo Descargando el modelo de MediaPipe...
    "%PYTHON%" runner.py --download-model
    if errorlevel 1 (
        echo ERROR: No se pudo descargar el modelo de MediaPipe.
        goto :error
    )
)

if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    if errorlevel 1 (
        echo ERROR: No se pudo crear .env desde .env.example.
        goto :error
    )
)

echo Iniciando PostgreSQL y esperando a que esté listo...
docker compose up -d --wait --wait-timeout 60 postgres
if errorlevel 1 (
    echo ERROR: PostgreSQL no quedó listo. Revisá Docker Desktop y el puerto 5433.
    goto :error
)

echo Aplicando migraciones...
"%PYTHON%" -m alembic upgrade head
if errorlevel 1 (
    echo ERROR: No se pudieron aplicar las migraciones. Revisá PostgreSQL.
    goto :error
)

echo Creando los datos iniciales...
"%PYTHON%" -m database.seed
if errorlevel 1 (
    echo ERROR: No se pudieron crear los datos iniciales.
    goto :error
)

rem Durante setup, el Chat ID se toma de .env; setlocal conserva el entorno original.
set "TELEGRAM_CHAT_ID="
"%PYTHON%" -B -c "import os, sys; from alerts.telegram import load_env; from services.contacts import valid_chat_id; load_env(); sys.exit(0 if valid_chat_id(os.environ.get('TELEGRAM_CHAT_ID')) else 10)"
set "TELEGRAM_CHECK=%errorlevel%"
if "%TELEGRAM_CHECK%"=="10" goto :telegram_pending
if not "%TELEGRAM_CHECK%"=="0" goto :telegram_error

echo Configurando el contacto de Telegram...
"%PYTHON%" -m database.configure_contact
if errorlevel 1 goto :telegram_error
echo El contacto de Telegram fue configurado correctamente.
goto :ready

:telegram_pending
echo.
echo La instalación principal se completó, pero falta configurar Telegram.
echo Agregá TELEGRAM_CHAT_ID en .env y volvé a ejecutar setup.bat para registrar el contacto de confianza.

:ready
echo.
echo Preparación principal lista. Los datos existentes se conservaron.
echo Después ejecutá start.bat.
popd
pause
exit /b 0

:telegram_error
echo ERROR: No se pudo revisar o configurar el contacto de Telegram.
echo Revisá el error anterior y la configuración de .env y PostgreSQL.
goto :error

:error
echo.
echo La preparación no se completó. Corregí el error y ejecutá setup.bat nuevamente.
popd
pause
exit /b 1
