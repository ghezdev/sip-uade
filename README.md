# Detector de caídas — motor e integración local

Proyecto SIP (UADE): motor de Python independiente, adaptadores OpenCV/MediaPipe,
diagnóstico y cuenta regresiva **local** basada en eventos. No se implementan
Telegram, web, SQLite, zonas de piso, reconocimiento de muebles ni calibración.
Los originales de [FirstTests](archive/FirstTests/) y
[Presentation1](archive/Presentation1/) se conservan intactos dentro de `archive/`.
Son material histórico y académico; no forman parte de la ejecución actual.

`ON_FLOOR` significa **postura compatible con estar en el suelo**, no ubicación
confirmada. Una postura horizontal prolongada puede ser voluntaria: el motor
reporta una situación posible, no determina la intención ni mide inmovilidad real.

## Preparación en VS Code (Windows)

Abrir la raíz del proyecto. Usar Python de 64 bits, versión 3.10 a 3.12.
En la terminal PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe runner.py --download-model
```

Si `.venv` y el modelo ya existen, omitir su creación/descarga. En la paleta
`Ctrl+Shift+P`, elegir **Python: Select Interpreter** y `.venv\Scripts\python.exe`.
Los comandos con ruta explícita no requieren activar el entorno ni cambiar la
política de PowerShell. `--download-model` descarga el modelo oficial versionado
Pose Landmarker Lite y termina; no sobrescribe uno existente ni abre la cámara.
Se puede elegir otro archivo compatible con `--model "C:\modelos\pose.task"`.
La ejecución normal no necesita internet.

`requirements.txt` fija MediaPipe 0.10.21, OpenCV contrib 4.11.0.86 y NumPy 1.26.4;
se verificó este conjunto con Python 3.10.6. MediaPipe requiere NumPy < 2 en esa
versión. Solo se instala una distribución de `cv2`, `opencv-contrib-python`;
no mezclarla con `opencv-python` o paquetes headless. Las dependencias transitivas
las resuelve pip; no es un lock de todas las plataformas.

Referencias: [MediaPipe](https://pypi.org/project/mediapipe/0.10.21/),
[OpenCV contrib](https://pypi.org/project/opencv-contrib-python/4.11.0.86/),
[Pose Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python).

## Ejecutar cámara y videos

```powershell
# Webcam integrada; probar 1 o 2 para otro dispositivo
.\.venv\Scripts\python.exe runner.py --camera 0

# Video convencional, sin recorte (none es el valor predeterminado)
.\.venv\Scripts\python.exe runner.py --video "C:\videos\prueba.mp4" --crop none

# URFD: profundidad a la izquierda, RGB a la derecha
.\.venv\Scripts\python.exe runner.py --video "videos_prueba\fall-06-cam0.mp4" --crop right

# Otro caso y ejecución sin ventana
.\.venv\Scripts\python.exe runner.py --video "videos_prueba\fall-02-cam0.mp4" --crop right --no-preview
```

`--crop` acepta `left`, `right` y `none`. Se recorta antes de MediaPipe y del
diagnóstico, sin estirar ni redimensionar: 1280×480 produce una mitad de 640×480.
Con ancho impar, la derecha incluye la columna central restante. Un ancho menor
que dos píxeles no admite recorte. El adaptador usa las dimensiones del recorte
para su geometría; se conservan los timestamps de captura.

La ventana muestra estado actual, seguimiento, criterio del episodio, ángulo del
torso, descenso, velocidad, candidato horizontal, permanencia acumulada,
recuperación estable y estado de alerta local. `q`, `Esc`, cerrar la ventana o
`Ctrl+C` terminan el programa. Los eventos y cambios de estado se imprimen también
en consola con timestamp, criterio e identificador del episodio.

Si `FALLING` y `ON_FLOOR` ocurren en un mismo frame, el estado actual sigue siendo
`ON_FLOOR` y se muestra **Evento reciente: FALLING (fall_started)** durante dos
segundos de tiempo de presentación. Esto no demora el motor ni cambia el tiempo
del video. En consola aparecen ambos eventos con su timestamp original.

Cerrar Zoom/Meet si ocupan la webcam y habilitar el acceso de aplicaciones de
escritorio a la cámara en Windows.

## Rutas de detección

El adaptador convierte los puntos de MediaPipe a datos simples. El motor es el
único que clasifica; no importa OpenCV, MediaPipe, Telegram ni el flujo de alertas.
Las rutas producen un episodio con un único `criterion`:

| Criterio | Evidencia y transición |
|---|---|
| `rapid_descent` | Referencia corporal no horizontal y velocidad ≥ 1.2 torsos/s con descenso ≥ 0.5 torsos. Entra en `FALLING`; postura horizontal dentro de 1.5 s permite `ON_FLOOR`. |
| `posture_change` | Una postura previa no horizontal pasa a horizontal, con cambio de orientación y descenso corporal o rotación marcada. La evidencia debe mantenerse 0.75 s. Entra directamente en `ON_FLOOR`, sin inventar movimiento rápido. |
| `persistent_posture` | Postura horizontal válida durante 5 s, incluso si la persona ya estaba acostada al iniciar o no hubo referencia previa. Entra directamente en `ON_FLOOR`. |

Una persona inicialmente sentada puede iniciar cualquiera de las dos primeras
rutas. `UNKNOWN` ya no bloquea los episodios si hay geometría válida. `STANDING`
es una etiqueta aproximada de aspecto estrecho, no un clasificador completo de
actividades; una pose sentada ancha puede verse como `UNKNOWN` mientras se monitorea.

Con ángulo disponible, las rutas postural y persistente exigen torso ≥ 60° respecto
de la vertical de imagen y aspecto ≥ 0.65. Una silueta sentada ancha con torso
vertical no basta para esas rutas. La ruta rápida conserva también el aspecto
histórico ≥ 1.0 como evidencia de postura final y permanencia: en varios clips
URFD el torso proyectado no supera 60° aunque el cuerpo termina horizontal.
Sin el campo opcional de ángulo se usa el aspecto ≥ 1.0 en todas las rutas.
La vertical es la de la imagen, no una vertical del ambiente calibrada.

La ruta postural compara contra una referencia no horizontal dentro de una
ventana de 4 s. Exige giro ≥ 30° y descenso de cadera u hombros ≥ 0.25 torsos,
o giro ≥ 45° aunque la cadera casi no baje. Sin ángulos, usa cambio de aspecto
≥ 0.4 y descenso corporal. El descenso se divide por el torso de referencia.
Para movimientos más lentos que la ventana queda la ruta de persistencia.

Los umbrales de la ruta rápida no cambiaron. Los nuevos ángulos, ventanas y tiempos
son valores iniciales explicables, todavía pendientes de ajuste y evaluación con
videos positivos y actividades normales independientes de los usados para ajustar.

## Permanencia acumulada y recuperación confirmada

`floor_confirm_seconds` conserva su valor predeterminado de **15 s**, pero ahora
cuenta permanencia **acumulada observada** dentro del mismo episodio. Solo se suman
intervalos entre mediciones horizontales válidas consecutivas, separados como
máximo 0.5 s. No se acredita tiempo desconocido. Las rutas postural y persistente
incluyen el tramo horizontal continuo observado antes de abrir el episodio: no
hay que esperar 5 + 15 s para confirmar una postura presente desde el inicio.

Cuando deja de cumplir la postura horizontal, pasa a `RECOVERING` y pausa la
permanencia sin borrarla. Un intento fallido devuelve a `ON_FLOOR` con el mismo
identificador, criterio, confirmación y tiempo acumulado. Se pueden suceder varios
intentos sin crear episodios ni alertas nuevos.

La recuperación solo se confirma tras **5 s continuos** de torso vertical y
cadera suficientemente elevada respecto de la postura previa al episodio
(tolerancia de 0.25 torsos). Sin referencia previa se exige la postura vertical
sostenida. Si faltan ángulos, el aspecto estrecho sirve como señal vertical.
Esto permite volver a una postura sentada a la altura previa. No basta adoptar
brevemente una silueta vertical mientras la cadera sigue baja.

Una recuperación confirmada emite `person_recovered`, muestra `RECOVERED`, cierra
el episodio y rearma inmediatamente. La siguiente caída puede tener otro ID.
Se eliminó el antiguo `rearm_seconds`: `recovery_seconds` ahora contiene toda la
espera estable, evitando cerrar el episodio antes de tiempo.

Ejemplo de permanencia: 8 s observados en postura horizontal + intento de levantarse
de 3 s + 2 s horizontales = 10 s acumulados, no 13 s ni un episodio nuevo.

## Cuenta regresiva local, separada del motor

`alerts.workflow.AlertWorkflow` consume eventos. Una única confirmación
`fall_confirmed` inicia una cuenta de 30 s por episodio. Los intentos de levantarse
y las pérdidas de seguimiento **no la cancelan, pausan ni reinician**: su vencimiento
permanece igual. Solo `person_recovered` cancela la alerta pendiente.
Si la recuperación llega exactamente al vencimiento, tiene prioridad.

Los estados locales son `IDLE`, `COUNTDOWN`, `CANCELLED` y `READY`. `READY` significa
que venció la ventana; **no se envió una notificación**. No hay Telegram ni otro
canal externo. Una recuperación posterior también puede cancelar un `READY` local
que aún no se despachó. Los eventos repetidos del mismo episodio no reinician la
cuenta, ni después de cancelarla. Este registro vive en memoria y no sobrevive al
reinicio del proceso.

Para modificar únicamente los tiempos de una ejecución:

```powershell
.\.venv\Scripts\python.exe runner.py --video "videos_prueba\fall-06-cam0.mp4" --crop right --recovery-seconds 5

# Ensayo rápido de la cuenta local, solo si el clip conserva suficiente postura válida
.\.venv\Scripts\python.exe runner.py --video "videos_prueba\fall-06-cam0.mp4" --crop right --floor-confirm-seconds 1 --cancel-seconds 0.5
```

Reducir estos tiempos es una prueba funcional, no una calibración validada.
Un video termina en EOF: no se inventan frames ni se prolonga el reloj para hacer
vencer una cuenta pendiente. Muchos clips son demasiado cortos para confirmar con
15 s o demostrar una recuperación estable de 5 s; esos casos están cubiertos por
mediciones sintéticas reproducibles.

## Contrato y seguimiento

```python
from fall_detection import DetectorConfig, FallDetector, Measurement

detector = FallDetector(DetectorConfig(recovery_seconds=5.0))
result = detector.update(Measurement(
    timestamp=0.0, person_present=True,
    hip_y=0.6, torso_length=0.4, aspect_ratio=0.8, visibility=0.9,
    shoulder_y=0.2, torso_angle=0.0,
))
print(result.state, result.criterion, result.events, result.metrics)
```

`update(measurement) -> DetectorResult` acepta una secuencia de una persona y un
único llamador. Todos los modelos son inmutables. Los campos corporales básicos
siguen siendo `person_present`, `hip_y`, `torso_length`, `aspect_ratio` y `visibility`.
Se agregan `shoulder_y` y `torso_angle` opcionales para admitir mediciones antiguas.
Los valores no finitos/incorrectos generan medición inválida; no simulan ausencia.

El adaptador trabaja en unidades de alto de imagen (`x' = x * ancho / alto`, `y' = y`),
para no mezclar ejes de escalas distintas. Se exigen hombros/caderas dentro del
frame, su visibilidad mínima de 0.5 y al menos ocho puntos visibles. La longitud
del torso y el aspecto deben ser positivos. MediaPipe Tasks utiliza una sola pose
y modo `VIDEO` sincrónico para conservar la asociación entre frame y medición.

La webcam aporta `time.monotonic()`; el video aporta `CAP_PROP_POS_MSEC` relativo
al primer frame, sin depender de la velocidad de inferencia. Si faltan tiempos
crecientes, se advierte y aproxima con FPS constantes; `--video-fps 30` permite
reemplazarlos explícitamente. Esto no reproduce exactamente videos de tasa variable.
MediaPipe recibe milisegundos crecientes; el motor conserva los segundos originales.

Timestamps repetidos, desordenados o inválidos se rechazan antes de modificar el
estado. El motor no lee relojes ni duerme. Cada nueva medición hace avanzar la
máquina; la cuenta local usa la misma línea temporal de los eventos.

El seguimiento (`VALID`, `ABSENT`, `INVALID`, `LOST`) es independiente del estado.
Una medición inválida o un hueco excesivo limpia la historia usada para iniciar
candidatos, pausa la permanencia y reinicia la evidencia de recuperación estable.
No borra episodios activos ni tiempo acumulado. Tras 1 s sin datos válidos se
emite `person_lost` una vez y se muestra `NO_PERSON`; al reaparecer se conserva el
episodio y se emite `person_detected`. La pérdida nunca cuenta como recuperación.

Los eventos son `person_detected`, `person_lost`, `fall_started`, `fall_suspected`,
`person_on_floor`, `fall_confirmed` y `person_recovered`. Incluyen UUID, timestamp,
episodio, criterio y permanencia acumulada. Cada episodio establecido emite una
sola entrada al suelo, confirmación y recuperación. Los candidatos rápidos que
no alcanzan postura compatible en 1.5 s se descartan sin confirmar.

Un fallo de cámara/modelo/inferencia/ventana termina con error y libera recursos;
EOF normal termina con éxito. No hay reconexión ni watchdog para drivers que
bloqueen `read()`. Si no llegan entradas, las máquinas no ejecutan solas un tick;
al reanudarse, la cuenta conserva su vencimiento original. No hay garantías de
seguimiento de identidad ni de múltiples personas.

## Pruebas y validación pendiente

```powershell
# Biblioteca estándar: motor y dobles de adaptadores; algunas pruebas pueden omitirse
python -B -m unittest discover -v

# Todas las pruebas, incluyendo OpenCV/MediaPipe reales y render sin abrir ventanas
.\.venv\Scripts\python.exe -B -m unittest discover -v
.\.venv\Scripts\python.exe -m pip check
```

Se prueban rutas rápidas/posturales/persistentes, inicio sentado, rotación con poca
bajada de cadera, distintos FPS, recortes, datos inválidos, pérdida de seguimiento,
permanencia acumulada, múltiples intentos fallidos, recuperación estable y nueva
caída. También se verifica el vencimiento inalterado de alertas durante intentos,
la cancelación tras recuperación confirmada y el recuerdo visual de `FALLING`.

Las pruebas anteriores siguen ejecutándose; se actualizaron las expectativas que
asumían reinicio de permanencia o cierre temprano del episodio, porque contradicen
la recuperación confirmada solicitada.

Antes de afirmar precisión real falta medir falsos positivos al sentarse,
agacharse, arrodillarse y acostarse voluntariamente, junto con caídas reales de
distintas direcciones, distancia, iluminación y oclusión. La cámara puede hacer
que un cuerpo acostado parezca vertical; el ángulo del torso y el aspecto tampoco
distinguen suelo, cama o sillón. Una postura voluntaria sostenida e idéntica a una
caída puede confirmar por persistencia: es una limitación explícita, cubierta por
una prueba, que se debe cuantificar con videos negativos.

## Estructura

```text
fall_detection/         # modelos, configuración y motor puro
adapters/              # captura, MediaPipe y diagnóstico OpenCV
alerts/workflow.py     # cuenta regresiva local por eventos; sin envío
runner.py              # composición y argumentos de consola
requirements.txt       # dependencias de adaptadores
tests/                 # motor, recuperación, alertas, adaptadores y recortes
videos_prueba/         # videos actuales de evaluación
models/                # modelo descargado localmente; ignorado por Git
archive/
  FirstTests/          # primer prototipo y documentación original
  Presentation1/       # primera presentación, PDF, script y video originales
```

`.venv/` se conserva localmente y está ignorado por Git. Las carpetas
`__pycache__/` y los archivos `.pyc` se regeneran al ejecutar Python y pueden
eliminarse sin perder código ni datos. También se ignoran cachés de herramientas,
reportes de cobertura y directorios de construcción. Los videos actuales y el
material de `archive/` no se excluyen mediante estas reglas.

Los parámetros completos y sus valores están en `fall_detection/config.py`.
Las reglas permanecen juntas en el motor para poder leerlas y ajustarlas con
evidencia. No se intenta reemplazarlas con lógica en el runner o en MediaPipe.
