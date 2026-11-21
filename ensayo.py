"""Precarga reproducible, restauración explícita y verificación de los tres escenarios.

    py ensayo.py generar-precarga   Reconstruye datos/demo/decisiones_iniciales.csv (30 decisiones ficticias).
    py ensayo.py restaurar          Respalda datos/decisiones.csv y repone la precarga. Nunca ocurre al abrir la app.
    py ensayo.py verificar          Escribe datos/demo/verificacion_escenarios.csv con 24 s de decisión por caso.
"""
import argparse
import csv
from datetime import timedelta

from src.datos import cargar
from src.decisiones import CAMPOS, INICIALES, confirmar, para_csv, restaurar
from src.recomendacion import evaluar, preparar


def referencia(datos, solicitud):
    ref = datos["referencia_despachador"]
    return list(ref[ref.id_solicitud == solicitud].sort_values("orden_movil").id_movil)


VERIFICACION = INICIALES.with_name("verificacion_escenarios.csv")


def escribir(ruta, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(para_csv(f) for f in filas)


def generar():
    datos = cargar()
    ids = list(datos["solicitudes"].id_solicitud)
    # Quince solicitudes en ambas modalidades: 6 de ESC-01, 7 de ESC-02 y las 2 de ESC-04.
    muestra = ids[:6] + ids[6:13] + ids[-2:]
    filas = []
    for i, solicitud in enumerate(muestra):
        caso = preparar(datos, solicitud)
        vista = evaluar(caso)
        opciones = vista["opciones"]
        for j, modo in enumerate(("manual", "asistida")):
            segundos = 18 + (7 * i + 11 * j) % 46  # Duraciones ficticias de demostración.
            posicion = 1 if (i + j) % 4 == 0 and len(opciones) > 1 else 0
            pendiente = (i, j) in {(5, 0), (11, 1)}
            plan = opciones[posicion]["plan_id"] if opciones and not pendiente else None
            motivo = "consulta_coordinador" if plan is None else "revision_manual"
            fecha = (caso["fecha_solicitud"] + timedelta(seconds=segundos)).isoformat() + "-05:00"
            filas.append(confirmar(caso, vista, f"DEMO-{i * 2 + j + 1:03}", modo, plan, motivo, segundos, fecha,
                                   "precargado", detalle="Decisión ficticia de demostración",
                                   referencia=referencia(datos, solicitud)))
    escribir(INICIALES, filas)
    print(f"{len(filas)} decisiones ficticias en {INICIALES}")


def verificar():
    datos = cargar()
    filas = []
    for n, (solicitud, plan, modo) in enumerate([("ESC-01-S01", "MOV-005", "asistida"),
                                                ("ESC-02-S01", "MOV-025", "manual"),
                                                ("ESC-04-S01", "MOV-016+MOV-013", "asistida")], 1):
        caso = preparar(datos, solicitud)
        filas.append(confirmar(caso, evaluar(caso), f"VERIF-{n:03}", modo, plan, "revision_manual", 24,
                               caso["fecha_solicitud"].isoformat() + "-05:00", "verificacion",
                               referencia=referencia(datos, solicitud)))
    escribir(VERIFICACION, filas)
    for f in filas:
        print(f"{f['solicitud_fuente']}: {f['plan_elegido_id']} viaje {f['min_viaje_elegido']:.2f} min · primera llegada "
              f"{f['primera_llegada_estimada_min']:.3f} min · costo de ida {f['costo_viaje_elegido_cop']:,.0f} COP")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("accion", choices=["generar-precarga", "restaurar", "verificar"])
    accion = parser.parse_args().accion
    if accion == "generar-precarga":
        generar()
    elif accion == "verificar":
        verificar()
    else:
        copia = restaurar()
        print("Ensayo restaurado con 30 decisiones precargadas. " +
              (f"Copia del registro anterior: {copia}" if copia else "No había registro anterior."))
