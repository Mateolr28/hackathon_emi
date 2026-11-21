"""Aplicación local EMI EnRuta. Demo académica con datos ficticios."""
import time
from threading import Lock
from uuid import uuid4

import pandas as pd
import streamlit as st

from src import decisiones as registro
from src.datos import ENTRADA, cargar
from src.decisiones import MOTIVOS, MOTIVOS_PENDIENTE, confirmar
from src.recomendacion import (AMBULANCIAS, NOMBRES_COMP, UMBRAL_R04, cop, evaluar, explicar, f1, preparar)

ROTULO = "Demo académica con datos ficticios"
PENDIENTE = "__pendiente__"
CADUCIDAD_H = 8  # C-03: un caso sin uso durante un turno de 8 h se libera de la memoria del servidor.

st.set_page_config(page_title="EMI EnRuta · " + ROTULO, layout="wide", initial_sidebar_state="collapsed")
st.title("EMI EnRuta")
st.warning(f"**{ROTULO}.** Los resultados representan el ejercicio y no la operación real. "
           "La decisión final corresponde al despachador.", icon="🎓")


@st.cache_resource
def casos_abiertos():
    # El enlace (?caso=…) permite recuperar el mismo cronómetro al recargar la pestaña.
    return {}


@st.cache_resource
def _cerrojo():
    return Lock()


def abrir_caso(identificador):
    """Devuelve el caso del enlace y libera los que llevan más de CADUCIDAD_H horas sin uso (C-03).

    Un caso confirmado cuyo guardado falló no se libera: conserva la decisión para reintentar.
    """
    ahora = time.monotonic()
    with _cerrojo():
        casos = casos_abiertos()
        for clave, caso in list(casos.items()):
            sin_guardar = caso["fila"] is not None and not caso["guardada"]
            if ahora - caso.get("visto", ahora) > CADUCIDAD_H * 3600 and not sin_guardar:
                del casos[clave]
        activo = casos.get(identificador)
        if activo is not None:
            activo["visto"] = ahora
        return activo


@st.cache_data
def _datos(firma):
    return cargar()


def datos():
    # C-02: la caché se invalida cuando cambia cualquier CSV de entrada (por ejemplo, tras preparar_datos.py).
    return _datos(tuple(sorted((f.name, f.stat().st_mtime_ns) for f in ENTRADA.glob("*.csv"))))


def estado_en_instante(m):
    """C-01: estado en el instante del caso, no el de la foto inicial."""
    if m["estado_foto"] in {"EN_ATENCION", "EN_TRASLADO"} and m["liberacion_conocida"]:
        if m["espera"] > 0:
            return f"{m['estado_foto']} · se libera en {f1(m['espera'])} min"
        return f"DISPONIBLE · liberada (foto: {m['estado_foto']})"
    return m["estado"]


def nuevo():
    with _cerrojo():
        casos_abiertos().pop(st.query_params.get("caso", ""), None)
    st.query_params.clear()
    st.session_state.pop("activo", None)
    st.rerun()


def etiqueta(motivo):
    return motivo.replace("_", " ").capitalize()


def configuracion():
    try:
        tablas = datos()
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(f"Revisa los datos de entrada. {exc}")
        st.stop()
    st.header("Iniciar caso")
    escenarios = tablas["escenarios"].set_index("id_escenario")
    esc = st.selectbox("Escenario", escenarios.index, format_func=lambda i: f"{i} · {escenarios.at[i, 'nombre']}")
    st.caption(escenarios.at[esc, "descripcion"])
    casos = tablas["solicitudes"].query("id_escenario == @esc").set_index("id_solicitud")
    a, b = st.columns([2, 1])
    solicitud = a.selectbox("Solicitud ya clasificada", casos.index, format_func=lambda i:
                            f"{i} · min {casos.at[i, 'minuto_llegada']:g} · EMI {casos.at[i, 'clasificacion_inicial']} · "
                            f"{casos.at[i, 'comuna']}")
    modo = b.radio("Modalidad", ["asistida", "manual"], horizontal=True,
                   help="Manual: flota y restricciones sin ranking. Asistida: añade ranking y mensajes predefinidos.")
    st.write(f"{casos.at[solicitud, 'motivo_consulta']} · {casos.at[solicitud, 'discriminador']}")
    supuesto = st.checkbox("Usar el supuesto de demostración: paso inmediato a despacho (0 min previos)", value=True,
                           help="El escenario no entrega la hora de paso a despacho. El supuesto queda registrado.")
    previo = None
    if not supuesto:
        previo = st.number_input("Minutos desde la solicitud hasta el paso a despacho", min_value=0., value=0., step=0.5)
    if st.button("Iniciar caso", type="primary"):
        caso = preparar(tablas, solicitud, previo)
        identificador = str(uuid4())
        with _cerrojo():
            casos_abiertos()[identificador] = dict(id=identificador, caso=caso, inicio=None, modalidad=modo,
                                                   vista=evaluar(caso), fila=None, guardada=False,
                                                   visto=time.monotonic())
        st.session_state.activo = casos_abiertos()[identificador]
        st.query_params["caso"] = identificador
        st.rerun()


def tabla_flota(vista, asistida):
    planes = {p["id_movil"]: p for p in vista["opciones"] + vista["excepciones"]}
    filas = []
    for m in vista["flota"]:
        p = planes.get(m["id_movil"], {})
        apoyo = p.get("apoyo") or {}
        filas.append({
            "Móvil": m["id_movil"], "Tipo": m["tipo"], "Compatibilidad": NOMBRES_COMP[m["compatibilidad"]],
            "Zona actual": m["zona"], "Estado en el instante": estado_en_instante(m),
            "Uso en el caso": m["exclusion"] or ("Alternativa · " + p["rol"] if p else ""),
            "Ambulancia preasignada": apoyo.get("id_movil"),
            "Espera hasta salida (min)": round(m["espera"], 1),
            "Viaje (min)": round(m["viaje"], 1) if m["viaje"] is not None else None,
            "Llegada desde solicitud (min)": round(m["llegada"], 1) if m["llegada"] is not None else None,
            "Km": m["km"], "Factor horario": m["factor"],
            "Costo de ida (COP)": round(m["costo"]) if m["costo"] is not None else None,
            "Carga del turno": str(m["carga"]) if m["carga"] is not None else "sin dato"})
    df = pd.DataFrame(filas)
    if not asistida:
        df = df.sort_values("Móvil")
    st.dataframe(df, hide_index=True)
    periodo = next((m["periodo_carga"] for m in vista["flota"] if m["periodo_carga"]), "")
    st.caption(f"Carga del turno = participaciones completadas y liberadas en el histórico ficticio ({periodo}). "
               "«sin dato» significa que la móvil no aparece en el histórico; no equivale a cero.")


def respuestas(caso, vista, consulta):
    if consulta.startswith("¿Por qué"):
        descartadas = [m for m in vista["flota"] if m["exclusion"] and m["viaje"] is not None
                       and m["estado_foto"] != "FUERA_SERVICIO"]
        if descartadas:
            m = min(descartadas, key=lambda u: (u["viaje"], u["id_movil"]))
            st.write(f"{m['id_movil']} ({m['tipo']}) está a {f1(m['viaje'])} min de viaje estimado. {m['exclusion']}.")
        else:
            st.write("No hay unidades cercanas descartadas por compatibilidad.")
    elif consulta.startswith("¿Cómo"):
        st.write("Viaje = minutos valle desde la zona actual × factor del tipo de día y la hora de salida (una sola vez). "
                 "Respuesta = minutos ya transcurridos desde la solicitud + espera hasta quedar utilizable + viaje. "
                 "Costo de ida por móvil = km × tarifa por km + (viaje / 60) × tarifa por hora.")
    elif consulta.startswith("¿Aplica"):
        mejor = vista["mejor_ambulancia"]
        if caso["codigo_emi"] not in {"01", "02"}:
            st.write("R04 solo aplica a los códigos 01 y 02.")
        elif mejor is None:
            st.write("No hay ambulancia con llegada estimable: no se puede formar la pareja R04.")
        else:
            st.write(f"La primera ambulancia viable es {mejor['id_movil']} con llegada a {f1(mejor['llegada'])} min "
                     f"(objetivo {caso['objetivo_min']:g}). R04 exige que ninguna ambulancia llegue a tiempo y que una "
                     f"VMD llegue al menos {UMBRAL_R04:g} min antes. Resultado: {'se cumple' if vista['r04'] else 'no se cumple'}.")
    else:
        st.write(", ".join(p["plan_id"] for p in vista["opciones"]) or "Sin alternativas elegibles.")


def despachar(activo):
    caso = activo["caso"]
    if activo["inicio"] is None:
        # El cronómetro empieza cuando el caso queda visible y listo para decidir.
        activo["inicio"] = time.monotonic()
    st.header(f"{caso['solicitud_fuente']} · {caso['tipo_servicio']}")
    a, b, c, d = st.columns(4)
    a.metric("Código EMI vigente", caso["codigo_emi"])
    b.metric("Objetivo de primera llegada", f"{caso['objetivo_min']:g} min")
    c.metric("Zona de destino", caso["zona_destino_id"])
    d.metric("Minutos previos a despacho", f"{caso['previo_min']:g}")
    st.write(f"{caso['motivo']} · {caso['discriminador']} · {caso['comuna']} · Solicitud del "
             f"{caso['fecha_solicitud']:%d/%m/%Y a las %H:%M} · Modalidad **{activo['modalidad']}**.")
    if caso["fuente_previo"].startswith("supuesto"):
        st.caption("Supuesto de demostración: paso inmediato a despacho. El escenario no permite derivar el tiempo previo.")
    if caso["reclasificaciones"]:
        st.info(f"R07 · Se aplica la clasificación vigente ({caso['codigo_emi']}, antes {caso['codigo_emi_inicial']}): "
                + "; ".join(caso["reclasificaciones"]))
    if caso["codigo_emi"] in {"01", "02"}:
        st.caption("R02 · Meta: primera asignación dentro de 2 min desde el paso a despacho.")
    if caso["codigo_emi"] == "06":
        st.caption("06 · El caso llegó a despacho porque la orientación telefónica indicó visita: corresponde VMD.")
    if st.button("Actualizar estimaciones"):
        activo["vista"] = evaluar(caso, time.monotonic() - activo["inicio"])
    vista = activo["vista"]
    opciones, excepciones = vista["opciones"], vista["excepciones"]
    asistida = activo["modalidad"] == "asistida"
    st.caption(f"Estimaciones a los {vista['segundos']:.0f} s de decisión ({f1(vista['transcurrido_min'])} min "
               "transcurridos desde la solicitud). Una unidad libre sale de inmediato. Al confirmar se incorpora una "
               "sola vez el tiempo de decisión.")
    if asistida:
        st.subheader("Alternativas de despacho")
        if not opciones:
            st.write("No hay alternativas elegibles.")
        elif all(not p["cumple"] for p in opciones):
            st.write("Todas las alternativas exceden el objetivo. Se muestra el exceso de cada una.")
        for i, opcion in enumerate(opciones[:3], 1):
            with st.chat_message("assistant"):
                titulo = (f"**Opción {i} · {opcion['plan_id']}**" + (" · pareja R04" if opcion["apoyo"] else "")
                          + (" · ⏳ depende de liberación" if opcion["espera"] > 0 else ""))
                st.markdown(titulo + "  \n" + " ".join(explicar(opcion, caso)))
        consulta = st.selectbox("Consultar al asistente", [
            "¿Por qué se descarta una unidad cercana?", "¿Cómo se estiman el tiempo y el costo?",
            "¿Aplica R04 (VMD primero)?", "¿Qué alternativas son elegibles?"])
        respuestas(caso, vista, consulta)
    if not opciones:
        st.warning("Ninguna unidad reúne disponibilidad y capacidad para el rol. Puedes registrar el caso sin asignar.")
    with st.expander("Flota, compatibilidad y estimaciones", expanded=not asistida):
        tabla_flota(vista, asistida)

    st.subheader("Decisión del despachador")
    ids = [p["plan_id"] for p in opciones]
    if not asistida:
        ids.sort()
    exc = [p["plan_id"] for p in excepciones]
    nombres = {p["plan_id"]: f"{p['plan_id']} · {p['tipo']} · llegada {f1(p['llegada'])} min · {cop(p['costo_plan'])}"
               + (" · depende de liberación" if p["espera"] > 0 else "") for p in opciones}
    nombres.update({p["plan_id"]: f"{p['plan_id']} · {p['tipo']} · excepción (no recomendada)" for p in excepciones})
    nombres[PENDIENTE] = "Dejar pendiente" if opciones else "Registrar sin asignar"
    clave = "plan_" + activo["id"]
    previa = st.session_state.get(clave)
    if previa is not None and previa not in ids + exc + [PENDIENTE]:
        # C-05: sin esto, Streamlit cambiaría en silencio la elección por otra alternativa.
        st.session_state[clave] = None
        st.warning(f"La alternativa elegida ({previa}) ya no está disponible con las estimaciones actualizadas. "
                   "Elige de nuevo.")
    seleccion = st.selectbox("Alternativa a despachar", ids + exc + [PENDIENTE], key=clave,
                             index=0 if asistida and ids else None, format_func=nombres.get,
                             placeholder="Elige una alternativa o deja el caso pendiente")
    elegida = next((p for p in opciones + excepciones if p["plan_id"] == seleccion), None)
    if elegida and elegida["apoyo"]:
        st.info(f"Se confirmarán ambos roles en una sola decisión. {elegida['id_movil']} estabiliza. "
                f"{elegida['apoyo']['id_movil']} queda preasignada para atención y traslado.")
    if elegida and elegida["d03"]:
        st.warning(f"D03 · Quedarían sin ambulancia a 20 min o menos: {', '.join(elegida['d03'])}.")
    motivo, detalle = "revision_manual", ""
    es_recomendada = asistida and ids and seleccion == ids[0]
    if seleccion == PENDIENTE:
        motivo = st.selectbox("Motivo para dejar el caso pendiente", MOTIVOS_PENDIENTE if opciones else
                              ("sin_elegibles",) + MOTIVOS_PENDIENTE, format_func=etiqueta)
        detalle = st.text_input("Detalle (opcional)")
    elif seleccion and not es_recomendada:
        motivo = st.selectbox("Motivo de la decisión", MOTIVOS, format_func=etiqueta)
        detalle = st.text_input("Detalle del motivo" + (" (obligatorio para una excepción)" if seleccion in exc else ""))

    def detener():
        activo.setdefault("fin", time.monotonic())

    if st.button("Confirmar decisión", type="primary", disabled=seleccion is None, on_click=detener):
        duracion = activo["fin"] - activo["inicio"]
        referencia = list(activo["referencia"].id_movil) if activo.get("referencia") is not None else []
        try:
            activo["fila"] = confirmar(caso, vista, activo["id"], activo["modalidad"],
                                       None if seleccion == PENDIENTE else seleccion, motivo, duracion,
                                       detalle=detalle, referencia=referencia)
        except ValueError as exc:
            activo.pop("fin", None)  # El cronómetro sigue: la decisión no quedó confirmada.
            activo["vista"] = evaluar(caso, duracion)
            activo["aviso"] = str(exc)
            st.rerun()
        activo["intentar"] = True
        st.rerun()


def revisar(activo, intentar=False):
    fila = activo["fila"]
    if not activo["guardada"] and intentar:
        try:
            registro.guardar(fila, registro.REGISTRO)  # Devuelve False si ya existía: no duplica.
            activo["guardada"] = True
        except (OSError, ValueError) as exc:
            st.error(f"No se pudo escribir decisiones.csv. {exc}")
    if not activo["guardada"]:
        st.warning("La decisión está confirmada y el cronómetro se detuvo. Puedes reintentar el guardado: se conserva "
                   "la misma duración y el mismo identificador.")
        if st.button("Reintentar guardado", type="primary"):
            activo["intentar"] = True
            st.rerun()
        return
    guardada = next((r for r in registro.leer(registro.REGISTRO) if r["solicitud_id"] == fila["solicitud_id"]), None)
    st.success(f"Decisión guardada en decisiones.csv · ID {fila['solicitud_id']}")
    st.write(f"Solicitud {fila['solicitud_fuente']} · Estado: {fila['estado_decision'].replace('_', ' ')} · "
             f"Tiempo de decisión: {fila['segundos_decision']:.1f} s · Costo de decisión (supuesto): "
             f"{cop(fila['costo_decision_cop'])}.")
    if fila["movil_elegido_id"]:
        cumple = "cumple" if fila["cumple_objetivo"] else f"excede en {f1(fila['exceso_min'])} min"
        st.write(f"{fila['plan_elegido_id']} · {fila['rol_elegido']} · primera llegada estimada "
                 f"{f1(fila['primera_llegada_estimada_min'])} min desde la solicitud ({cumple} el objetivo de "
                 f"{fila['objetivo_min']:g}) · {f1(fila['km_total_elegido'])} km · costo de ida {cop(fila['costo_viaje_elegido_cop'])}.")
    else:
        st.write(f"Motivo: {etiqueta(fila['motivo_decision'])}. {fila['motivo_detalle']}")
    if fila["ambulancia_preasignada_id"]:
        st.write(f"Ambulancia preasignada para atención y traslado: {fila['ambulancia_preasignada_id']} · llegada "
                 f"estimada {f1(fila['llegada_ambulancia_estimada_min'])} min desde la solicitud.")
    if guardada is None:
        st.error("No se encontró la fila en el CSV. Revisa el archivo antes de continuar.")

    st.subheader("Revisión frente a la referencia del escenario")
    ref = activo.get("referencia")
    if ref is None or ref.empty:
        st.write("El escenario no trae decisión de referencia para esta solicitud.")
    else:
        flota = {m["id_movil"]: m for m in activo["vista"]["flota"]}
        filas = []
        for r in ref.itertuples():
            m = flota.get(r.id_movil, {})
            filas.append({"Orden": r.orden_movil, "Móvil": r.id_movil, "Tipo": r.tipo_movil, "Rol": r.rol,
                          "Minuto de asignación": r.minuto_asignacion, "Zona de origen": r.zona_origen_movil,
                          "Viaje de referencia (min)": r.tiempo_estimado_llegada_min,
                          "Viaje recalculado en este caso (min)": round(m["viaje"], 1) if m.get("viaje") is not None else None,
                          "Costo de ida recalculado (COP)": round(m["costo"]) if m.get("costo") is not None else None,
                          "Justificación": r.justificacion_despachador, "Comentario del coordinador": r.comentario_coordinador})
        st.dataframe(pd.DataFrame(filas), hide_index=True)
        ids_ref = list(ref.id_movil)
        elegidos = [x for x in (fila["movil_elegido_id"], fila["ambulancia_preasignada_id"]) if x]
        if elegidos == ids_ref[:len(elegidos)] and len(elegidos) == len(ids_ref):
            st.write("La decisión del ensayo coincide con la referencia.")
        else:
            st.write(f"El ensayo eligió {' + '.join(elegidos) or 'ninguna unidad'}; la referencia, {' + '.join(ids_ref)}. "
                     "La referencia documenta lo que decidió el despachador ficticio y admite alternativas justificadas; "
                     "el comentario del coordinador ayuda a explicar la diferencia.")
    if st.button("Abrir un nuevo caso"):
        nuevo()


def principal():
    identificador = st.query_params.get("caso")
    activo = abrir_caso(identificador)
    if activo is None:
        if identificador:
            # C-03: enlace caducado o servidor reiniciado. Se avisa y se vuelve al inicio sin error.
            st.query_params.clear()
            st.session_state.pop("activo", None)
            st.warning("Caso no encontrado: el enlace caducó o el servidor se reinició. Inicia uno nuevo. "
                       "Las decisiones ya guardadas siguen en decisiones.csv.")
        configuracion()
        return
    st.session_state.activo = activo
    if "referencia" not in activo:
        ref = datos()["referencia_despachador"]
        # Se carga al abrir, pero solo se muestra tras confirmar para no sesgar el ensayo.
        activo["referencia"] = ref[ref.id_solicitud == activo["caso"]["solicitud_fuente"]].sort_values("orden_movil")
    if activo.get("aviso"):
        st.warning(activo.pop("aviso"))
    if activo["fila"] is not None:
        revisar(activo, intentar=activo.pop("intentar", False))
    else:
        despachar(activo)


principal()
