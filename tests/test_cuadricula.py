"""Pruebas de fotos difíciles: hojas cuadriculadas o rayadas de colores, tintas de colores, fotos giradas y números
chicos o lejanos. Usan fotos simuladas con dígitos de MNIST y la CNN de v1 (solo se lee, no se modifica)."""
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.configuracion import CARPETA_MODELOS
from nucleo.datos import cargar_mnist
from nucleo.formularios_ficticios import COLORES_CUADRICULA, COLORES_TINTA, TIPOS_FORMULARIO, GeneradorDigitos
from nucleo.modelos import ModeloBase
from nucleo.preprocesado import (LADO_GUARDADO, _lineas_largas, decodificar_imagen, orientar, procesar_foto,
                                 quitar_cuadricula)


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


class PruebasFotosDificiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, x_pru, y_pru = cargar_mnist()
        cls.x_pru, cls.y_pru = x_pru, y_pru
        cls.cnn = ModeloBase.cargar(CARPETA_MODELOS / "v1" / "cnn.joblib")

    def generador(self, semilla):
        return GeneradorDigitos(self.x_pru, self.y_pru, semilla=semilla)

    def leer(self, foto, texto):
        """Devuelve (cantidad correcta, numero exacto) para una foto."""
        r = procesar_foto(foto, esperado=len(texto))
        if len(r["cajas"]) != len(texto):
            return False, False
        return True, "".join(str(d) for d in self.cnn.predecir(r["digitos"])) == texto

    def resumen(self, fotos):
        lecturas = [self.leer(f, t) for f, t in fotos]
        return np.mean([c for c, _ in lecturas]), np.mean([e for _, e in lecturas])

    def numero(self, g):
        return g.numero_aleatorio(int(g.azar.integers(1, 6)))

    # --- Hojas cuadriculadas y rayadas ---

    def test_cada_color_de_cuadricula(self):
        g = self.generador(101)
        for color in COLORES_CUADRICULA:
            with self.subTest(cuadricula=color):
                fotos = [(g.foto_cuadriculada(t, 0.4, color_linea=color), t) for t in (self.numero(g) for _ in range(8))]
                cantidad, exacto = self.resumen(fotos)
                self.assertGreaterEqual(cantidad, 0.85)
                self.assertGreaterEqual(exacto, 0.5)

    def test_cada_color_de_tinta_sobre_cuadricula_oscura(self):
        g = self.generador(102)
        for cuadricula in ((160, 80, 20), (60, 60, 60), (60, 60, 200), (60, 130, 40)):
            for tinta in COLORES_TINTA:
                with self.subTest(cuadricula=cuadricula, tinta=tinta):
                    fotos = [(g.foto_cuadriculada(t, 0.4, color_linea=cuadricula, color_tinta=tinta), t)
                             for t in (self.numero(g) for _ in range(6))]
                    cantidad, _ = self.resumen(fotos)
                    self.assertGreaterEqual(cantidad, 0.8)

    def test_en_conjunto_se_leen_bien_las_hojas_cuadriculadas(self):
        g = self.generador(103)
        fotos = [(g.foto_cuadriculada(t, float(g.azar.uniform(0.1, 0.8))), t) for t in (self.numero(g) for _ in range(80))]
        cantidad, exacto = self.resumen(fotos)
        self.assertGreaterEqual(cantidad, 0.95)
        self.assertGreaterEqual(exacto, 0.75)

    def test_la_cuadricula_desaparece_de_la_imagen_binaria(self):
        g = self.generador(104)
        for _ in range(10):
            texto = self.numero(g)
            r = procesar_foto(g.foto_cuadriculada(texto, 0.3, color_linea=(60, 60, 60)), esperado=len(texto))
            binaria = r["binaria"]
            for horizontal in (True, False):
                lineas = _lineas_largas(binaria, horizontal)
                largo = binaria.shape[1] if horizontal else binaria.shape[0]
                cantidad, _, estadisticas, _ = cv2.connectedComponentsWithStats(lineas)
                largos = estadisticas[1:, cv2.CC_STAT_WIDTH if horizontal else cv2.CC_STAT_HEIGHT]
                self.assertFalse((largos >= 0.8 * largo).any(), "no deben quedar líneas que crucen la foto")

    def test_cuadricula_torcida_y_foto_grande_de_celular(self):
        g = self.generador(105)
        fotos = []
        for texto in (self.numero(g) for _ in range(12)):
            foto = g.foto_cuadriculada(texto, 0.8, color_linea=(160, 80, 20))
            fotos.append((cv2.resize(foto, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC), texto))
        cantidad, exacto = self.resumen(fotos)
        self.assertGreaterEqual(cantidad, 0.9)
        self.assertGreaterEqual(exacto, 0.6)

    def test_quitar_cuadricula_no_cambia_una_hoja_lisa(self):
        g = self.generador(106)
        for _ in range(10):
            foto = g.foto_numero(self.numero(g), dificultad=0.4)
            binaria = procesar_foto(foto)["pasos"]["binaria"]
            self.assertTrue((quitar_cuadricula(binaria) == binaria).all())

    def test_hojas_vacias_o_con_ruido_no_fallan(self):
        azar = np.random.default_rng(7)
        vacia = np.full((750, 1000, 3), 225, np.uint8)
        ruidosa = np.clip(vacia + azar.normal(0, 12, vacia.shape), 0, 255).astype(np.uint8)
        g = self.generador(107)
        solo_cuadricula = g.foto_cuadriculada("1", 0.3, color_linea=(60, 60, 60))
        solo_cuadricula[:] = np.where(solo_cuadricula.min(axis=2, keepdims=True) < 90, solo_cuadricula, 235)
        for foto in (vacia, ruidosa, np.zeros((300, 400, 3), np.uint8), solo_cuadricula):
            procesar_foto(foto)
        self.assertEqual(len(procesar_foto(vacia)["cajas"]), 0)

    # --- Que lo que ya funcionaba siga igual ---

    def test_fotos_lisas_siguen_igual_de_bien(self):
        g = self.generador(108)
        fotos = [(g.foto_numero(t, dificultad=0.4), t) for t in (self.numero(g) for _ in range(40))]
        cantidad, exacto = self.resumen(fotos)
        self.assertEqual(cantidad, 1.0)
        self.assertGreaterEqual(exacto, 0.85)

    def test_casillas_de_formulario_siguen_igual_de_bien(self):
        g = self.generador(109)
        fotos = []
        for tipo in TIPOS_FORMULARIO:
            for _ in range(3):
                imagen, campos = g.formulario(tipo, dificultad=0.3)
                for campo in campos:
                    x, y, w, h = campo["caja"]
                    fotos.append((imagen[y + 6 : y + h - 6, x + 6 : x + w - 6], campo["valor"]))
        cantidad, exacto = self.resumen(fotos)
        self.assertGreaterEqual(cantidad, 0.95)
        self.assertGreaterEqual(exacto, 0.75)

    # --- Números chicos o lejanos ---

    def test_numeros_chicos_o_lejanos(self):
        g = self.generador(110)
        for altura in (35, 25, 18, 12):
            with self.subTest(altura_digito=altura):
                fotos = [(foto_lejana(g, t, altura), t) for t in (self.numero(g) for _ in range(10))]
                cantidad, exacto = self.resumen(fotos)
                self.assertGreaterEqual(cantidad, 0.9)
                self.assertGreaterEqual(exacto, 0.6)

    def test_las_fotos_se_guardan_con_mas_detalle(self):
        foto = np.full((3000, 4000, 3), 220, np.uint8)
        datos = cv2.imencode(".jpg", foto)[1].tobytes()
        self.assertEqual(max(decodificar_imagen(datos).shape[:2]), LADO_GUARDADO)
        chica = cv2.imencode(".png", np.full((300, 400, 3), 220, np.uint8))[1].tobytes()
        self.assertEqual(decodificar_imagen(chica).shape[:2], (300, 400))

    # --- Fotos giradas ---

    def confianza(self, X):
        return self.cnn.probabilidades(X).max(axis=1)

    def test_una_foto_derecha_no_se_gira(self):
        g = self.generador(111)
        fotos = [g.foto_numero(self.numero(g), dificultad=0.4) for _ in range(30)]
        fotos += [g.foto_cuadriculada(self.numero(g), 0.4) for _ in range(15)]
        giradas = sum(orientar(f, self.confianza)[0] is not None for f in fotos)
        self.assertLessEqual(giradas, 1)

    def test_fotos_de_lado_se_enderezan(self):
        g = self.generador(112)
        textos = [t for t in (g.numero_aleatorio(int(g.azar.integers(2, 6))) for _ in range(60)) if set(t) <= set("23457")][:20]
        for giro, inverso in ((cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE),
                              (cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_90_CLOCKWISE)):
            with self.subTest(giro=giro):
                bien = sum(orientar(cv2.rotate(g.foto_numero(t, dificultad=0.3), giro), self.confianza)[0] == inverso
                           for t in textos)
                self.assertGreaterEqual(bien / len(textos), 0.7)

    def test_foto_de_cabeza_nunca_se_gira_de_lado(self):
        # De cabeza es dificil de distinguir (6/9, 0, 1, 8): se prefiere no girar antes que estropear una foto derecha,
        # y para eso esta el boton «Girar». Lo que no puede pasar es que la deje de lado.
        g = self.generador(113)
        textos = [t for t in (g.numero_aleatorio(int(g.azar.integers(2, 6))) for _ in range(150)) if set(t) <= set("2347")][:20]
        giros = [orientar(cv2.rotate(g.foto_numero(t, dificultad=0.3), cv2.ROTATE_180), self.confianza)[0] for t in textos]
        self.assertTrue(all(giro in (None, cv2.ROTATE_180) for giro in giros))
        self.assertGreaterEqual(giros.count(cv2.ROTATE_180), 1)


if __name__ == "__main__":
    unittest.main()
