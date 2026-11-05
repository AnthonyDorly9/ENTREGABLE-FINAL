import time

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

from .configuracion import CLASES


def calcular_metricas(y_real, y_predicho):
    precision, recall, f1, soporte = precision_recall_fscore_support(
        y_real, y_predicho, labels=CLASES, zero_division=0
    )
    macro = precision_recall_fscore_support(
        y_real, y_predicho, labels=CLASES, average="macro", zero_division=0
    )
    return {
        "exactitud": float(accuracy_score(y_real, y_predicho)),
        "precision_macro": float(macro[0]),
        "recall_macro": float(macro[1]),
        "f1_macro": float(macro[2]),
        "por_clase": [
            {
                "digito": clase,
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "soporte": int(soporte[i]),
            }
            for i, clase in enumerate(CLASES)
        ],
        "matriz_confusion": confusion_matrix(y_real, y_predicho, labels=CLASES).tolist(),
    }


def evaluar_modelo(modelo, X, y):
    inicio = time.perf_counter()
    y_predicho = modelo.predecir(X)
    duracion = time.perf_counter() - inicio
    metricas = calcular_metricas(y, y_predicho)
    metricas["ms_por_muestra"] = 1000.0 * duracion / len(y)
    metricas["indices_error"] = np.flatnonzero(y_predicho != y).tolist()
    metricas["predicciones_error"] = y_predicho[y_predicho != y].tolist()
    return metricas
