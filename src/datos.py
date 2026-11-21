"""Carga y valida las tablas derivadas antes de abrir una solicitud."""
from itertools import product
from math import isfinite
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "datos" / "entrada"
TIPOS = {"TAM", "TAB", "VMD"}
CODIGOS = ("01", "02", "07", "03", "06")  # Orden de prioridad R01.
DIAS = {"LUNES_A_VIERNES", "SABADO", "DOMINGO_FESTIVO"}
ESTADOS = {"DISPONIBLE", "RETORNANDO", "EN_RUTA", "EN_ATENCION", "EN_TRASLADO", "FUERA_SERVICIO"}
EVENTOS = {"MOVIL_LIBERADA", "RECLASIFICACION_TELEFONICA", "RECLASIFICACION_EN_SITIO", "CANCELACION", "REASIGNACION"}
COMPATIBILIDADES = {"preferida", "permitida", "solo_estabilizacion", "posible_traslado", "no_permitida", "no_recomendada"}
# Clave primaria y campos requeridos. Los identificadores y los códigos EMI siempre se leen como texto.
ESQUEMA = {
    "zonas": ("id_zona", "municipio comuna demanda_relativa"),
    "flota": ("id_movil", "tipo_movil id_base activo costo_km costo_hora"),
    "escenarios": ("id_escenario", "nombre fecha_hora_inicio tipo_dia"),
    "solicitudes": ("id_solicitud", "id_escenario minuto_llegada id_zona clasificacion_inicial descripcion motivo_consulta posible_traslado"),
    "estado_inicial_moviles": ("id_escenario id_movil", "tipo_movil estado id_zona_actual min_para_liberarse"),
    "eventos": ("", "id_escenario minuto tipo_evento id_solicitud id_movil nueva_clasificacion"),
    "carga": ("id_solicitud id_movil", "servicios_turno periodo_carga"),
    "matriz_tiempos": ("zona_origen zona_destino", "distancia_km tiempo_valle_min"),
    "factor_trafico": ("tipo_dia hora_inicio", "factor"),
    "objetivos_urgencia": ("codigo_emi", "objetivo_min"),
    "reglas_movil_servicio": ("codigo_emi tipo_movil", "compatibilidad"),
    "referencia_despachador": ("id_solicitud orden_movil", "id_escenario minuto_asignacion id_movil rol tiempo_estimado_llegada_min"),
}
# Columnas que admiten vacío: liberación desconocida, carga sin dato y campos opcionales de eventos.
OPCIONALES = {"min_para_liberarse", "servicios_turno", "id_solicitud", "id_movil", "nueva_clasificacion"}


def cargar(base=ENTRADA):
    base = Path(base)
    tablas = {}
    for nombre, (clave, campos) in ESQUEMA.items():
        path = base / f"{nombre}.csv"
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        columnas = (clave + " " + campos).split()
        faltan = set(columnas) - set(df)
        if faltan:
            raise ValueError(f"{path.name}: faltan columnas {sorted(faltan)}")
        for col in columnas:
            if (col not in OPCIONALES or col in clave.split()) and df[col].str.strip().eq("").any():
                raise ValueError(f"{path.name}: valor vacío en {col} (fila {df.index[df[col].str.strip().eq('')][0] + 2})")
        if clave:
            repetidos = df.duplicated(clave.split(), keep=False)
            if repetidos.any():
                raise ValueError(f"{path.name}: clave duplicada {df.loc[repetidos, clave.split()].iloc[0].to_dict()}")
        tablas[nombre] = df

    def dominio(tabla, col, opciones, vacio=False):
        valores = set(tablas[tabla][col]) - ({""} if vacio else set())
        invalidos = valores - set(opciones)
        if invalidos:
            raise ValueError(f"{tabla}.csv: {col} desconocido {sorted(invalidos)}")

    def cubrir(tabla, columnas, esperado):
        esperado = set(esperado)
        actual = set(tablas[tabla][columnas.split()].itertuples(index=False, name=None))
        faltan, sobran = esperado - actual, actual - esperado
        if faltan:
            raise ValueError(f"{tabla}.csv: falta la combinación {columnas} = {min(faltan)}")
        if sobran:
            raise ValueError(f"{tabla}.csv: combinación desconocida {columnas} = {min(sobran)}")

    zonas = tablas["zonas"].id_zona
    flota = tablas["flota"]
    escenarios = tablas["escenarios"]
    solicitudes = tablas["solicitudes"]
    estados = tablas["estado_inicial_moviles"]
    dominio("flota", "tipo_movil", TIPOS)
    dominio("flota", "activo", {"True", "False"})
    dominio("escenarios", "tipo_dia", DIAS)
    dominio("estado_inicial_moviles", "estado", ESTADOS)
    dominio("estado_inicial_moviles", "id_zona_actual", zonas)
    dominio("solicitudes", "id_escenario", escenarios.id_escenario)
    dominio("solicitudes", "id_zona", zonas)
    dominio("solicitudes", "clasificacion_inicial", CODIGOS)
    dominio("solicitudes", "posible_traslado", {"0", "1"})
    dominio("eventos", "id_escenario", escenarios.id_escenario)
    dominio("eventos", "tipo_evento", EVENTOS)
    dominio("eventos", "id_movil", flota.id_movil, vacio=True)
    dominio("eventos", "id_solicitud", solicitudes.id_solicitud, vacio=True)
    dominio("eventos", "nueva_clasificacion", CODIGOS, vacio=True)
    dominio("referencia_despachador", "id_solicitud", solicitudes.id_solicitud)
    dominio("referencia_despachador", "id_movil", flota.id_movil)
    dominio("reglas_movil_servicio", "compatibilidad", COMPATIBILIDADES)
    cubrir("objetivos_urgencia", "codigo_emi", product(CODIGOS))
    cubrir("reglas_movil_servicio", "codigo_emi tipo_movil", product(CODIGOS, TIPOS))
    cubrir("matriz_tiempos", "zona_origen zona_destino", product(zonas, zonas))
    cubrir("factor_trafico", "tipo_dia hora_inicio", product(DIAS, [f"{h:02}:00" for h in range(24)]))
    cubrir("estado_inicial_moviles", "id_escenario id_movil", product(escenarios.id_escenario, flota.id_movil))
    cubrir("carga", "id_solicitud id_movil", product(solicitudes.id_solicitud, flota.id_movil))
    distintos = estados.tipo_movil != estados.id_movil.map(flota.set_index("id_movil").tipo_movil)
    if distintos.any():
        raise ValueError(f"estado_inicial_moviles.csv: tipo incoherente para {estados[distintos].iloc[0].id_movil}")
    for tabla, cols, admite_cero in [
        ("flota", "costo_km costo_hora", False), ("factor_trafico", "factor", False),
        ("matriz_tiempos", "distancia_km tiempo_valle_min", False), ("objetivos_urgencia", "objetivo_min", False),
        ("carga", "servicios_turno", True), ("estado_inicial_moviles", "min_para_liberarse", True),
        ("solicitudes", "minuto_llegada", True), ("eventos", "minuto", True),
        ("referencia_despachador", "minuto_asignacion tiempo_estimado_llegada_min", True),
    ]:
        for col in cols.split():
            df = tablas[tabla]
            vacio = df[col].eq("") if col in OPCIONALES else pd.Series(False, index=df.index)
            numeros = pd.to_numeric(df[col], errors="coerce")
            invalidos = ~numeros.map(lambda x: isfinite(x) if x == x else False) | (numeros < 0 if admite_cero else numeros <= 0)
            if col == "servicios_turno":
                invalidos |= numeros.mod(1).ne(0)
            invalidos &= ~vacio
            if col == "min_para_liberarse":
                # Solo una unidad fuera de servicio puede carecer de hora de liberación en la foto.
                sin_hora = vacio & ~df.estado.eq("FUERA_SERVICIO")
                if sin_hora.any():
                    fila = df[sin_hora].iloc[0]
                    raise ValueError(f"{tabla}.csv: {fila.id_movil} en {fila.id_escenario} no tiene min_para_liberarse")
            if invalidos.any():
                raise ValueError(f"{tabla}.csv: {col} inválido en fila {df.index[invalidos][0] + 2}")
            df[col] = numeros
    for fecha in escenarios.fecha_hora_inicio:
        try:
            pd.Timestamp(fecha)
        except ValueError as error:
            raise ValueError(f"escenarios.csv: fecha inválida {fecha}") from error
    return tablas
