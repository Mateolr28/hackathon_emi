# EMI EnRuta en cinco minutos · Demo académica con datos ficticios

Preparación: `.\.venv\Scripts\python.exe ensayo.py restaurar` (30 decisiones precargadas), Streamlit abierto y, si está montado, el informe de Power BI actualizado.

| Tiempo | Acción | Qué mostrar |
|---|---|---|
| 0:00–1:20 | **ESC-01-S01**, modalidad asistida, supuesto de 0 min previos. **Iniciar caso**. | Consulta 03 con objetivo de 90 min. TAM *no permitida* y TAB *no recomendada* (solo como excepción con motivo), por eso la alternativa es una VMD. MOV-005 y MOV-003 tienen el mismo viaje (12,1 min) y MOV-011, el de la referencia, tarda 12,5 min. Las tres difieren en menos de 3 min y D02 ordena por costo: MOV-005 queda primera y MOV-011, tercera. |
| 1:20–2:00 | Confirma MOV-005 y muestra el ID. | Tras confirmar aparece la referencia (MOV-011, «Correcta») con el viaje y el costo recalculados en el mismo instante. Si el informe está montado, **Actualizar** pasa de 30 a 31 decisiones. |
| 2:00–3:10 | **ESC-02-S01** en modalidad manual. Abre la tabla de flota, elige MOV-025, indica el motivo y confirma. | Hora pico con factor 1,60. MOV-025 (TAB) sale de su zona actual, Z-MED-07-01, y viaja 24,5 min. Excede el objetivo de 20 min y la pantalla muestra el exceso. MOV-015 (VMD) está retornando desde Z-MED-05-01 y llega 6,6 min antes, menos que los 12 que exige R04. Una VMD no puede trasladar. |
| 3:10–4:20 | **ESC-04-S01** en modalidad asistida. Lee la opción 1 y confirma la pareja. | Ninguna ambulancia llega a tiempo. MOV-016 (VMD) llega en 7,2 min y gana 27,3 min a la primera ambulancia. MOV-013 (TAM) queda preasignada: se libera al minuto 22 y llega al 34,5. Es una sola decisión con dos roles y el costo de ida conjunto es 61.891 COP. La referencia coincide y el coordinador comenta que pudo preasignarse desde el minuto 1. |
| 4:20–5:00 | En Power BI, **Actualizar** y filtrar por origen `sesion`. | Tres decisiones de sesión: ESC-04 tiene una decisión y dos participaciones, y la primera llegada se muestra separada de la llegada de la ambulancia. La línea base histórica ficticia (P90 de 52,9 y 55,1 min) va rotulada aparte del ensayo. |

Verificación controlada (`ensayo.py verificar`, 24 s de decisión y 0 min previos): las primeras llegadas son 12,525, 24,88 y 7,22 min. En vivo cambian según los segundos que pasen antes de confirmar, porque al confirmar se suma una sola vez el tiempo de decisión.

Cierre: la herramienta sugiere y explica, pero decide el despachador. Las cifras son de un ejercicio ficticio. Para medir un ahorro real de operación haría falta otra evaluación.
