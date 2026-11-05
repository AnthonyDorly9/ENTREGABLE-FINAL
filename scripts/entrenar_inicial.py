"""Entrena los siete modelos con MNIST, ajusta hiperparametros con validacion cruzada,
evalua en el conjunto de prueba y guarda modelos y resultados de la version indicada."""
import argparse
import json
import time

from nucleo.configuracion import (
    CARPETA_MODELOS,
    CARPETA_RESULTADOS,
    CLAVES_MODELOS,
    MUESTRAS_ENTRENAMIENTO,
    MUESTRAS_VALIDACION_CRUZADA,
    NOMBRES_MODELOS,
)
from nucleo.datos import cargar_mnist, submuestra_estratificada
from nucleo.evaluacion import evaluar_modelo
from nucleo.modelos import crear_modelo
from nucleo.validacion import validacion_cruzada


def guardar_json(ruta, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    analizador = argparse.ArgumentParser()
    analizador.add_argument("--version", default="v1")
    analizador.add_argument("--modelos", default=",".join(CLAVES_MODELOS))
    analizador.add_argument("--sin-validacion-cruzada", action="store_true")
    analizador.add_argument("--muestras-rapidas", type=int, default=0, help="limita las muestras (solo para pruebas)")
    argumentos = analizador.parse_args()

    x_ent, y_ent, x_pru, y_pru = cargar_mnist()
    carpeta_modelos = CARPETA_MODELOS / argumentos.version
    carpeta_resultados = CARPETA_RESULTADOS / argumentos.version

    metricas_totales, arquitecturas, validaciones, historiales = {}, {}, {}, {}
    for clave in argumentos.modelos.split(","):
        nombre = NOMBRES_MODELOS[clave]
        print(f"\n=== {nombre} ===", flush=True)
        cantidad = argumentos.muestras_rapidas or MUESTRAS_ENTRENAMIENTO[clave]
        X, y = submuestra_estratificada(x_ent, y_ent, cantidad)

        parametros = {}
        if not argumentos.sin_validacion_cruzada:
            X_cv, y_cv = submuestra_estratificada(x_ent, y_ent, argumentos.muestras_rapidas or MUESTRAS_VALIDACION_CRUZADA)
            cv = validacion_cruzada(
                clave, X_cv, y_cv, parametros_fijos={"epocas": 2} if clave in ("cnn", "mlp") else None,
                progreso=lambda k, r: print(f"  CV {r['parametros']} -> {r['exactitud_media']:.4f} (+-{r['desviacion']:.4f}) {r['segundos']:.0f}s", flush=True),
            )
            validaciones[clave] = cv
            parametros = cv[0]["parametros"]
            print(f"  mejores hiperparametros: {parametros}", flush=True)

        modelo = crear_modelo(clave, **parametros)
        inicio = time.perf_counter()
        historial = modelo.entrenar(X, y, X_val=x_pru[:2000], y_val=y_pru[:2000],
                                    callback=lambda r: print(f"  epoca {r['epoca']}: perdida {r['perdida']:.4f} exactitud {r['exactitud']:.4f} val {r.get('exactitud_val', 0):.4f}", flush=True))
        segundos = time.perf_counter() - inicio

        metricas = evaluar_modelo(modelo, x_pru, y_pru)
        metricas["segundos_entrenamiento"] = segundos
        metricas["muestras_entrenamiento"] = len(y)
        metricas["hiperparametros"] = modelo.parametros
        print(f"  prueba: exactitud {metricas['exactitud']:.4f} F1 {metricas['f1_macro']:.4f} entrenamiento {segundos:.0f}s", flush=True)

        modelo.guardar(carpeta_modelos / f"{clave}.joblib")
        metricas_totales[clave] = metricas
        arquitecturas[clave] = modelo.arquitectura()
        historiales[clave] = historial

    guardar_json(carpeta_resultados / "metricas.json", metricas_totales)
    guardar_json(carpeta_resultados / "arquitecturas.json", arquitecturas)
    guardar_json(carpeta_resultados / "curvas_entrenamiento.json", historiales)
    if validaciones:
        guardar_json(carpeta_resultados / "validacion_cruzada.json", validaciones)
    print("\nListo.", flush=True)


if __name__ == "__main__":
    main()
