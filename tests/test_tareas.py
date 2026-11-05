import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as aplicacion
from nucleo.almacen import Almacen
from nucleo.configuracion import CARPETA_MODELOS, RAIZ
from nucleo.servicio import ErrorUsuario, Servicio
from nucleo.tareas import Tareas


def esperar(condicion, segundos=60):
    fin = time.time() + segundos
    while time.time() < fin:
        if condicion():
            return True
        time.sleep(0.1)
    return False


class PruebasGestorDeTareas(unittest.TestCase):
    def setUp(self):
        self.tareas = Tareas()

    def esperar_fin(self, id_tarea):
        self.assertTrue(esperar(lambda: self.tareas.obtener(id_tarea)["estado"] != "en_curso", 10))
        return self.tareas.obtener(id_tarea)

    def test_resultado_y_seguimiento(self):
        puerta = threading.Event()
        creada = self.tareas.lanzar("prueba", "Trabajo largo", lambda: (puerta.wait(5), {"dato": 42})[1], url="/pagina?tarea={id}")
        self.assertEqual(creada["estado"], "en_curso")
        self.assertEqual(creada["url"], f"/pagina?tarea={creada['id']}")
        self.assertEqual(self.tareas.lista()[-1]["estado"], "en_curso", "sigue corriendo aunque nadie la mire")
        puerta.set()
        final = self.esperar_fin(creada["id"])
        self.assertEqual((final["estado"], final["resultado"]), ("terminado", {"dato": 42}))
        self.assertFalse(final["vista"])
        self.tareas.marcar(creada["id"])
        self.assertTrue(self.tareas.obtener(creada["id"])["notificada"])
        self.tareas.marcar(creada["id"], vista=True)
        self.assertTrue(self.tareas.obtener(creada["id"])["vista"])

    def test_errores_claros_y_archivos(self):
        def falla():
            raise ErrorUsuario("Mensaje claro para la persona.")

        def rompe():
            raise RuntimeError("detalle interno que no se debe mostrar")

        malo = self.esperar_fin(self.tareas.lanzar("prueba", "Falla", falla)["id"])
        self.assertEqual((malo["estado"], malo["error"]), ("error", "Mensaje claro para la persona."))
        roto = self.esperar_fin(self.tareas.lanzar("prueba", "Se rompe", rompe)["id"])
        self.assertEqual(roto["estado"], "error")
        self.assertNotIn("interno", roto["error"])
        conarchivo = self.esperar_fin(self.tareas.lanzar("prueba", "Archivo", lambda: ("archivo", b"%PDF-1", "application/pdf", "x.pdf"))["id"])
        self.assertEqual(self.tareas.archivo(conarchivo["id"]), (b"%PDF-1", "application/pdf", "x.pdf"))
        with self.assertRaises(ErrorUsuario):
            self.tareas.obtener("no_existe")
        with self.assertRaises(ErrorUsuario):
            self.tareas.archivo(malo["id"])

    def test_avance_paso_y_tiempo_que_falta(self):
        from nucleo import avance
        puertas = [threading.Event(), threading.Event()]

        def trabajo():
            avance.informar(0.25, "Paso 1 de 2")
            puertas[0].wait(5)
            with avance.tramo(0.5, 1):
                avance.informar(0.5, "Paso 2 de 2")
            puertas[1].wait(5)
            return {"ok": True}

        creada = self.tareas.lanzar("medida", "Trabajo medido", trabajo, url="/seccion?tarea={id}", origen="/api/tareas/medida")
        self.assertEqual((creada["pagina"], creada["origen"], creada["etiqueta"]), ("/seccion", "/api/tareas/medida", "Ver resultado"))
        self.assertTrue(esperar(lambda: self.tareas.obtener(creada["id"])["paso"] == "Paso 1 de 2", 5))
        self.assertAlmostEqual(self.tareas.obtener(creada["id"])["progreso"], 0.25, delta=0.03)
        puertas[0].set()
        self.assertTrue(esperar(lambda: self.tareas.obtener(creada["id"])["paso"] == "Paso 2 de 2", 5))
        self.assertAlmostEqual(self.tareas.obtener(creada["id"])["progreso"], 0.75, delta=0.03, msg="la mitad del tramo 0,5-1")
        time.sleep(1.1)
        self.assertGreaterEqual(self.tareas.obtener(creada["id"])["falta"], 1, "con el avance real ya se calcula cuánto falta")
        sola = self.tareas.obtener(creada["id"])["progreso"]
        self.assertTrue(0.75 < sola <= 0.95, "entre un paso y otro la barra sigue avanzando sola, sin pasar del tope")
        puertas[1].set()
        final = self.esperar_fin(creada["id"])
        self.assertEqual((final["progreso"], final["falta"]), (1.0, 0))

        # Sin pasos y sin historia no se inventa un porcentaje; con historia, la barra avanza por el tiempo que suele tardar.
        puerta = threading.Event()
        nueva = self.tareas.lanzar("nunca_vista", "Sin medida", lambda: puerta.wait(5) and None)
        repetida = self.tareas.lanzar("medida", "Otra vez", lambda: puerta.wait(5) and None)
        time.sleep(0.4)
        self.assertIsNone(self.tareas.obtener(nueva["id"])["progreso"])
        en_marcha = self.tareas.obtener(repetida["id"])
        self.assertGreater(en_marcha["progreso"], 0)
        self.assertLess(en_marcha["progreso"], 1)
        self.assertGreaterEqual(en_marcha["falta"], 1)
        puerta.set()
        self.esperar_fin(nueva["id"])
        self.esperar_fin(repetida["id"])

    def test_los_tiempos_se_recuerdan_entre_sesiones(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "datos" / "tiempos.json"
            primera = Tareas(ruta)
            primera.lanzar("rapida", "Rápida", lambda: time.sleep(0.2))
            self.assertTrue(esperar(ruta.exists, 5))
            self.assertTrue(esperar(lambda: "rapida" in Tareas(ruta)._tiempos, 5))
            self.assertIsNotNone(Tareas(ruta).crear("rapida", "Rápida")["previsto"])


class PruebasRutasDeTareas(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        base = Path(self.temporal.name)
        shutil.copytree(CARPETA_MODELOS / "v1", base / "modelos" / "v1")
        (base / "resultados").mkdir()
        shutil.copytree(RAIZ / "resultados" / "v1", base / "resultados" / "v1")
        shutil.copytree(RAIZ / "resultados" / "preprocesado", base / "resultados" / "preprocesado")
        self.parches = [mock.patch("nucleo.servicio.CARPETA_MODELOS", base / "modelos"),
                        mock.patch("nucleo.servicio.CARPETA_FOTOS", base / "fotos"),
                        mock.patch("nucleo.graficos.CARPETA_RESULTADOS", base / "resultados"),
                        mock.patch("nucleo.informe.CARPETA_RESULTADOS", base / "resultados")]
        for p in self.parches:
            p.start()
        self.original = (aplicacion.servicio, aplicacion.tareas)
        aplicacion.servicio = Servicio(Almacen(base / "prueba.db"))
        aplicacion.tareas = Tareas()
        self.cliente = aplicacion.app.test_client()

    def tearDown(self):
        aplicacion.servicio, aplicacion.tareas = self.original
        for p in self.parches:
            p.stop()
        self.temporal.cleanup()

    def esperar_fin(self, id_tarea):
        self.assertTrue(esperar(lambda: self.cliente.get(f"/api/tareas/{id_tarea}").get_json()["estado"] != "en_curso", 90))
        return self.cliente.get(f"/api/tareas/{id_tarea}").get_json()

    def test_informe_en_segundo_plano_y_aviso(self):
        creada = self.cliente.post("/api/tareas/informe", json={"secciones": ["resumen"]}).get_json()
        self.assertEqual(creada["tipo"], "informe")
        # Aunque la persona "se vaya a otra pagina", la tarea sigue y queda pendiente de avisar.
        final = self.esperar_fin(creada["id"])
        self.assertEqual(final["estado"], "terminado")
        self.assertEqual(final["url"], f"/informe?tarea={creada['id']}")
        listado = self.cliente.get("/api/tareas").get_json()["tareas"]
        pendiente = next(t for t in listado if t["id"] == creada["id"])
        self.assertEqual((pendiente["notificada"], pendiente["vista"]), (False, False))
        pdf = self.cliente.get(f"/api/tareas/{creada['id']}/archivo")
        self.assertEqual(pdf.mimetype, "application/pdf")
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        self.cliente.post(f"/api/tareas/{creada['id']}/notificada")
        self.cliente.post(f"/api/tareas/{creada['id']}/vista")
        listado = self.cliente.get("/api/tareas").get_json()["tareas"]
        visto = next(t for t in listado if t["id"] == creada["id"])
        self.assertEqual((visto["notificada"], visto["vista"]), (True, True))

    def test_correccion_con_error_llega_como_tarea(self):
        creada = self.cliente.post("/api/tareas/corregir", json={"lote": "lote_inexistente", "pagina": "ficticios"}).get_json()
        self.assertEqual(creada["url"], f"/ficticios?tarea={creada['id']}")
        final = self.esperar_fin(creada["id"])
        self.assertEqual(final["estado"], "error")
        self.assertIn("Primero predice", final["error"])

    def test_version_en_el_cuerpo_json_se_respeta(self):
        respuesta = self.cliente.post("/api/tareas/graficos", json={"version": "v99"})
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("no existe", respuesta.get_json()["error"])
        self.assertEqual(self.cliente.get("/api/tareas/no_existe").status_code, 400)

    def test_rutas_lentas_corren_como_tarea_con_la_cabecera(self):
        directa = self.cliente.get("/api/graficos").get_json()
        self.assertNotIn("origen", directa, "sin la cabecera responde como siempre")
        creada = self.cliente.get("/api/graficos", headers={"X-Tarea": "1"}).get_json()
        self.assertEqual((creada["pagina"], creada["origen"], creada["etiqueta"]), ("/graficos", "/api/graficos", "Ir a la sección"))
        final = self.esperar_fin(creada["id"])
        self.assertEqual((final["estado"], final["resultado"]), ("terminado", directa))

        mala = self.cliente.post("/api/predecir", json={"lote": "lote_inexistente", "textos": {}}, headers={"X-Tarea": "1"}).get_json()
        final = self.esperar_fin(mala["id"])
        self.assertEqual(final["estado"], "error")
        self.assertIn("No hay fotos", final["error"])

    def test_el_codigo_se_empaqueta_como_tarea(self):
        creada = self.cliente.post("/api/tareas/codigo-zip").get_json()
        self.assertEqual((creada["pagina"], creada["etiqueta"]), ("/informe", "Descargar"))
        final = self.esperar_fin(creada["id"])
        self.assertEqual(final["estado"], "terminado")
        archivo = self.cliente.get(final["url"])
        self.assertEqual(archivo.mimetype, "application/zip")
        self.assertTrue(archivo.data.startswith(b"PK"))

    def test_el_avance_se_reparte_por_tramos(self):
        from nucleo import avance
        pasos = []
        avance.escuchar(lambda fraccion, paso: pasos.append((fraccion, paso)))
        try:
            with avance.tramo(0.2, 0.4):
                avance.informar(0.5, "mitad")
        finally:
            avance.escuchar(None)
        self.assertAlmostEqual(pasos[-1][0], 0.3)
        self.assertEqual(pasos[-1][1], "mitad")
        avance.informar(0.9, "nadie escucha")
        self.assertEqual(len(pasos), 1)

    def test_entrenador_avisa_al_terminar(self):
        from nucleo.entrenador import Entrenador
        entrenador = Entrenador(aplicacion.servicio, aplicacion.tareas)
        original = aplicacion.entrenamientos
        aplicacion.entrenamientos = entrenador
        try:
            trabajo = self.cliente.post("/api/entrenador/iniciar", json={"modelo": "regresion_lineal", "parametros": {}, "muestras": 5000, "modo": "entrenar"}).get_json()
            self.assertTrue(trabajo["tarea"])
            self.assertEqual(self.cliente.get("/api/entrenador/ultimo").get_json()["trabajo"]["id"], trabajo["id"])
            self.assertTrue(esperar(lambda: self.cliente.get(f"/api/entrenador/estado/{trabajo['id']}").get_json()["estado"] != "en_curso", 60))
            tarea = self.cliente.get(f"/api/tareas/{trabajo['tarea']}").get_json()
            self.assertEqual((tarea["tipo"], tarea["estado"]), ("entrenador", "terminado"))
            self.assertEqual(tarea["url"], f"/entrenador?trabajo={trabajo['id']}")
        finally:
            aplicacion.entrenamientos = original


if __name__ == "__main__":
    unittest.main()
