# Página de decisiones en Power BI Desktop

El tablero lee los mismos CSV locales que escribe la demo y se actualiza a mano.

**Forma rápida:** abre `tablero/EMI_EnRuta.pbip` en Power BI Desktop y pulsa **Inicio → Actualizar**. El proyecto ya trae los parámetros de ruta, las tres consultas, la relación, las medidas y la página «Decisiones de despacho». Si cambias de carpeta o editas las consultas o medidas, regenera el proyecto con `.\.venv\Scripts\python.exe tablero\generar_pbip.py`. Para entregar un solo archivo, usa **Archivo → Guardar como → .pbix**.

Los pasos de montaje manual que siguen quedan como referencia.

| Archivo | Contenido |
|---|---|
| [decisiones.pq](decisiones.pq) | Una fila por decisión (un intento confirmado), con tipos explícitos. Lee también un registro del esquema v1. |
| [participaciones.pq](participaciones.pq) | Una fila por móvil elegido, expandida desde `participaciones_json`. R04 aporta dos filas a una sola decisión. |
| [linea_base.pq](linea_base.pq) | Línea base histórica ficticia (`datos/entrada/linea_base_kpi.csv`), vistas *original* y *corregida*. |
| [medidas.dax](medidas.dax) | Conteos por ID, medianas, cumplimiento con denominador, costos y diferencias frente a la referencia. |

## Montaje

1. Abre un informe vacío. En **Transformar datos → Administrar parámetros** crea dos parámetros de texto:
   - `RutaCSV` = ruta absoluta de `EMI_EnRuta\datos\decisiones.csv`
   - `RutaLineaBase` = ruta absoluta de `EMI_EnRuta\datos\entrada\linea_base_kpi.csv`
2. Crea tres consultas en blanco llamadas `decisiones`, `participaciones` y `linea_base`, y pega en el **Editor avanzado** el archivo `.pq` correspondiente. Los CSV usan punto decimal; las consultas convierten con cultura `en-US`. El código EMI, los identificadores y la franja quedan como texto, para conservar el cero inicial.
3. **Cerrar y aplicar.** En la vista de modelo crea la relación `decisiones[solicitud_id]` (uno) → `participaciones[solicitud_id]` (varios), con filtro en un solo sentido. `linea_base` queda sin relación.
4. Crea cada medida de [medidas.dax](medidas.dax) con **Modelado → Nueva medida**. Da formato de porcentaje a las que terminan en `(%)`, de moneda sin decimales a las de COP y de un decimal a los minutos. Si tu configuración regional usa `;` como separador DAX, cambia las comas entre argumentos.
5. Crea una página horizontal llamada **Decisiones de despacho** y coloca en el encabezado el texto **«Demo académica con datos ficticios»**.
6. **Filtros** (segmentadores arriba): `escenario_id`, `codigo_emi`, `modalidad` y `origen_registro`. Añade `solicitud_fuente` para comparar el mismo caso en las dos modalidades.
7. **¿Cuánto tarda la decisión?** Matriz con `modalidad` en filas y los valores *Decisiones* (número de ensayos), *Decisión mediana (s)* y *Cumple R02 (%)*. En el ensayo, el paso a despacho es el inicio del caso y la primera asignación es la confirmación, así que esta mediana es el equivalente de KPI-04 en segundos.
8. **¿Cuándo llegaría la primera unidad?** Tarjeta *Primera llegada mediana (min)*, gráfico de columnas *Dentro del objetivo (%)* por `codigo_emi` con el título «Primera llegada estimada dentro del objetivo · denominador: decisiones asignadas», tarjeta *Denominador cumplimiento* y tarjeta *Llegada mediana de ambulancia R04 (min)*, separada de la primera llegada.
9. **¿Cuánto cuesta la alternativa?** Tarjetas *Costo medio de ida por decisión (COP)* y *Km medio por decisión*. Debajo, barras de *Costo de ida por móvil (COP)* por `participaciones[id_movil]`, con `participaciones[rol]` como leyenda. Pon *Costo medio de decisión, supuesto (COP)* en una tarjeta aparte con esa etiqueta. No compares estos costos de ida con el KPI-08 histórico (127.300 COP), que incluye las horas desde la asignación hasta la liberación.
10. **¿Qué cambió respecto de la referencia?** Tabla con `solicitud_fuente`, `modalidad`, *Observaciones con referencia*, *Δ primera llegada vs referencia (min)*, *Δ costo de ida vs referencia (COP)* y *Coincide con la referencia (%)*. La referencia se recalcula en el mismo instante del caso con el mismo motor.
11. **Línea base histórica (ficticia).** Tabla aparte con `linea_base`: filtro `vista = original`, columnas `codigo_emi`, `p90_min`, `pct_cumple`, `denominador` y `kpi04_espera_asignacion_mediana_min`. Rotúlala «Línea base histórica ficticia: no es resultado del ensayo». La vista *corregida* excluye 183 llegadas anómalas y se presenta solo como comparación, al lado de la original.
12. Guarda el informe como `tablero/EMI_EnRuta.pbix`. Después de cada ensayo pulsa **Inicio → Actualizar**.

## Comprobación en Desktop (hecha el 21/11/2026 con Power BI Desktop 2.159)

Con `EMI_EnRuta.pbip` abierto, `powershell -ExecutionPolicy Bypass -File tableroerificar_tablero.ps1` actualiza el modelo local de Desktop y consulta las medidas. Resultados obtenidos:

| Comprobación | Resultado |
|---|---|
| Precarga | 30 decisiones: 15 manuales y 15 asistidas, 28 asignadas y 2 pendientes, todas `precargado`. 30 participaciones (28 + 2 ambulancias R04). |
| Sin doble conteo | Σ costo por participación = Σ costo de ida por decisión = 1.000.397,35 COP. |
| 30 → 31 con dos móviles | Después de guardar ESC-04-S01 (MOV-016+MOV-013) como `sesion` y actualizar: 31 decisiones y 32 participaciones. La decisión de sesión es una sola, con MOV-016 (estabilización, 10.217,33 COP) y MOV-013 (atención y traslado, 51.673,40 COP), y un costo de ida de 61.890,73 COP. Primera llegada 7,3 min y ambulancia 34,5 min. Luego se restauró a 30. |
| Línea base original | P90 de 52,9 y 55,1 min; 25,7 % y 49,2 % dentro del objetivo (códigos 01 y 02). |

Durante la comprobación apareció un error y se corrigió: las tres medidas de varias líneas tenían « =» pegado al nombre, así que los visuales que las usan no las encontraban. `generar_pbip.py` ahora valida los nombres, y la prueba `Tablero.test_visuales_usan_campos_del_modelo` confirma que cada campo de cada visual existe en el modelo.

Pendiente para la persona usuaria: revisar la página a la vista (tamaños y formatos) y usar **Archivo → Guardar como → .pbix** si se necesita un solo archivo. La verificación se hizo contra el motor del modelo; no se inspeccionaron visualmente los gráficos.
