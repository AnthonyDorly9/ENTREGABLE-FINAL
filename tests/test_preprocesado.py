import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.datos import cargar_mnist
from nucleo.formularios_ficticios import ALTO_ENCABEZADO, ANCHO_FORMULARIO, TIPOS_FORMULARIO, GeneradorDigitos
from nucleo.preprocesado import a_data_uri, decodificar_imagen, procesar_foto


class PruebasPreprocesado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, x_pru, y_pru = cargar_mnist()
        cls.generador = GeneradorDigitos(x_pru, y_pru, semilla=3)

    def test_segmenta_en_orden_de_lectura(self):
        foto = self.generador.foto_numero("123", dificultad=0.1)
        resultado = procesar_foto(foto)
        self.assertEqual(len(resultado["cajas"]), 3)
        posiciones = [c[0] for c in resultado["cajas"]]
        self.assertEqual(posiciones, sorted(posiciones))
        self.assertEqual(resultado["digitos"].shape, (3, 784))
        self.assertGreaterEqual(resultado["digitos"].min(), 0.0)
        self.assertLessEqual(resultado["digitos"].max(), 1.0)

    def test_recorte_esta_centrado_en_formato_mnist(self):
        resultado = procesar_foto(self.generador.foto_numero("8", dificultad=0.1))
        imagen = resultado["digitos"][0].reshape(28, 28)
        ys, xs = np.nonzero(imagen > 0.3)
        self.assertLessEqual(abs(xs.mean() - 14), 2.5)
        self.assertLessEqual(abs(ys.mean() - 14), 2.5)
        self.assertLessEqual(max(xs.max() - xs.min(), ys.max() - ys.min()) + 1, 24)

    def test_separa_digitos_pegados_si_se_conoce_la_cantidad(self):
        for texto in ("12", "3579", "40"):
            with self.subTest(texto=texto):
                foto = self.generador.foto_numero(texto, dificultad=0.2, toque=1.0)
                resultado = procesar_foto(foto, esperado=len(texto))
                self.assertEqual(len(resultado["cajas"]), len(texto))

    def test_une_cajas_si_hay_de_mas(self):
        foto = self.generador.foto_numero("123", dificultad=0.1)
        resultado = procesar_foto(foto, esperado=2)
        self.assertEqual(len(resultado["cajas"]), 2)
        self.assertIsNotNone(resultado["aviso"])

    def test_foto_sin_digitos(self):
        resultado = procesar_foto(np.full((200, 300, 3), 230, np.uint8))
        self.assertEqual(len(resultado["cajas"]), 0)
        self.assertEqual(resultado["digitos"].shape, (0, 784))

    def test_decodificar_imagen(self):
        foto = self.generador.foto_numero("7", dificultad=0.1)
        correcto, buffer = cv2.imencode(".png", foto)
        self.assertTrue(correcto)
        self.assertEqual(decodificar_imagen(buffer.tobytes()).shape[2], 3)
        with self.assertRaises(ValueError):
            decodificar_imagen(b"no es una imagen")

    def test_data_uri(self):
        self.assertTrue(a_data_uri(np.zeros((4, 4), np.uint8)).startswith("data:image/png;base64,"))


class PruebasFormulariosFicticios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, x_pru, y_pru = cargar_mnist()
        cls.generador = GeneradorDigitos(x_pru, y_pru, semilla=11)

    def test_estructura_de_los_formularios(self):
        for tipo, (_, campos_definidos) in TIPOS_FORMULARIO.items():
            with self.subTest(tipo=tipo):
                imagen, campos = self.generador.formulario(tipo)
                self.assertEqual(imagen.shape[:2], (ALTO_ENCABEZADO + 130 * len(campos_definidos), ANCHO_FORMULARIO))
                self.assertEqual([len(c["valor"]) for c in campos], [n for _, n in campos_definidos])
                for campo in campos:
                    x, y, w, h = campo["caja"]
                    self.assertLessEqual(x + w, imagen.shape[1])
                    self.assertLessEqual(y + h, imagen.shape[0])

    def test_se_leen_los_campos_de_un_formulario(self):
        correctos = total = 0
        for tipo in TIPOS_FORMULARIO:
            for _ in range(3):
                imagen, campos = self.generador.formulario(tipo, dificultad=0.3)
                for campo in campos:
                    x, y, w, h = campo["caja"]
                    recorte = imagen[y + 6 : y + h - 6, x + 6 : x + w - 6]
                    resultado = procesar_foto(recorte, esperado=len(campo["valor"]))
                    correctos += len(resultado["cajas"]) == len(campo["valor"])
                    total += 1
        self.assertGreaterEqual(correctos / total, 0.9)


if __name__ == "__main__":
    unittest.main()
