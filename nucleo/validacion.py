import itertools
import time

import numpy as np
from sklearn.model_selection import StratifiedKFold

from .configuracion import GRILLAS, PLIEGUES, SEMILLA
from .modelos import crear_modelo


def validacion_cruzada(clave, X, y, parametros_fijos=None, pliegues=PLIEGUES, progreso=None):
    """Busca en malla los hiperparametros de un modelo con validacion cruzada estratificada.

    Devuelve una lista de combinaciones ordenada de mejor a peor exactitud media.
    """
    grilla = GRILLAS[clave]
    nombres = list(grilla)
    divisor = StratifiedKFold(n_splits=pliegues, shuffle=True, random_state=SEMILLA)
    resultados = []
    for valores in itertools.product(*grilla.values()):
        combinacion = dict(zip(nombres, valores))
        exactitudes, inicio = [], time.perf_counter()
        for entrenamiento, validacion in divisor.split(X, y):
            modelo = crear_modelo(clave, **{**(parametros_fijos or {}), **combinacion})
            modelo.entrenar(X[entrenamiento], y[entrenamiento])
            exactitudes.append(float((modelo.predecir(X[validacion]) == y[validacion]).mean()))
        registro = {
            "parametros": combinacion,
            "exactitud_media": float(np.mean(exactitudes)),
            "desviacion": float(np.std(exactitudes)),
            "exactitud_por_pliegue": exactitudes,
            "segundos": time.perf_counter() - inicio,
        }
        resultados.append(registro)
        if progreso:
            progreso(clave, registro)
    resultados.sort(key=lambda r: r["exactitud_media"], reverse=True)
    return resultados
