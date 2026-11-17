# CareWatch

CareWatch es un proyecto de Ingeniería Informática de UADE para detectar posibles
caídas con una cámara o un video. Usa MediaPipe y OpenCV, envía alertas y avisos de
recuperación por Telegram y guarda episodios e historial en PostgreSQL.
Se ejecuta localmente; todavía no tiene FastAPI ni interfaz web.

## Estructura

- `runner.py`: conecta captura, detector, alertas, notificaciones y persistencia.
- `fall_detection/`: motor, estados, eventos y configuración de detección.
- `adapters/`: cámara, conversión de posturas y vista previa.
- `alerts/`: cuenta regresiva y envíos de Telegram en segundo plano.
- `services/contacts.py`: reglas de selección y configuración de contactos.
- `database/`: conexión, modelos, repositorios, guardado y worker de persistencia.
- `database/migrations/`: migraciones de Alembic.
- `tests/`: pruebas locales, ignoradas por Git.
- `archive/`: material histórico local; no usar como implementación actual.
- `videos_prueba/`: entradas manuales; solo se comparten los dos videos del README.

## Ejecutar

Usar el entorno virtual del proyecto, compatible con Python 3.10.6.
Los pasos de instalación, PostgreSQL y configuración de Telegram están en README.md.
Desde la raíz, en PowerShell:

```powershell
.\.venv\Scripts\python.exe runner.py --camera 0
.\.venv\Scripts\python.exe runner.py --video "videos_prueba\fall-06-cam0.mp4" --crop right
```

## Pruebas locales

`tests/` debe existir localmente; no se incluye al clonar el repositorio.
Las pruebas simulan Telegram y no deben enviar mensajes reales. Las de PostgreSQL
usan una base temporal aislada y no deben modificar la base de desarrollo.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -v
.\.venv\Scripts\python.exe -m pip check
```

## Restricciones

- Mantener el detector independiente de cámara, Telegram, PostgreSQL y futura API.
- No cambiar algoritmos, umbrales, tiempos, estados, eventos ni pausas sin pedido explícito.
- No modificar reintentos, cancelaciones, recuperación o prevención de duplicados de Telegram.
- `READY` no confirma un envío; `SENT` requiere aceptación de Telegram y `UNKNOWN` indica incertidumbre.
- Mantener el destinatario del episodio y el respaldo de entorno solo ante indisponibilidad inicial de PostgreSQL.
- No bloquear la cámara con red o SQL; conservar workers independientes y cierre compartido de hasta 3 s.
- Conservar transacciones, claves foráneas y protección atómica de notificaciones `SENT`.
- No cambiar modelos o migraciones, borrar datos ni volúmenes de Docker sin autorización.
- No modificar ni mostrar `.env`; no incorporar credenciales reales a Git.
- Conservar el modelo MediaPipe local e ignorado; no borrar pruebas ni recursos locales sin autorización.
- Usar nombres de código en inglés y comentarios breves en español cuando aporten claridad.
- No agregar capas, dependencias o funcionalidades fuera del alcance solicitado.
- No hacer commits, push ni crear ramas automáticamente.
