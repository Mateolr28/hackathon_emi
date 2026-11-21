"""Extrae de los originales los CSV que usa la demo.

Uso:  py preparar_datos.py [DIRECTORIO_FUENTES]
Si no se indica, se usa la variable de entorno EMI_FUENTES y, en su defecto,
C:\\Users\\Usuario\\Documents\\EstudIA\\11. Los originales se abren solo para lectura.
"""
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "datos" / "entrada"
FUENTES_POR_DEFECTO = Path(r"C:\Users\Usuario\Documents\EstudIA\11")
ESCENARIOS = {"ESC-01", "ESC-02", "ESC-04"}


def hoja(libro, nombre):
    """Lee una hoja Open XML con la biblioteca estándar. Todo se conserva como texto."""
    with ZipFile(libro) as z:
        sheets = ET.fromstring(z.read("xl/workbook.xml")).findall(".//{*}sheet")
        sheet = next(s for s in sheets if s.get("name") == nombre)
        rel = next(v for k, v in sheet.attrib.items() if k.endswith("}id"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        ruta = next(r.get("Target") for r in rels if r.get("Id") == rel)
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(t.text or "" for t in s.findall(".//{*}t"))
                      for s in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        root = ET.fromstring(z.read(ruta.lstrip("/") if ruta.startswith("/") else "xl/" + ruta))
        filas, encabezados = [], None
        for row in root.findall(".//{*}sheetData/{*}row"):
            values = {}
            for cell in row:
                col = cell.get("r").rstrip("0123456789")
                val = cell.findtext("{*}v", default="")
                if cell.get("t") == "inlineStr":
                    val = "".join(x.text or "" for x in cell.findall(".//{*}t"))
                elif cell.get("t") == "s":
                    val = shared[int(val)]
                values[col] = val
            if encabezados is None:
                encabezados = values
            else:
                filas.append({key: values.get(col, "") for col, key in encabezados.items()})
        return filas


def escribir(nombre, filas, campos=None):
    campos = campos or list(filas[0].keys())
    with (SALIDA / (nombre + ".csv")).open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def texto(valor):
    """JSON → CSV sin perder ceros iniciales ni convertir None en 'None'."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return str(valor)
    return str(valor)


def validar_historico(historico, flota, zonas, bases):
    """Comprobaciones de calidad. Devuelve filas para calidad_datos.csv; lanza error si una clave falla."""
    ids_movil = {m["id_movil"] for m in flota}
    reporte = []

    def registrar(chequeo, n, detalle, bloqueante=False):
        reporte.append(dict(chequeo=chequeo, resultado=n, detalle=detalle))
        if bloqueante and n:
            raise ValueError(f"01_servicios_historicos.json: {chequeo} ({n}). {detalle}")

    ids = Counter(s["id_servicio"] for s in historico)
    registrar("id_servicio duplicado", sum(1 for v in ids.values() if v > 1), "Debe ser 0.", True)
    registrar("zona de servicio desconocida", sum(s["id_zona"] not in zonas for s in historico), "Debe ser 0.", True)
    participaciones = [m for s in historico for m in s["moviles"]]
    registrar("móvil desconocida en participaciones", sum(m["id_movil"] not in ids_movil for m in participaciones),
              "Debe ser 0.", True)
    registrar("zona de origen desconocida en participaciones",
              sum(m["zona_origen_movil"] not in zonas for m in participaciones), "Debe ser 0.", True)
    registrar("base desconocida en flota", sum(m["id_base"] not in bases for m in flota), "Debe ser 0.", True)
    registrar("tarifa no positiva en flota",
              sum(not (float(m["costo_km"]) > 0 and float(m["costo_hora"]) > 0) for m in flota), "Debe ser 0.", True)
    n_mov = Counter(len(s["moviles"]) for s in historico)
    registrar("servicios totales", len(historico), "Periodo 2026-03-16 a 2026-04-30.")
    for k in sorted(n_mov):
        registrar(f"servicios con {k} participaciones", n_mov[k], "Una solicitud puede tener 0, 1 o 2 móviles.")
    for estado, n in sorted(Counter(s["estado_cierre"] for s in historico).items()):
        registrar(f"estado_cierre {estado}", n, "Cancelados y resueltos por teléfono no tienen llegada.")
    registrar("servicios sin canal", sum(s["canal"] is None for s in historico), "Advertencia del Readme (≈1 %).")
    registrar("participaciones sin fin de atención", sum(m["fecha_hora_fin_atencion"] is None for m in participaciones),
              "Incluye cancelaciones en ruta.")
    registrar("servicios con reclasificación", sum(len(s["clasificaciones"]) > 1 for s in historico),
              "Base de KPI-12. La demo usa la clasificación vigente en el instante del caso (R07).")
    registrar("servicios sin tiempo_respuesta_min", sum(s["tiempo_respuesta_min"] is None for s in historico),
              "Quedan fuera del denominador de KPI-01 a KPI-03.")
    return reporte


def preparar(base):
    base = Path(base)
    if not base.is_dir():
        raise SystemExit(f"No existe la carpeta de fuentes {base}. Indícala como argumento o en EMI_FUENTES.")
    SALIDA.mkdir(parents=True, exist_ok=True)

    def fuente(prefijo):
        try:
            return next(base.glob(prefijo + "_*"))
        except StopIteration:
            raise SystemExit(f"Falta el archivo {prefijo}_* en {base}") from None

    def json_fuente(prefijo):
        return json.loads(fuente(prefijo).read_text(encoding="utf-8-sig"))

    def seleccion(tabla):
        return [r for r in hoja(fuente("06"), tabla) if r["id_escenario"] in ESCENARIOS]

    escenarios = seleccion("escenarios")
    solicitudes = seleccion("solicitudes")
    historico = json_fuente("01")["servicios"]
    catalogo = json_fuente("02")
    flota = [{k: texto(v) for k, v in m.items()} for m in catalogo["moviles"]]
    bases = [{k: texto(v) for k, v in b.items()} for b in catalogo["bases"]]
    zonas = hoja(fuente("05"), "zonas")
    escribir("flota", flota)
    escribir("bases", bases)
    escribir("zonas", zonas)
    for nombre in ("matriz_tiempos", "factor_trafico"):
        escribir(nombre, hoja(fuente("05"), nombre))
    escribir("escenarios", escenarios)
    escribir("estado_inicial_moviles", seleccion("estado_inicial_moviles"))
    escribir("eventos", seleccion("eventos"), ["id_escenario", "minuto", "tipo_evento", "id_solicitud", "id_movil",
                                                "detalle", "nueva_clasificacion", "escala_manchester_nueva"])
    escribir("referencia_despachador", seleccion("decision_despachador"))

    calidad = validar_historico(historico, flota, {z["id_zona"] for z in zonas}, {b["id_base"] for b in bases})

    # Carga D04: participaciones COMPLETADAS liberadas entre el inicio del turno de 8 h y la hora de la
    # solicitud. Solo usa hechos anteriores al instante del caso. Vacío = la móvil no aparece en el histórico.
    con_historia = {m["id_movil"] for s in historico for m in s["moviles"]}
    inicio = {e["id_escenario"]: datetime.fromisoformat(e["fecha_hora_inicio"]) for e in escenarios}
    cargas = []
    for s in solicitudes:
        # D06: caídas, fracturas o deshidratación en un 07 → posible traslado.
        disc = s["discriminador"].lower()
        s["posible_traslado"] = int(s["clasificacion_inicial"] == "07" and (
            s["motivo_consulta"] == "Caídas" or "fractura" in disc or "deshidratación" in disc and "sin " not in disc))
        instante = inicio[s["id_escenario"]] + timedelta(minutes=int(s["minuto_llegada"]))
        turno = instante.replace(hour=8 * (instante.hour // 8), minute=0)
        cuenta = Counter(m["id_movil"] for h in historico for m in h["moviles"]
                         if m["estado"] == "COMPLETADO" and m["fecha_hora_liberacion"]
                         and turno.isoformat() <= m["fecha_hora_liberacion"] <= instante.isoformat())
        cargas.extend(dict(id_solicitud=s["id_solicitud"], id_movil=m["id_movil"],
                           servicios_turno=cuenta[m["id_movil"]] if m["id_movil"] in con_historia else "",
                           periodo_carga=f"{turno:%Y-%m-%d %H:%M}–{instante:%H:%M}",
                           unidad_carga="participaciones completadas y liberadas en el turno")
                      for m in flota)
    escribir("carga", cargas)
    escribir("solicitudes", solicitudes)

    objetivos = hoja(fuente("07"), "linea_base_por_clasificacion")
    escribir("objetivos_urgencia", [dict(codigo_emi=x["clasificacion"], descripcion=x["descripcion"],
                                          objetivo_min=x["tiempo_objetivo_min"]) for x in objetivos])
    escribir("indicadores", hoja(fuente("07"), "kpis"))
    # Compatibilidad del documento 03. 'posible_traslado' = TAB permitida en 07 solo con posible traslado.
    reglas = {"01": ("preferida", "permitida", "solo_estabilizacion"),
              "02": ("permitida", "preferida", "solo_estabilizacion"),
              "07": ("no_recomendada", "posible_traslado", "preferida"),
              "03": ("no_permitida", "no_recomendada", "preferida"),
              "06": ("no_permitida", "no_permitida", "preferida")}
    escribir("reglas_movil_servicio", [dict(codigo_emi=c, tipo_movil=t, compatibilidad=r)
             for c, estados in reglas.items() for t, r in zip(("TAM", "TAB", "VMD"), estados)])

    # Línea base histórica (KPI-01 a KPI-03): vista original y vista con llegadas anómalas excluidas.
    sys.path.insert(0, str(RAIZ))
    from src.linea_base import calcular
    filas, resumen = calcular(historico, SALIDA, objetivos)
    escribir("linea_base_kpi", filas)
    calidad.append(dict(chequeo="KPI-08 costo completo medio por servicio con móvil (COP)",
                        resultado=resumen["costo_completo_medio_cop"],
                        detalle=f"km × costo_km + horas asignación→liberación × costo_hora; denominador "
                                f"{resumen['servicios_con_movil']} servicios con móvil. Archivo 07: 127300."))
    calidad.append(dict(chequeo="llegadas anómalas (> 45 min sobre la matriz)", resultado=resumen["anomalias"],
                        detalle="Excluidas solo en la vista 'corregida' de linea_base_kpi.csv. La vista 'original' las conserva."))
    escribir("calidad_datos", calidad)
    print(f"CSV derivados escritos en {SALIDA}")


if __name__ == "__main__":
    preparar(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("EMI_FUENTES", FUENTES_POR_DEFECTO)))
