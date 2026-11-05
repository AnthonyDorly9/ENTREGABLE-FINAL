import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as aplicacion
from nucleo.almacen import Almacen
from nucleo.configuracion import CARPETA_DATOS, CLAVES_MODELOS
from nucleo.servicio import Servicio

# Solo las fotos en hoja lisa: las cuadriculadas tienen sus propias pruebas en test_cuadricula.py.
ETIQUETAS = {n: t for n, t in json.loads((CARPETA_DATOS / "ficticios" / "etiquetas.json").read_text(encoding="utf-8"))["numeros"].items()
             if n.startswith("numero_")}
CARPETA_NUMEROS = CARPETA_DATOS / "ficticios" / "numeros"
# Un número sin dígitos que se confundan al girarlos (0, 1, 6, 8, 9), para las pruebas de giro.
SIN_AMBIGUEDAD = next(n for n in sorted(ETIQUETAS) if len(ETIQUETAS[n]) >= 3 and set(ETIQUETAS[n]) <= set("23457"))


def archivo(nombre):
    return (io.BytesIO((CARPETA_NUMEROS / nombre).read_bytes()), nombre)


class PruebasApi(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        base = Path(self.temporal.name)
        self.parche = mock.patch("nucleo.servicio.CARPETA_FOTOS", base / "fotos")
        self.parche.start()
        self.original = aplicacion.servicio
        aplicacion.servicio = Servicio(Almacen(base / "prueba.db"))
        self.cliente = aplicacion.app.test_client()

    def tearDown(self):
        aplicacion.servicio = self.original
        self.parche.stop()
        self.temporal.cleanup()

    def subir(self, nombres, **extra):
        return self.cliente.post("/api/fotos", data={"fotos": [archivo(n) for n in nombres], **extra},
                                 content_type="multipart/form-data")

    def test_paginas(self):
        inicio = self.cliente.get("/")
        self.assertEqual(inicio.status_code, 200)
        self.assertIn("Leer formulario", inicio.get_data(as_text=True))
        self.assertEqual(self.cliente.get("/predecir").status_code, 302)

    def test_flujo_completo(self):
        nombres = sorted(ETIQUETAS)[:4]
        respuesta = self.subir(nombres)
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(len(datos["fotos"]), 4)
        self.assertTrue(datos["lote"].startswith("lote_"))
        textos = {str(f["id"]): ETIQUETAS[f["nombre"]] for f in datos["fotos"]}

        pasos = self.cliente.get(f"/api/fotos/{datos['fotos'][0]['id']}/pasos").get_json()
        self.assertEqual(len(pasos["pasos"]), 5)
        self.assertTrue(all(p["uri"].startswith("data:image/png;base64,") for p in pasos["pasos"]))

        resultado = self.cliente.post("/api/predecir", json={"lote": datos["lote"], "textos": textos}).get_json()
        self.assertEqual(resultado["version"], self.servicio_activa())
        self.assertEqual(len(resultado["marcador"]), len(CLAVES_MODELOS))
        self.assertEqual(len(resultado["fotos"]), 4)
        for foto in resultado["fotos"]:
            self.assertEqual(len(foto["digitos"]), len(foto["texto"]))
            self.assertTrue(foto["completa"])
            for digito in foto["digitos"]:
                self.assertEqual(set(digito["modelos"]), set(CLAVES_MODELOS))
        cnn = next(f for f in resultado["marcador"] if f["modelo"] == "cnn")
        self.assertGreaterEqual(cnn["digitos_ok"] / cnn["digitos"], 0.8)

        digito_id = resultado["fotos"][0]["digitos"][0]["id"]
        for clave in CLAVES_MODELOS:
            with self.subTest(modelo=clave):
                explicacion = self.cliente.get(f"/api/explicacion/{digito_id}/{clave}").get_json()
                self.assertAlmostEqual(sum(explicacion["probabilidades"]), 1.0, places=3)
                self.assertTrue(explicacion["imagenes"])
                self.assertTrue(explicacion["texto"])

        recuperado = self.cliente.get(f"/api/lote/{datos['lote']}").get_json()
        self.assertEqual(len(recuperado["fotos"]), 4)

        galeria = self.cliente.get(f"/api/lote/{datos['lote']}/predicciones/cnn.png")
        self.assertEqual(galeria.status_code, 200)
        self.assertEqual(galeria.mimetype, "image/png")
        self.assertTrue(galeria.data.startswith(b"\x89PNG"))
        self.assertEqual(self.cliente.get(f"/api/lote/{datos['lote']}/predicciones/otro.png").status_code, 404)

        primera = recuperado["fotos"][0]
        con_recuadro = self.cliente.get(f"/foto/{primera['id']}/digito/{primera['digitos'][0]['posicion']}.png")
        self.assertEqual(con_recuadro.status_code, 200)
        self.assertTrue(con_recuadro.data.startswith(b"\x89PNG"))

    def servicio_activa(self):
        return aplicacion.servicio.version_activa()

    def test_foto_se_guarda_en_carpeta_del_lote_con_nombre_legible(self):
        datos = self.subir(sorted(ETIQUETAS)[:2]).get_json()
        carpeta = Path(self.temporal.name) / "fotos" / datos["lote"]
        self.assertEqual(sorted(p.name for p in carpeta.iterdir()), [f"foto_{f['id']:04d}.png" for f in datos["fotos"]])

    def test_errores_claros(self):
        datos = self.subir(sorted(ETIQUETAS)[:1]).get_json()
        foto_id = str(datos["fotos"][0]["id"])
        malo = self.cliente.post("/api/predecir", json={"lote": datos["lote"], "textos": {foto_id: "12a"}})
        self.assertEqual(malo.status_code, 400)
        self.assertIn("dígitos", malo.get_json()["error"])
        sin_numero = self.cliente.post("/api/predecir", json={"lote": datos["lote"], "textos": {}})
        self.assertEqual(sin_numero.status_code, 400)
        no_imagen = self.cliente.post("/api/fotos", data={"fotos": [(io.BytesIO(b"hola"), "a.png")]},
                                      content_type="multipart/form-data")
        self.assertEqual(no_imagen.status_code, 400)
        self.assertEqual(self.cliente.get("/api/explicacion/99999/cnn").status_code, 400)

    def test_maximo_de_veinte_fotos_por_tanda(self):
        nombres = sorted(ETIQUETAS)[:20]
        self.assertEqual(self.subir(nombres).status_code, 200)
        primera = self.subir(nombres[:1])
        self.assertEqual(primera.status_code, 200)
        lote = primera.get_json()["lote"]
        exceso = self.subir(nombres[:20] + nombres[:1], lote=lote)
        self.assertEqual(exceso.status_code, 400)
        self.assertIn("Máximo 20", exceso.get_json()["error"])

    def test_foto_de_lado_se_endereza_al_subir(self):
        import cv2
        import numpy as np
        nombre = SIN_AMBIGUEDAD
        derecha = cv2.imread(str(CARPETA_NUMEROS / nombre))
        de_lado = cv2.imencode(".png", cv2.rotate(derecha, cv2.ROTATE_90_CLOCKWISE))[1].tobytes()
        datos = self.cliente.post("/api/fotos", data={"fotos": [(io.BytesIO(de_lado), "de_lado.png"), archivo(nombre)]},
                                  content_type="multipart/form-data").get_json()
        girada, normal = datos["fotos"]
        self.assertTrue(girada["girada"])
        self.assertFalse(normal["girada"], "una foto derecha no se debe girar")
        guardada = cv2.imread(str(aplicacion.servicio.ruta_foto(girada["id"])))
        self.assertEqual(guardada.shape, derecha.shape)
        self.assertLess(np.abs(guardada.astype(int) - derecha.astype(int)).mean(), 2)

    def test_boton_girar(self):
        import cv2
        datos = self.subir([SIN_AMBIGUEDAD]).get_json()
        foto_id = datos["fotos"][0]["id"]
        ruta = aplicacion.servicio.ruta_foto(foto_id)
        original = cv2.imread(str(ruta))
        r = self.cliente.post(f"/api/fotos/{foto_id}/girar").get_json()
        self.assertIn("?v=", r["url"])
        self.assertEqual(cv2.imread(str(ruta)).shape[:2], original.shape[1::-1])
        for _ in range(3):
            r = self.cliente.post(f"/api/fotos/{foto_id}/girar").get_json()
        self.assertTrue((cv2.imread(str(ruta)) == original).all(), "cuatro giros vuelven a la foto original")
        self.assertEqual(r["detectados"], len(ETIQUETAS[SIN_AMBIGUEDAD]))
        self.assertEqual(self.cliente.post("/api/fotos/99999/girar").status_code, 400)

    def test_quitar_foto(self):
        datos = self.subir(sorted(ETIQUETAS)[:2]).get_json()
        foto_id = datos["fotos"][0]["id"]
        self.assertEqual(self.cliente.delete(f"/api/fotos/{foto_id}").status_code, 200)
        self.assertEqual(self.cliente.get(f"/foto/{foto_id}").status_code, 400)


if __name__ == "__main__":
    unittest.main()
