import cv2
import numpy as np


def aumentar(X, y, copias, semilla=0):
    """Devuelve X, y mas `copias` variantes de cada digito (giro, escala y desplazamiento pequenos)."""
    if copias <= 0 or len(y) == 0:
        return X.copy(), y.copy()
    azar = np.random.default_rng(semilla)
    bloques_x, bloques_y = [X], [y]
    for _ in range(copias):
        nuevo = np.empty_like(X)
        for i, vector in enumerate(X):
            matriz = cv2.getRotationMatrix2D((13.5, 13.5), azar.uniform(-12, 12), azar.uniform(0.9, 1.1))
            matriz[:, 2] += azar.uniform(-2, 2, size=2)
            nuevo[i] = cv2.warpAffine(vector.reshape(28, 28), matriz, (28, 28)).reshape(-1)
        bloques_x.append(nuevo)
        bloques_y.append(y)
    return np.concatenate(bloques_x), np.concatenate(bloques_y)
