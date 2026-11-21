let
    // RutaLineaBase: parámetro de texto con la ruta absoluta de EMI_EnRuta\datos\entrada\linea_base_kpi.csv.
    // Línea base histórica ficticia (archivo 01). No se relaciona con decisiones: se rotula por separado.
    Origen = Csv.Document(File.Contents(RutaLineaBase), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Cabeceras = Table.PromoteHeaders(Origen, [PromoteAllScalars=true]),
    Tipos = Table.TransformColumnTypes(Cabeceras, {{"vista", type text}, {"codigo_emi", type text},
        {"objetivo_min", type number}, {"servicios", Int64.Type}, {"denominador", Int64.Type},
        {"excluidos_anomalia", Int64.Type}, {"p90_min", type number}, {"mediana_min", type number},
        {"promedio_min", type number}, {"pct_cumple", type number}, {"costo_completo_medio_cop", type number},
        {"kpi04_espera_asignacion_mediana_min", type number}, {"archivo_p90_min", type number},
        {"archivo_pct_cumple", type number}, {"definicion", type text}}, "en-US")
in
    Tipos
