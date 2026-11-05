import os
import sys
from pathlib import Path

# CODIGO: carpeta del proyecto (codigo, vistas y recursos).
# RAIZ: donde se guardan los datos (base de datos, fotos, versiones). TRAZO_DATOS permite probar con datos temporales.
CODIGO = Path(__file__).resolve().parent.parent
RAIZ = Path(os.environ["TRAZO_DATOS"]) if os.environ.get("TRAZO_DATOS") else CODIGO
CARPETA_DATOS = RAIZ / "datos"
CARPETA_MODELOS = RAIZ / "modelos"
CARPETA_RESULTADOS = RAIZ / "resultados"

SEMILLA = 42
CLASES = list(range(10))

CLAVES_MODELOS = ["cnn", "mlp", "svm", "knn", "regresion", "regresion_lineal", "kmeans"]

NOMBRES_MODELOS = {
    "cnn": "CNN (red convolucional)",
    "mlp": "MLP (red densa)",
    "svm": "SVM (RBF)",
    "knn": "KNN",
    "regresion": "Regresión logística",
    "regresion_lineal": "Regresión lineal",
    "kmeans": "K-Means",
}

# Color de cada modelo en fondo claro y oscuro, en el orden de CLAVES_MODELOS.
COLORES_MODELOS = {
    "cnn": "#e8590c",
    "mlp": "#6c4dff",
    "svm": "#12a06a",
    "knn": "#0a84d6",
    "regresion": "#d6336c",
    "regresion_lineal": "#00a3a3",
    "kmeans": "#b58900",
}

COLORES_MODELOS_OSCURO = {
    "cnn": "#e8590c",
    "mlp": "#8a6cff",
    "svm": "#12a06a",
    "knn": "#2794ea",
    "regresion": "#e2447a",
    "regresion_lineal": "#00a3a3",
    "kmeans": "#b58900",
}

NOMBRES_CORTOS = {
    "cnn": "CNN",
    "mlp": "MLP",
    "svm": "SVM",
    "knn": "KNN",
    "regresion": "Reg. logística",
    "regresion_lineal": "Reg. lineal",
    "kmeans": "K-Means",
}

MUESTRAS_ENTRENAMIENTO = {
    "cnn": 30000,
    "mlp": 30000,
    "svm": 10000,
    "knn": 20000,
    "regresion": 30000,
    "regresion_lineal": 30000,
    "kmeans": 30000,
}

MUESTRAS_VALIDACION_CRUZADA = 5000
PLIEGUES = 5

GRILLAS = {
    "cnn": {"filtros": [8, 16], "tasa_aprendizaje": [0.001, 0.003]},
    "mlp": {"neuronas": [64, 128], "tasa_aprendizaje": [0.001, 0.003]},
    "svm": {"C": [1, 10], "gamma": ["scale", 0.05]},
    "knn": {"k": [1, 3, 5, 7]},
    "regresion": {"C": [0.1, 1.0, 10.0]},
    "regresion_lineal": {"alpha": [0.1, 1.0, 10.0, 100.0]},
    "kmeans": {"clusteres": [10, 30, 60]},
}

PARAMETROS_INICIALES = {
    "cnn": {"filtros": 16, "tasa_aprendizaje": 0.003, "epocas": 3, "dropout": 0.25},
    "mlp": {"neuronas": 128, "tasa_aprendizaje": 0.003, "epocas": 8, "dropout": 0.2},
    "svm": {"C": 10, "gamma": "scale", "componentes": 50},
    "knn": {"k": 3, "componentes": 50},
    "regresion": {"C": 1.0, "iteraciones": 200},
    "regresion_lineal": {"alpha": 1.0},
    "kmeans": {"clusteres": 60, "componentes": 50},
}
