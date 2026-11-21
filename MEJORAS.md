# Mejoras propuestas para EMI EnRuta

Revisión del 21/11/2026 sobre la versión de `mvp\salviada\EMI_EnRuta`: código, interfaz y tablero. Para la revisión se evaluaron las 18 solicitudes de ESC-01, ESC-02 y ESC-04 con 24 s de decisión y se compararon con `referencia_despachador.csv`. **Demo académica con datos ficticios.**

## Estado de implementación (21/11/2026)

| ID | Estado | Resultado |
|---|---|---|
| C-01 | Hecho | La columna pasa a llamarse **Estado en el instante**. En ESC-02-S10, MOV-022 aparece «DISPONIBLE · liberada (foto: EN_ATENCION)», y una unidad ocupada muestra «se libera en X min». Prueba `test_c01_estado_en_el_instante`. |
| C-02 | Hecho | La caché de tablas usa como clave la fecha de modificación de cada CSV de `datos/entrada`. |
| C-04 | Hecho | El CSV y los JSON se escriben con 2 decimales en COP y 4 en el resto; los cálculos internos no se redondean. Ejemplo: `61890.73`, `7.22`. Prueba `test_c04_csv_redondeado`. |
| C-06 | Hecho | `requirements.txt` fija streamlit 1.67.0, pandas 3.1.1, pyarrow 26.0.1 y numpy 2.5.5. |
| M-02 (a) | Hecho | Las alternativas que esperan una liberación llevan el rótulo «⏳ depende de liberación» y una frase D08 en la explicación. |
| M-02 (b) | Hecho, con alcance limitado | Dentro del grupo de llegadas a menos de 3 min, una unidad libre va antes que una que debe liberarse (regla D08). En los escenarios actúa en ESC-02-S03. **No cambia ESC-02-S05**: MOV-022 llega 9,1 min antes que MOV-021 y queda fuera del grupo. Para acercarse a la referencia en ese caso hace falta M-02 (c), un margen de incertidumbre, o M-01. La coincidencia con la referencia sigue en 9 de 18. |
| I-01 | Hecho | Las alternativas 2 y 3 dicen el motivo concreto («llegada similar a MOV-005 (diferencia 0,4 min), pero cuesta … más de ida») y una comparación con la opción 1 («llega 9,1 min después y cuesta … menos»). |
| T-01 | Hecho (falta solo la revisión visual y guardar el .pbix) | El modelo se actualizó en Desktop 2.159 y las consultas dieron 30 decisiones; con una decisión R04 de sesión, 31 decisiones y 32 participaciones, sin doble conteo de costos; línea base 52,9 / 55,1. Se encontró y corrigió un error en los nombres de tres medidas. Detalle en `tablero/README.md`; nueva prueba de consistencia entre visuales y modelo. |

| C-03 | Hecho | Los casos sin uso durante 8 h (`CADUCIDAD_H` en `app.py`) se liberan de la memoria del servidor. Si la decisión ya se confirmó pero falló el guardado, el caso se conserva para reintentar. Un enlace caducado, o de un servidor reiniciado, muestra «Caso no encontrado… Inicia uno nuevo» y vuelve al inicio sin error. Prueba `test_c03_enlace_caducado_o_desconocido`. |
| C-05 | Hecho | Se reprodujo: no fallaba, pero Streamlit **cambiaba en silencio** la alternativa elegida por la nueva opción 1. Ahora la selección se vacía, se muestra un aviso y el botón de confirmar queda deshabilitado hasta que el despachador elija de nuevo. Prueba `test_c05_alternativa_que_desaparece_al_actualizar`. |

Pruebas: 30 de 30 en verde (antes 28).

## Resumen

| Indicador de la revisión | Resultado |
|---|---|
| Recomendación n.º 1 igual a la referencia del despachador | **9 de 18** solicitudes |
| Referencia fuera de las tres primeras alternativas | 2 (ESC-02-S06 en la posición 5 y ESC-02-S10 en la 9; el coordinador marca ambas como «discutibles») |
| Tiempo de cálculo por solicitud | 75–130 ms; la carga de tablas tarda 0,2 s |
| Pruebas automáticas | 23 de 23 en verde |

La mayoría de las diferencias con la referencia no vienen de las reglas. Vienen de un límite conocido: **las decisiones anteriores del mismo escenario no ocupan flota** (mejora M-01). Además aparecieron dos defectos menores de interfaz (C-01 y C-02).

Prioridad: **Alta** = corrige un error o cambia la recomendación en los escenarios de la demo. **Media** = mejora la fidelidad o la presentación. **Baja** = conveniente. Los esfuerzos están en horas y se pueden comparar con el límite de 24–38 h del proyecto. Ya se usaron unas 31 h, así que quedan unas **7 h**.

## 1. Correcciones

| ID | Prioridad | Problema y evidencia | Propuesta | Esfuerzo | Criterio de aceptación |
|---|---|---|---|---:|---|
| C-01 | Alta | La columna **Estado** de la tabla de flota muestra el estado de la foto inicial y no el del instante del caso (`app.py:85` usa `estado_foto`). En ESC-02-S10 (minuto 55), MOV-022 aparece «EN_ATENCION» aunque se liberó en el minuto 25 y su espera es 0. | Mostrar `estado` (estado en el instante) y, si cambió, una nota «liberada en el min X». | 0,5 | ESC-02-S10 muestra MOV-022 como DISPONIBLE. |
| C-02 | Alta | `datos()` usa `st.cache_data` sin invalidación. Si se ejecuta `preparar_datos.py` con el servidor abierto, la app sigue con las tablas anteriores hasta reiniciarlo. | Usar la fecha de modificación de los CSV como clave de caché, o añadir un botón «Recargar datos». | 0,5 | Después de regenerar los CSV, el siguiente caso usa los datos nuevos sin reiniciar. |
| C-03 | Media | `casos_abiertos()` (`st.cache_resource`) acumula todos los casos de la sesión del servidor y nunca los libera. Además se pierden al reiniciar sin avisar. | Expirar los casos sin confirmar después de N horas. Al recargar un enlace caducado, mostrar «caso no encontrado: inicia uno nuevo». | 1 | Una prueba con un enlace caducado muestra el aviso y no lanza error. |
| C-04 | Media | Los CSV de decisiones guardan ruido de coma flotante (`24.880000000000003`, `61890.73333333334`), lo que dificulta leerlos en Excel y en Power BI. | Redondear al escribir: 4 decimales en minutos y km, 2 en COP. El valor exacto ya queda en `vista_json`. | 0,5 | `verificacion_escenarios.csv` muestra `24.88` y `61890.73`. |
| C-05 | Media (por verificar) | Al pulsar **Actualizar estimaciones**, si la alternativa elegida desaparece (por ejemplo, la pareja R04 deja de valer), el `selectbox` conserva un valor que ya no está en la lista. Podría quedar sin selección o fallar. | Añadir una prueba con AppTest. Si falla, reiniciar la selección y avisar. | 1 | La prueba pasa y la interfaz explica el cambio. |
| C-06 | Baja | `requirements.txt` usa rangos (`streamlit>=1.45,<2`), así que una instalación futura puede romper la demo. | Fijar las versiones probadas: `streamlit==1.67.0`, `pandas==3.1.1` y la versión de pyarrow instalada. | 0,2 | Una instalación limpia reproduce las 23 pruebas. |

## 2. Fidelidad de la recomendación

| ID | Prioridad | Problema y evidencia | Propuesta | Esfuerzo | Criterio de aceptación |
|---|---|---|---|---:|---|
| M-01 | **Alta** | Cada solicitud parte de la foto inicial, así que **una unidad ya asignada vuelve a recomendarse**. ESC-01-S02 recomienda MOV-011, pero el coordinador dice «MOV-011 ya ocupada» (se asignó en S01). Pasa lo mismo con MOV-021 en ESC-02-S10 (asignada en S05) y con ESC-02-S09. | **Modo escenario secuencial**, opcional y apagado por defecto: las decisiones confirmadas en la sesión ocupan la unidad hasta una liberación estimada (llegada + mediana histórica de atención por tipo y código, archivo 01). No es una simulación de cola, solo «la flota recuerda» lo confirmado. | 6–8 | Con el modo activo, después de confirmar S01 con MOV-011, ESC-01-S02 no la propone. Con el modo apagado, los resultados actuales no cambian. |
| M-02 | Alta | **Incertidumbre de la liberación (D08).** En ESC-02-S05 la n.º 1 es MOV-022, que está EN_ATENCION y se espera 6,6 min, por delante de MOV-021, libre. La referencia eligió MOV-021 («la de Sabaneta está ocupada»). El motor trata la liberación de la foto como un dato seguro. | (a) Rotular «depende de una liberación» en la explicación y en la tabla. (b) Dentro del grupo de llegadas a menos de 3 min, preferir una unidad libre sobre una que debe liberarse. (c) Opcional: sumar un margen de retraso tomado del histórico (P75 de liberación tardía por estado) y mostrar un rango de llegada. | 3 | ESC-02-S05 muestra el rótulo. Con (c) activo, la explicación incluye el rango. |
| M-03 | Media | **Preservar ambulancias en un 07.** En ESC-01-S06, el n.º 1 es la TAB MOV-023 (9,9 min), igual que la referencia, pero el coordinador la marca «discutible»: había VMD dentro del objetivo y convenía dejar libre la TAB. | Cuando una VMD preferida cumple el objetivo con un margen definido, ponerla por delante de la TAB con posible traslado. Mostrar la TAB como alternativa y explicar el motivo (D06 frente a D03/D05). El margen queda como parámetro documentado. | 2 | ESC-01-S06 propone primero la VMD y la TAB queda en la posición 2, con su explicación. |
| M-04 | Media | En **R04**, la ambulancia preasignada es la primera que se libera, no la primera que llega. Hoy coinciden (MOV-013), pero pueden no coincidir. | Calcular las dos opciones, mostrar la diferencia y dejar elegir al despachador. Registrar cuál se usó. | 2 | Una prueba con dos ambulancias en las que difieren muestra ambas. |
| M-05 | Media | **D03** solo cuenta las ambulancias libres en este momento con el factor de la hora actual. Ignora las que se liberan en pocos minutos. | Incluir las que se liberan dentro de un horizonte corto (por ejemplo, 10 min) y mostrar las zonas cubiertas antes y después. | 3 | ESC-02-S07 muestra las 3 zonas afectadas con el detalle de antes y después. |
| M-06 | Media | Se dejaron fuera **R06** (desvío de una unidad en ruta), **D07** (apoyo VMD a una TAB en un 01, que hoy es solo una nota) y la ampliación a ESC-03 y ESC-05 a ESC-08. El motor ya aplica eventos y R07, pero `preparar_datos.py` fija `ESCENARIOS = {"ESC-01", "ESC-02", "ESC-04"}`. | Fase 2: (a) parametrizar los escenarios; (b) D07 como segundo móvil opcional en la misma decisión; (c) R06 con el servicio desplazado devuelto a la cola. Empezar por ESC-05 (VMD cerca, ambulancia lejos) y ESC-06 (reclasificación en sitio). | 4–10 | ESC-05 y ESC-06 tienen pruebas de aceptación como las de la sección 8. |
| M-07 | Baja | El factor de tráfico se aplica a la hora de salida. Un trayecto largo que cruza de hora (por ejemplo 17:50 → 18:20) no cambia de factor. | Documentarlo como supuesto o prorratear el factor por minuto de cada franja. | 1 | Una prueba con un viaje que cruza 18:00. |

## 3. Interfaz y explicación

| ID | Prioridad | Problema | Propuesta | Esfuerzo |
|---|---|---|---|---:|
| I-01 | Media | Para las alternativas 2 y 3, la explicación es genérica («mayor costo o tipo no preferido»). | Explicar respecto de la n.º 1: «llega X min después y cuesta Y COP más» o «es TAM y el 02 prefiere TAB». | 1 |
| I-02 | Media | No hay mapa, aunque `zonas.csv` trae coordenadas. | Mapa con el destino, las alternativas y las zonas que D03 dejaría descubiertas (`st.map` o pydeck, sin servicios externos de tráfico). | 3 |
| I-03 | Media | Restaurar el ensayo y consultar el registro solo se puede hacer desde la consola. | Página «Registro» con las últimas decisiones, filtros y descarga. Restauración con confirmación explícita y respaldo, igual que en `ensayo.py`. | 2 |
| I-04 | Baja | El tiempo de decisión solo se ve al final. La meta R02 (2 min en 01 y 02) no se ve mientras se decide. | Indicador discreto «R02: dentro de la meta o meta superada», actualizado con `st.fragment`. Evaluar si presiona demasiado el ensayo. | 1 |
| I-05 | Baja | Las tres primeras alternativas se leen como mensajes separados. | Tabla compacta lado a lado: llegada, margen, km, costo, D03 y regla aplicada. | 1 |

## 4. Datos y calidad

| ID | Prioridad | Problema | Propuesta | Esfuerzo |
|---|---|---|---|---:|
| D-01 | Media | KPI-04 del código 03 da **26,2 min** y el archivo 07 publica 26,1. | Revisar la definición: primera asignación frente a cualquier asignación, servicios cancelados y redondeo. Documentar la causa. | 1 |
| D-02 | Media | `posible_traslado` (D06) se deduce del texto del motivo y del discriminador dentro del código. | Moverlo a una tabla editable `reglas_traslado.csv` (motivo, discriminador, traslado) que el equipo pueda revisar. | 1 |
| D-03 | Media | `preparar_datos.py` no tiene prueba automática porque depende de la carpeta `EstudIA\11`. | Fixture mínimo (2 zonas, 3 móviles, 5 servicios) en `pruebas\fuentes_minimas` y una prueba de extremo a extremo. | 2 |
| D-04 | Baja | La detección de llegadas anómalas usa un umbral fijo de 45 min y festivos escritos en el código. | Parametrizarlos en un archivo de configuración e informar cuánto cambia la vista corregida con 30, 45 y 60 min. | 1 |

## 5. Tablero de Power BI

| ID | Prioridad | Problema | Propuesta | Esfuerzo |
|---|---|---|---|---:|
| T-01 | Alta | El `.pbip` abre en Desktop 2.159, pero **falta confirmar la actualización**: los 30 registros, la expansión de `participaciones_json` y los formatos. | Ejecutar la comprobación de `tablero/README.md` y, si todo cuadra, guardar `EMI_EnRuta.pbix`. Ajustar los visuales vacíos. | 1–2 |
| T-02 | Media | Los parámetros `RutaCSV` y `RutaLineaBase` son rutas absolutas. Al mover la carpeta hay que regenerar. | Documentarlo en la página del informe y añadir `generar_pbip.py --ruta` para otro equipo. | 0,5 |
| T-03 | Baja | No hay P90 del ensayo comparable con KPI-01 y KPI-02. | Añadir una medida P90 de primera llegada estimada por código, rotulada «ensayo, n = …». | 0,5 |

## 6. Ingeniería

| ID | Prioridad | Propuesta | Esfuerzo |
|---|---|---|---:|
| E-01 | Media | Script `verificar.ps1` que ejecute las pruebas, un linter (ruff) y `ensayo.py verificar` antes de cada entrega. | 1 |
| E-02 | Baja | Registrar en un CSV aparte los intentos rechazados (por ejemplo, «cambió la combinación R04») para analizar la fricción del ensayo. | 1 |

## Plan sugerido con las ~7 h restantes

1. **C-01, C-02, C-04, C-06** (≈ 1,7 h): defectos visibles en la demo y reproducibilidad.
2. **T-01** (≈ 1,5 h): cerrar el tablero con el `.pbix` comprobado.
3. **M-02 (a)+(b)** (≈ 2 h): rotular y desempatar las unidades que dependen de una liberación. El desempate solo actúa dentro del grupo de llegadas a menos de 3 min.
4. **I-01** (≈ 1 h): explicaciones específicas para las alternativas 2 y 3.

**M-01 (modo secuencial)** es la mejora de mayor impacto en la coincidencia con la referencia, pero no cabe en el presupuesto restante. Se propone como primera tarea de la siguiente fase, junto con M-03 y M-06.
