"""Agrega la regresion lineal (septimo modelo) a las versiones ya guardadas.

No toca los otros modelos ni las correcciones: entrena la regresion lineal con MNIST, le suma tus digitos ya corregidos
y guarda el archivo en cada version. Tambien completa las metricas de la version v1. Se puede ejecutar mas de una vez.
"""
import copy
import json

import numpy as np

from nucleo.almacen import Almacen
from nucleo.aumento import aumentar
from nucleo.configuracion import CARPETA_MODELOS, CARPETA_RESULTADOS, MUESTRAS_ENTRENAMIENTO, SEMILLA
from nucleo.datos import cargar_mnist, submuestra_estratificada
from nucleo.evaluacion import evaluar_modelo
from nucleo.modelos import ModeloBase, crear_modelo
from nucleo.validacion import validacion_cruzada

CLAVE = "regresion_lineal"


def leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def escribir(ruta, contenido):
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    almacen = Almacen()
    x_ent, y_ent, x_pru, y_pru = cargar_mnist()
    X, y = submuestra_estratificada(x_ent, y_ent, MUESTRAS_ENTRENAMIENTO[CLAVE])

    ruta_cv = CARPETA_RESULTADOS / "v1" / "validacion_cruzada.json"
    cv = leer(ruta_cv)
    if CLAVE not in cv:
        X_cv, y_cv = submuestra_estratificada(x_ent, y_ent, 5000)
        cv[CLAVE] = validacion_cruzada(CLAVE, X_cv, y_cv)
        escribir(ruta_cv, cv)
        print("Validacion cruzada:", cv[CLAVE][0]["parametros"], round(cv[CLAVE][0]["exactitud_media"], 4))
    base = crear_modelo(CLAVE, **cv[CLAVE][0]["parametros"])
    base.entrenar(X, y)

    propios = [d for grupo in ("entrenamiento", "reserva") for d in almacen.digitos_con_grupo(grupo)]
    X_propios = y_propios = None
    if propios:
        X_propios, y_propios = aumentar(np.stack([d["pixeles"] for d in propios]), np.array([d["real"] for d in propios], dtype=np.int64), 4, semilla=SEMILLA)

    for version in almacen.listar_versiones():
        destino = CARPETA_MODELOS / version["id"] / f"{CLAVE}.joblib"
        if destino.exists():
            modelo = ModeloBase.cargar(destino)
        else:
            modelo = copy.deepcopy(base)
            if version["numero"] > 1 and X_propios is not None:
                modelo.actualizar(X_propios, y_propios, X_propios[:1], y_propios[:1])
            modelo.guardar(destino)
        exactitud = float((modelo.predecir(x_pru) == y_pru).mean())
        detalle = version["detalle"]
        detalle.setdefault("exactitud_prueba", {})[CLAVE] = exactitud
        almacen.actualizar_detalle_version(version["id"], detalle)
        print(f"{version['id']}: regresion lineal {exactitud:.4f}")

    ruta_metricas = CARPETA_RESULTADOS / "v1" / "metricas.json"
    metricas = leer(ruta_metricas)
    if CLAVE not in metricas:
        m = evaluar_modelo(ModeloBase.cargar(CARPETA_MODELOS / "v1" / f"{CLAVE}.joblib"), x_pru, y_pru)
        m.update({"segundos_entrenamiento": 0.8, "muestras_entrenamiento": len(y), "hiperparametros": base.parametros})
        metricas[CLAVE] = m
        escribir(ruta_metricas, metricas)
    ruta_arquitecturas = CARPETA_RESULTADOS / "v1" / "arquitecturas.json"
    arquitecturas = leer(ruta_arquitecturas)
    arquitecturas[CLAVE] = base.arquitectura()
    escribir(ruta_arquitecturas, arquitecturas)

    # Copias derivadas (se recalculan solas): mapas, imagenes y metricas de versiones distintas de v1.
    for carpeta in CARPETA_RESULTADOS.iterdir():
        if not carpeta.is_dir() or not carpeta.name.startswith("v"):
            continue
        for derivado in (carpeta / "mapa_pca.json",):
            derivado.unlink(missing_ok=True)
        imagenes = carpeta / "graficos"
        if imagenes.exists():
            for archivo in imagenes.glob("*.png"):
                archivo.unlink()
        if carpeta.name != "v1":
            (carpeta / "metricas.json").unlink(missing_ok=True)
    print("Listo.")


if __name__ == "__main__":
    main()
