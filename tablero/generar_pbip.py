"""Genera el proyecto de Power BI (tablero/EMI_EnRuta.pbip) a partir de las consultas .pq y medidas.dax.

Uso:  .\\.venv\\Scripts\\python.exe tablero\\generar_pbip.py
Las rutas de los CSV se escriben como parámetros (RutaCSV, RutaLineaBase) con la ubicación actual del proyecto.
Después: abrir EMI_EnRuta.pbip en Power BI Desktop y pulsar Inicio → Actualizar.
"""
import csv
import json
import re
import shutil
from pathlib import Path

TABLERO = Path(__file__).resolve().parent
RAIZ = TABLERO.parent
NOMBRE = "EMI_EnRuta"
MODELO = TABLERO / f"{NOMBRE}.SemanticModel"
INFORME = TABLERO / f"{NOMBRE}.Report"


def lista_m(pq, nombre):
    """Extrae una lista {"a","b"} declarada en una consulta M."""
    cuerpo = re.search(nombre + r"\s*=\s*\{(.*?)\},\n", pq, re.S).group(1)
    return re.findall(r'"([^"]+)"', cuerpo)


def columnas_decisiones():
    pq = (TABLERO / "decisiones.pq").read_text(encoding="utf-8")
    enteros, decimales = set(lista_m(pq, "Enteros")), set(lista_m(pq, "Decimales"))
    with (RAIZ / "datos" / "decisiones.csv").open(encoding="utf-8-sig", newline="") as f:
        cabecera = next(csv.reader(f))
    tipos = []
    for c in cabecera:
        if c in ("vista_json", "participaciones_json"):
            continue
        tipos.append((c, "int64" if c in enteros else "double" if c in decimales
                      else "dateTime" if c == "fecha_solicitud_escenario" else "string"))
    return tipos


PARTICIPACIONES = [("solicitud_id", "string"), ("id_movil", "string"), ("tipo", "string"), ("rol", "string"),
                   ("zona_origen", "string"), ("espera_min", "double"), ("viaje_min", "double"),
                   ("llegada_min", "double"), ("km", "double"), ("costo_ida_cop", "double")]
LINEA_BASE = [("vista", "string"), ("codigo_emi", "string"), ("objetivo_min", "double"), ("servicios", "int64"),
              ("denominador", "int64"), ("excluidos_anomalia", "int64"), ("p90_min", "double"),
              ("mediana_min", "double"), ("promedio_min", "double"), ("pct_cumple", "double"),
              ("costo_completo_medio_cop", "double"), ("kpi04_espera_asignacion_mediana_min", "double"),
              ("archivo_p90_min", "double"), ("archivo_pct_cumple", "double"), ("definicion", "string")]


def medidas():
    texto = (TABLERO / "medidas.dax").read_text(encoding="utf-8")
    salida = []
    for bloque in re.split(r"\n\s*\n", texto):
        lineas = [x for x in bloque.splitlines() if x.strip() and not x.strip().startswith("//")]
        if not lineas:
            continue
        # «Nombre = expresión» en una línea, o «Nombre =» con la expresión en las líneas siguientes.
        nombre, resto = re.match(r"^(.*?)\s*=\s*(.*)$", lineas[0]).groups()
        expresion = "\n".join([resto] + lineas[1:]).strip()
        n = nombre.strip()
        formato = ("0.0%;-0.0%;0.0%" if "(%)" in n or n.startswith("Cumplimiento") else
                   "#,0" if "COP" in n else "0" if n in ("Decisiones", "Asignadas", "Participaciones",
                   "Pendientes o sin asignar", "Observaciones con referencia") else
                   None if n.startswith("Denominador") else "0.0")
        m = {"name": n, "expression": expresion}
        if formato:
            m["formatString"] = formato
        salida.append(m)
    nombres = [m["name"] for m in salida]
    if any(not n or n.endswith("=") for n in nombres) or len(set(nombres)) != len(nombres):
        raise ValueError(f"Revisa los nombres de medidas.dax: {nombres}")
    return salida


def tabla(nombre, columnas, consulta, con_medidas=False):
    t = {"name": nombre,
         "columns": [{"name": c, "dataType": tipo, "sourceColumn": c,
                      "summarizeBy": "none" if tipo == "string" or c.startswith(("cumple", "codigo")) else "sum"}
                     for c, tipo in columnas],
         "partitions": [{"name": nombre, "mode": "import",
                         "source": {"type": "m", "expression": consulta.splitlines()}}]}
    if con_medidas:
        t["measures"] = medidas()
    return t


def parametro(nombre, ruta):
    valor = str(ruta).replace('"', '""')
    return {"name": nombre, "kind": "m",
            "expression": f'"{valor}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}


def modelo():
    pq = {n: (TABLERO / f"{n}.pq").read_text(encoding="utf-8") for n in ("decisiones", "participaciones", "linea_base")}
    return {"compatibilityLevel": 1567, "model": {
        "culture": "es-CO", "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "sourceQueryCulture": "es-CO", "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
        "expressions": [parametro("RutaCSV", RAIZ / "datos" / "decisiones.csv"),
                        parametro("RutaLineaBase", RAIZ / "datos" / "entrada" / "linea_base_kpi.csv")],
        "tables": [tabla("decisiones", columnas_decisiones(), pq["decisiones"], True),
                   tabla("participaciones", PARTICIPACIONES, pq["participaciones"]),
                   tabla("linea_base", LINEA_BASE, pq["linea_base"])],
        "relationships": [{"name": "participaciones_decisiones", "fromTable": "participaciones",
                           "fromColumn": "solicitud_id", "toTable": "decisiones", "toColumn": "solicitud_id"}],
        "annotations": [{"name": "PBI_QueryOrder",
                         "value": json.dumps(["RutaCSV", "RutaLineaBase", "decisiones", "participaciones", "linea_base"])},
                        {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"}]}}


# ----------------------------------------------------------------------------------------- informe (report.json)
ALIAS = {"decisiones": "d", "participaciones": "p", "linea_base": "l"}


def campo(ref):
    """'decisiones.modalidad' (columna) o 'decisiones.[Decisiones]' (medida)."""
    tabla_, nombre = ref.split(".", 1)
    medida = nombre.startswith("[")
    nombre = nombre.strip("[]")
    expr = {"Expression": {"SourceRef": {"Source": ALIAS[tabla_]}}, "Property": nombre}
    return tabla_, nombre, ({"Measure": expr} if medida else {"Column": expr})


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


class Pagina:
    def __init__(self):
        self.visuales = []

    def visual(self, tipo, x, y, w, h, roles=None, titulo=None, objetos=None):
        roles = roles or {}
        tablas, select, proyecciones = [], [], {}
        for rol, refs in roles.items():
            proyecciones[rol] = []
            for ref in refs:
                t, n, sel = campo(ref)
                nombre = f"{t}.{n}"
                if t not in tablas:
                    tablas.append(t)
                if nombre not in [s["Name"] for s in select]:
                    select.append(dict(sel, Name=nombre))
                proyecciones[rol].append({"queryRef": nombre} | ({"active": True} if tipo == "slicer" else {}))
        sv = {"visualType": tipo, "projections": proyecciones, "drillFilterOtherVisuals": True}
        if select:
            sv["prototypeQuery"] = {"Version": 2, "From": [{"Name": ALIAS[t], "Entity": t, "Type": 0} for t in tablas],
                                    "Select": select}
        if objetos:
            sv["objects"] = objetos
        if titulo:
            sv["vcObjects"] = {"title": [{"properties": {"show": lit("true"), "text": lit(f"'{titulo}'")}}]}
        nombre = f"v{len(self.visuales):02d}"
        pos = {"x": x, "y": y, "z": len(self.visuales), "width": w, "height": h}
        cfg = {"name": nombre, "layouts": [{"id": 0, "position": pos}], "singleVisual": sv}
        self.visuales.append(dict(pos, config=json.dumps(cfg, ensure_ascii=False), filters="[]"))

    def texto(self, contenido, x, y, w, h, tam="14pt", negrita=False):
        estilo = {"fontSize": tam} | ({"fontWeight": "bold"} if negrita else {})
        objetos = {"general": [{"properties": {"paragraphs": [{"textRuns": [{"value": contenido, "textStyle": estilo}]}]}}]}
        self.visual("textbox", x, y, w, h, objetos=objetos)


def informe():
    p = Pagina()
    p.texto("EMI EnRuta · Demo académica con datos ficticios", 16, 8, 760, 40, "18pt", True)
    p.texto("Resultados del ensayo (decisiones.csv). La línea base histórica ficticia se rotula aparte. "
            "Actualizar: Inicio → Actualizar.", 16, 46, 760, 30, "10pt")
    for i, col in enumerate(["escenario_id", "codigo_emi", "modalidad", "origen_registro"]):
        p.visual("slicer", 16 + i * 158, 80, 150, 92, {"Values": [f"decisiones.{col}"]})
    p.visual("slicer", 648, 80, 150, 92, {"Values": ["decisiones.solicitud_fuente"]})
    # ¿Cuánto tarda la decisión?
    p.visual("tableEx", 16, 182, 400, 130, {"Values": ["decisiones.modalidad", "decisiones.[Decisiones]",
             "decisiones.[Decisión mediana (s)]", "decisiones.[Cumple R02 (%)]"]}, "¿Cuánto tarda la decisión?")
    # ¿Cuándo llegaría la primera unidad?
    p.visual("card", 424, 182, 180, 130, {"Values": ["decisiones.[Primera llegada mediana (min)]"]},
             "Primera llegada mediana (min)")
    p.visual("card", 612, 182, 186, 130, {"Values": ["decisiones.[Llegada mediana de ambulancia R04 (min)]"]},
             "Llegada de ambulancia R04 (min)")
    p.visual("clusteredColumnChart", 16, 320, 400, 210, {"Category": ["decisiones.codigo_emi"],
             "Y": ["decisiones.[Dentro del objetivo (%)]"]},
             "Primera llegada estimada dentro del objetivo · denominador: asignadas")
    p.visual("card", 16, 536, 400, 60, {"Values": ["decisiones.[Denominador cumplimiento]"]}, "Denominador")
    # ¿Cuánto cuesta la alternativa?
    p.visual("card", 424, 320, 180, 100, {"Values": ["decisiones.[Costo medio de ida por decisión (COP)]"]},
             "Costo medio de ida (COP)")
    p.visual("card", 612, 320, 186, 100, {"Values": ["decisiones.[Km medio por decisión]"]}, "Km medio por decisión")
    p.visual("card", 424, 426, 374, 80, {"Values": ["decisiones.[Costo medio de decisión, supuesto (COP)]"]},
             "Costo de decisión · supuesto del equipo (300 COP/min)")
    p.visual("clusteredBarChart", 808, 8, 456, 300, {"Category": ["participaciones.id_movil"],
             "Series": ["participaciones.rol"], "Y": ["decisiones.[Costo de ida por móvil (COP)]"]},
             "Costo de ida por móvil elegido y rol (COP)")
    # ¿Qué cambió respecto de la referencia?
    p.visual("tableEx", 808, 316, 456, 190, {"Values": ["decisiones.solicitud_fuente", "decisiones.modalidad",
             "decisiones.[Observaciones con referencia]", "decisiones.[Δ primera llegada vs referencia (min)]",
             "decisiones.[Δ costo de ida vs referencia (COP)]", "decisiones.[Coincide con la referencia (%)]"]},
             "¿Qué cambió respecto de la referencia? (mismo caso e instante)")
    # Línea base histórica
    p.visual("tableEx", 424, 512, 840, 200, {"Values": ["linea_base.vista", "linea_base.codigo_emi",
             "linea_base.denominador", "linea_base.p90_min", "linea_base.pct_cumple",
             "linea_base.kpi04_espera_asignacion_mediana_min", "linea_base.archivo_p90_min",
             "linea_base.archivo_pct_cumple"]},
             "Línea base histórica ficticia (archivo 01): no es resultado del ensayo")
    seccion = {"name": "ReportSection", "displayName": "Decisiones de despacho", "displayOption": 1,
               "width": 1280, "height": 720, "ordinal": 0, "filters": "[]", "config": "{}",
               "visualContainers": p.visuales}
    config = {"version": "5.43", "themeCollection": {}, "activeSectionIndex": 0,
              "defaultDrillFilterOtherVisuals": True, "settings": {"useStylableVisualContainerHeader": True}}
    return {"config": json.dumps(config), "layoutOptimization": 0, "sections": [seccion]}


def escribir(ruta, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")


def generar():
    for carpeta in (MODELO, INFORME):
        if carpeta.exists():
            shutil.rmtree(carpeta)
    escribir(TABLERO / f"{NOMBRE}.pbip", {"version": "1.0", "artifacts": [{"report": {"path": f"{NOMBRE}.Report"}}],
                                          "settings": {"enableAutoRecovery": True}})
    escribir(MODELO / "definition.pbism", {"version": "1.0", "settings": {}})
    escribir(MODELO / "model.bim", modelo())
    escribir(INFORME / "definition.pbir", {"version": "1.0", "datasetReference": {
        "byPath": {"path": f"../{NOMBRE}.SemanticModel"}, "byConnection": None}})
    escribir(INFORME / "report.json", informe())
    print(f"Proyecto generado: {TABLERO / (NOMBRE + '.pbip')}")


if __name__ == "__main__":
    generar()
