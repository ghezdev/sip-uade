---
description: Sincroniza y hace triage del GitHub Project del repo (agente board-manager)
---

Invocá el agente `board-manager` para revisar el estado actual del GitHub Project de este repositorio:

1. Listar issues abiertos y su estado actual en el board.
2. Detectar issues sin columna asignada y proponer dónde van (Todo/In Progress/Done).
3. Aplicar los cambios inequívocos; listar los ambiguos para que el usuario decida.
4. Cerrar el resumen con qué se movió, creó o quedó pendiente de decisión.

Argumentos opcionales del usuario (si los hay): $ARGUMENTS
