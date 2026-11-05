"""Mide la lectura de fotos difíciles con fotos simuladas: hojas cuadriculadas o rayadas, tintas de color, fotos
grandes de celular, números chicos o lejanos y fotos de lado o de cabeza. Guarda resultados/preprocesado/fotos_dificiles.json,
que usa el informe PDF."""
import argparse
import json

import cv2
import numpy as np

from nucleo.configuracion import CARPETA_MODELOS, CARPETA_RESULTADOS, CLAVES_MODELOS
from nucleo.datos import cargar_mnist
from nucleo.formularios_ficticios import TIPOS_FORMULARIO, GeneradorDigitos
from nucleo.modelos import ModeloBase
from nucleo.preprocesado import orientar, procesar_foto

CUADRICULAS_OSCURAS = [(60, 60, 60), (160, 80, 20), (40, 80, 120), (150, 60, 120), (60, 130, 40)]
TINTA_Y_CUADRICULA = [((190, 120, 50), (40, 40, 200)), ((60, 60, 200), (150, 50, 20)), ((80, 150, 60), (130, 40, 110)),
                      ((60, 60, 60), (40, 120, 20)), ((190, 120, 50), (110, 110, 110))]


def foto_lejana(generador, texto, altura_final, lado_foto=3000):
    """Número chico en una foto grande; `altura_final` es la altura del dígito cuando la foto se reduce a 1000 px."""
    azar = generador.azar
    tinta = generador.capa_tinta(texto, int(altura_final * lado_foto / 1000))
    alto, ancho = int(lado_foto * 0.75), lado_foto
    papel = np.full((alto, ancho), azar.uniform(200, 240), np.float32)
    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float32)
    papel *= 1 + 0.12 * ((xx / ancho - 0.5) + 0.5 * (yy / alto - 0.5))
    y0 = int(azar.integers(0, alto - tinta.shape[0]))
    x0 = int(azar.integers(0, ancho - tinta.shape[1]))
    zona = papel[y0 : y0 + tinta.shape[0], x0 : x0 + tinta.shape[1]]
    zona -= tinta * (zona - azar.uniform(20, 70))
    papel = cv2.GaussianBlur(papel + azar.normal(0, 4, papel.shape), (0, 0), 1.0)
    return cv2.cvtColor(np.clip(papel, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def main():
    analizador = argparse.ArgumentParser()
    analizador.add_argument("--version", default="v1")
    analizador.add_argument("--por-caso", type=int, default=40)
    argumentos = analizador.parse_args()

    _, _, x_pru, y_pru = cargar_mnist()
    g = GeneradorDigitos(x_pru, y_pru, semilla=17)
    modelos = {c: ModeloBase.cargar(CARPETA_MODELOS / argumentos.version / f"{c}.joblib") for c in CLAVES_MODELOS}
    cnn = modelos["cnn"]
    confianza = lambda X: cnn.probabilidades(X).max(axis=1)  # la app endereza las fotos con la CNN
    n = argumentos.por_caso
    numero = lambda: g.numero_aleatorio(int(g.azar.integers(1, 6)))

    formularios = []
    while len(formularios) < n:
        imagen, campos = g.formulario(list(TIPOS_FORMULARIO)[len(formularios) % len(TIPOS_FORMULARIO)], dificultad=0.3)
        for c in campos:
            x, y, w, h = c["caja"]
            formularios.append((imagen[y + 6 : y + h - 6, x + 6 : x + w - 6], c["valor"]))
    casos = {
        "Hoja lisa": [(g.foto_numero(t, dificultad=0.4), t) for t in (numero() for _ in range(n))],
        "Casillas de formulario": formularios[:n],
        "Cuadriculada o rayada (colores al azar)": [(g.foto_cuadriculada(t, float(g.azar.uniform(0.1, 0.8))), t) for t in (numero() for _ in range(n))],
        "Cuadrícula oscura (negra, azul, café, morada, verde)": [
            (g.foto_cuadriculada(t, 0.5, color_linea=CUADRICULAS_OSCURAS[i % len(CUADRICULAS_OSCURAS)]), t) for i, t in enumerate(numero() for _ in range(n))],
        "Tinta de otro color que la cuadrícula": [
            (g.foto_cuadriculada(t, 0.4, *TINTA_Y_CUADRICULA[i % len(TINTA_Y_CUADRICULA)]), t) for i, t in enumerate(numero() for _ in range(n))],
        "Foto grande de celular con cuadrícula": [
            (cv2.resize(g.foto_cuadriculada(t, 0.6), None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC), t) for t in (numero() for _ in range(n))],
        "Número chico o lejano (12 a 25 px de alto)": [(foto_lejana(g, t, int(g.azar.choice([12, 18, 25]))), t) for t in (numero() for _ in range(n))],
        "Foto de lado (girada 90°)": [
            (cv2.rotate(g.foto_numero(t, dificultad=0.3), cv2.ROTATE_90_CLOCKWISE if i % 2 else cv2.ROTATE_90_COUNTERCLOCKWISE), t)
            for i, t in enumerate(numero() for _ in range(n))],
        "Foto de cabeza (girada 180°)": [(cv2.rotate(g.foto_numero(t, dificultad=0.3), cv2.ROTATE_180), t) for t in (numero() for _ in range(n))],
    }

    resultados = []
    for nombre, fotos in casos.items():
        cantidad = 0
        exactos = {c: 0 for c in modelos}
        for foto, texto in fotos:
            _, foto = orientar(foto, confianza)
            r = procesar_foto(foto, esperado=len(texto))
            if len(r["cajas"]) == len(texto):
                cantidad += 1
                for clave, modelo in modelos.items():
                    exactos[clave] += "".join(str(d) for d in modelo.predecir(r["digitos"])) == texto
        n = len(fotos)
        resultados.append({"caso": nombre, "fotos": n, "cantidad_correcta": cantidad / n,
                           "numero_exacto": {c: exactos[c] / n for c in modelos}, "numero_exacto_cnn": exactos["cnn"] / n})
        print(f"{nombre}: cantidad {cantidad}/{n}, número exacto " + ", ".join(f"{c} {exactos[c]}" for c in modelos), flush=True)

    destino = CARPETA_RESULTADOS / "preprocesado"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "fotos_dificiles.json").write_text(json.dumps({"version": argumentos.version, "casos": resultados}, ensure_ascii=False, indent=1),
                                                  encoding="utf-8")


if __name__ == "__main__":
    main()
