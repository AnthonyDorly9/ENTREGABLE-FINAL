"""Explica como llego cada modelo a su respuesta para un digito: mapas de calor, vecinos, centroides y puntajes."""
import math

import cv2
import numpy as np
import torch

from .preprocesado import a_data_uri

ESCALA = 8


def _normalizar(mapa):
    mapa = np.asarray(mapa, np.float32)
    mapa = mapa - mapa.min()
    return mapa / (mapa.max() + 1e-8)


def _base_gris(vector, escala=ESCALA):
    imagen = np.clip(vector.reshape(28, 28) * 255, 0, 255).astype(np.uint8)
    return cv2.resize(imagen, (28 * escala, 28 * escala), interpolation=cv2.INTER_NEAREST)


def uri_digito(vector, escala=ESCALA):
    return a_data_uri(_base_gris(vector, escala))


def _superponer(vector, mapa):
    base = cv2.cvtColor(_base_gris(vector), cv2.COLOR_GRAY2BGR)
    mapa = cv2.resize(_normalizar(mapa), (28 * ESCALA, 28 * ESCALA), interpolation=cv2.INTER_CUBIC)
    color = cv2.applyColorMap(np.clip(mapa * 255, 0, 255).astype(np.uint8), cv2.COLORMAP_JET)
    return a_data_uri(cv2.addWeighted(base, 0.45, color, 0.55, 0))


def _cuadricula(mapas, columnas, escala=3):
    filas = math.ceil(len(mapas) / columnas)
    alto, ancho = mapas[0].shape
    lienzo = np.zeros((filas * (alto + 1), columnas * (ancho + 1)), np.uint8)
    for i, mapa in enumerate(mapas):
        f, c = divmod(i, columnas)
        lienzo[f * (alto + 1) : f * (alto + 1) + alto, c * (ancho + 1) : c * (ancho + 1) + ancho] = np.uint8(
            _normalizar(mapa) * 255
        )
    lienzo = cv2.resize(lienzo, None, fx=escala, fy=escala, interpolation=cv2.INTER_NEAREST)
    return a_data_uri(cv2.applyColorMap(lienzo, cv2.COLORMAP_MAGMA))


def _cnn(modelo, X, predicho, probs):
    red = modelo.red.eval()
    entrada = modelo._preparar(torch.from_numpy(X))
    intermedia = red[:5](entrada)
    intermedia.retain_grad()
    red[5:](intermedia)[0, predicho].backward()
    pesos = intermedia.grad.mean(dim=(2, 3), keepdim=True)
    combinado = (pesos * intermedia).sum(1)[0].detach().numpy()
    cam = np.maximum(combinado, 0)
    if cam.max() <= 0:
        cam = combinado - combinado.min()
    red.zero_grad()
    with torch.no_grad():
        primera = red[:2](entrada)[0].numpy()
    return {
        "texto": (
            f"La CNN pasó la imagen por filtros que detectan bordes y trazos. Luego calculó qué zonas empujaron "
            f"más hacia el {predicho} (mapa de calor, rojo = más importante) y respondió con {probs[predicho]:.0%} de confianza."
        ),
        "imagenes": [
            {"titulo": "Dónde miró", "uri": _superponer(X[0], cam), "pie": f"Zonas que votaron por el {predicho}"},
            {"titulo": "Lo que ve la primera capa", "uri": _cuadricula(list(primera), 4),
             "pie": f"{len(primera)} filtros: cada cuadro resalta un tipo de trazo"},
        ],
    }


def _mlp(modelo, X, predicho, probs):
    red = modelo.red.eval()
    entrada = modelo._preparar(torch.from_numpy(X)).requires_grad_(True)
    red(entrada)[0, predicho].backward()
    sensibilidad = entrada.grad.abs()[0].numpy().reshape(28, 28)
    red.zero_grad()
    with torch.no_grad():
        oculta = torch.relu(red[0](modelo._preparar(torch.from_numpy(X))))[0].numpy()
    columnas = 16
    filas = math.ceil(len(oculta) / columnas)
    relleno = np.zeros(filas * columnas, np.float32)
    relleno[: len(oculta)] = oculta
    return {
        "texto": (
            f"La red densa mezcla los 784 píxeles en {len(oculta)} neuronas de la primera capa; solo algunas se encienden "
            f"con este dígito. Después las combina y concluye que es un {predicho} ({probs[predicho]:.0%})."
        ),
        "imagenes": [
            {"titulo": "Píxeles que más pesaron", "uri": _superponer(X[0], sensibilidad),
             "pie": "Si cambian, cambia la respuesta"},
            {"titulo": "Neuronas encendidas", "uri": _cuadricula([relleno.reshape(filas, columnas)], 1, escala=14),
             "pie": f"{int((oculta > 0).sum())} de {len(oculta)} neuronas activas"},
        ],
    }


def _regresion(modelo, X, predicho, probs):
    pesos = modelo.modelo.coef_[predicho].reshape(28, 28)
    aporte = pesos * X[0].reshape(28, 28)
    return {
        "texto": (
            f"La regresión logística asigna a cada píxel un peso por dígito y suma. Para el {predicho}, los píxeles "
            f"encendidos con peso positivo sumaron más que en los otros dígitos ({probs[predicho]:.0%})."
        ),
        "imagenes": [
            {"titulo": "Aporte de cada píxel", "uri": _superponer(X[0], np.clip(aporte, 0, None)),
             "pie": f"Rojo = empuja hacia el {predicho}"},
            {"titulo": f"Pesos aprendidos del {predicho}", "uri": _cuadricula([pesos], 1, escala=8),
             "pie": "Claro = peso alto, oscuro = peso bajo"},
        ],
    }


def _regresion_lineal(modelo, X, predicho, probs):
    pesos = modelo.pesos[:784, predicho].reshape(28, 28)
    aporte = pesos * X[0].reshape(28, 28)
    puntajes = modelo._con_sesgo(X) @ modelo.pesos
    return {
        "texto": (
            f"La regresión lineal calcula un puntaje para cada dígito sumando los píxeles multiplicados por su peso; el puntaje más alto gana. "
            f"Para el {predicho} el puntaje fue {puntajes[0, predicho]:.2f} (1 sería un ajuste perfecto)."
        ),
        "imagenes": [
            {"titulo": "Aporte de cada píxel", "uri": _superponer(X[0], np.clip(aporte, 0, None)), "pie": f"Rojo = suma puntos al {predicho}"},
            {"titulo": f"Pesos aprendidos del {predicho}", "uri": _cuadricula([pesos], 1, escala=8), "pie": "Claro = peso alto, oscuro = peso bajo"},
        ],
    }


def _etiquetas_vectores_soporte(modelo):
    return np.repeat(modelo.modelo.classes_, modelo.modelo.n_support_)


def _svm(modelo, X, predicho, probs):
    Z = modelo._proyectar(X)
    vectores = modelo.modelo.support_vectors_
    distancias = np.linalg.norm(vectores - Z, axis=1)
    etiquetas = _etiquetas_vectores_soporte(modelo)
    imagenes = []
    for indice in np.argsort(distancias)[:4]:
        reconstruido = np.clip(modelo.pca.inverse_transform(vectores[indice : indice + 1])[0], 0, 1)
        imagenes.append({"titulo": f"Vector de soporte: {etiquetas[indice]}", "uri": uri_digito(reconstruido, 5),
                         "pie": f"distancia {distancias[indice]:.2f}"})
    return {
        "texto": (
            f"La SVM guarda {len(vectores)} ejemplos clave (vectores de soporte) que definen las fronteras entre dígitos. "
            f"Comparó este dígito con ellos y el {predicho} obtuvo el puntaje más alto ({probs[predicho]:.0%})."
        ),
        "imagenes": imagenes,
    }


def _knn(modelo, X, predicho, probs):
    Z = modelo._proyectar(X)
    distancias, indices = modelo.modelo.kneighbors(Z)
    etiquetas = modelo.modelo.classes_[modelo.modelo._y[indices[0]]]
    imagenes = []
    for distancia, indice, etiqueta in zip(distancias[0], indices[0], etiquetas):
        reconstruido = np.clip(modelo.pca.inverse_transform(modelo.modelo._fit_X[indice : indice + 1])[0], 0, 1)
        imagenes.append({"titulo": f"Vecino: {etiqueta}", "uri": uri_digito(reconstruido, 5), "pie": f"distancia {distancia:.2f}"})
    votos = int((etiquetas == predicho).sum())
    return {
        "texto": (
            f"KNN no aprende reglas: busca los {len(etiquetas)} dígitos más parecidos que memorizó y vota. "
            f"{votos} de {len(etiquetas)} vecinos eran un {predicho}, así que respondió {predicho}."
        ),
        "imagenes": imagenes,
    }


def _kmeans(modelo, X, predicho, probs):
    Z = modelo._proyectar(X)
    distancias = modelo.modelo.transform(Z)[0]
    imagenes = []
    for indice in np.argsort(distancias)[:3]:
        centro = np.clip(modelo.pca.inverse_transform(modelo.modelo.cluster_centers_[indice : indice + 1])[0], 0, 1)
        imagenes.append({"titulo": f"Grupo {indice}: dígito {modelo.etiqueta_cluster[indice]}", "uri": uri_digito(centro, 5),
                         "pie": f"distancia {distancias[indice]:.2f}"})
    return {
        "texto": (
            f"K-Means agrupó los dígitos sin conocer las etiquetas y luego cada grupo tomó el dígito más común en él. "
            f"Este dígito cayó en el grupo más cercano, que representa al {predicho}."
        ),
        "imagenes": imagenes,
    }


EXPLICADORES = {"cnn": _cnn, "mlp": _mlp, "regresion": _regresion, "regresion_lineal": _regresion_lineal, "svm": _svm, "knn": _knn, "kmeans": _kmeans}


def explicar(modelo, vector):
    X = vector.reshape(1, 784).astype(np.float32)
    probs = modelo.probabilidades(X)[0]
    predicho = int(probs.argmax())
    resultado = EXPLICADORES[modelo.clave](modelo, X, predicho, probs)
    return {
        "modelo": modelo.clave,
        "predicho": predicho,
        "confianza": float(probs[predicho]),
        "probabilidades": [float(p) for p in probs],
        **resultado,
    }
