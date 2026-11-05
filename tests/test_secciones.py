import base64
import io
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as aplicacion
from nucleo.almacen import Almacen
from nucleo.configuracion import CARPETA_MODELOS, CLAVES_MODELOS
from nucleo.entrenador import Entrenador
from nucleo.ficticios import Ficticios
from nucleo.servicio import Servicio


def dibujo_de_un_siete():
    lienzo = np.zeros((280, 280), np.uint8)
    cv2.line(lienzo, (60, 60), (220, 60), 255, 22)
    cv2.line(lienzo, (220, 60), (110, 230), 255, 22)
    _, buffer = cv2.imencode(".png", lienzo)
    return "data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode()


class PruebasSecciones(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        base = Path(self.temporal.name)
        import shutil
        shutil.copytree(CARPETA_MODELOS / "v1", base / "modelos" / "v1")
        self.parches = [mock.patch("nucleo.servicio.CARPETA_FOTOS", base / "fotos"),
                        mock.patch("nucleo.servicio.CARPETA_MODELOS", base / "modelos"),
                        mock.patch("nucleo.entrenador.RUTA_INTENTOS", base / "intentos.json"),
                        mock.patch("nucleo.graficos.CARPETA_RESULTADOS", base / "resultados")]
        for p in self.parches:
            p.start()
        (base / "resultados").mkdir()
        shutil.copytree(Path(aplicacion.CODIGO) / "resultados" / "v1", base / "resultados" / "v1")
        self.original = (aplicacion.servicio, aplicacion.entrenamientos, aplicacion.ficticios)
        aplicacion.servicio = Servicio(Almacen(base / "prueba.db"))
        aplicacion.entrenamientos = Entrenador(aplicacion.servicio)
        aplicacion.ficticios = Ficticios(aplicacion.servicio)
        self.cliente = aplicacion.app.test_client()

    def tearDown(self):
        aplicacion.servicio, aplicacion.entrenamientos, aplicacion.ficticios = self.original
        for p in self.parches:
            p.stop()
        self.temporal.cleanup()

    def test_paginas_de_todas_las_secciones(self):
        for ruta in ("/", "/resumen", "/graficos", "/entrenador", "/antes-y-despues", "/por-dentro", "/ficticios", "/informe"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.cliente.get(ruta).status_code, 200)

    def test_graficos_generar_y_casilla(self):
        primera = self.cliente.get("/api/graficos?version=v1").get_json()
        self.assertTrue(primera["listo"])
        self.assertEqual(len(primera["imagenes"]["mapa"]), len(CLAVES_MODELOS), "las imagenes deben crearse solas si faltan")
        self.assertEqual(len(primera["imagenes"]["predicciones"]), len(CLAVES_MODELOS), "una galeria Real / Predijo por modelo")
        urls = [primera["imagenes"][k] for k in ("metricas", "curvas", "validacion", "velocidad")]
        urls += list(primera["imagenes"]["matriz"].values()) + list(primera["imagenes"]["mapa"].values()) + list(primera["imagenes"]["predicciones"].values())
        for url in urls:
            with self.subTest(url=url):
                respuesta = self.cliente.get(url)
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.mimetype, "image/png")
                self.assertTrue(respuesta.data.startswith(b"\x89PNG"))
                self.assertGreater(len(respuesta.data), 8000)
        self.assertEqual(self.cliente.get("/graficos-img/v1/../../app.py").status_code, 404)
        self.assertEqual(self.cliente.get("/graficos-img/v1/otra.png").status_code, 404)
        self.assertTrue(self.cliente.get("/figura/progreso.png").data.startswith(b"\x89PNG"))
        self.assertEqual(self.cliente.get("/descargar/graficos.zip?version=v1").mimetype, "application/zip")
        datos = self.cliente.post("/api/graficos/generar", json={"version": "v1"}).get_json()
        self.assertTrue(datos["listo"])
        self.assertEqual(set(datos["modelos"]), set(CLAVES_MODELOS))
        cnn = datos["modelos"]["cnn"]
        self.assertEqual(sum(map(sum, cnn["matriz_confusion"])), 10000)
        casilla = self.cliente.get("/api/matriz/imagenes?modelo=cnn&real=4&predicho=9").get_json()
        self.assertEqual(casilla["total"], cnn["matriz_confusion"][4][9])
        self.assertEqual(len(casilla["imagenes"]), min(16, casilla["total"]))
        self.assertEqual(self.cliente.get("/api/matriz/imagenes?modelo=xx&real=4&predicho=9").status_code, 400)

    def test_por_dentro(self):
        dentro = self.cliente.post("/api/por-dentro", json={"imagen": dibujo_de_un_siete()}).get_json()
        self.assertEqual(dentro["predicho"], 7)
        self.assertEqual(len(dentro["capas"]), 3)
        self.assertAlmostEqual(sum(dentro["probabilidades"]), 1.0, places=3)

    def test_formularios_ficticios(self):
        o = self.cliente.get("/api/ficticios/opciones").get_json()
        self.assertEqual(len(o["tipos"]), 3)
        f = self.cliente.post("/api/ficticios/generar", json={"tipo": "pago", "dificultad": 0.3}).get_json()
        self.assertEqual(len(f["campos"]), 4)
        lectura = self.cliente.get(f"/api/ficticios/leer/{f['token']}").get_json()
        cnn = next(x for x in lectura["resumen"] if x["modelo"] == "cnn")
        self.assertGreaterEqual(cnn["digitos_ok"] / cnn["digitos"], 0.8)
        self.assertEqual(self.cliente.post("/api/ficticios/generar", json={"tipo": "otro"}).status_code, 400)
        self.assertEqual(self.cliente.get("/api/ficticios/leer/noexiste").status_code, 400)
        if o["ejemplos"]:
            e = self.cliente.post("/api/ficticios/ejemplo", json={"nombre": o["ejemplos"][0]}).get_json()
            self.assertEqual(self.cliente.get(f"/api/ficticios/leer/{e['token']}").status_code, 200)

    def test_banco_galeria_ampliar_y_practicar(self):
        from nucleo.datos import cargar_mnist
        from nucleo.ficticios import ampliar_banco
        from nucleo.formularios_ficticios import GeneradorDigitos
        with mock.patch("nucleo.ficticios.CARPETA_EJEMPLOS", Path(self.temporal.name) / "banco"):
            _, _, x, y = cargar_mnist()
            self.assertEqual(ampliar_banco(GeneradorDigitos(x, y, semilla=3), 1, 12), {"formularios": 3, "numeros": 12, "cuadriculadas": 0})
            banco = self.cliente.get("/api/ficticios/opciones").get_json()["banco"]
            self.assertEqual((len(banco["formularios"]), len(banco["numeros"])), (3, 12))
            self.assertTrue({n["nivel"] for n in banco["numeros"]} >= {"Fácil", "Difícil"})
            nombre = banco["numeros"][0]["nombre"]
            miniatura = self.cliente.get(f"/ficticios-img/numeros/{nombre}?ancho=200")
            self.assertEqual((miniatura.status_code, miniatura.mimetype), (200, "image/jpeg"))
            self.assertEqual(self.cliente.get("/ficticios-img/numeros/no_existe.png").status_code, 400)
            self.assertEqual(self.cliente.get("/ficticios-img/otra/x.png").status_code, 400)
            abierto = self.cliente.post("/api/ficticios/numero", json={"nombre": nombre}).get_json()
            lectura = self.cliente.get(f"/api/ficticios/leer/{abierto['token']}").get_json()
            self.assertEqual(len(lectura["campos"]), 1)
            self.assertEqual(self.cliente.post("/api/ficticios/numero", json={"nombre": "../app.py"}).status_code, 400)
            # Al crear hay que elegir si o si la dificultad; todas las imagenes salen de ese nivel.
            sin_nivel = self.cliente.post("/api/ficticios/ampliar", json={"cantidad": 5})
            self.assertEqual((sin_nivel.status_code, sin_nivel.get_json()["error"]), (400, "Elige la dificultad antes de crear las imágenes."))
            self.assertEqual(self.cliente.post("/api/ficticios/ampliar", json={"cantidad": 5, "tipo": "otro", "nivel": "facil"}).status_code, 400)
            mas = self.cliente.post("/api/ficticios/ampliar", json={"cantidad": 5, "tipo": "liso", "nivel": "muy_dificil"}).get_json()
            self.assertEqual((mas["numeros"], mas["formularios"], mas["total_numeros"], mas["total_formularios"]), (5, 0, 17, 3))
            formularios = self.cliente.post("/api/ficticios/ampliar", json={"cantidad": 4, "tipo": "formularios", "nivel": "facil"}).get_json()
            self.assertEqual((formularios["formularios"], formularios["numeros"], formularios["total_formularios"]), (4, 0, 7))
            mas["nuevas"]["formularios"] = formularios["nuevas"]["formularios"]
            cuadriculadas = self.cliente.post("/api/ficticios/ampliar", json={"cantidad": 4, "tipo": "cuadriculado", "nivel": "mezcla"}).get_json()
            self.assertEqual((cuadriculadas["cuadriculadas"], cuadriculadas["numeros"], cuadriculadas["total_numeros"],
                              cuadriculadas["total_formularios"]), (4, 0, 21, 7))
            banco = self.cliente.get("/api/ficticios/opciones").get_json()["banco"]
            nuevas = [n for n in banco["numeros"] if n["nombre"].startswith("cuadriculada_")]
            self.assertEqual(len(nuevas), 4)
            cuadriculada = self.cliente.post("/api/ficticios/numero", json={"nombre": nuevas[0]["nombre"]}).get_json()
            leida = self.cliente.get(f"/api/ficticios/leer/{cuadriculada['token']}").get_json()
            self.assertEqual(len(leida["campos"][0]["recortes"]), len(nuevas[0]["texto"]), "la cuadrícula no debe impedir encontrar los dígitos")
            niveles = {n["nombre"]: n["nivel"] for c in ("numeros", "formularios") for n in banco[c]}
            self.assertEqual({niveles[n] for n in mas["nuevas"]["numeros"]}, {"Muy difícil"})
            self.assertEqual({niveles[n] for n in formularios["nuevas"]["formularios"]}, {"Fácil"})
            self.assertGreater(len({niveles[n] for n in cuadriculadas["nuevas"]["numeros"]}), 1, "«mezcla» da varios niveles")
            pagina = self.cliente.get("/ficticios").get_data(as_text=True)
            self.assertIn("Probar con ejemplos", pagina)
            for pieza in ('id="entrenar-elegidas"', 'id="mandar-basura"', 'id="aviso-nuevas"', 'id="abrir-basura-imagenes"', 'id="orden-galeria"',
                          'id="abrir-crear"', 'id="ventana-crear"', 'data-valor="muy_dificil"'):
                self.assertIn(pieza, pagina)
            self.assertNotIn('id="practicar"', pagina, "la práctica al azar se quitó: ahora se eligen las imágenes")

            # Lo recien creado se avisa: la respuesta dice cuales son y llevan fecha para salir primeras.
            self.assertEqual((len(mas["nuevas"]["numeros"]), len(mas["nuevas"]["formularios"])), (5, 4))
            self.assertEqual(len(cuadriculadas["nuevas"]["numeros"]), 4)
            creadas = {n["nombre"]: n["creada"] for n in banco["numeros"]}
            self.assertTrue(all(creadas[n] > 0 for n in mas["nuevas"]["numeros"]))

            # Entrenar con las imagenes elegidas: se leen como una tanda y aprenden los que fallan.
            elegidas = [n["nombre"] for n in banco["numeros"][:6]]
            practica = aplicacion.ficticios.entrenar_elegidas(elegidas)
            self.assertEqual((practica["fotos"], len(practica["marcador"])), (6, len(CLAVES_MODELOS)))
            self.assertEqual(len(self.cliente.get(f"/api/lote/{practica['lote']}").get_json()["fotos"]), 6)
            self.assertTrue(practica["correccion"] or "Ningún modelo se equivocó" in practica["mensaje"])
            if practica["correccion"]:
                self.assertIn("informe", practica["correccion"])
            tarea = self.cliente.post("/api/tareas/ficticios-entrenar", json={"nombres": []}).get_json()
            self.assertEqual(tarea["url"], f"/ficticios?tarea={tarea['id']}")
            for _ in range(100):
                estado = self.cliente.get(f"/api/tareas/{tarea['id']}").get_json()
                if estado["estado"] != "en_curso":
                    break
                time.sleep(0.05)
            self.assertEqual((estado["estado"], estado["error"]), ("error", "Elige al menos una imagen."))
            with self.assertRaisesRegex(Exception, "máximo 20"):
                aplicacion.ficticios.entrenar_elegidas([f"numero_{i:03d}.png" for i in range(1, 22)])
            with self.assertRaisesRegex(Exception, "ya no existe"):
                aplicacion.ficticios.entrenar_elegidas(["no_existe.png"])

            # Basura de imagenes: quitar varias, restaurar una, borrar otra para siempre y vaciar.
            carpeta_banco = Path(self.temporal.name) / "banco"
            quitar = [n["nombre"] for n in banco["numeros"][:3]]
            quitado = self.cliente.post("/api/ficticios/quitar", json={"carpeta": "numeros", "nombres": quitar}).get_json()
            self.assertEqual((quitado["quitadas"], quitado["total_numeros"], quitado["en_basura"]), (quitar, 18, 3))
            self.assertFalse((carpeta_banco / "numeros" / quitar[0]).exists())
            self.assertTrue((carpeta_banco / "_papelera" / "numeros" / quitar[0]).exists())
            en_galeria = {n["nombre"] for n in self.cliente.get("/api/ficticios/opciones").get_json()["banco"]["numeros"]}
            self.assertFalse(en_galeria & set(quitar))
            self.assertEqual({b["nombre"] for b in self.cliente.get("/api/ficticios/basura").get_json()["basura"]}, set(quitar))
            self.assertEqual(self.cliente.get(f"/ficticios-img/numeros/{quitar[0]}?basura=1").status_code, 200)
            self.assertEqual(self.cliente.get(f"/ficticios-img/numeros/{quitar[0]}").status_code, 400)
            self.assertEqual(self.cliente.post("/api/ficticios/numero", json={"nombre": quitar[0]}).status_code, 400)
            self.assertEqual(self.cliente.post("/api/ficticios/quitar", json={"carpeta": "numeros", "nombres": quitar[:1]}).status_code, 400)
            self.assertEqual(self.cliente.post("/api/ficticios/quitar", json={"carpeta": "../x", "nombres": ["a.png"]}).status_code, 400)
            self.assertEqual(self.cliente.post("/api/ficticios/quitar", json={"carpeta": "numeros", "nombres": []}).status_code, 400)
            # Las de la basura siguen ocupando su numero: lo nuevo no pisa lo que se puede restaurar.
            otra = self.cliente.post("/api/ficticios/ampliar", json={"cantidad": 1, "tipo": "liso", "nivel": "normal"}).get_json()
            self.assertFalse(set(otra["nuevas"]["numeros"]) & set(quitar))
            texto_original = next(n["texto"] for n in banco["numeros"] if n["nombre"] == quitar[0])
            restaurado = self.cliente.post("/api/ficticios/basura/restaurar", json={"carpeta": "numeros", "nombres": quitar[:1]}).get_json()
            self.assertEqual((restaurado["restauradas"], restaurado["en_basura"]), (quitar[:1], 2))
            vuelto = next(n for n in self.cliente.get("/api/ficticios/opciones").get_json()["banco"]["numeros"] if n["nombre"] == quitar[0])
            self.assertEqual(vuelto["texto"], texto_original)
            self.assertTrue((carpeta_banco / "numeros" / quitar[0]).exists())
            borrado = self.cliente.post("/api/ficticios/basura/borrar-para-siempre", json={"carpeta": "numeros", "nombres": quitar[1:2]}).get_json()
            self.assertEqual((borrado["borradas"], borrado["en_basura"]), (1, 1))
            self.assertFalse((carpeta_banco / "_papelera" / "numeros" / quitar[1]).exists())
            formulario = banco["formularios"][0]["nombre"]
            self.assertEqual(self.cliente.post("/api/ficticios/quitar", json={"carpeta": "formularios", "nombres": [formulario]}).get_json()["en_basura"], 2)
            vaciado = self.cliente.post("/api/ficticios/basura/vaciar").get_json()
            self.assertEqual((vaciado["borradas"], vaciado["en_basura"]), (2, 0))
            self.assertEqual(self.cliente.get("/api/ficticios/basura").get_json()["basura"], [])

            # Corregir a los modelos que se equivocaron desde una imagen abierta.
            desde_imagen = self.cliente.post("/api/ficticios/corregir", json={"token": abierto["token"]})
            self.assertIn(desde_imagen.status_code, (200, 400))
            if desde_imagen.status_code == 400:
                self.assertIn("Ningún modelo se equivocó", desde_imagen.get_json()["error"])
            self.assertEqual(self.cliente.post("/api/ficticios/corregir", json={"token": "noexiste"}).status_code, 400)

    def test_entrenador_entrenar_y_adoptar(self):
        opciones = self.cliente.get("/api/entrenador/opciones").get_json()
        self.assertEqual(len(opciones["modelos"]), len(CLAVES_MODELOS))
        malo = self.cliente.post("/api/entrenador/iniciar", json={"modelo": "knn", "parametros": {"k": 99}, "muestras": 5000, "modo": "entrenar"})
        self.assertEqual(malo.status_code, 400)
        trabajo = self.cliente.post("/api/entrenador/iniciar", json={"modelo": "knn", "parametros": {"k": 5}, "muestras": 5000, "modo": "entrenar"}).get_json()
        for _ in range(120):
            estado = self.cliente.get(f"/api/entrenador/estado/{trabajo['id']}").get_json()
            if estado["estado"] != "en_curso":
                break
            time.sleep(0.5)
        self.assertEqual(estado["estado"], "terminado", estado.get("error"))
        self.assertGreater(estado["resultado"]["exactitud"], 0.9)
        adoptado = self.cliente.post("/api/entrenador/adoptar", json={"id": trabajo["id"]}).get_json()
        self.assertEqual(adoptado["version_nueva"], "v2")
        self.assertEqual(aplicacion.servicio.version_activa(), "v2")
        self.assertEqual(self.cliente.post("/api/entrenador/adoptar", json={"id": trabajo["id"]}).status_code, 400)
        self.assertEqual(len(self.cliente.get("/api/entrenador/opciones").get_json()["intentos"]), 1)

    def test_entrenador_validar(self):
        trabajo = self.cliente.post("/api/entrenador/iniciar", json={"modelo": "regresion", "parametros": {}, "muestras": 5000, "modo": "validar"}).get_json()
        for _ in range(240):
            estado = self.cliente.get(f"/api/entrenador/estado/{trabajo['id']}").get_json()
            if estado["estado"] != "en_curso":
                break
            time.sleep(0.5)
        self.assertEqual(estado["estado"], "terminado", estado.get("error"))
        self.assertEqual(len(estado["resultado"]["exactitudes"]), 5)


if __name__ == "__main__":
    unittest.main()
