import numpy as np

from .configuracion import CARPETA_DATOS, SEMILLA


def cargar_mnist():
    """Devuelve (X_entrenamiento, y_entrenamiento, X_prueba, y_prueba) con pixeles en [0, 1] y forma (N, 784)."""
    archivo = np.load(CARPETA_DATOS / "mnist" / "mnist.npz")
    x_ent = archivo["x_train"].reshape(-1, 784).astype(np.float32) / 255.0
    x_pru = archivo["x_test"].reshape(-1, 784).astype(np.float32) / 255.0
    return x_ent, archivo["y_train"].astype(np.int64), x_pru, archivo["y_test"].astype(np.int64)


def submuestra_estratificada(X, y, cantidad, semilla=SEMILLA):
    """Toma `cantidad` muestras manteniendo la proporcion de cada digito."""
    if cantidad >= len(y):
        return X, y
    generador = np.random.default_rng(semilla)
    indices = []
    for clase in np.unique(y):
        posiciones = np.flatnonzero(y == clase)
        tomar = int(round(cantidad * len(posiciones) / len(y)))
        indices.extend(generador.choice(posiciones, size=min(tomar, len(posiciones)), replace=False))
    indices = generador.permutation(np.array(indices))
    return X[indices], y[indices]
