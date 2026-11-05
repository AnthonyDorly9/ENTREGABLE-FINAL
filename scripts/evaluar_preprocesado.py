"""Mide que tan bien funciona el preprocesado (segmentacion) y la lectura completa de numeros
con fotos ficticias de tres niveles de dificultad. Guarda resultados y ejemplos visuales."""
import argparse
import json

import cv2
import numpy as np

from nucleo.configuracion import CARPETA_MODELOS, CARPETA_RESULTADOS, CLAVES_MODELOS
from nucleo.datos import cargar_mnist
from nucleo.formularios_ficticios import GeneradorDigitos
from nucleo.modelos import ModeloBase
from nucleo.preprocesado import procesar_foto

NIVELES = {"limpio": (0.1, 0.0), "normal": (0.4, 0.1), "dificil": (0.8, 0.25)}


def mosaico(resultado, texto):
    pasos = resultado["pasos"]
    altura = 260
    paneles = []
    for nombre in ("original", "gris", "iluminacion", "binaria", "segmentacion"):
        imagen = pasos[nombre]
        if imagen.ndim == 2:
            imagen = cv2.cvtColor(imagen, cv2.COLOR_GRAY2BGR)
        escala = altura / imagen.shape[0]
        panel = cv2.resize(imagen, (max(1, round(imagen.shape[1] * escala)), altura))
        cv2.putText(panel, nombre, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        paneles.append(panel)
    fila_recortes = np.full((84, sum(p.shape[1] for p in paneles), 3), 255, np.uint8)
    x = 4
    for recorte in resultado["recortes"]:
        grande = cv2.cvtColor(255 - cv2.resize(recorte, (72, 72), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)
        if x + 76 > fila_recortes.shape[1]:
            break
        fila_recortes[6:78, x : x + 72] = grande
        x += 80
    cv2.putText(fila_recortes, f"real: {texto}", (max(x, 4), 46), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    return np.vstack([np.hstack(paneles), fila_recortes])


def main():
    analizador = argparse.ArgumentParser()
    analizador.add_argument("--version", default="v1")
    analizador.add_argument("--por-nivel", type=int, default=150)
    argumentos = analizador.parse_args()

    _, _, x_pru, y_pru = cargar_mnist()
    generador = GeneradorDigitos(x_pru, y_pru, semilla=7)
    modelos = {c: ModeloBase.cargar(CARPETA_MODELOS / argumentos.version / f"{c}.joblib") for c in CLAVES_MODELOS}
    destino = CARPETA_RESULTADOS / "preprocesado"
    destino.mkdir(parents=True, exist_ok=True)

    evaluacion = {}
    for nivel, (dificultad, toque) in NIVELES.items():
        sin_ajuste = con_ajuste = 0
        numeros_ok = {c: 0 for c in modelos}
        digitos_ok = {c: 0 for c in modelos}
        total_digitos = 0
        for i in range(argumentos.por_nivel):
            texto = generador.numero_aleatorio(int(generador.azar.integers(1, 7)))
            foto = generador.foto_numero(texto, dificultad, toque=toque)
            libre = procesar_foto(foto)
            sin_ajuste += len(libre["cajas"]) == len(texto)
            resultado = procesar_foto(foto, esperado=len(texto))
            con_ajuste += len(resultado["cajas"]) == len(texto)
            total_digitos += len(texto)
            if len(resultado["cajas"]) == len(texto):
                for clave, modelo in modelos.items():
                    predicho = "".join(str(d) for d in modelo.predecir(resultado["digitos"]))
                    numeros_ok[clave] += predicho == texto
                    digitos_ok[clave] += sum(a == b for a, b in zip(predicho, texto))
            if i < 3:
                cv2.imwrite(str(destino / f"ejemplo_{nivel}_{i + 1}.png"), mosaico(resultado, texto))
        n = argumentos.por_nivel
        evaluacion[nivel] = {
            "dificultad": dificultad,
            "probabilidad_digitos_pegados": toque,
            "numeros": n,
            "digitos": total_digitos,
            "segmentacion_correcta_sin_ajuste": sin_ajuste / n,
            "segmentacion_correcta_con_cantidad_conocida": con_ajuste / n,
            "numero_completo_correcto": {c: numeros_ok[c] / n for c in modelos},
            "digito_correcto": {c: digitos_ok[c] / total_digitos for c in modelos},
        }
        print(nivel, json.dumps({k: v for k, v in evaluacion[nivel].items() if k != "digito_correcto"}, ensure_ascii=False), flush=True)

    (destino / "evaluacion.json").write_text(json.dumps(evaluacion, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
