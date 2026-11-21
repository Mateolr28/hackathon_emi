"""Pruebas del motor, del registro y de los botones de Streamlit (criterios de la sección 8 del prompt)."""
import csv
import json
import shutil
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.datos import ENTRADA, RAIZ, cargar
from src.decisiones import CAMPOS, CAMPOS_V1, INICIALES, confirmar, guardar, leer, restaurar
from src.recomendacion import evaluar, explicar, f1, preparar


@contextmanager
def carpeta_de_prueba():
    ruta = RAIZ / (".prueba-" + uuid4().hex)
    ruta.mkdir()
    try:
        yield ruta
    finally:
        shutil.rmtree(ruta)


def filas_csv(ruta):
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo))


def plan(vista, plan_id):
    return next(p for p in vista["opciones"] + vista["excepciones"] if p["plan_id"] == plan_id)


def unidad(vista, id_movil):
    return next(m for m in vista["flota"] if m["id_movil"] == id_movil)


class Motor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datos = cargar()

    def caso(self, solicitud="ESC-01-S01", previo=None):
        return preparar(self.datos, solicitud, previo)

    def aislado(self, solicitud, unidades, factor=1):
        """Caso con flota reducida y factor horario fijo para probar umbrales exactos."""
        c = self.caso(solicitud)
        c["factores"] = {k: factor for k in c["factores"]}
        base = {m["id_movil"]: m for m in c["flota"]}
        c["flota"] = [dict(base[origen], id_movil=nuevo, **cambios) for nuevo, origen, cambios in unidades]
        return c

    # --- Escenarios de referencia ---------------------------------------------------------------------------
    def test_esc01_vmd_para_consulta_03(self):
        c = self.caso()
        v = evaluar(c)
        self.assertEqual(c["codigo_emi"], "03")
        self.assertTrue(all(p["tipo"] == "VMD" for p in v["opciones"]))
        self.assertEqual(v["opciones"][0]["compatibilidad"], "preferida")
        self.assertIn("no permitido", unidad(v, "MOV-001")["exclusion"])           # TAM no permitida en 03
        self.assertIn("MOV-002", [p["plan_id"] for p in v["excepciones"]])          # TAB no recomendada
        self.assertAlmostEqual(plan(v, "MOV-011")["viaje"], 12.5)                   # Viaje de referencia
        self.assertEqual([p["plan_id"] for p in v["opciones"][:3]], ["MOV-005", "MOV-003", "MOV-011"])
        self.assertEqual(v["opciones"][0]["regla"], "D02")
        texto = " ".join(explicar(v["opciones"][0], c))
        self.assertIn("MOV-005 puede salir desde Z-MED-10-02", texto)
        self.assertIn("diferencia es inferior a 3 min", texto)

    def test_esc02_hora_pico_zona_actual(self):
        c = self.caso("ESC-02-S01")
        v = evaluar(c)
        p = v["opciones"][0]
        self.assertEqual(p["plan_id"], "MOV-025")
        self.assertEqual(p["zona"], "Z-MED-07-01")
        self.assertEqual(p["factor"], 1.6)
        self.assertAlmostEqual(p["viaje"], 15.3 * 1.6)
        self.assertEqual(f1(p["viaje"]), "24,5")
        retornando = unidad(v, "MOV-015")
        self.assertEqual(retornando["estado"], "RETORNANDO")
        self.assertEqual(retornando["zona"], "Z-MED-05-01")                         # Zona actual, no la base
        self.assertIn("R03", retornando["exclusion"])
        self.assertLess(v["mejor_ambulancia_min"] - retornando["llegada"], 12)
        self.assertFalse(v["r04"])

    def test_esc04_r04_una_decision_dos_roles(self):
        c = self.caso("ESC-04-S01")
        v = evaluar(c)
        self.assertTrue(v["r04"])
        p = v["opciones"][0]
        self.assertEqual(p["plan_id"], "MOV-016+MOV-013")
        self.assertGreaterEqual(p["ventaja_r04"], 12)
        f = confirmar(c, v, "doble", "asistida", "MOV-016+MOV-013", "", 24)
        self.assertEqual((f["rol_elegido"], f["ambulancia_preasignada_id"], f["rol_ambulancia"]),
                         ("PRIMER_RESPONDIENTE_ESTABILIZACION", "MOV-013", "ATENCION_Y_TRASLADO"))
        self.assertAlmostEqual(f["primera_llegada_estimada_min"], 7.22)
        self.assertAlmostEqual(f["espera_liberacion_min"], 21.6)
        self.assertAlmostEqual(f["llegada_ambulancia_estimada_min"], 34.54)
        partes = json.loads(f["participaciones_json"])
        self.assertEqual([x["id_movil"] for x in partes], ["MOV-016", "MOV-013"])
        self.assertAlmostEqual(sum(x["costo_ida_cop"] for x in partes), f["costo_viaje_elegido_cop"], delta=0.02)
        self.assertAlmostEqual(f["costo_viaje_elegido_cop"], 61890.733333333)
        self.assertAlmostEqual(f["costo_total_estimado_cop"], f["costo_viaje_elegido_cop"] + 120)
        self.assertEqual(f["cantidad_moviles"], 2)
        # Si la ambulancia se libera antes de confirmar, la pareja deja de ser válida y se pide revisar.
        with self.assertRaisesRegex(ValueError, "R04"):
            confirmar(c, v, "tardia", "asistida", "MOV-016+MOV-013", "", 22 * 60)

    # --- Umbrales exactos ------------------------------------------------------------------------------------
    def test_umbral_d02_exactamente_3_no_activa(self):
        caro = dict(tiempo_valle_min=10, costo_km=9000)
        barato = dict(costo_km=10)
        c = self.aislado("ESC-01-S01", [("A", "MOV-005", caro), ("B", "MOV-003", dict(barato, tiempo_valle_min=13))])
        self.assertEqual([p["plan_id"] for p in evaluar(c)["opciones"]], ["A", "B"])
        c = self.aislado("ESC-01-S01", [("A", "MOV-005", caro), ("B", "MOV-003", dict(barato, tiempo_valle_min=12.99))])
        orden = evaluar(c)["opciones"]
        self.assertEqual([p["plan_id"] for p in orden], ["B", "A"])
        self.assertEqual(orden[0]["regla"], "D02")

    def test_umbral_r04_exactamente_12_activa(self):
        def r04(vmd, amb):
            c = self.aislado("ESC-04-S01", [("MOV-013", "MOV-013", dict(estado="DISPONIBLE", tiempo_valle_min=amb)),
                                            ("MOV-016", "MOV-016", dict(tiempo_valle_min=vmd))])
            return evaluar(c)["r04"]
        self.assertTrue(r04(8, 20))      # Ventaja exacta de 12 min y ambulancia fuera del objetivo.
        self.assertFalse(r04(8.01, 20))  # 11,99 min de ventaja.
        self.assertFalse(r04(2, 15))     # La ambulancia llega exactamente en el objetivo: no aplica R04.

    def test_llegada_exacta_en_objetivo_cumple(self):
        c = self.caso(previo=2)
        p = evaluar(c)["opciones"][0]
        c["objetivo_min"] = p["viaje"] + 3
        self.assertTrue(evaluar(c, 60)["opciones"][0]["cumple"])
        self.assertFalse(evaluar(c, 61)["opciones"][0]["cumple"])

    def test_relojes_6_mas_11_son_17(self):
        c = self.aislado("ESC-02-S04", [("MOV-013", "MOV-013", dict(tiempo_valle_min=11))])
        c["previo_min"] = 6.
        self.assertEqual(c["codigo_emi"], "01")
        p = evaluar(c)["opciones"][0]
        self.assertAlmostEqual(p["llegada"], 17)
        self.assertAlmostEqual(p["exceso"], 2)
        self.assertIn("Excede el objetivo de 15 min en 2,0 min", " ".join(explicar(p, c)))
        # Al confirmar se incorpora una sola vez el tiempo de decisión; el cronómetro se guarda aparte.
        f = confirmar(c, evaluar(c), "reloj", "asistida", "MOV-013", "", 30)
        self.assertAlmostEqual(f["primera_llegada_estimada_min"], 17.5)
        self.assertEqual(f["segundos_decision"], 30)
        self.assertAlmostEqual(f["llegada_mostrada_min"], 17)

    # --- Elegibilidad y datos --------------------------------------------------------------------------------
    def test_elegibilidad_y_ruta_faltante(self):
        c = self.caso("ESC-02-S01")
        v = evaluar(c)
        self.assertIn("R03", unidad(v, "MOV-004")["exclusion"])                     # VMD no traslada
        self.assertIn("R05", unidad(v, "MOV-012")["exclusion"])                     # Fuera de servicio
        c["flota"] = [dict(m, activo="False") if m["id_movil"] == "MOV-025" else m for m in c["flota"]]
        self.assertNotIn("MOV-025", [p["plan_id"] for p in evaluar(c)["opciones"]])  # Inactiva
        c = self.caso("ESC-02-S01")
        for m in c["flota"]:
            if m["id_movil"] == "MOV-025":
                m["tiempo_valle_min"] = float("nan")
                m["distancia_km"] = float("nan")
        v = evaluar(c)
        m = unidad(v, "MOV-025")
        self.assertIsNone(m["viaje"])
        self.assertIn("Sin tiempo de ruta Z-MED-07-01 → Z-MED-06-02", m["exclusion"])
        self.assertNotIn("MOV-025", [p["plan_id"] for p in v["opciones"]])

    def test_ocupada_espera_separada_del_viaje(self):
        c = self.caso("ESC-02-S01")
        v = evaluar(c, 30)
        m = unidad(v, "MOV-002")                                                    # TAB en atención hasta el min 20
        self.assertAlmostEqual(m["espera"], 19.5)
        self.assertEqual(m["zona"], "Z-MED-08-01")
        self.assertAlmostEqual(m["llegada"], 0.5 + 19.5 + m["viaje"])
        self.assertIn("MOV-002", [p["plan_id"] for p in v["opciones"]])

    def test_eventos_hasta_el_instante_y_r07(self):
        tablas = {k: v.copy() for k, v in self.datos.items()}
        nuevo = pd.DataFrame([dict(id_escenario="ESC-02", minuto=9., tipo_evento="RECLASIFICACION_TELEFONICA",
                                   id_solicitud="ESC-02-S03", id_movil="", detalle="", nueva_clasificacion="02",
                                   escala_manchester_nueva="NARANJA")])
        tablas["eventos"] = pd.concat([tablas["eventos"], nuevo], ignore_index=True)
        c = preparar(tablas, "ESC-02-S03")
        self.assertEqual((c["codigo_emi_inicial"], c["codigo_emi"], c["objetivo_min"]), ("03", "02", 20))
        tablas["eventos"].loc[tablas["eventos"].index[-1], "minuto"] = 30.
        self.assertEqual(preparar(tablas, "ESC-02-S03")["codigo_emi"], "03")       # Evento posterior: no influye
        # La liberación de MOV-003 al minuto 10 ya es conocida para una solicitud del minuto 25.
        self.assertEqual(unidad(evaluar(self.caso("ESC-02-S06")), "MOV-003")["estado"], "DISPONIBLE")

    def test_m02_libre_antes_que_la_que_depende_de_liberarse(self):
        # Misma llegada y tipo; la ocupada es más barata, pero D08 prefiere la libre dentro del grupo.
        c = self.aislado("ESC-02-S05", [("LIBRE", "MOV-021", dict(tiempo_valle_min=20, estado="DISPONIBLE")),
                                        ("OCUPADA", "MOV-022", dict(tiempo_valle_min=10, costo_km=1, costo_hora=1))])
        c["minuto_llegada"] = 15.
        orden = evaluar(c)["opciones"]
        self.assertAlmostEqual(orden[0]["llegada"], 20)
        self.assertAlmostEqual(orden[1]["llegada"], 20)            # 10 de espera + 10 de viaje
        self.assertEqual([p["plan_id"] for p in orden], ["LIBRE", "OCUPADA"])
        self.assertEqual((orden[0]["regla"], orden[1]["regla"]), ("D08", "D08"))
        self.assertEqual(orden[1]["depende_liberacion"], ["OCUPADA"])

    def test_m02_rotulo_y_i01_comparacion(self):
        c = self.caso("ESC-02-S05")
        v = evaluar(c, 24)
        p = v["opciones"][0]
        self.assertEqual(p["plan_id"], "MOV-022")
        self.assertIn("Depende de liberación: MOV-022", " ".join(explicar(p, c)))
        segunda = " ".join(explicar(v["opciones"][1], c))
        self.assertIn("Frente a la opción 1 (MOV-022): llega 9,1 min después", segunda)
        c = self.caso()
        v = evaluar(c)
        tercera = v["opciones"][2]
        self.assertTrue(tercera["criterio"].startswith("llegada similar a MOV-005"))
        self.assertIn("más de ida", tercera["criterio"])

    def test_d03_cobertura_zona_alta(self):
        v = evaluar(self.caso("ESC-02-S01"))
        self.assertIn("Z-BEL-01", plan(v, "MOV-017")["d03"])
        self.assertEqual(plan(v, "MOV-025")["d03"], [])

    def test_orden_costo_carga_empate_estable(self):
        c = self.caso()
        base = next(m for m in c["flota"] if m["id_movil"] == "MOV-005")
        c["flota"] = [dict(base, id_movil=i, tiempo_valle_min=t, costo_km=k, servicios_turno=n)
                      for i, t, k, n in [("B", 10, 150, 0), ("A", 10, 150, 0), ("C", 10, 150, 1),
                                          ("F", 10, 150, None), ("D", 9.9, 20000, 0), ("E", 95, 1, 0)]]
        for _ in range(2):
            self.assertEqual([x["plan_id"] for x in evaluar(c)["opciones"]], list("ABCFDE"))
            c["flota"].reverse()

    def test_archivos_incompletos(self):
        with carpeta_de_prueba() as carpeta:
            shutil.copytree(ENTRADA, carpeta, dirs_exist_ok=True)
            ruta = carpeta / "matriz_tiempos.csv"
            filas = ruta.read_text(encoding="utf-8-sig").splitlines()
            ruta.write_text("\n".join(filas[:-1]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "matriz_tiempos.csv: falta la combinación"):
                cargar(carpeta)
            ruta.write_text("zona_origen\nX", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "columnas"):
                cargar(carpeta)

    def test_codigos_como_texto_y_objetivos(self):
        self.assertEqual(dict(zip(self.datos["objetivos_urgencia"].codigo_emi,
                                  self.datos["objetivos_urgencia"].objetivo_min)),
                         {"01": 15, "02": 20, "07": 45, "03": 90, "06": 180})
        self.assertTrue(self.datos["solicitudes"].clasificacion_inicial.str.match(r"^0\d$").all())

    # --- Decisión humana -------------------------------------------------------------------------------------
    def test_alternativa_manual_cero_candidatos_y_pendiente(self):
        c = self.caso()
        v = evaluar(c)
        for modo in ("manual", "asistida"):
            f = confirmar(c, v, "alternativa", modo, "MOV-011", "prefiere_menor_carga", 60)
            self.assertEqual(f["movil_elegido_id"], "MOV-011")
            self.assertEqual(f["posicion_elegida"], 3 if modo == "asistida" else None)
            self.assertEqual(f["movil_recomendado_id"], "MOV-005" if modo == "asistida" else None)
            self.assertEqual(f["motivo_decision"], "prefiere_menor_carga")
        with self.assertRaisesRegex(ValueError, "motivo"):
            confirmar(c, v, "x", "asistida", "MOV-011", "", 60)
        with self.assertRaisesRegex(ValueError, "pendiente"):
            confirmar(c, v, "x", "asistida", None, "", 60)
        f = confirmar(c, v, "pend", "asistida", None, "consulta_coordinador", 60, detalle="Revisar con coordinación")
        self.assertEqual((f["estado_decision"], f["motivo_detalle"]), ("pendiente", "Revisar con coordinación"))
        c["flota"] = [m for m in c["flota"] if m["id_movil"] == "MOV-011"]
        self.assertEqual(len(evaluar(c)["opciones"]), 1)
        c["flota"][0]["estado"] = "FUERA_SERVICIO"
        v = evaluar(c)
        self.assertEqual(v["opciones"], [])
        f = confirmar(c, v, "sin", "asistida", None, "", 30)
        self.assertEqual((f["estado_decision"], f["motivo_decision"]), ("sin_asignar", "sin_elegibles"))
        self.assertEqual(f["costo_decision_cop"], 150)
        self.assertIsNone(f["costo_total_estimado_cop"])
        self.assertIsNone(f["primera_llegada_estimada_min"])

    def test_excepcion_no_recomendada_requiere_motivo(self):
        c = self.caso()
        v = evaluar(c)
        with self.assertRaisesRegex(ValueError, "excepción"):
            confirmar(c, v, "exc", "asistida", "MOV-002", "criterio_clinico", 40)
        f = confirmar(c, v, "exc", "asistida", "MOV-002", "criterio_clinico", 40, detalle="Posible traslado")
        self.assertEqual((f["es_excepcion"], f["posicion_elegida"], f["tipo_movil_elegido"]), (1, None, "TAB"))


class Registro(unittest.TestCase):
    def fila(self, ident="reintento"):
        datos = cargar()
        c = preparar(datos, "ESC-01-S01")
        return confirmar(c, evaluar(c), ident, "manual", "MOV-011", "revision_manual", 60)

    def test_guardado_fallo_reintento_doble_y_restauracion(self):
        f = self.fila()
        with carpeta_de_prueba() as ruta:
            destino = ruta / "decisiones.csv"
            shutil.copyfile(INICIALES, destino)
            with patch("src.decisiones.os.replace", side_effect=PermissionError("ocupado")):
                with self.assertRaises(PermissionError):
                    guardar(f, destino)
            self.assertEqual(len(filas_csv(destino)), 30)
            self.assertTrue(guardar(f, destino))
            self.assertFalse(guardar(f, destino))                                   # Doble confirmación
            self.assertEqual(len(filas_csv(destino)), 31)
            self.assertEqual(float(filas_csv(destino)[-1]["segundos_decision"]), 60)
            copia = restaurar(destino)
            self.assertEqual(len(filas_csv(copia)), 31)
            self.assertEqual(len(filas_csv(destino)), 30)

    def test_c04_csv_redondeado(self):
        datos = cargar()
        c = preparar(datos, "ESC-04-S01")
        f = confirmar(c, evaluar(c), "redondeo", "asistida", "MOV-016+MOV-013", "", 24)
        with carpeta_de_prueba() as ruta:
            destino = ruta / "decisiones.csv"
            guardar(f, destino)
            fila = filas_csv(destino)[0]
            self.assertEqual(fila["costo_viaje_elegido_cop"], "61890.73")
            self.assertEqual(fila["primera_llegada_estimada_min"], "7.22")
            self.assertIn('"costo_ida_cop":', fila["participaciones_json"])
            self.assertNotIn("0000000", fila["participaciones_json"] + fila["vista_json"])

    def test_lectura_compatible_con_filas_v1(self):
        f = self.fila("nueva")
        with carpeta_de_prueba() as ruta:
            destino = ruta / "decisiones.csv"
            with destino.open("w", encoding="utf-8-sig", newline="") as out:
                w = csv.DictWriter(out, fieldnames=CAMPOS_V1, extrasaction="ignore")
                w.writeheader()
                w.writerow(dict(f, solicitud_id="antigua"))
            antiguas = leer(destino)
            self.assertEqual(antiguas[0]["participaciones_json"], "")
            self.assertTrue(guardar(f, destino))
            filas = filas_csv(destino)
            self.assertEqual([r["solicitud_id"] for r in filas], ["antigua", "nueva"])
            self.assertEqual(list(filas[0]), CAMPOS)

    def test_precarga_identificada_y_sin_doble_conteo(self):
        d = pd.DataFrame(leer(INICIALES))
        self.assertEqual(len(d), 30)
        self.assertEqual(set(d.origen_registro), {"precargado"})
        self.assertEqual(d.modalidad.value_counts().to_dict(), {"manual": 15, "asistida": 15})
        asignadas = d[d.estado_decision == "asignada"]
        for r in asignadas.itertuples():
            partes = json.loads(r.participaciones_json)
            self.assertAlmostEqual(sum(p["costo_ida_cop"] for p in partes), float(r.costo_viaje_elegido_cop), delta=0.02)
        self.assertEqual(sum(len(json.loads(x)) for x in asignadas.participaciones_json),
                         len(asignadas) + (asignadas.ambulancia_preasignada_id != "").sum())

    def test_linea_base_reproduce_archivo_07(self):
        lb = pd.read_csv(ENTRADA / "linea_base_kpi.csv", dtype={"codigo_emi": str}, encoding="utf-8-sig")
        original = lb[lb.vista == "original"].set_index("codigo_emi")
        self.assertEqual(original.at["01", "p90_min"], 52.9)
        self.assertEqual(original.at["02", "p90_min"], 55.1)
        self.assertEqual(original.at["01", "pct_cumple"], 25.7)
        self.assertEqual(original.at["02", "pct_cumple"], 49.2)
        corregida = lb[lb.vista == "corregida"].set_index("codigo_emi")
        self.assertGreater(corregida.at["01", "excluidos_anomalia"], 0)


class Tablero(unittest.TestCase):
    def test_visuales_usan_campos_del_modelo(self):
        import sys
        sys.path.insert(0, str(RAIZ / "tablero"))
        import generar_pbip as g
        modelo = g.modelo()["model"]
        medidas = {m["name"] for t in modelo["tables"] for m in t.get("measures", [])}
        self.assertFalse([n for n in medidas if n.endswith("=")])
        columnas = {(t["name"], c["name"]) for t in modelo["tables"] for c in t["columns"]}
        anfitrion = {m["name"]: t["name"] for t in modelo["tables"] for m in t.get("measures", [])}
        faltan = []
        for v in g.informe()["sections"][0]["visualContainers"]:
            consulta = json.loads(v["config"])["singleVisual"].get("prototypeQuery", {})
            alias = {f["Name"]: f["Entity"] for f in consulta.get("From", [])}
            for sel in consulta.get("Select", []):
                tipo, ref = next(iter((k, x) for k, x in sel.items() if k in ("Measure", "Column")))
                tabla = alias[ref["Expression"]["SourceRef"]["Source"]]
                ok = (anfitrion.get(ref["Property"]) == tabla if tipo == "Measure"
                      else (tabla, ref["Property"]) in columnas)
                if not ok:
                    faltan.append(f"{tabla}.{ref['Property']}")
        self.assertEqual(faltan, [])


class Interfaz(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()

    @staticmethod
    def boton(app, etiqueta):
        return next(b for b in app.button if b.label == etiqueta)

    @staticmethod
    def textos(app):
        return " ".join(str(x.value) for x in list(app.markdown) + list(app.caption)) + " ".join(
            df.value.to_csv() for df in app.dataframe)

    def test_tres_escenarios_referencia_oculta_y_30_a_33(self):
        with carpeta_de_prueba() as carpeta:
            ruta = carpeta / "decisiones.csv"
            shutil.copyfile(INICIALES, ruta)
            with patch("src.decisiones.REGISTRO", ruta):
                app = self.app()
                self.assertIn("Demo académica con datos ficticios", app.warning[0].value)
                for n, (esc, plan_id, modo) in enumerate([("ESC-01", "MOV-005", "asistida"),
                        ("ESC-02", "MOV-025", "manual"), ("ESC-04", "MOV-016+MOV-013", "asistida")], 31):
                    app.selectbox[0].select(esc).run()
                    app.radio[0].set_value(modo).run()
                    self.boton(app, "Iniciar caso").click().run()
                    self.assertFalse(app.exception)
                    inicio = app.session_state["activo"]["inicio"]
                    self.assertIsNotNone(inicio)
                    self.assertEqual(bool(app.chat_message), modo == "asistida")
                    self.assertNotIn("Comentario del coordinador", self.textos(app))   # Referencia oculta
                    self.assertNotIn("Correcta", self.textos(app))
                    sel = next(s for s in app.selectbox if s.label == "Alternativa a despachar")
                    sel.select(plan_id).run()
                    if modo == "manual":
                        next(s for s in app.selectbox if s.label == "Motivo de la decisión").select("prefiere_menor_tiempo").run()
                    self.assertEqual(app.session_state["activo"]["inicio"], inicio)
                    self.boton(app, "Confirmar decisión").click().run()
                    self.assertFalse(app.exception)
                    self.assertTrue(app.success)
                    self.assertIn("Comentario del coordinador", self.textos(app))      # Revisión tras confirmar
                    registros = leer(ruta)
                    self.assertEqual(len(registros), n)
                    self.assertEqual(registros[-1]["plan_elegido_id"], plan_id)
                    self.assertEqual(registros[-1]["origen_registro"], "sesion")
                    self.assertEqual(registros[-1]["modalidad"], modo)
                    if esc == "ESC-04":
                        self.assertEqual(registros[-1]["ambulancia_preasignada_id"], "MOV-013")
                        self.assertEqual(len(json.loads(registros[-1]["participaciones_json"])), 2)
                    app.run()
                    self.assertEqual(len(leer(ruta)), n)                               # Sin duplicar al recargar
                    self.boton(app, "Abrir un nuevo caso").click().run()

    def test_recarga_y_reintento_desde_la_interfaz(self):
        with carpeta_de_prueba() as carpeta:
            ruta = carpeta / "decisiones.csv"
            with patch("src.decisiones.REGISTRO", ruta):
                app = self.app()
                self.boton(app, "Iniciar caso").click().run()
                primero = app.session_state["activo"]
                recarga = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60)
                recarga.query_params["caso"] = [primero["id"]]
                recarga.run()
                self.assertEqual(recarga.session_state["activo"]["inicio"], primero["inicio"])
                with patch("src.decisiones.guardar", side_effect=PermissionError("archivo ocupado")):
                    self.boton(recarga, "Confirmar decisión").click().run()
                self.assertTrue(recarga.error)
                self.assertFalse(ruta.exists())
                segundos = recarga.session_state["activo"]["fila"]["segundos_decision"]
                self.boton(recarga, "Reintentar guardado").click().run()
                self.assertTrue(recarga.success)
                recarga.run()
                filas = filas_csv(ruta)
                self.assertEqual(len(filas), 1)
                self.assertEqual(filas[0]["solicitud_id"], primero["id"])
                self.assertAlmostEqual(float(filas[0]["segundos_decision"]), segundos, places=4)

    def test_c01_estado_en_el_instante(self):
        with carpeta_de_prueba() as carpeta:
            with patch("src.decisiones.REGISTRO", carpeta / "decisiones.csv"):
                app = self.app()
                app.selectbox[0].select("ESC-02").run()
                app.selectbox[1].select("ESC-02-S10").run()
                self.boton(app, "Iniciar caso").click().run()
                tabla = next(d.value for d in app.dataframe if "Estado en el instante" in d.value.columns)
                estado = tabla.set_index("Móvil")["Estado en el instante"]
                self.assertTrue(estado["MOV-022"].startswith("DISPONIBLE · liberada"))
                self.assertEqual(estado["MOV-015"], "RETORNANDO")

    def test_pendiente_desde_la_interfaz(self):
        with carpeta_de_prueba() as carpeta:
            ruta = carpeta / "decisiones.csv"
            with patch("src.decisiones.REGISTRO", ruta):
                app = self.app()
                app.radio[0].set_value("manual").run()
                self.boton(app, "Iniciar caso").click().run()
                next(s for s in app.selectbox if s.label == "Alternativa a despachar").select("__pendiente__").run()
                next(s for s in app.selectbox if s.label.startswith("Motivo para dejar")).select("espera_liberacion").run()
                self.boton(app, "Confirmar decisión").click().run()
                self.assertFalse(app.exception)
                fila = leer(ruta)[0]
                self.assertEqual((fila["estado_decision"], fila["motivo_decision"]), ("pendiente", "espera_liberacion"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
