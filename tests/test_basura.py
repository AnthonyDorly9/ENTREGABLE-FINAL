import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as aplicacion
from nucleo.almacen import Almacen
from nucleo.configuracion import CARPETA_MODELOS, CLAVES_MODELOS, RAIZ
from nucleo.servicio import ErrorUsuario, Servicio


class PruebasBasuraDeVersiones(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.base = Path(self.temporal.name)
        shutil.copytree(CARPETA_MODELOS / "v1", self.base / "modelos" / "v1")
        (self.base / "resultados").mkdir()
        shutil.copytree(RAIZ / "resultados" / "v1", self.base / "resultados" / "v1")
        self.parches = [mock.patch("nucleo.servicio.CARPETA_MODELOS", self.base / "modelos"),
                        mock.patch("nucleo.servicio.CARPETA_RESULTADOS", self.base / "resultados")]
        for p in self.parches:
            p.start()
        self.servicio = Servicio(Almacen(self.base / "prueba.db"))

    def tearDown(self):
        for p in self.parches:
            p.stop()
        self.temporal.cleanup()

    def ids(self):
        return [v["id"] for v in self.servicio.almacen.listar_versiones()]

    def test_version_nueva_reutiliza_el_numero_libre_mas_bajo(self):
        s = self.servicio
        for _ in range(3):
            s.crear_version("x", {})
        self.assertEqual(self.ids(), ["v1", "v2", "v3", "v4"])
        s.activar_version("v4")
        s.quitar_versiones(["v2", "v3"])
        s.vaciar_basura()
        self.assertEqual(s.crear_version("nueva", {}), "v2")
        self.assertEqual(self.ids(), ["v1", "v2", "v4"])
        # una versión en la basura sigue ocupando su número: se puede restaurar sin choques
        s.activar_version("v4")
        s.quitar_versiones(["v2"])
        self.assertEqual(s.crear_version("otra", {}), "v3")
        s.restaurar_version("v2")
        self.assertEqual(self.ids(), ["v1", "v2", "v3", "v4"])

    def test_quitar_restaurar_y_borrar_para_siempre(self):
        s = self.servicio
        s.crear_version("a", {})
        s.crear_version("b", {})
        self.assertEqual(self.ids(), ["v1", "v2", "v3"])
        self.assertEqual(s.almacen.version_activa(), "v3")

        for malo, texto in ((["v1"], "inicial"), (["v3"], "activa"), ([], "al menos una"), (["v99"], "no existe"), (["../x"], "no válida")):
            with self.subTest(ids=malo), self.assertRaises(ErrorUsuario) as contexto:
                s.quitar_versiones(malo)
            self.assertIn(texto, str(contexto.exception))
        self.assertEqual(self.ids(), ["v1", "v2", "v3"], "los intentos invalidos no deben cambiar nada")

        s.quitar_versiones(["v2"])
        self.assertEqual(self.ids(), ["v1", "v3"])
        self.assertTrue((self.base / "modelos" / "_papelera" / "v2").is_dir())
        self.assertFalse((self.base / "modelos" / "v2").exists())
        self.assertEqual([v["id"] for v in s.versiones_basura()], ["v2"])
        with self.assertRaises(ErrorUsuario):
            s.quitar_versiones(["v2"])

        # Los numeros no se repiten aunque se quite la ultima version.
        s.crear_version("c", {})
        self.assertEqual(s.almacen.version_activa(), "v4")
        s.activar_version("v3")
        s.quitar_versiones(["v4"])
        s.crear_version("d", {})
        self.assertEqual(self.ids(), ["v1", "v3", "v5"])

        s.restaurar_version("v2")
        self.assertEqual(self.ids(), ["v1", "v2", "v3", "v5"])
        self.assertTrue((self.base / "modelos" / "v2" / "cnn.joblib").exists())
        with self.assertRaises(ErrorUsuario):
            s.restaurar_version("v2")

        s.borrar_para_siempre("v4")
        self.assertFalse((self.base / "modelos" / "_papelera" / "v4").exists())
        self.assertEqual(s.versiones_basura(), [])
        with self.assertRaises(ErrorUsuario):
            s.borrar_para_siempre("v2")
        self.assertTrue((self.base / "modelos" / "v2").is_dir(), "no se debe borrar una version que no esta en la basura")

        s.quitar_versiones(["v2", "v5"]) if False else s.quitar_versiones(["v2"])
        s.vaciar_basura()
        self.assertEqual(s.versiones_basura(), [])
        self.assertFalse((self.base / "modelos" / "_papelera" / "v2").exists())
        self.assertTrue((self.base / "modelos" / "v1" / "cnn.joblib").exists(), "v1 nunca se toca")

    def test_rutas(self):
        original = aplicacion.servicio
        aplicacion.servicio = self.servicio
        try:
            self.servicio.crear_version("a", {})
            self.servicio.crear_version("b", {})
            cliente = aplicacion.app.test_client()
            self.assertEqual(cliente.post("/api/versiones/quitar", json={"ids": ["v3"]}).status_code, 400)
            respuesta = cliente.post("/api/versiones/quitar", json={"ids": ["v2"]}).get_json()
            self.assertEqual(respuesta["quitadas"], ["v2"])
            self.assertEqual(respuesta["en_basura"], 1)
            self.assertEqual([v["id"] for v in cliente.get("/api/versiones/basura").get_json()["basura"]], ["v2"])
            self.assertEqual(cliente.get("/api/versiones").get_json()["en_basura"], 1)
            self.assertEqual(cliente.post("/api/versiones/v2/restaurar").status_code, 200)
            self.assertEqual(cliente.post("/api/versiones/v2/borrar-para-siempre").status_code, 400)
            cliente.post("/api/versiones/quitar", json={"ids": ["v2"]})
            self.assertEqual(cliente.post("/api/versiones/vaciar-basura").get_json()["en_basura"], 0)
            self.assertEqual(cliente.get("/api/versiones/v2/x").status_code, 404)
        finally:
            aplicacion.servicio = original


class PruebasBasuraDeTandas(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.base = Path(self.temporal.name)
        self.fotos = self.base / "fotos_usuario"
        self.almacen = Almacen(self.base / "prueba.db")
        self.servicio = Servicio.__new__(Servicio)
        self.servicio.almacen = self.almacen
        import threading
        self.servicio._candado = threading.RLock()
        self.parche = mock.patch("nucleo.servicio.CARPETA_FOTOS", self.fotos)
        self.parche.start()
        self.pixeles = [__import__("numpy").zeros(784, dtype="float32")]
        for lote in ("lote_2026-01-01_100000", "lote_2026-02-02_120000"):
            (self.fotos / lote).mkdir(parents=True)
            foto = self.almacen.insertar_foto(lote, f"{lote}/a.png", "a.png")
            (self.fotos / lote / "a.png").write_bytes(b"x")
            self.almacen.actualizar_foto(foto, "7", None)
            ids = self.almacen.reemplazar_digitos(foto, [7], self.pixeles)
            self.almacen.marcar_grupo(ids[0], "entrenamiento")

    def tearDown(self):
        self.parche.stop()
        self.temporal.cleanup()

    def nombres(self):
        return [l["lote"] for l in self.almacen.lotes()]

    def test_quitar_restaurar_y_borrar(self):
        s = self.servicio
        antiguo, reciente = "lote_2026-01-01_100000", "lote_2026-02-02_120000"
        self.assertEqual(len(self.almacen.digitos_con_grupo("entrenamiento")), 2)
        for malo in ([], ["../x"], ["lote_2000-01-01_000000"]):
            with self.subTest(ids=malo), self.assertRaises(ErrorUsuario):
                s.quitar_lotes(malo)
        s.quitar_lotes([antiguo])
        self.assertEqual(self.nombres(), [reciente])
        self.assertEqual([l["lote"] for l in s.lotes_basura()], [antiguo])
        self.assertEqual(self.almacen.ultimo_lote(), reciente)
        self.assertEqual(len(self.almacen.digitos_con_grupo("entrenamiento")), 1, "la tanda de la basura no sirve de memoria")
        self.assertTrue((self.fotos / antiguo / "a.png").exists(), "en la basura las fotos siguen guardadas")
        with self.assertRaises(ErrorUsuario):
            s.borrar_lote_para_siempre(reciente)  # solo se borra lo que esta en la basura
        s.restaurar_lote(antiguo)
        self.assertEqual(self.nombres(), [antiguo, reciente])
        self.assertEqual(len(self.almacen.digitos_con_grupo("entrenamiento")), 2)
        s.quitar_lotes([antiguo])
        s.vaciar_basura_lotes()
        self.assertEqual(s.lotes_basura(), [])
        self.assertFalse((self.fotos / antiguo).exists())
        self.assertTrue((self.fotos / reciente / "a.png").exists())
        self.assertEqual(self.nombres(), [reciente])

    def test_rutas(self):
        original = aplicacion.servicio
        aplicacion.servicio = self.servicio
        try:
            cliente = aplicacion.app.test_client()
            antiguo = "lote_2026-01-01_100000"
            self.assertEqual(cliente.post("/api/lotes/quitar", json={"ids": []}).status_code, 400)
            respuesta = cliente.post("/api/lotes/quitar", json={"ids": [antiguo]}).get_json()
            self.assertEqual(respuesta["quitadas"], [antiguo])
            self.assertEqual([l["lote"] for l in cliente.get("/api/lotes/basura").get_json()["basura"]], [antiguo])
            self.assertEqual(len(cliente.get("/api/lotes").get_json()), 1)
            self.assertEqual(cliente.post(f"/api/lotes/{antiguo}/restaurar").status_code, 200)
            self.assertEqual(cliente.post(f"/api/lotes/{antiguo}/borrar-para-siempre").status_code, 400)
        finally:
            aplicacion.servicio = original


if __name__ == "__main__":
    unittest.main()
