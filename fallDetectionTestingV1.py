import time
import collections

import cv2
import numpy as np
import mediapipe as mp


CAMARA = 0  # 0 es la webcam integrada. Probar 1 o 2 si tenes otra conectada.

# Que tan rapido tiene que bajar la cadera para considerar
# que empezo una caida. Se mide en "largos de torso por segundo".
# Mas chico = mas sensible (mas falsas alarmas).
VELOCIDAD_CAIDA = 1.2

# Cuanto tiene que haber bajado la cadera respecto de un
# segundo antes. Tambien en largos de torso.
DESCENSO_MINIMO = 0.5

# A partir de que valor consideramos que el cuerpo esta
# horizontal. Es ancho dividido alto. Parado da menos de 0.6, acostado
# suele dar mas de 1.0.
ASPECTO_ACOSTADO = 1.0

DE_PIE = "DE PIE"
CAYENDO = "CAYENDO"
EN_SUELO = "EN EL SUELO"

HOMBRO_IZQ, HOMBRO_DER = 11, 12
CADERA_IZQ, CADERA_DER = 23, 24

VISIBILIDAD_MINIMA = 0.5

def medir(landmarks):
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
        colores = {
            DE_PIE: (0, 180, 0),
            CAYENDO: (0, 200, 255),
            EN_SUELO: (0, 120, 255),
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
                        "En el suelo hace %.0f s" % quieto,
                        (15, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (0, 180, 255), 1)

        if not hay_persona:
            cv2.putText(frame, "No se detecta a nadie", (15, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 1)

        frame_mostrado = cv2.resize(frame, None, fx=2, fy=2)
        cv2.imshow("Detector de caidas", frame_mostrado)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    pose.close()


if __name__ == "__main__":
    main()
