@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

pushd "%~dp0"
if errorlevel 1 (
    echo ERROR: No se pudo acceder a la carpeta de CareWatch.
    pause
    exit /b 1
)

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo ERROR: Falta el entorno virtual. Ejecutá setup.bat primero.
    goto :error
)
if not exist "models\pose_landmarker_lite.task" (
    echo ERROR: Falta el modelo de MediaPipe. Ejecutá setup.bat primero.
    goto :error
)
if not exist ".env" (
    echo ERROR: Falta .env. Ejecutá setup.bat primero.
    goto :error
)
"%PYTHON%" -B -c "import cv2, mediapipe, numpy, sqlalchemy, alembic, psycopg" >nul 2>&1
if errorlevel 1 (
    echo ERROR: No se pudieron cargar las dependencias. Ejecutá setup.bat.
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

echo Preparando PostgreSQL...
docker compose up -d --wait --wait-timeout 60 postgres
if errorlevel 1 (
    echo ERROR: PostgreSQL no quedó listo. Revisá Docker Desktop y el puerto 5433.
    goto :error
)

rem Estas comprobaciones solo consultan la base, sin ejecutar migraciones ni seed.
"%PYTHON%" -B -m alembic current --check-heads >nul 2>&1
if errorlevel 1 (
    echo ERROR: No se pudo comprobar que la base esté actualizada. Ejecutá setup.bat.
    goto :error
)
"%PYTHON%" -B -c "from database.connection import create_db_engine; from sqlalchemy.orm import Session; from database.repositories import get_user_by_code; engine = create_db_engine(); session = Session(engine); assert get_user_by_code(session, 'demo') is not None; session.close(); engine.dispose()" >nul 2>&1
if errorlevel 1 (
    echo ERROR: No se pudo comprobar el usuario inicial. Ejecutá setup.bat.
    goto :error
)

echo Iniciando CareWatch con la cámara 0...
"%PYTHON%" runner.py --camera 0
if errorlevel 1 (
    echo ERROR: CareWatch terminó con un error. Revisá los mensajes anteriores.
    goto :error
)

popd
exit /b 0

:error
popd
pause
exit /b 1
