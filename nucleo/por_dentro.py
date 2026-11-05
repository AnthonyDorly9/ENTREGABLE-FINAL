"""Activaciones internas de la CNN para un dibujo, para mostrar como una red neuronal ve un digito."""
import torch

from .explicacion import _cuadricula, uri_digito
from .preprocesado import dibujo_a_vector
from .servicio import ErrorUsuario


def activaciones(servicio, data_uri):
    try:
        vector = dibujo_a_vector(data_uri)
    except ValueError as error:
        raise ErrorUsuario(str(error))
    cnn = servicio.modelos()["cnn"]
    red = cnn.red.eval()
    entrada = cnn._preparar(torch.from_numpy(vector.reshape(1, 784)))
    with torch.no_grad():
        capa1 = red[:2](entrada)[0].numpy()
        capa2 = red[:5](entrada)[0].numpy()
        densa = red[:10](entrada)[0].numpy()
        probs = torch.softmax(red(entrada), dim=1)[0].numpy()
    return {
        "entrada": uri_digito(vector, 6),
        "capas": [
            {"titulo": "Capa 1: filtros de trazos", "uri": _cuadricula(list(capa1), 4, escala=2),
             "detalle": f"{len(capa1)} filtros de 3×3 recorren la imagen. Cada cuadro se enciende donde encuentra un tipo de trazo (bordes, curvas, diagonales)."},
            {"titulo": "Capa 2: formas más grandes", "uri": _cuadricula(list(capa2), 8, escala=3),
             "detalle": f"{len(capa2)} filtros combinan los trazos de la capa 1 en formas más grandes, sobre una imagen reducida a la mitad."},
            {"titulo": "Capa densa: 64 neuronas", "uri": _cuadricula([densa.reshape(4, 16)], 1, escala=14),
             "detalle": f"{int((densa > 0).sum())} de 64 neuronas se encienden. Ya no ven la imagen: resumen las formas encontradas."},
        ],
        "probabilidades": [float(p) for p in probs],
        "predicho": int(probs.argmax()),
    }
