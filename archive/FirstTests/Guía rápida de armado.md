# **Guía rápida de armado** 

Detector de caídas — versión mínima para tener algo funcionando 

Esta guía es el camino más corto para que el sistema funcione. Es la versión práctica: el documento largo tiene el detalle técnico, el cronograma y el reparto del equipo. Esta hoja es para tener la cámara detectando caídas lo antes posible. 

Se acompaña con el archivo detector_caidas.py, que ya trae todo el programa escrito. 

## **Antes de empezar** 

Hace falta: una computadora con webcam, Python 3.11 y unos 30 minutos para los primeros tres pasos. El ajuste fino lleva más tiempo, pero es la parte interesante del proyecto. 

## **Paso 1 — Instalar** 

1. Descargar Python 3.11 desde python.org. No usar la versión más nueva: MediaPipe todavía no anda bien con ella. 

2. Durante la instalación, tildar la casilla que dice "Add Python to PATH". 

3. Abrir la terminal (o CMD en Windows) y escribir el comando de abajo. 

```
pip install mediapipe opencv-python numpy requests
```

Si termina sin errores en rojo, está listo. Puede tardar varios minutos porque MediaPipe es pesado. 

## **Paso 2 — Ver el esqueleto** 

Guardar el archivo detector_caidas.py en una carpeta, abrir la terminal en esa carpeta y escribir: 

```
python detector_caidas.py
```

Se abre una ventana con la imagen de la cámara y un esqueleto de palitos dibujado sobre la persona. Si lo ves, la parte más difícil ya está resuelta. Apretar la tecla q para cerrar. 

Si dice que no puede abrir la cámara, cambiar el valor de CAMARA de 0 a 1 o 2 dentro del archivo. 

## **Paso 3 — Mirar los números** 

Arriba de la ventana aparecen tres números que cambian mientras la persona se mueve. Hay que pararse frente a la cámara y hacer cada una de estas cosas, anotando qué valores aparecen: 

- Parado, quieto. 

- Sentarse rápido en una silla. 

- Acostarse en el piso. 

- Agacharse a atarse los cordones. 

- Caminar hacia la cámara y alejarse. 

**Este paso parece opcional y no lo es. Los umbrales que salen de esta observación son los que se pueden justificar en la defensa. Los copiados de un paper ajeno, con otra cámara y otro montaje, no.** 

## **Paso 4 — Ajustar los cuatro números** 

Al principio del archivo hay cuatro valores marcados con AJUSTAR. Estos son: 

|**Nombre**|**Valor**<br>**inicial**|**Qué controla**|
|---|---|---|
|`VELOCIDAD_CAIDA`|1.2|Qué tan rápido tene que bajar la cadera para sospechar una<br>caída. Más chico = más sensible = más falsas alarmas.|
|`DESCENSO_MINIMO`|0.5|Cuánto tene que haber bajado la cadera respecto de un<br>segundo antes.|
|`ASPECTO_ACOSTADO`|1.0|A partr de qué valor se considera que el cuerpo está<br>horizontal. Parado da menos de 0.6, acostado más de 1.0.|
|`SEGUNDOS_INMOVIL`|15|Cuántos segundos tene que quedarse quieto en el piso antes<br>de avisar.|



Método: subir o bajar de a poco hasta que detecte las caídas reales y no se dispare al sentarse rápido. Es prueba y error. Acá se va la mayor parte del tiempo del proyecto y es normal. 

_Truco para ir más rápido: poner SEGUNDOS_INMOVIL en 5 mientras se ajusta, así no hay que quedarse tirado en el piso quince segundos en cada prueba. Subirlo cuando ya funcione._ 

## **Paso 5 — La cuenta regresiva** 

Cuando detecta una caída y la persona no se levanta, aparece una cuenta regresiva de 30 segundos con un pitido. Cualquier tecla la cancela. Ya viene programado, solo hay que probarlo. 

Es lo primero que pregunta cualquiera que ve la demostración, así que conviene tenerlo andando bien. 

## **Paso 6 — Que llegue el mensaje al celular** 

1. Abrir Telegram y buscar el contacto BotFather (el que tiene el tilde azul). 

2. Mandarle /newbot y seguir las instrucciones. Devuelve un código largo: ese es el token. 

3. Buscar el bot userinfobot y mandarle cualquier mensaje. Devuelve un número: ese es el chat ID. 

4. Pegar ambos datos en TELEGRAM_TOKEN y TELEGRAM_CHAT_ID al principio del archivo. 

5. Importante: escribirle algo al bot propio desde el celular antes de probar, porque si no Telegram bloquea el primer mensaje. 

Si se dejan vacíos, el sistema funciona igual pero solo avisa por pantalla y por consola. 

## **Paso 7 — Grabar los videos de prueba** 

### **Juntar al equipo, conseguir un colchón y grabar entre 20 y 30 clips cortos. Hacerlo temprano en el cuatrimestre, no la semana antes de entregar: coordinar cinco agendas en época de parciales es más difícil de lo que parece.** 

Grabar tanto caídas como los casos que engañan al sistema, que son los importantes: 

- Caídas hacia adelante, hacia atrás y de costado. 

- Sentarse rápido en una silla y dejarse caer en un sillón. 

- Acostarse a propósito en el piso o en un sofá. 

- Agacharse a levantar algo del suelo. 

- Caminar de frente hacia la cámara y alejarse. 

Averiguar en la facultad si hace falta permiso del comité de ética para grabar personas, aunque sean los propios integrantes. Preguntarlo la primera semana, no en la última. 

## **Si algo falla** 

|**Problema**|**Qué hacer**|
|---|---|
|No se abre la cámara|Cambiar CAMARA de 0 a 1 o 2. Cerrar Zoom, Meet o cualquier<br>programa que la esté usando.|
|Error al instalar mediapipe|Verifcar la versión con python --version. Tiene que decir 3.11.|
|El esqueleto parpadea o desaparece|La persona está demasiado lejos o mal iluminada. MediaPipe<br>necesita ver el cuerpo entero.|
|Se dispara cuando alguien se sienta|Subir VELOCIDAD_CAIDA o subir SEGUNDOS_INMOVIL.|
|No detecta las caídas|Bajar VELOCIDAD_CAIDA y revisar que la caída quede dentro del<br>encuadre.|
|No llega el mensaje de Telegram|Escribirle primero al bot propio desde el celular. Revisar que el<br>token esté completo.|



## **Dónde ubicar la cámara** 

Entre 2 y 2,5 metros de altura, en una esquina del ambiente, inclinada hacia abajo unos 20 a 30 grados. La vista en diagonal funciona mejor que la frontal, porque evita que las caídas ocurran justo sobre el eje de la cámara, que es el caso en que el sistema no las ve bien. 

No poner la cámara casi en el techo: desde arriba, estar parado y estar acostado se ven casi igual y el sistema deja de distinguirlos. 

