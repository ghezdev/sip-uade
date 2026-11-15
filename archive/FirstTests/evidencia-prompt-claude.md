# Evidencia de conversación con Claude

Conversación inicial con Claude que dio origen a los archivos `Guía rápida de armado.md` y `detector_caidas.py` de esta carpeta.

---

**Usuario:**

> im thinking of developing a project for my computer engineering thesis. it would solve the problem of elders who fall in their homes and have no way of getting back up. it would be connected to a camera that detects the sudden movement and calls a relative. how doable is this

**Claude:**

La versión rápida, sin vueltas:

1. **Instalar Python y tres cosas más.** Descargá Python 3.11 (no la versión más nueva, se rompe). Abrís la terminal y escribís: `pip install mediapipe opencv-python numpy requests`. Espera unos minutos y listo. Si termina sin errores rojos, ya está.

2. **Ver el esqueleto en pantalla.** Con el programa que te paso abajo, apuntás la webcam a alguien y ves un esqueleto de palitos dibujado encima de la persona. Eso confirma que la cámara y la librería funcionan. Si ves el esqueleto, el 60% del trabajo técnico ya está resuelto.

3. **Mirar cómo cambian los números.** En la pantalla van a aparecer tres números que cambian mientras te movés. Uno dice si el cuerpo está parado o acostado, otro cuánto bajó la cadera, otro qué tan rápido bajó. Paráte, sentate, acostate en el piso, agachate. Anotá en un papel qué valores te da cada cosa. Estos números son los que después vas a defender ante el tribunal, así que no los inventes: mirálos.

4. **Ajustar los cuatro números.** En el programa hay cuatro números de configuración arriba de todo. Cambiálos según lo que anotaste en el paso anterior hasta que el sistema detecte tus caídas y no se dispare cuando te sentás rápido. Es prueba y error, y es normal que te lleve un rato. Acá se va la mayor parte del tiempo del proyecto.

5. **Probar la cuenta regresiva.** Cuando el sistema detecta una caída y la persona no se levanta, empieza una cuenta regresiva en pantalla con un pitido. Si apretás cualquier tecla, se cancela. Esto ya viene hecho en el programa. Es lo primero que te va a preguntar cualquiera que vea la demo, así que dejálo funcionando.

6. **Crear el bot de Telegram.** Abrí Telegram, buscá el contacto BotFather, mandále `/newbot` y seguí las instrucciones. Te va a dar un código largo. Después buscá el bot userinfobot para conseguir tu número de chat. Pegás ambos datos arriba del programa y ya te llega el mensaje al celular.

7. **Grabar los videos de prueba.** Junten al equipo, pongan un colchón y graben entre 20 y 30 videos cortos: caídas, pero también sentarse rápido, acostarse en un sillón y agacharse a atarse los cordones. Estos últimos son los importantes porque son los que engañan al sistema. Haganlo temprano, no la semana antes de entregar.

Te dejo el programa ya escrito para que no tengas que armarlo:

*[Claude crea el archivo `detector_caidas.py`]*

Verifiqué que el código no tiene errores de sintaxis, pero no puedo probarlo contra una cámara real desde acá, así que puede que algo haya que ajustar la primera vez que lo corras.

Los valores que están puestos son un punto de partida razonable, no la respuesta correcta. Van a fallar en tu ambiente porque dependen de la altura de la cámara y de la distancia a la que esté la persona. Corré el programa, mirá los tres números que aparecen arriba mientras te movés, y ajustá desde ahí.

Un consejo para acelerar el paso 4: poné `SEGUNDOS_INMOVIL = 5` mientras estás ajustando, así no tenés que quedarte tirado en el piso quince segundos cada vez que probás algo. Subilo cuando ya funcione.

Si algo tira error al correrlo, pegámelo acá y lo resolvemos.

*[Adjunto: `Detector caidas.py`]*

---

**Usuario:**

> entonces dame tanto las instrucciones como el programa como archivos

**Claude:**

Tres archivos: la guía rápida en Word (3 páginas, para trabajar con ella al lado de la computadora), el programa, y el plan largo que ya te había pasado.

La guía incluye una tabla de qué hacer si algo falla y otra con los cuatro valores a ajustar, así no tenés que volver al chat cada vez. Repartila entre los cinco antes de la primera reunión.

*[Adjuntos: `Guía rápida de armado.docx`, `Detector caidas.py`]*
