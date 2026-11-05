import io
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as aplicacion
from nucleo import informe
from nucleo.almacen import Almacen
from nucleo.configuracion import CARPETA_MODELOS, RAIZ
from nucleo.datos import cargar_mnist
from nucleo.formularios_ficticios import GeneradorDigitos
from nucleo.servicio import ErrorUsuario, Servicio

try:
    import pymupdf
except ImportError:  # PyMuPDF solo se usa para revisar el PDF; la aplicacion no lo necesita
    pymupdf = None

MARGEN_PUNTOS = 1.9 * 28.35


class PruebasInforme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporal = tempfile.TemporaryDirectory()
        base = Path(cls.temporal.name)
        shutil.copytree(CARPETA_MODELOS / "v1", base / "modelos" / "v1")
        (base / "resultados").mkdir()
        shutil.copytree(RAIZ / "resultados" / "v1", base / "resultados" / "v1")
        shutil.copytree(RAIZ / "resultados" / "preprocesado", base / "resultados" / "preprocesado")
        cls.parches = [mock.patch("nucleo.servicio.CARPETA_FOTOS", base / "fotos"),
                       mock.patch("nucleo.servicio.CARPETA_MODELOS", base / "modelos"),
                       mock.patch("nucleo.graficos.CARPETA_RESULTADOS", base / "resultados"),
                       mock.patch("nucleo.informe.CARPETA_RESULTADOS", base / "resultados")]
        for p in cls.parches:
            p.start()
        cls.servicio = Servicio(Almacen(base / "prueba.db"))
        _, _, x, y = cargar_mnist()
        g = GeneradorDigitos(x, y, semilla=17)
        fotos = []
        for i in range(3):
            t = g.numero_aleatorio(5)
            fotos.append((f"f{i}.png", cv2.imencode(".png", g.foto_numero(t, 0.3))[1].tobytes(), t))
        subida = cls.servicio.subir([(n, d) for n, d, _ in fotos])
        cls.lote = subida["lote"]
        cls.ids = [f["id"] for f in subida["fotos"]]
        cls.servicio.predecir(cls.lote, {str(f["id"]): t for f, (_, _, t) in zip(subida["fotos"], fotos)})

    @classmethod
    def tearDownClass(cls):
        for p in cls.parches:
            p.stop()
        cls.temporal.cleanup()

    def test_pdf_completo_con_todas_las_secciones(self):
        pdf = informe.generar_pdf(self.servicio, {"autor": "Prueba", "curso": "Curso", "lote": self.lote, "fotos": self.ids, "portada": "tsne_mnist", "tema": "azul"})
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 200_000)
        if pymupdf is None:
            self.skipTest("PyMuPDF no esta instalado")
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        self.assertGreaterEqual(len(doc), 10)
        texto = "\n".join(p.get_text() for p in doc)
        for _, titulo, _ in informe.SECCIONES:
            self.assertIn(titulo, texto)
        self.assertIn("Prueba", doc[0].get_text())
        for novedad in ("Figura 2.", "hoja cuadriculada", "Tabla 2.", "Foto de lado", "Número chico o lejano", "se endereza"):
            self.assertIn(novedad, texto, "el informe debe explicar el preprocesado nuevo")
        plano = " ".join(texto.split())
        for de_tus_fotos in ("Figura 12.", "Aciertos de cada modelo en tus 3 fotos", "Tabla 7.", "Figura 13.",
                             "Matrices de confusión de los siete modelos con los", "dígitos de tu tanda", "Tabla 8.", "Qué confundió cada modelo",
                             "Figura 14a.", "con los dígitos de tus fotos", "Figura 15.", "Pasos del preprocesado sobre tu foto",
                             "Dígitos que recortó la aplicación"):
            self.assertIn(de_tus_fotos, plano, "el informe debe llevar gráficos hechos con las fotos de la tanda elegida")
        for todos_los_modelos in ("Figura 8. Matrices de confusión de los siete modelos", "Figura 9. Aciertos de cada modelo en cada dígito", "R. log.", "K-M.",
                                  *(f"Figura 10{letra}. Predicciones de" for letra in "abcdefg")):
            self.assertIn(todos_los_modelos, plano, "las matrices y gráficos deben mostrar los siete modelos, no solo la CNN")
        self.assertEqual(len(set(re.findall(r"Figura (\d+)\.", plano))), len(re.findall(r"Figura (\d+)\.", plano)), "sin números de figura repetidos")
        self.assertIn("Tanda: " + informe.nombre_tanda(self.lote), " ".join(texto.split()))
        ancho, alto = doc[1].rect.width, doc[1].rect.height
        for numero, pagina in enumerate(doc):
            if numero == 0:
                continue
            for imagen in pagina.get_image_info():
                x0, y0, x1, y1 = imagen["bbox"]
                self.assertGreaterEqual(x0, MARGEN_PUNTOS - 3, f"imagen cortada a la izquierda en la página {numero + 1}")
                self.assertLessEqual(x1, ancho - MARGEN_PUNTOS + 3, f"imagen cortada a la derecha en la página {numero + 1}")
                self.assertGreaterEqual(y0, 0)
                self.assertLessEqual(y1, alto - MARGEN_PUNTOS + 40, f"imagen cortada abajo en la página {numero + 1}")
            for bloque in pagina.get_text("blocks"):
                self.assertLessEqual(bloque[2], ancho - MARGEN_PUNTOS + 8, f"texto fuera del margen en la página {numero + 1}")

    def test_nombre_de_tanda_con_fecha_y_hora(self):
        self.assertEqual(informe.nombre_tanda("lote_2026-09-20_143651"), "20/09/2026 a las 14:36:51")
        self.assertEqual(informe.nombre_tanda("lote_2026-09-20_143651b"), "20/09/2026 a las 14:36:51 (2)")
        self.assertEqual(informe.nombre_tanda("otra"), "otra")

    def test_pdf_con_solo_algunas_secciones_y_texto_editado(self):
        pdf = informe.generar_pdf(self.servicio, {"secciones": ["resumen", "conclusiones"], "textos": {"resumen": "Texto escrito por la persona para el resumen."}})
        if pymupdf is None:
            self.skipTest("PyMuPDF no esta instalado")
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        texto = "\n".join(p.get_text() for p in doc)
        self.assertIn("Texto escrito por la persona para el resumen.", texto)
        self.assertIn("Conclusiones y recomendaciones", texto)
        self.assertNotIn("Arquitectura de las redes neuronales", texto.split("Índice")[-1].split("1. Resumen")[-1])
        self.assertLess(len(doc), 8)

    def test_caratula_con_foto_propia(self):
        import base64
        import numpy as np
        foto = np.full((300, 500, 3), (40, 120, 200), np.uint8)
        cv2.putText(foto, "MI FOTO", (60, 170), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 5)
        uri = "data:image/jpeg;base64," + base64.b64encode(cv2.imencode(".jpg", foto)[1].tobytes()).decode()
        pdf = informe.generar_pdf(self.servicio, {"secciones": ["resumen"], "portada": "propia", "portada_propia": uri})
        if pymupdf is None:
            self.assertTrue(pdf.startswith(b"%PDF"))
            return
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        imagenes = doc[0].get_image_info()
        self.assertEqual(len(imagenes), 1)
        x0, y0, x1, y1 = imagenes[0]["bbox"]
        self.assertAlmostEqual((x1 - x0) / (y1 - y0), 500 / 300, delta=0.05, msg="la foto propia debe conservar su proporcion (sin cortarse)")
        self.assertLessEqual(x1, doc[0].rect.width - MARGEN_PUNTOS + 3)
        for malo in ("data:image/png;base64,####", "no es una imagen", "data:image/jpeg;base64," + base64.b64encode(b"texto").decode()):
            with self.assertRaises(ErrorUsuario):
                informe.generar_pdf(self.servicio, {"portada_propia": malo})

    def test_opciones_invalidas(self):
        with self.assertRaises(ErrorUsuario):
            informe.generar_pdf(self.servicio, {"version": "v99"})
        with self.assertRaises(ErrorUsuario):
            informe.generar_pdf(self.servicio, {"secciones": ["no_existe"]})

    def test_rutas_del_informe_y_del_codigo(self):
        original = aplicacion.servicio
        aplicacion.servicio = self.servicio
        try:
            cliente = aplicacion.app.test_client()
            self.assertEqual(cliente.get("/informe").status_code, 200)
            opciones = cliente.get("/api/informe/opciones").get_json()
            self.assertEqual(len(opciones["secciones"]), len(informe.SECCIONES))
            self.assertTrue(all(opciones["textos"][s["clave"]] for s in opciones["secciones"]))
            respuesta = cliente.post("/api/informe/pdf", json={"secciones": ["resumen"]})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.mimetype, "application/pdf")
            self.assertEqual(cliente.post("/api/informe/pdf", json={"secciones": ["nada"]}).status_code, 400)
            zip_respuesta = cliente.get("/descargar/codigo.zip")
            nombres = zipfile.ZipFile(io.BytesIO(zip_respuesta.data)).namelist()
            self.assertIn("digitos_manuscritos/app.py", nombres)
            self.assertIn("digitos_manuscritos/nucleo/modelos.py", nombres)
            self.assertFalse([n for n in nombres if "/datos/" in n or "/modelos/" in n or n.endswith(".joblib") or n.endswith(".db")])
        finally:
            aplicacion.servicio = original


if __name__ == "__main__":
    unittest.main()
