import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.almacen import Almacen
from nucleo.configuracion import CARPETA_MODELOS, CLAVES_MODELOS
from nucleo.datos import cargar_mnist
from nucleo.formularios_ficticios import GeneradorDigitos
from nucleo.servicio import Servicio, TOLERANCIA_MNIST


def fotos_dificiles(generador, cantidad, prefijo):
    """Devuelve [(nombre, bytes_png, texto)] con numeros dificiles (ruido, sombras, digitos pegados)."""
    resultado = []
    for i in range(cantidad):
        texto = generador.numero_aleatorio(int(generador.azar.integers(3, 6)))
        correcto, buffer = cv2.imencode(".png", generador.foto_numero(texto, dificultad=0.85, toque=0.3))
        resultado.append((f"{prefijo}_{i}.png", buffer.tobytes(), texto))
    return resultado


class PruebasCorreccion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, x_pru, y_pru = cargar_mnist()
        cls.generador = GeneradorDigitos(x_pru, y_pru, semilla=21)

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.base = Path(self.temporal.name)
        shutil.copytree(CARPETA_MODELOS / "v1", self.base / "modelos" / "v1")
        self.parches = [
            mock.patch("nucleo.servicio.CARPETA_FOTOS", self.base / "fotos"),
            mock.patch("nucleo.servicio.CARPETA_MODELOS", self.base / "modelos"),
        ]
        for parche in self.parches:
            parche.start()
        self.servicio = self.nuevo_servicio()

    def tearDown(self):
        for parche in self.parches:
            parche.stop()
        self.temporal.cleanup()

    def nuevo_servicio(self):
        return Servicio(Almacen(self.base / "prueba.db"))

    def predecir_tanda(self, fotos):
        subida = self.servicio.subir([(n, datos) for n, datos, _ in fotos])
        textos = {str(f["id"]): t for f, (_, _, t) in zip(subida["fotos"], fotos)}
        return subida["lote"], self.servicio.predecir(subida["lote"], textos)

    def test_correccion_crea_version_y_conserva_las_mejoras(self):
        lote1, antes1 = self.predecir_tanda(fotos_dificiles(self.generador, 8, "a"))
        errores_antes = {f["modelo"]: f["digitos"] - f["digitos_ok"] for f in antes1["marcador"]}
        self.assertTrue(any(errores_antes.values()), "las fotos dificiles deberian producir errores")

        informe1 = self.servicio.corregir(lote1)
        self.assertEqual(informe1["version_anterior"], "v1")
        self.assertEqual(informe1["version_nueva"], "v2")
        aceptados = [i["modelo"] for i in informe1["informe"] if i["aceptado"]]
        self.assertTrue(aceptados, "al menos un modelo debe poder corregirse")
        for entrada in informe1["informe"]:
            if entrada["aceptado"]:
                self.assertGreaterEqual(entrada["mnist_despues"], entrada["mnist_antes"] - TOLERANCIA_MNIST)
                self.assertGreater(entrada["corregidos"], 0)
            if entrada["entrenado"] and not entrada["aceptado"]:
                self.assertTrue(entrada["motivo"])
        self.assertTrue((self.base / "modelos" / "v2").is_dir())
        self.assertEqual(sorted(p.name for p in (self.base / "modelos" / "v2").iterdir()),
                         sorted(f"{c}.joblib" for c in CLAVES_MODELOS))

        despues1 = informe1["resultado"]
        self.assertEqual(despues1["version"], "v2")
        for clave in aceptados:
            antes = next(f for f in antes1["marcador"] if f["modelo"] == clave)
            despues = next(f for f in despues1["marcador"] if f["modelo"] == clave)
            self.assertGreaterEqual(despues["digitos_ok"], antes["digitos_ok"])

        # Persistencia: un servicio nuevo (como tras reiniciar la aplicacion) sigue con v2 y las mismas respuestas.
        reiniciado = self.nuevo_servicio()
        self.assertEqual(reiniciado.version_activa(), "v2")
        recargado = reiniciado.resultado_lote(lote1)
        self.assertEqual(recargado["marcador"], despues1["marcador"])

        # Una segunda correccion parte de v2 y no pierde lo corregido en la primera.
        digitos_lote1 = {d["id"]: d for f in despues1["fotos"] for d in f["digitos"]}
        arreglados = {clave: [i for i, d in digitos_lote1.items()
                              if d["modelos"][clave]["acierto"]
                              and not next(x for f in antes1["fotos"] for x in f["digitos"] if x["id"] == i)["modelos"][clave]["acierto"]]
                      for clave in aceptados}
        lote2, _ = self.predecir_tanda(fotos_dificiles(self.generador, 8, "b"))
        informe2 = reiniciado.corregir(lote2)
        if informe2["version_nueva"] is None:
            self.skipTest("la segunda tanda no necesito cambios")
        self.assertEqual(informe2["version_anterior"], "v2")
        self.assertEqual(informe2["version_nueva"], "v3")
        final = reiniciado.resultado_lote(lote1, "v3")
        digitos_final = {d["id"]: d for f in final["fotos"] for d in f["digitos"]}
        for clave, ids in arreglados.items():
            if not ids:
                continue
            siguen = sum(1 for i in ids if digitos_final[i]["modelos"][clave]["acierto"])
            self.assertGreaterEqual(siguen / len(ids), 0.7, f"{clave} olvido lo que habia corregido")

    def test_no_hay_nada_que_corregir(self):
        limpias = []
        for i in range(2):
            texto = self.generador.numero_aleatorio(3)
            _, buffer = cv2.imencode(".png", self.generador.foto_numero(texto, dificultad=0.05))
            limpias.append((f"c_{i}.png", buffer.tobytes(), texto))
        lote, resultado = self.predecir_tanda(limpias)
        con_error = [d["id"] for f in resultado["fotos"] for d in f["digitos"]
                     if any(p["acierto"] is False for p in d["modelos"].values())]
        from nucleo.servicio import ErrorUsuario
        with self.assertRaises(ErrorUsuario):
            self.servicio.corregir(lote, excluir=con_error)
        with self.assertRaises(ErrorUsuario):
            self.servicio.corregir("lote_inexistente")

    def test_activar_y_volver_a_una_version_anterior(self):
        lote, _ = self.predecir_tanda(fotos_dificiles(self.generador, 8, "c"))
        informe = self.servicio.corregir(lote)
        self.assertEqual(informe["version_nueva"], "v2")
        self.assertEqual(self.servicio.activar_version("v1")["activa"], "v1")
        self.assertEqual(self.nuevo_servicio().version_activa(), "v1")
        self.assertEqual(self.servicio.activar_version("v2")["activa"], "v2")


if __name__ == "__main__":
    unittest.main()
