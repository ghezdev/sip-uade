"""
Detector de caidas con una camara.
Proyecto final de Ingenieria en Computacion.

COMO USARLO:
  1) pip install mediapipe opencv-python numpy requests
  2) Ajustar los valores de CONFIGURACION que estan aca abajo.
  3) python detector_caidas.py
  4) Apretar 'q' para salir. Cualquier tecla cancela una alerta en curso.

Los cuatro numeros que hay que ajustar estan marcados con >>> AJUSTAR <<<
"""

import time
import collections

import cv2
import numpy as np
import mediapipe as mp

try:
    import requests
except ImportError:
    requests = None


# ==========================================================================
# CONFIGURACION
# ==========================================================================

CAMARA = 0  # 0 es la webcam integrada. Probar 1 o 2 si tenes otra conectada.

# --- Los cuatro numeros a ajustar en el paso 4 ---

# >>> AJUSTAR <<< Que tan rapido tiene que bajar la cadera para considerar
# que empezo una caida. Se mide en "largos de torso por segundo".
# Mas chico = mas sensible (mas falsas alarmas).
VELOCIDAD_CAIDA = 1.2

# >>> AJUSTAR <<< Cuanto tiene que haber bajado la cadera respecto de un
# segundo antes. Tambien en largos de torso.
DESCENSO_MINIMO = 0.5

# >>> AJUSTAR <<< A partir de que valor consideramos que el cuerpo esta
# horizontal. Es ancho dividido alto. Parado da menos de 0.6, acostado
# suele dar mas de 1.0.
ASPECTO_ACOSTADO = 1.0

# >>> AJUSTAR <<< Cuantos segundos tiene que quedarse quieto en el piso
# antes de que se dispare la alerta.
# Para probar poner 10. Para la version real, entre 60 y 300.
SEGUNDOS_INMOVIL = 15

# --- Alerta ---

SEGUNDOS_CANCELACION = 30  # Cuenta regresiva antes de mandar el mensaje.

# Datos del bot de Telegram (paso 6). Si los dejas vacios, el sistema
# funciona igual pero solo avisa por pantalla.
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""


# ==========================================================================
# DE ACA PARA ABAJO NO HACE FALTA TOCAR NADA
# ==========================================================================

DE_PIE = "DE PIE"
CAYENDO = "CAYENDO"
EN_SUELO = "EN EL SUELO"
ALERTANDO = "ALERTA"

# Indices de los puntos que nos interesan (MediaPipe numera 33 en total)
HOMBRO_IZQ, HOMBRO_DER = 11, 12
CADERA_IZQ, CADERA_DER = 23, 24

VISIBILIDAD_MINIMA = 0.5


def enviar_telegram(texto):
    """Manda el mensaje al celular. Si algo falla, no rompe el programa."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or requests is None:
        print("[AVISO] Telegram no configurado. Mensaje:", texto)
        return False
    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
        r = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "text": texto},
            timeout=10,
        )
        print("[TELEGRAM] Enviado." if r.ok else "[TELEGRAM] Fallo el envio.")
        return r.ok
    except Exception as e:
        print("[TELEGRAM] Error:", e)
        return False


def medir(landmarks):
    """
    Saca las tres medidas del cuerpo a partir de los puntos detectados.
    Devuelve None si no se ve bien a la persona.

    Todo se divide por el largo del torso para que funcione igual sin
    importar si la persona esta cerca o lejos de la camara.
    """
    puntos_clave = [HOMBRO_IZQ, HOMBRO_DER, CADERA_IZQ, CADERA_DER]
    for i in puntos_clave:
        if landmarks[i].visibility < VISIBILIDAD_MINIMA:
            return None

    hombro_y = (landmarks[HOMBRO_IZQ].y + landmarks[HOMBRO_DER].y) / 2
    hombro_x = (landmarks[HOMBRO_IZQ].x + landmarks[HOMBRO_DER].x) / 2
    cadera_y = (landmarks[CADERA_IZQ].y + landmarks[CADERA_DER].y) / 2
    cadera_x = (landmarks[CADERA_IZQ].x + landmarks[CADERA_DER].x) / 2

    torso = np.hypot(hombro_x - cadera_x, hombro_y - cadera_y)
    if torso < 0.02:  # persona demasiado lejos o mal detectada
        return None

    visibles = [p for p in landmarks if p.visibility >= VISIBILIDAD_MINIMA]
    if len(visibles) < 8:
        return None

    xs = [p.x for p in visibles]
    ys = [p.y for p in visibles]
    ancho = max(xs) - min(xs)
    alto = max(ys) - min(ys)
    aspecto = ancho / alto if alto > 0.001 else 99.0

    return {"aspecto": aspecto, "cadera_y": cadera_y, "torso": torso}


def main():
    cap = cv2.VideoCapture(CAMARA)
    if not cap.isOpened():
        print("No se pudo abrir la camara. Proba cambiar el numero en CAMARA.")
        return

    pose = mp.solutions.pose.Pose(
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    dibujante = mp.solutions.drawing_utils

    # Guardamos el historial del ultimo segundo para calcular el descenso
    historial = collections.deque(maxlen=60)

    estado = DE_PIE
    momento_cambio = time.time()
    ultimo_aspecto = 0.0
    ultimo_descenso = 0.0
    ultima_velocidad = 0.0
    alerta_enviada = False

    print("Sistema iniciado. 'q' para salir.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame = cv2.flip(frame, 1)
        ahora = time.time()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        resultado = pose.process(rgb)

        hay_persona = resultado.pose_landmarks is not None
        m = None

        if hay_persona:
            dibujante.draw_landmarks(
                frame,
                resultado.pose_landmarks,
                mp.solutions.pose.POSE_CONNECTIONS,
            )
            m = medir(resultado.pose_landmarks.landmark)

        if m is not None:
            historial.append((ahora, m["cadera_y"], m["torso"]))
            ultimo_aspecto = m["aspecto"]

            # Cuanto bajo la cadera respecto de hace ~1 segundo, en largos
            # de torso. Usamos el valor relativo y no la posicion absoluta
            # para que la camara pueda estar inclinada sin romper todo.
            referencia = None
            for t, y, torso in historial:
                if ahora - t >= 0.8:
                    referencia = (t, y, torso)
            if referencia is not None:
                dt = ahora - referencia[0]
                ultimo_descenso = (m["cadera_y"] - referencia[1]) / m["torso"]
                ultima_velocidad = ultimo_descenso / dt if dt > 0 else 0.0
            else:
                ultimo_descenso = 0.0
                ultima_velocidad = 0.0

            acostado = (
                ultimo_aspecto >= ASPECTO_ACOSTADO
                or ultimo_descenso >= DESCENSO_MINIMO
            )

            # --- Maquina de estados ---
            if estado == DE_PIE:
                if ultima_velocidad >= VELOCIDAD_CAIDA:
                    estado, momento_cambio = CAYENDO, ahora

            elif estado == CAYENDO:
                if acostado:
                    estado, momento_cambio = EN_SUELO, ahora
                elif ahora - momento_cambio > 1.5:
                    estado, momento_cambio = DE_PIE, ahora

            elif estado == EN_SUELO:
                if not acostado:
                    estado, momento_cambio = DE_PIE, ahora
                elif ahora - momento_cambio >= SEGUNDOS_INMOVIL:
                    estado, momento_cambio = ALERTANDO, ahora
                    alerta_enviada = False

            elif estado == ALERTANDO:
                restante = SEGUNDOS_CANCELACION - (ahora - momento_cambio)
                if restante <= 0 and not alerta_enviada:
                    marca = time.strftime("%H:%M:%S")
                    enviar_telegram(
                        "Posible caida detectada a las " + marca +
                        ". La persona lleva mas de " + str(SEGUNDOS_INMOVIL) +
                        " segundos en el suelo sin moverse."
                    )
                    alerta_enviada = True

        # --- Lo que se muestra en pantalla ---
        colores = {
            DE_PIE: (0, 180, 0),
            CAYENDO: (0, 200, 255),
            EN_SUELO: (0, 120, 255),
            ALERTANDO: (0, 0, 255),
        }
        color = colores.get(estado, (200, 200, 200))

        cv2.rectangle(frame, (0, 0), (frame.shape[1], 110), (25, 25, 25), -1)
        cv2.putText(frame, "Estado: " + estado, (15, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.putText(frame,
                    "aspecto %.2f   descenso %.2f   velocidad %.2f"
                    % (ultimo_aspecto, ultimo_descenso, ultima_velocidad),
                    (15, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (220, 220, 220), 1)

        if estado == EN_SUELO:
            quieto = ahora - momento_cambio
            cv2.putText(frame,
                        "Inmovil hace %.0f s (avisa a los %d s)"
                        % (quieto, SEGUNDOS_INMOVIL),
                        (15, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (0, 180, 255), 1)

        if estado == ALERTANDO:
            restante = max(0, SEGUNDOS_CANCELACION - (ahora - momento_cambio))
            if not alerta_enviada:
                cv2.putText(frame,
                            "AVISANDO EN %d s - apreta una tecla para cancelar"
                            % int(restante),
                            (15, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 0, 255), 2)
                if int(ahora * 2) % 2 == 0:
                    print("\a", end="", flush=True)  # pitido
            else:
                cv2.putText(frame, "ALERTA ENVIADA", (15, 90),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if not hay_persona:
            cv2.putText(frame, "No se detecta a nadie", (15, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 1)

        cv2.imshow("Detector de caidas", frame)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord('q'):
            break
        if tecla != 255 and estado == ALERTANDO:
            print("[CANCELADO] El usuario cancelo la alerta.")
            estado, momento_cambio = DE_PIE, ahora
            alerta_enviada = False
            historial.clear()

    cap.release()
    cv2.destroyAllWindows()
    pose.close()


if __name__ == "__main__":
    main()
