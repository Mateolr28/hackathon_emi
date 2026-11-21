let
    // Una fila por móvil elegido. R04 aporta dos filas (VMD + ambulancia) a una sola decisión.
    // Se relaciona con decisiones[solicitud_id] (uno a varios). El costo de decisión vive solo en `decisiones`.
    Origen = Csv.Document(File.Contents(RutaCSV), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Cabeceras = Table.PromoteHeaders(Origen, [PromoteAllScalars=true]),
    Asignadas = Table.SelectRows(Cabeceras, each [estado_decision] = "asignada"),
    ConJson = if List.Contains(Table.ColumnNames(Asignadas), "participaciones_json")
        then Asignadas else Table.AddColumn(Asignadas, "participaciones_json", each ""),
    // Filas v1 sin JSON: se reconstruyen desde las columnas del primer móvil y la ambulancia preasignada.
    Lista = Table.AddColumn(ConJson, "partes", each
        if [participaciones_json] <> null and [participaciones_json] <> "" then Json.Document([participaciones_json])
        else List.RemoveNulls({
            [id_movil=[movil_elegido_id], tipo=[tipo_movil_elegido], rol=[rol_elegido], zona_origen=[zona_actual_elegido],
             espera_min="0", viaje_min=[min_viaje_elegido], llegada_min=[primera_llegada_estimada_min],
             km=[distancia_elegida_km], costo_ida_cop=[costo_viaje_primera_cop]],
            if [ambulancia_preasignada_id] = "" then null else
            [id_movil=[ambulancia_preasignada_id], tipo=null, rol=[rol_ambulancia], zona_origen=[zona_actual_ambulancia],
             espera_min=[espera_liberacion_min], viaje_min=[min_viaje_ambulancia],
             llegada_min=[llegada_ambulancia_estimada_min], km=[km_ambulancia], costo_ida_cop=[costo_viaje_ambulancia_cop]]})),
    Base = Table.SelectColumns(Lista, {"solicitud_id", "partes"}),
    Expandida = Table.ExpandListColumn(Base, "partes"),
    Campos = {"id_movil", "tipo", "rol", "zona_origen", "espera_min", "viaje_min", "llegada_min", "km", "costo_ida_cop"},
    Registros = Table.ExpandRecordColumn(Expandida, "partes", Campos, Campos),
    ComoTexto = Table.TransformColumns(Registros, List.Transform({"espera_min", "viaje_min", "llegada_min", "km", "costo_ida_cop"},
        (c) => {c, each if _ = null or _ = "" then null else Text.From(_, "en-US")})),
    Tipos = Table.TransformColumnTypes(ComoTexto, {{"solicitud_id", type text}, {"id_movil", type text}, {"tipo", type text},
        {"rol", type text}, {"zona_origen", type text}, {"espera_min", type number}, {"viaje_min", type number},
        {"llegada_min", type number}, {"km", type number}, {"costo_ida_cop", type number}}, "en-US")
in
    Tipos
