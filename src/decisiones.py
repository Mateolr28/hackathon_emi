"""Confirmación, escritura atómica e idempotencia por identificador de decisión."""
import csv
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import Lock

from .datos import RAIZ
from .recomendacion import AMBULANCIA, AMBULANCIAS, evaluar, franja

REGISTRO = RAIZ / "datos" / "decisiones.csv"
INICIALES = RAIZ / "datos" / "demo" / "decisiones_iniciales.csv"
TARIFA_DESPACHADOR = 300.0  # COP por minuto. Supuesto del equipo, registrado aparte del costo de desplazamiento.
MOTIVOS = ("prefiere_menor_tiempo", "prefiere_menor_costo", "prefiere_menor_carga", "preserva_cobertura",
           "criterio_clinico", "revision_manual")
MOTIVOS_PENDIENTE = ("espera_liberacion", "consulta_coordinador", "datos_incompletos", "prioriza_otro_servicio",
                     "revision_manual")
MUTEX = Lock()

# Esquema v1 (se conserva en el mismo orden) + columnas v2 al final. Las filas v1 se leen con campos v2 vacíos.
CAMPOS_V1 = (
    "solicitud_id escenario_id solicitud_fuente modalidad origen_registro fecha_hora_decision fecha_solicitud_escenario "
    "tipo_servicio codigo_emi zona_destino_id franja tipo_dia objetivo_min previo_despacho_min cantidad_elegibles "
    "movil_recomendado_id min_viaje_recomendado costo_viaje_recomendado_cop ambulancia_recomendada_id estado_decision "
    "movil_elegido_id tipo_movil_elegido rol_elegido zona_actual_elegido posicion_elegida motivo_decision "
    "servicios_turno_elegido cumple_objetivo segundos_decision cumple_r02 min_viaje_elegido factor_trafico "
    "distancia_elegida_km primera_llegada_estimada_min exceso_min tarifa_despachador_min_cop tarifa_movil_km_cop "
    "tarifa_movil_hora_cop costo_decision_cop costo_viaje_primera_cop ambulancia_preasignada_id rol_ambulancia "
    "zona_actual_ambulancia espera_liberacion_min min_viaje_ambulancia km_ambulancia factor_ambulancia "
    "tarifa_ambulancia_km_cop tarifa_ambulancia_hora_cop llegada_ambulancia_estimada_min costo_viaje_ambulancia_cop "
    "costo_viaje_elegido_cop costo_total_estimado_cop vista_json").split()
CAMPOS_V2 = (
    "version_esquema codigo_emi_inicial minuto_solicitud_escenario fuente_previo_despacho transcurrido_al_confirmar_min "
    "plan_recomendado_id plan_elegido_id es_excepcion motivo_detalle espera_elegido_min llegada_mostrada_min "
    "costo_mostrado_cop cantidad_moviles km_total_elegido advertencia_d03 referencia_movil_ids "
    "referencia_primera_llegada_min referencia_costo_ida_cop coincide_referencia participaciones_json").split()
CAMPOS = CAMPOS_V1 + CAMPOS_V2


def redondear(valor, campo=""):
    """C-04: COP a 2 decimales; minutos, km, factores y tarifas a 4. Recorre listas y diccionarios (JSON)."""
    if isinstance(valor, dict):
        return {k: redondear(v, k) for k, v in valor.items()}
    if isinstance(valor, list):
        return [redondear(v, campo) for v in valor]
    if isinstance(valor, float):
        return round(valor, 2 if campo.endswith("_cop") or campo.startswith("costo") else 4)
    return valor


def para_csv(fila):
    """Fila lista para escribir: mismos campos con los decimales redondeados."""
    return {k: redondear(v, k) for k, v in fila.items()}


def buscar_plan(planes, plan):
    """Acepta el identificador del plan (MOV-016+MOV-013) o el del primer móvil."""
    return next((p for p in planes if p["plan_id"] == plan), None) or next(
        (p for p in planes if p["id_movil"] == plan), None)


def confirmar(caso, vista, solicitud_id, modalidad, plan, motivo, segundos, fecha=None, origen="sesion",
              detalle="", referencia=()):
    """Construye la fila. `vista` es lo que vio el usuario; se recalcula una sola vez con la duración final."""
    actual = evaluar(caso, segundos)
    mostradas, excepciones = vista["opciones"], vista.get("excepciones", [])
    previa = (buscar_plan(mostradas, plan) or buscar_plan(excepciones, plan)) if plan else None
    elegida = (buscar_plan(actual["opciones"], plan) or buscar_plan(actual["excepciones"], plan)) if plan else None
    if plan and not previa:
        raise ValueError(f"{plan} no figura entre las alternativas mostradas.")
    if plan and (not elegida or previa["plan_id"] != elegida["plan_id"] or previa["rol"] != elegida["rol"]):
        raise ValueError("Cambió la disponibilidad o la combinación R04. Revisa las opciones actualizadas y confirma.")
    asistida = modalidad == "asistida"
    rec = mostradas[0] if asistida and mostradas else {}
    excepcion = bool(plan) and any(p is previa for p in excepciones)
    detalle = (detalle or "").strip()
    if plan and rec and previa["plan_id"] == rec["plan_id"]:
        motivo = "confirma_recomendacion"
    elif not plan and not actual["opciones"]:
        motivo = motivo if motivo in MOTIVOS_PENDIENTE else "sin_elegibles"
    elif not plan and motivo not in MOTIVOS_PENDIENTE:
        raise ValueError("Selecciona el motivo para dejar el caso pendiente.")
    elif plan and motivo not in MOTIVOS:
        raise ValueError("Selecciona un motivo para la decisión.")
    if excepcion and not detalle:
        raise ValueError("Una excepción con tipo no recomendado requiere describir el motivo.")
    estado = "asignada" if plan else ("pendiente" if actual["opciones"] else "sin_asignar")
    pos = mostradas.index(previa) + 1 if plan and asistida and not excepcion else None
    costo_decision = segundos / 60 * TARIFA_DESPACHADOR
    x = elegida or {}
    a = x.get("apoyo") or {}
    partes = x.get("participaciones", [])
    dia, hora = franja(caso, caso["previo_min"] + segundos / 60)

    def plan_resumen(p, criterio=True):
        return dict(plan_id=p["plan_id"], rol=p["rol"], llegada=p["llegada"], costo_plan=p["costo_plan"],
                    criterio=p["criterio"] if criterio else None)
    resumen = {"segundos_al_mostrar": vista["segundos"], "transcurrido_al_mostrar_min": vista["transcurrido_min"],
               "flota": [{k: m[k] for k in ("id_movil", "tipo", "zona", "estado", "compatibilidad", "espera", "viaje",
                                            "llegada", "km", "costo", "carga", "exclusion")} for m in vista["flota"]],
               "planes": [plan_resumen(p, asistida) for p in
                          (mostradas if asistida else sorted(mostradas, key=lambda p: p["plan_id"]))],
               "excepciones": [p["plan_id"] for p in excepciones]}
    tiene_amb = bool(a) or x.get("tipo") in AMBULANCIAS
    # Referencia del escenario recalculada en el mismo instante. Solo se guarda; la interfaz la muestra tras confirmar.
    referencia = list(referencia)
    por_id = {m["id_movil"]: m for m in actual["flota"]}
    ref = [por_id[r] for r in referencia if r in por_id]
    ref_ok = len(ref) == len(referencia) and all(m["costo"] is not None for m in ref)
    elegidos = [p["id_movil"] for p in partes]
    return dict(
        solicitud_id=solicitud_id, escenario_id=caso["escenario_id"], solicitud_fuente=caso["solicitud_fuente"],
        modalidad=modalidad, origen_registro=origen, fecha_hora_decision=fecha or datetime.now().astimezone().isoformat(),
        fecha_solicitud_escenario=caso["fecha_solicitud"].isoformat(), tipo_servicio=caso["tipo_servicio"],
        codigo_emi=caso["codigo_emi"], zona_destino_id=caso["zona_destino_id"], franja=hora, tipo_dia=dia,
        objetivo_min=caso["objetivo_min"], previo_despacho_min=caso["previo_min"], cantidad_elegibles=len(mostradas),
        movil_recomendado_id=rec.get("id_movil"), min_viaje_recomendado=rec.get("viaje"),
        costo_viaje_recomendado_cop=rec.get("costo_plan"),
        ambulancia_recomendada_id=rec["apoyo"]["id_movil"] if rec.get("apoyo") else "",
        estado_decision=estado, movil_elegido_id=x.get("id_movil"), tipo_movil_elegido=x.get("tipo"),
        rol_elegido=x.get("rol"), zona_actual_elegido=x.get("zona"), posicion_elegida=pos, motivo_decision=motivo,
        servicios_turno_elegido=x.get("carga"), cumple_objetivo=int(x["cumple"]) if x else None,
        segundos_decision=segundos,
        cumple_r02=int(segundos <= 120) if plan and caso["codigo_emi"] in {"01", "02"} else None,
        min_viaje_elegido=x.get("viaje"), factor_trafico=x.get("factor"), distancia_elegida_km=x.get("km"),
        primera_llegada_estimada_min=x.get("llegada"), exceso_min=x.get("exceso"),
        tarifa_despachador_min_cop=TARIFA_DESPACHADOR, tarifa_movil_km_cop=x.get("tarifa_km"),
        tarifa_movil_hora_cop=x.get("tarifa_hora"), costo_decision_cop=costo_decision,
        costo_viaje_primera_cop=x.get("costo"), ambulancia_preasignada_id=a.get("id_movil"),
        rol_ambulancia=AMBULANCIA if a else None, zona_actual_ambulancia=a.get("zona"),
        espera_liberacion_min=a.get("espera"), min_viaje_ambulancia=a.get("viaje"), km_ambulancia=a.get("km"),
        factor_ambulancia=a.get("factor"), tarifa_ambulancia_km_cop=a.get("tarifa_km"),
        tarifa_ambulancia_hora_cop=a.get("tarifa_hora"),
        llegada_ambulancia_estimada_min=x.get("llegada_ambulancia") if tiene_amb else None,
        costo_viaje_ambulancia_cop=a.get("costo"), costo_viaje_elegido_cop=x.get("costo_plan"),
        costo_total_estimado_cop=costo_decision + x["costo_plan"] if x else None,
        vista_json=json.dumps(redondear(resumen), ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        version_esquema=2, codigo_emi_inicial=caso["codigo_emi_inicial"], minuto_solicitud_escenario=caso["minuto_llegada"],
        fuente_previo_despacho=caso["fuente_previo"], transcurrido_al_confirmar_min=caso["previo_min"] + segundos / 60,
        plan_recomendado_id=rec.get("plan_id"), plan_elegido_id=x.get("plan_id"), es_excepcion=int(excepcion),
        motivo_detalle=detalle, espera_elegido_min=x.get("espera"), llegada_mostrada_min=previa["llegada"] if previa else None,
        costo_mostrado_cop=previa["costo_plan"] if previa else None, cantidad_moviles=len(partes),
        km_total_elegido=x.get("km_plan"), advertencia_d03=";".join(x.get("d03", [])), referencia_movil_ids="+".join(referencia),
        referencia_primera_llegada_min=min(m["llegada"] for m in ref) if ref_ok and ref else None,
        referencia_costo_ida_cop=sum(m["costo"] for m in ref) if ref_ok and ref else None,
        coincide_referencia=int(elegidos == referencia) if referencia else None,
        participaciones_json=json.dumps(redondear(partes), ensure_ascii=False, separators=(",", ":"), allow_nan=False))


@contextmanager
def bloqueo(ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with MUTEX, ruta.with_suffix(".lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def leer(ruta=REGISTRO):
    """Lee el registro con el esquema vigente. Las filas v1 reciben las columnas v2 vacías."""
    if not Path(ruta).exists():
        return []
    with Path(ruta).open(encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        extra = set(lector.fieldnames or ()) - set(CAMPOS)
        if extra:
            raise ValueError(f"Revisa los encabezados de {Path(ruta).name}: columnas desconocidas {sorted(extra)}.")
        return [{c: row.get(c, "") or "" for c in CAMPOS} for row in lector]


def guardar(fila, ruta=REGISTRO):
    """Agrega la fila de forma atómica. Devuelve False si el identificador ya estaba (doble confirmación)."""
    if list(fila) != CAMPOS:
        raise ValueError("La fila no sigue el esquema del registro.")
    with bloqueo(ruta):
        anteriores = leer(ruta)
        if any(r["solicitud_id"] == fila["solicitud_id"] for r in anteriores):
            return False
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8-sig", dir=ruta.parent,
                                             delete=False) as out:
                tmp = Path(out.name)
                writer = csv.DictWriter(out, fieldnames=CAMPOS)
                writer.writeheader()
                writer.writerows(anteriores)
                writer.writerow(para_csv(fila))
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, ruta)
            return True
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)


def restaurar(ruta=REGISTRO, iniciales=INICIALES):
    """Restauración explícita: respalda el registro actual y repone la precarga de 30 decisiones."""
    with bloqueo(ruta):
        copia = ruta.with_name(f"decisiones_antes_{datetime.now():%Y%m%d_%H%M%S_%f}.csv")
        if ruta.exists():
            shutil.copy2(ruta, copia)
        with tempfile.NamedTemporaryFile(dir=ruta.parent, delete=False) as f:
            tmp = Path(f.name)
        try:
            shutil.copyfile(iniciales, tmp)
            os.replace(tmp, ruta)
        finally:
            tmp.unlink(missing_ok=True)
        return copia if copia.exists() else None
