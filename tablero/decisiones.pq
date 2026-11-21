let
    // RutaCSV: parámetro de texto con la ruta absoluta de EMI_EnRuta\datos\decisiones.csv.
    // Una fila = una decisión (un intento confirmado). Las filas del esquema v1 traen vacías las columnas v2.
    Origen = Csv.Document(File.Contents(RutaCSV), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Cabeceras = Table.PromoteHeaders(Origen, [PromoteAllScalars=true]),
    Vacias = Table.ReplaceValue(Cabeceras, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabeceras)),
    Enteros = {"cantidad_elegibles","posicion_elegida","servicios_turno_elegido","cumple_objetivo","cumple_r02",
        "version_esquema","es_excepcion","cantidad_moviles","coincide_referencia"},
    Decimales = {"objetivo_min","previo_despacho_min","min_viaje_recomendado","costo_viaje_recomendado_cop",
        "segundos_decision","min_viaje_elegido","factor_trafico","distancia_elegida_km","primera_llegada_estimada_min",
        "exceso_min","tarifa_despachador_min_cop","tarifa_movil_km_cop","tarifa_movil_hora_cop","costo_decision_cop",
        "costo_viaje_primera_cop","espera_liberacion_min","min_viaje_ambulancia","km_ambulancia","factor_ambulancia",
        "tarifa_ambulancia_km_cop","tarifa_ambulancia_hora_cop","llegada_ambulancia_estimada_min",
        "costo_viaje_ambulancia_cop","costo_viaje_elegido_cop","costo_total_estimado_cop",
        "minuto_solicitud_escenario","transcurrido_al_confirmar_min","espera_elegido_min","llegada_mostrada_min",
        "costo_mostrado_cop","km_total_elegido","referencia_primera_llegada_min","referencia_costo_ida_cop"},
    // fecha_hora_decision conserva su desfase horario como texto ISO; la fecha del escenario es datetime.
    Fechas = {{"fecha_solicitud_escenario", type datetime}},
    // Solo se tipan las columnas presentes, para leer también un registro v1.
    Presentes = Table.ColumnNames(Vacias),
    EnterosP = List.Intersect({Enteros, Presentes}),
    DecimalesP = List.Intersect({Decimales, Presentes}),
    Texto = List.Difference(Presentes, List.Combine({EnterosP, DecimalesP, List.Transform(Fechas, each _{0})})),
    Tipos = List.Combine({List.Transform(Texto, each {_, type text}), List.Transform(EnterosP, each {_, Int64.Type}),
        List.Transform(DecimalesP, each {_, type number}), Fechas}),
    // Los CSV usan punto decimal: se convierte con cultura en-US. Código EMI e identificadores quedan como texto.
    Datos = Table.TransformColumnTypes(Vacias, Tipos, "en-US"),
    // Las participaciones se expanden en otra consulta: aquí no se suman móviles para no duplicar costos.
    Resultado = Table.RemoveColumns(Datos, List.Intersect({{"vista_json", "participaciones_json"}, Presentes}))
in
    Resultado
