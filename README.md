# EMI EnRuta · Demo académica con datos ficticios

Demo local en español para comparar, explicar y registrar qué móvil, o qué pareja de móviles, enviar a **una solicitud ya clasificada**. Trabaja con las 18 solicitudes de ESC-01, ESC-02 y ESC-04. Las modalidades manual y asistida usan los mismos datos y las mismas reglas. La decisión final la toma el despachador. Todos los datos son ficticios y las reglas son académicas. El uso público de las marcas requiere revisión previa de la organización.

Presupuesto: **0 COP**. Usa Python, pandas, Streamlit en local, archivos CSV y Power BI Desktop con actualización manual. No usa APIs de IA, tráfico en vivo, nube, triaje automático, predicción, optimización por lotes ni simulación de colas.

## Instalación y arranque en Windows

```powershell
cd 'C:\Users\Usuario\Documents\EstudIA\mvp\salviada\EMI_EnRuta'
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Abre `http://127.0.0.1:8501`. En los ensayos siguientes basta con el último comando. La instalación inicial necesita acceso al índice de paquetes. Después, todo funciona sin conexión.

Recorrido de la demo:

1. **Iniciar caso.** Elige escenario, solicitud y modalidad. El cronómetro monotónico arranca cuando el caso aparece en pantalla.
2. **Comparar.** Todas las unidades aparecen con su categoría de compatibilidad, espera, viaje, llegada, km y costo. La modalidad asistida añade el ranking y los mensajes predefinidos.
3. **Confirmar.** Puedes aceptar la alternativa, elegir otra válida, usar una excepción *no recomendada* (con motivo escrito obligatorio) o dejar el caso pendiente con su motivo.
4. **Revisar.** Después de guardar aparecen el ID, la decisión leída del CSV y, por primera vez, la referencia del escenario con el comentario del coordinador. Antes de confirmar nunca se muestran.

Si recargas el enlace `?caso=…` mientras el servidor sigue abierto, recuperas el mismo caso y el mismo cronómetro.

## Preparación de datos

Los CSV derivados ya están en `datos/entrada`, así que para ejecutar la demo no hacen falta los originales. Para regenerarlos:

```powershell
.\.venv\Scripts\python.exe preparar_datos.py 'C:\Users\Usuario\Documents\EstudIA\11'
# o bien:  $env:EMI_FUENTES = 'D:\otra\carpeta'; .\.venv\Scripts\python.exe preparar_datos.py
```

Si no indicas la ruta, se usa `EMI_FUENTES` y, si no existe, `C:\Users\Usuario\Documents\EstudIA\11`. Los originales solo se leen. Los CSV se escriben en UTF-8 con BOM, separados por coma y con punto decimal. Una celda vacía significa «no aplica» o «sin dato». Los identificadores y los códigos EMI (`01`, `02`, `07`, `03`, `06`) se conservan como texto. Si abres un CSV en Excel para la web, importa esas columnas como texto.

| Fuente | Derivado | Uso |
|---|---|---|
| 01 · Histórico (10.402 servicios) | `carga.csv`, `linea_base_kpi.csv`, `calidad_datos.csv` | Carga D04 por turno y línea base KPI-01 a KPI-04 y KPI-08. También el informe de calidad. |
| 02 · Móviles y bases | `flota.csv`, `bases.csv` | 26 móviles (24 activas) con sus tarifas `costo_km` y `costo_hora`. La base es solo un atributo del catálogo. |
| 03 · Lineamientos | `reglas_movil_servicio.csv`, `objetivos_urgencia.csv` | Compatibilidad, objetivos, R01–R07 y D01–D08. |
| 04 · Proceso | (reglas en código) | Estados asignables, estabilización y preasignación. Define qué se conoce en cada instante. |
| 05 · Zonas y tiempos | `zonas.csv`, `matriz_tiempos.csv`, `factor_trafico.csv` | 62 zonas, 3.844 pares y 72 factores. Las zonas con demanda ALTA alimentan D03. |
| 06 · Escenarios | `escenarios.csv`, `solicitudes.csv`, `estado_inicial_moviles.csv`, `eventos.csv`, `referencia_despachador.csv` | Foto de la flota, eventos hasta el instante del caso y referencia que solo se muestra tras confirmar. |
| 07 · Indicadores | `indicadores.csv`, `objetivos_urgencia.csv` | Definiciones originales y línea base publicada. |

**Calidad y denominadores** (`calidad_datos.csv`). La preparación se detiene si encuentra claves duplicadas, referencias a zonas, móviles o bases que no existen, o tarifas no positivas. Al cargar se validan columnas, vacíos, duplicados, dominios, la cobertura completa de la matriz (62 × 62) y los 72 factores horarios. Un faltante se informa con el archivo y la combinación exacta. El informe registra 564 servicios sin móvil, 359 con dos, 562 resueltos por teléfono, 186 cancelados, 748 sin tiempo de respuesta y 183 llegadas anómalas, con la llegada registrada más de 45 min después de la estimación de la matriz.

**Línea base.** La vista *original* reproduce el archivo 07: P90 de 52,9 min (01) y 55,1 min (02), y 25,7 % y 49,2 % dentro del objetivo. El denominador son los servicios con `tiempo_respuesta_min`, por clasificación final. KPI-08 da 127.282 COP frente a 127.300 publicado. La vista *corregida* excluye las 183 llegadas anómalas (P90 de 50,7 y 52,3 min). Se publica al lado de la original y no la reemplaza.

## Reglas implementadas

| EMI | Objetivo | Preferida | Permitida | No recomendada | No permitida | Solo estabilización |
|---|---:|---|---|---|---|---|
| 01 | 15 | TAM | TAB | | | VMD (R04) |
| 02 | 20 | TAB | TAM | | | VMD (R04) |
| 07 | 45 | VMD | TAB con posible traslado (D06) | TAM; TAB sin indicio de traslado | | |
| 03 | 90 | VMD | | TAB | TAM | |
| 06 | 180 | VMD | | | TAM, TAB | |

- **Instante de comparación.** Es el minuto de la solicitud más los minutos previos a despacho y los segundos de decisión. Todas las alternativas de un caso se comparan en el mismo instante. Solo se aplican los eventos ocurridos hasta ese minuto: liberaciones y reclasificaciones (R07). La clasificación final, la decisión histórica y los eventos posteriores no influyen.
- **Unidades.** Las inactivas o fuera de servicio quedan excluidas (R05). Una unidad que retorna se evalúa desde su zona actual. Una ocupada con liberación conocida se evalúa con su **espera** hasta quedar libre, separada del **viaje** que hace después desde su última zona conocida. Una unidad en ruta queda fuera porque R06 es de una fase posterior. Solo TAM y TAB trasladan (R03).
- **Tiempo.** `viaje = tiempo_valle × factor[tipo_día, hora de salida]`, con el tráfico aplicado una sola vez. `respuesta = transcurrido + espera + viaje`. El escenario no trae la hora de paso a despacho, así que se usa el **supuesto de demostración de 0 min**, que queda registrado en `fuente_previo_despacho`. También puedes ingresar otro valor. Al confirmar se suma una sola vez el tiempo de decisión. El cronómetro se guarda aparte en `segundos_decision`. Una ruta que falta en la matriz excluye la unidad con un mensaje y nunca se toma como viaje cero.
- **Costo de ida.** `km × costo_km + viaje / 60 × costo_hora` por móvil. Una pareja R04 suma los dos trayectos y conserva el detalle por rol. El costo de decisión (300 COP/min, `TARIFA_DESPACHADOR` en `src/decisiones.py`) es un **supuesto del equipo** y se registra por separado.
- **Orden (D01, D02, D04, D05).** Primero van los planes que cumplen el objetivo. Se agrupan los que están a **menos de 3 min** del más rápido del grupo. Dentro del grupo va primero el tipo preferido y después el menor costo, la menor carga del turno (la carga sin dato va al final) y el identificador. Se repite con los planes restantes. Los planes que exceden el objetivo se ordenan por menor llegada. Los umbrales usan una tolerancia de 1e-9: a exactamente 3 min D02 no se activa, una ventaja de exactamente 12 min sí activa R04 y llegar exactamente en el objetivo cuenta como cumplimiento.
- **R04** (01 y 02). Se activa si ninguna ambulancia llega dentro del objetivo y una VMD libre llega al menos 12 min antes que la primera ambulancia viable. En ese caso se propone una pareja: la VMD como primer respondiente y la primera ambulancia disponible (menor espera, luego menor llegada) para atención y traslado. Las dos llegadas se calculan desde el mismo instante y la pareja ocupa una sola posición. La liberación es una estimación de la foto y puede demorarse (D08). D07 (apoyo VMD a una TAB en un 01) aparece solo como nota.
- **D03.** Avisa si la alternativa deja alguna zona de demanda ALTA sin ambulancia libre a 20 min o menos. Es solo una advertencia y no cambia el orden.
- **Decisión de diseño:** las unidades *no recomendadas* no entran en el ranking. El despachador puede elegirlas como **excepción**, con motivo escrito (`es_excepcion = 1`).
- **Carga D04.** Cuenta las participaciones completadas y liberadas en el histórico ficticio desde el inicio del turno de 8 h hasta la hora de la solicitud. MOV-012 y MOV-024 no aparecen en el histórico y se muestran como «sin dato», que no es lo mismo que cero.

## Registro de decisiones

`datos/decisiones.csv` guarda **una fila por intento confirmado**. El ID es único por sesión, así que la misma solicitud puede ensayarse otra vez en la otra modalidad. Se conservan las 54 columnas del esquema v1 en el mismo orden y se añaden columnas v2 al final: `participaciones_json` (una entrada por móvil con ID, tipo, rol, zona, espera, viaje, llegada, km, tarifas y costo de ida), `plan_elegido_id`, `estado_decision` (asignada, pendiente o sin asignar), `motivo_detalle`, `llegada_mostrada_min`, `fuente_previo_despacho`, `advertencia_d03` y la referencia recalculada en el mismo instante. Las filas v1 se leen con esas columnas vacías.

La escritura usa un bloqueo de archivo y un reemplazo atómico. Si falla, la decisión queda en memoria para reintentar con el mismo ID y la misma duración. Una segunda confirmación con el mismo ID no duplica la fila.

**Precarga y restauración.** `datos/demo/decisiones_iniciales.csv` contiene 30 decisiones de demostración con `origen_registro = precargado`: 15 solicitudes en las dos modalidades, 2 de ellas pendientes y 2 con dos móviles (R04). Los ensayos quedan como `sesion`. Abrir la app nunca borra el registro. Para empezar un ensayo nuevo, cierra el caso abierto y ejecuta:

```powershell
.\.venv\Scripts\python.exe ensayo.py restaurar          # respalda en datos\decisiones_antes_FECHA.csv y repone las 30
.\.venv\Scripts\python.exe ensayo.py generar-precarga   # solo si cambiaste reglas o supuestos
.\.venv\Scripts\python.exe ensayo.py verificar          # datos\demo\verificacion_escenarios.csv (24 s por caso)
```

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_flujo
```

Son 28 pruebas que cubren los criterios del recorrido. Las de interfaz pulsan los botones de Streamlit y escriben en una copia temporal.

- **ESC-01-S01:** VMD para el 03, MOV-011 a 12,5 min.
- **ESC-02-S01:** MOV-025 a 24,5 min desde su zona actual con factor 1,6.
- **ESC-04-S01:** MOV-016 + MOV-013 en una sola decisión.
- **Umbrales exactos:** 3 min, 12 min y llegada en el objetivo.
- **Relojes:** 6 + 11 = 17 min, con 2 min de exceso.
- **Elegibilidad:** VMD sin traslado, unidad inactiva, unidad retornando, ruta faltante, espera de una ocupada.
- **Eventos y R07, D03, desempate D08 y rótulo de liberación, estado en el instante y redondeo del CSV.**
- **Decisión humana:** alternativa distinta, cero candidatos, pendiente, excepción, modalidad manual y referencia oculta hasta confirmar.
- **Persistencia:** fallo y reintento, doble confirmación, lectura v1, restauración, paso de 30 a 33 decisiones y línea base.

## Tablero y presentación

- Power BI: [tablero/README.md](tablero/README.md) contiene las consultas de Power Query, las medidas DAX y el montaje. El proyecto `tablero/EMI_EnRuta.pbip` abre y se actualiza en Desktop 2.159; `tablero/verificar_tablero.ps1` comprueba los conteos.
- Guion de cinco minutos: [presentacion/guion_demo.md](presentacion/guion_demo.md).
- Distribución prevista: 5 h de datos y reglas, 5 h de recomendación, 8 h de interfaz y persistencia, 6 h de tablero y 7 h de pruebas y presentación, **31 h** en total.

## Supuestos vigentes

1. Paso inmediato a despacho (0 min previos), salvo que se ingrese otro valor.
2. Salida inmediata de una unidad libre.
3. Origen de una ocupada al liberarse: su zona actual en la foto.
4. Liberaciones tomadas de la foto del escenario. Son estimaciones (D08).
5. Las decisiones de otros casos no consumen flota, porque no hay simulación de cola.
6. Tarifa del despachador: 300 COP/min.
7. Turnos de 8 h para la carga.
8. Festivos 23/03, 02/04 y 03/04 en la detección de anomalías.
9. Umbral de anomalía: más de 45 min sobre la matriz.
10. Las unidades *no recomendadas* solo se usan como excepción manual.
11. R06, cobertura dinámica, D07 como segundo móvil y simulación de colas quedan fuera de alcance.

## Mejoras propuestas

El backlog priorizado, con la evidencia de cada punto, está en [MEJORAS.md](MEJORAS.md).
