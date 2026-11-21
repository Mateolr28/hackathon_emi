"""Reglas del ejercicio para una solicitud ya clasificada.

Todos los minutos de respuesta se cuentan desde la solicitud:
    respuesta = transcurrido hasta el instante de comparación + espera hasta salida + viaje
    viaje     = tiempo_valle[origen, destino] × factor_trafico[tipo_dia, hora de salida]   (tráfico una sola vez)
    costo ida = km × costo_km + viaje / 60 × costo_hora
"""
from datetime import timedelta
from math import isfinite

import pandas as pd

EPS = 1e-9            # Tolerancia de coma flotante para los umbrales exactos.
UMBRAL_D02 = 3.0      # D02: «menos de 3 minutos» (exactamente 3 no activa D02).
UMBRAL_R04 = 12.0     # R04: «al menos 12 minutos antes» (exactamente 12 sí activa R04).
COBERTURA_D03 = 20.0  # D03: zona ALTA con ambulancia a 20 min o menos.
ATENCION = "ATENCION"
RESPONDIENTE = "PRIMER_RESPONDIENTE_ESTABILIZACION"
AMBULANCIA = "ATENCION_Y_TRASLADO"
LIBRES = {"DISPONIBLE", "RETORNANDO"}
OCUPADAS = {"EN_ATENCION", "EN_TRASLADO"}
AMBULANCIAS = {"TAM", "TAB"}  # R03: solo TAM y TAB trasladan.
CRITICOS = {"01", "02"}
SUPUESTO_PREVIO = "supuesto_demo_paso_inmediato"
NOMBRES_COMP = {"preferida": "preferida", "permitida": "permitida", "posible_traslado": "permitida con posible traslado",
                "no_recomendada": "no recomendada", "no_permitida": "no permitida",
                "solo_estabilizacion": "solo estabilización"}


def preparar(tablas, solicitud_id, previo=None):
    """Fija el caso en el instante de comparación. previo=None aplica el supuesto de demostración (0 min)."""
    fuente_previo = SUPUESTO_PREVIO if previo is None else "ingresado_por_usuario"
    previo = 0. if previo is None else float(previo)
    if not isfinite(previo) or previo < 0:
        raise ValueError("Los minutos previos a despacho deben ser finitos y no negativos.")
    s = tablas["solicitudes"].set_index("id_solicitud").loc[solicitud_id].to_dict()
    e = tablas["escenarios"].set_index("id_escenario").loc[s["id_escenario"]]
    instante = float(s["minuto_llegada"]) + previo  # Minuto del escenario en que se compara.

    # Eventos conocidos hasta el instante de comparación. Nada posterior influye en la recomendación.
    ev = tablas["eventos"]
    ev = ev[(ev.id_escenario == s["id_escenario"]) & (ev.minuto <= instante + EPS)].sort_values("minuto")
    codigo_inicial = codigo = s["clasificacion_inicial"]
    reclasificaciones = []
    liberadas = set()
    for x in ev.itertuples():
        if x.tipo_evento.startswith("RECLASIFICACION") and x.id_solicitud == solicitud_id and x.nueva_clasificacion:
            codigo = x.nueva_clasificacion  # R07: rige la clasificación vigente en el instante.
            reclasificaciones.append(f"min {x.minuto:g}: {x.tipo_evento.lower()} a {codigo}")
        elif x.tipo_evento == "MOVIL_LIBERADA" and x.id_movil:
            liberadas.add(x.id_movil)

    objetivo = tablas["objetivos_urgencia"].set_index("codigo_emi").at[codigo, "objetivo_min"]
    flota = tablas["estado_inicial_moviles"]
    flota = flota[flota.id_escenario == s["id_escenario"]].merge(
        tablas["flota"].drop(columns="id_base"), on=["id_movil", "tipo_movil"])
    for i in flota.index[flota.id_movil.isin(liberadas)]:
        flota.loc[i, ["estado", "min_para_liberarse"]] = ["DISPONIBLE", 0.]
    carga = tablas["carga"]
    flota = flota.merge(carga[carga.id_solicitud == solicitud_id].drop(columns="id_solicitud"), on="id_movil", how="left")
    matriz = tablas["matriz_tiempos"]
    # Unión externa por la izquierda: una ruta faltante queda visible como NaN y nunca como viaje cero.
    flota = flota.merge(matriz[matriz.zona_destino == s["id_zona"]], left_on="id_zona_actual",
                        right_on="zona_origen", how="left")
    reglas = tablas["reglas_movil_servicio"]
    flota = flota.merge(reglas[reglas.codigo_emi == codigo], on="tipo_movil")
    zonas = tablas["zonas"]
    return dict(solicitud_fuente=solicitud_id, escenario_id=s["id_escenario"], codigo_emi=codigo,
                codigo_emi_inicial=codigo_inicial, reclasificaciones=reclasificaciones,
                tipo_servicio=s["descripcion"], motivo=s["motivo_consulta"], discriminador=s.get("discriminador", ""),
                comuna=s.get("comuna", ""), zona_destino_id=s["id_zona"], posible_traslado=s["posible_traslado"] == "1",
                objetivo_min=float(objetivo), minuto_llegada=float(s["minuto_llegada"]), previo_min=previo,
                fuente_previo=fuente_previo, tipo_dia=e.tipo_dia,
                fecha_solicitud=pd.Timestamp(e.fecha_hora_inicio) + timedelta(minutes=float(s["minuto_llegada"])),
                factores=tablas["factor_trafico"].set_index(["tipo_dia", "hora_inicio"]).factor.to_dict(),
                valle=dict(zip(zip(matriz.zona_origen, matriz.zona_destino), matriz.tiempo_valle_min)),
                zonas_alta=sorted(zonas.loc[zonas.demanda_relativa == "ALTA", "id_zona"]),
                flota=flota.sort_values("id_movil").to_dict("records"))


def franja(caso, minutos):
    """Tipo de día y hora de salida, `minutos` después de la solicitud."""
    hora = caso["fecha_solicitud"] + timedelta(minutes=minutos)
    dia = caso["tipo_dia"]
    if hora.date() != caso["fecha_solicitud"].date():
        dia = (("LUNES_A_VIERNES",) * 5 + ("SABADO", "DOMINGO_FESTIVO"))[hora.weekday()]
    return dia, hora.strftime("%H:00")


def _numero(x):
    return x if isinstance(x, (int, float)) and x == x else None


def medir(caso, m, transcurrido):
    estado = m["estado"]
    liberacion = _numero(m["min_para_liberarse"])
    espera = 0.
    if estado in OCUPADAS and liberacion is not None:
        # Espera futura hasta quedar utilizable, separada del viaje posterior.
        espera = max(0., liberacion - caso["minuto_llegada"] - transcurrido)
    clave = franja(caso, transcurrido + espera)
    if clave not in caso["factores"]:
        raise ValueError(f"factor_trafico.csv: falta el factor para {clave[0]} {clave[1]}")
    factor = caso["factores"][clave]
    valle = _numero(m.get("tiempo_valle_min"))
    viaje = valle * factor if valle is not None else None
    km = _numero(m.get("distancia_km"))
    costo = km * m["costo_km"] + viaje / 60 * m["costo_hora"] if viaje is not None and km is not None else None
    estado_actual = "DISPONIBLE" if estado in OCUPADAS and liberacion is not None and espera == 0 else estado
    carga = _numero(m.get("servicios_turno"))
    return dict(id_movil=m["id_movil"], tipo=m["tipo_movil"], zona=m["id_zona_actual"], estado=estado_actual,
                estado_foto=estado, activo=str(m["activo"]) == "True", compatibilidad=m["compatibilidad"],
                carga=int(carga) if carga is not None else None, periodo_carga=m.get("periodo_carga") or "",
                km=km, valle=valle, factor=factor, salida=clave[1], tarifa_km=m["costo_km"],
                tarifa_hora=m["costo_hora"], espera=espera,
                liberacion_conocida=estado not in OCUPADAS or liberacion is not None, viaje=viaje,
                llegada=transcurrido + espera + viaje if viaje is not None else None, costo=costo)


def participacion(m, rol):
    """Lo que se guarda de cada móvil elegido."""
    return dict(id_movil=m["id_movil"], tipo=m["tipo"], rol=rol, zona_origen=m["zona"], estado=m["estado_foto"],
                espera_min=m["espera"], viaje_min=m["viaje"], llegada_min=m["llegada"], km=m["km"],
                factor=m["factor"], tarifa_km_cop=m["tarifa_km"], tarifa_hora_cop=m["tarifa_hora"],
                costo_ida_cop=m["costo"])


def cobertura(caso, flota, excluir=()):
    """Zonas de demanda ALTA alcanzables por una ambulancia libre en ≤ 20 min (D03)."""
    libres = [m for m in flota if m["activo"] and m["tipo"] in AMBULANCIAS and m["estado"] in LIBRES
              and m["id_movil"] not in excluir]
    cubiertas = set()
    for z in caso["zonas_alta"]:
        for m in libres:
            valle = caso["valle"].get((m["zona"], z))
            if valle is not None and valle * m["factor"] <= COBERTURA_D03 + EPS:
                cubiertas.add(z)
                break
    return cubiertas


def _clave(x):
    # En igualdad de costo: carga del turno (sin dato al final), llegada e identificador.
    return (x["costo_plan"], x["carga"] is None, x["carga"] or 0, x["llegada"], x["plan_id"])


def ordenar(opciones, caso):
    """D01/D02 reproducible.

    Primero los planes que cumplen el objetivo. Se agrupa respecto de la llegada más rápida del grupo restante
    (diferencia < 3 min). Dentro del grupo va primero el tipo preferido, luego una unidad libre antes que una
    que depende de liberarse (D08), y después el menor costo, la menor carga y el identificador. Se repite con
    los restantes. Los planes que exceden el objetivo se ordenan por menor
    llegada (protección asistencial) y desempatan igual.
    """
    orden = []
    for cumple in (True, False):
        pendientes = sorted((x for x in opciones if x["cumple"] == cumple), key=lambda x: (x["llegada"], x["plan_id"]))
        while pendientes:
            ancla = pendientes[0]
            if cumple:
                grupo = [x for x in pendientes if x["llegada"] - ancla["llegada"] < UMBRAL_D02 - EPS]
            else:
                grupo = [x for x in pendientes if abs(x["llegada"] - ancla["llegada"]) <= EPS]
            grupo.sort(key=lambda x: (x["compatibilidad"] != "preferida", x["espera"] > EPS) + _clave(x))
            for i, x in enumerate(grupo):
                x["criterio"], x["regla"] = _criterio(x, grupo, i, cumple, caso)
            orden.extend(grupo)
            usados = {id(x) for x in grupo}
            pendientes = [x for x in pendientes if id(x) not in usados]
    # I-01: cada alternativa posterior se explica frente a la opción 1.
    if orden:
        primera = orden[0]
        for x in orden[1:]:
            dl, dc = x["llegada"] - primera["llegada"], x["costo_plan"] - primera["costo_plan"]
            tiempo = (f"llega {f1(abs(dl))} min {'después' if dl > 0 else 'antes'}" if abs(dl) >= 0.05
                      else "llega al mismo tiempo")
            costo = (f"cuesta {cop(abs(dc))} {'más' if dc > 0 else 'menos'}" if abs(dc) >= 0.5
                     else "cuesta lo mismo")
            x["comparacion"] = f"Frente a la opción 1 ({primera['plan_id']}): {tiempo} y {costo}."
    return orden


def _criterio(x, grupo, i, cumple, caso):
    if not cumple:
        return "ninguna alternativa restante cumple el objetivo; se ordena por menor llegada estimada", "D01"
    if len(grupo) == 1:
        return "menor llegada estimada entre las alternativas restantes", "D01"
    otros = [g for g in grupo if g is not x]
    if i == 0:
        if x["compatibilidad"] == "preferida" and any(g["compatibilidad"] != "preferida" for g in otros):
            regla = "D05" if caso["codigo_emi"] == "02" else "D01"
            return (f"tipo {x['tipo']} preferido para EMI {caso['codigo_emi']} entre alternativas con diferencia "
                    f"inferior a {UMBRAL_D02:g} min", regla)
        siguiente = grupo[1]
        if x["espera"] <= EPS and siguiente["espera"] > EPS and siguiente["compatibilidad"] == x["compatibilidad"]:
            return (f"unidad libre preferida sobre {siguiente['plan_id']}, que depende de liberarse, entre alternativas "
                    f"con diferencia inferior a {UMBRAL_D02:g} min", "D08")
        if x["costo_plan"] < siguiente["costo_plan"] - EPS:
            return f"diferencia inferior a {UMBRAL_D02:g} min; menor costo estimado de ida", "D02"
        if x["carga"] is not None and (siguiente["carga"] is None or x["carga"] < siguiente["carga"]):
            return "igual costo; menor carga en el turno entre unidades comparables", "D04"
        return "igual costo y carga; desempate estable por llegada e identificador", "desempate"
    lider = grupo[0]
    if lider["compatibilidad"] == "preferida" and x["compatibilidad"] != "preferida":
        motivo, regla = f"el tipo {x['tipo']} no es el preferido para EMI {caso['codigo_emi']}", (
            "D05" if caso["codigo_emi"] == "02" else "D01")
    elif lider["espera"] <= EPS and x["espera"] > EPS:
        motivo, regla = "depende de una liberación estimada (D08)", "D08"
    elif x["costo_plan"] > lider["costo_plan"] + EPS:
        motivo, regla = f"cuesta {cop(x['costo_plan'] - lider['costo_plan'])} más de ida", "D02"
    elif x["carga"] is None or (lider["carga"] is not None and x["carga"] > lider["carga"]):
        motivo, regla = "tiene más carga en el turno o carga sin dato", "D04"
    else:
        motivo, regla = "desempate estable por identificador", "desempate"
    return (f"llegada similar a {lider['plan_id']} (diferencia {f1(x['llegada'] - lider['llegada'])} min), "
            f"pero {motivo}", regla)


def evaluar(caso, segundos=0.):
    """Alternativas compatibles en el instante de comparación (previo + segundos de decisión)."""
    if not isfinite(segundos) or segundos < 0:
        raise ValueError("Duración de decisión inválida.")
    transcurrido = caso["previo_min"] + segundos / 60
    flota = [medir(caso, m, transcurrido) for m in caso["flota"]]
    objetivo = caso["objetivo_min"]
    codigo = caso["codigo_emi"]
    critico = codigo in CRITICOS

    def operativa(m):
        return m["activo"] and m["estado_foto"] != "FUERA_SERVICIO"

    # Ambulancias con llegada estimable: libres o con liberación conocida (D08: la liberación es una estimación).
    ambulancias = [m for m in flota if operativa(m) and m["tipo"] in AMBULANCIAS and m["llegada"] is not None
                   and (m["estado"] in LIBRES or m["estado_foto"] in OCUPADAS and m["liberacion_conocida"])]
    mejor_amb = min(ambulancias, key=lambda m: (m["llegada"], m["id_movil"]), default=None)
    # R04 preasigna la primera ambulancia disponible: menor espera, luego menor llegada, costo e identificador.
    respaldo = min(ambulancias, key=lambda m: (m["espera"], m["llegada"], m["costo"], m["id_movil"]), default=None)
    vmd_r04 = set()
    if critico and mejor_amb and mejor_amb["llegada"] > objetivo + EPS:
        vmd_r04 = {m["id_movil"] for m in flota if operativa(m) and m["estado"] in LIBRES and m["llegada"] is not None
                   and m["compatibilidad"] == "solo_estabilizacion"
                   and mejor_amb["llegada"] - m["llegada"] >= UMBRAL_R04 - EPS}
    cubiertas = cobertura(caso, flota)

    opciones, excepciones = [], []
    for m in flota:
        comp = m["compatibilidad"]
        r04 = m["id_movil"] in vmd_r04
        if not operativa(m):
            motivo = "Inactiva o fuera de servicio (R05)"
        elif m["viaje"] is None:
            motivo = f"Sin tiempo de ruta {m['zona']} → {caso['zona_destino_id']} en la matriz; no se estima"
        elif m["estado_foto"] == "EN_RUTA":
            motivo = "En ruta a otro servicio. El desvío R06 queda para una fase posterior"
        elif m["estado_foto"] in OCUPADAS and not m["liberacion_conocida"]:
            motivo = "Ocupada sin hora de liberación conocida"
        elif vmd_r04 and not r04:
            if respaldo and m["id_movil"] == respaldo["id_movil"]:
                motivo = "Ambulancia preasignada en la pareja R04"
            else:
                motivo = "R04 activa: se envía VMD primero y se preasigna la primera ambulancia disponible"
        elif comp == "solo_estabilizacion" and not r04:
            motivo = "VMD sin capacidad de traslado (R03). Solo estabilización si se cumple R04"
        elif comp == "no_permitida":
            motivo = f"Tipo no permitido para EMI {codigo}"
        else:
            motivo = ""
        m["exclusion"] = motivo
        if motivo:
            continue
        apoyo = respaldo if r04 else None
        partes = [participacion(m, RESPONDIENTE if r04 else (AMBULANCIA if m["tipo"] in AMBULANCIAS else ATENCION))]
        if apoyo:
            partes.append(participacion(apoyo, AMBULANCIA))
        usadas = {p["id_movil"] for p in partes}
        perdidas = sorted(cubiertas - cobertura(caso, flota, usadas))
        plan = dict(m, plan_id=m["id_movil"] + (f"+{apoyo['id_movil']}" if apoyo else ""),
                    rol=partes[0]["rol"], apoyo=dict(apoyo) if apoyo else None, participaciones=partes,
                    cumple=m["llegada"] <= objetivo + EPS, exceso=max(0., m["llegada"] - objetivo),
                    llegada_ambulancia=apoyo["llegada"] if apoyo else (m["llegada"] if m["tipo"] in AMBULANCIAS else None),
                    ventaja_r04=mejor_amb["llegada"] - m["llegada"] if r04 else None,
                    costo_plan=sum(p["costo_ida_cop"] for p in partes), km_plan=sum(p["km"] for p in partes),
                    d03=perdidas, criterio="", regla="", comparacion="",
                    depende_liberacion=[p["id_movil"] for p in partes if p["espera_min"] > EPS])
        no_rec = comp == "no_recomendada" or (comp == "posible_traslado" and not caso["posible_traslado"])
        if no_rec:
            # Decisión de diseño: no entra al ranking; el despachador puede elegirla como excepción con motivo.
            plan["exclusion"] = m["exclusion"] = (
                f"Tipo no recomendado para EMI {codigo}" if comp == "no_recomendada"
                else "TAB en 07 sin indicio de traslado (D06): no recomendada")
            plan["criterio"] = "excepción manual: requiere motivo"
            excepciones.append(plan)
        else:
            opciones.append(plan)
    return dict(flota=flota, opciones=ordenar(opciones, caso), excepciones=sorted(excepciones, key=lambda p: p["plan_id"]),
                segundos=segundos, transcurrido_min=transcurrido, mejor_ambulancia=mejor_amb and dict(mejor_amb),
                mejor_ambulancia_min=mejor_amb["llegada"] if mejor_amb else None, r04=bool(vmd_r04),
                respaldo=respaldo and dict(respaldo))


def f1(x):
    """Redondeo de presentación a una décima con coma decimal."""
    return f"{x:.1f}".replace(".", ",")


def cop(x):
    return f"{x:,.0f}".replace(",", ".") + " COP"


def explicar(opcion, caso):
    """Mensajes deterministas construidos con plantillas."""
    o = opcion
    frases = []
    salida = (f"{o['id_movil']} puede salir desde {o['zona']}" if not o["espera"] else
              f"{o['id_movil']} queda utilizable en {f1(o['espera'])} min y saldría desde {o['zona']} (zona conocida)")
    frases.append(f"{salida}. Llegaría en {f1(o['viaje'])} min de viaje y {f1(o['llegada'])} min desde la solicitud.")
    if o["espera"] > EPS:
        frases.append(f"Depende de liberación: {o['id_movil']} figura {o['estado_foto'].replace('_', ' ').lower()} y se "
                      f"estima libre en {f1(o['espera'])} min según la foto del escenario. Si se demora, la llegada se "
                      "retrasa en la misma medida (D08).")
    if o["apoyo"]:
        a = o["apoyo"]
        frases.append(f"{o['id_movil']} puede llegar {f1(o['ventaja_r04'])} min antes para estabilización. "
                      f"Se propone {a['id_movil']} ({a['tipo']}) como ambulancia de apoyo o traslado.")
        frases.append(f"{a['id_movil']} sale desde {a['zona']} tras {f1(a['espera'])} min de espera y llegaría al minuto "
                      f"{f1(a['llegada'])} desde la solicitud. La liberación proviene de la foto del escenario y puede "
                      f"demorarse (D08).")
    if o["regla"] == "D02" and o["criterio"].startswith("diferencia"):
        frases.append(f"Las unidades del grupo son aptas y su diferencia es inferior a {UMBRAL_D02:g} min. "
                      "La opción elegida tiene menor costo estimado de ida.")
    elif o["criterio"]:
        frases.append(o["criterio"][0].upper() + o["criterio"][1:] + ".")
    if o.get("comparacion"):
        frases.append(o["comparacion"])
    margen = caso["objetivo_min"] - o["llegada"]
    frases.append((f"Margen frente al objetivo de {caso['objetivo_min']:g} min: {f1(margen)} min." if o["cumple"] else
                   f"Excede el objetivo de {caso['objetivo_min']:g} min en {f1(o['exceso'])} min."))
    frases.append(f"Recorrido {f1(o['km_plan'])} km · costo estimado de ida {cop(o['costo_plan'])}.")
    if o["d03"]:
        frases.append(f"Advertencia D03: {len(o['d03'])} zona(s) de demanda alta quedarían sin ambulancia a 20 min "
                      f"o menos ({', '.join(o['d03'][:4])}{'…' if len(o['d03']) > 4 else ''}).")
    if caso["codigo_emi"] == "01" and o["tipo"] == "TAB" and not o["apoyo"]:
        frases.append("D07: en un 01 atendido por TAB es deseable un apoyo VMD si hay una cercana. Es una preferencia, "
                      "distinta de R04, y queda a criterio del despachador.")
    return frases
