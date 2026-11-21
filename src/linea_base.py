"""Línea base histórica ficticia (archivo 01) con las definiciones del archivo 07.

Vista 'original': reproduce KPI-01 a KPI-03 tal como están publicados.
Vista 'corregida': excluye llegadas anómalas. Se publica aparte y nunca reemplaza la original.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

UMBRAL_ANOMALIA_MIN = 45  # llegada real − estimación de la matriz. Separa con holgura el 2 % de errores de registro.
FESTIVOS = {"2026-03-23", "2026-04-02", "2026-04-03"}  # Supuesto: festivos de Colombia en el periodo.


def tipo_dia(instante):
    if instante.strftime("%Y-%m-%d") in FESTIVOS or instante.weekday() == 6:
        return "DOMINGO_FESTIVO"
    return "SABADO" if instante.weekday() == 5 else "LUNES_A_VIERNES"


def servicios(historico, entrada):
    """Una fila por servicio con primera llegada, marca de anomalía y costo completo (KPI-08)."""
    entrada = Path(entrada)
    m = pd.read_csv(entrada / "matriz_tiempos.csv", dtype=str, encoding="utf-8-sig")
    f = pd.read_csv(entrada / "factor_trafico.csv", dtype=str, encoding="utf-8-sig")
    flota = pd.read_csv(entrada / "flota.csv", dtype=str, encoding="utf-8-sig").set_index("id_movil")
    valle = dict(zip(zip(m.zona_origen, m.zona_destino), m.tiempo_valle_min.astype(float)))
    factor = dict(zip(zip(f.tipo_dia, f.hora_inicio), f.factor.astype(float)))
    filas = []
    for s in historico:
        llegadas = [x for x in s["moviles"] if x["fecha_hora_llegada"]]
        anomalia = None
        if llegadas:
            x = min(llegadas, key=lambda x: x["fecha_hora_llegada"])
            salida = datetime.fromisoformat(x["fecha_hora_salida"])
            real = (datetime.fromisoformat(x["fecha_hora_llegada"]) - salida).total_seconds() / 60
            clave = (x["zona_origen_movil"], s["id_zona"])
            if clave not in valle:
                raise ValueError(f"matriz_tiempos.csv: falta la ruta {clave[0]} → {clave[1]} ({s['id_servicio']})")
            estimado = valle[clave] * factor[(tipo_dia(salida), f"{salida.hour:02}:00")]
            anomalia = real - estimado > UMBRAL_ANOMALIA_MIN
        costo = 0.
        for x in s["moviles"]:
            t = flota.loc[x["id_movil"]]
            fin = x["fecha_hora_liberacion"] or x["fecha_hora_fin_atencion"] or x["fecha_hora_llegada"]
            horas = ((datetime.fromisoformat(fin) - datetime.fromisoformat(x["fecha_hora_asignacion"])).total_seconds()
                     / 3600 if fin else 0.)
            costo += (x["distancia_km"] or 0) * float(t.costo_km) + horas * float(t.costo_hora)
        asignaciones = [x["fecha_hora_asignacion"] for x in s["moviles"] if x["fecha_hora_asignacion"]]
        espera_asig = ((datetime.fromisoformat(min(asignaciones)) - datetime.fromisoformat(s["fecha_hora_paso_a_despacho"]))
                       .total_seconds() / 60 if asignaciones and s["fecha_hora_paso_a_despacho"] else None)
        filas.append(dict(id_servicio=s["id_servicio"], espera_asignacion_min=espera_asig, clasificacion_final=s["clasificacion_final"],
                          tiempo_respuesta_min=s["tiempo_respuesta_min"], anomalia=anomalia,
                          n_moviles=len(s["moviles"]), costo_completo_cop=costo if s["moviles"] else None))
    return pd.DataFrame(filas)


def calcular(historico, entrada, objetivos):
    df = servicios(historico, entrada)
    publicados = {o["clasificacion"]: o for o in objetivos}
    filas = []
    for vista in ("original", "corregida"):
        base = df if vista == "original" else df[df.anomalia != True]  # noqa: E712 (None = sin llegada)
        for codigo, o in publicados.items():
            objetivo = float(o["tiempo_objetivo_min"])
            g = base[base.clasificacion_final == codigo]
            t = g.tiempo_respuesta_min.dropna().astype(float)
            filas.append(dict(
                vista=vista, codigo_emi=codigo, objetivo_min=objetivo, servicios=len(g),
                denominador=len(t), excluidos_anomalia=int((df[df.clasificacion_final == codigo].anomalia == True).sum())
                if vista == "corregida" else 0,
                p90_min=round(t.quantile(0.9), 1), mediana_min=round(t.median(), 1), promedio_min=round(t.mean(), 1),
                pct_cumple=round((t <= objetivo).mean() * 100, 1),
                costo_completo_medio_cop=round(g[g.n_moviles > 0].costo_completo_cop.mean()),
                kpi04_espera_asignacion_mediana_min=round(g.espera_asignacion_min.dropna().median(), 1),
                archivo_p90_min=o["tr_p90_min"], archivo_pct_cumple=o["pct_cumple_objetivo"],
                definicion="Solicitud → llegada de la primera móvil; clasificación final; denominador = servicios "
                           "con tiempo_respuesta_min" + ("; excluye llegadas anómalas" if vista == "corregida" else "")))
    con_movil = df[df.n_moviles > 0]
    resumen = dict(anomalias=int((df.anomalia == True).sum()), servicios_con_movil=len(con_movil),  # noqa: E712
                   costo_completo_medio_cop=round(con_movil.costo_completo_cop.mean()))
    return filas, resumen
