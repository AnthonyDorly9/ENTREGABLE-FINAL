import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.datos import cargar_mnist, submuestra_estratificada
from nucleo.evaluacion import calcular_metricas
from nucleo.modelos import CLASES_MODELOS, crear_modelo


class PruebasDatos(unittest.TestCase):
    def test_forma_y_rango(self):
        x_ent, y_ent, x_pru, y_pru = cargar_mnist()
        self.assertEqual(x_ent.shape, (60000, 784))
        self.assertEqual(x_pru.shape, (10000, 784))
        self.assertGreaterEqual(x_ent.min(), 0.0)
        self.assertLessEqual(x_ent.max(), 1.0)
        self.assertEqual(set(np.unique(y_ent)), set(range(10)))

    def test_submuestra_conserva_proporcion(self):
        _, y, _, _ = cargar_mnist()
        X = np.zeros((len(y), 1), dtype=np.float32)
        _, y_sub = submuestra_estratificada(X, y, 2000)
        self.assertAlmostEqual(len(y_sub), 2000, delta=10)
        conteos = np.bincount(y_sub, minlength=10)
        self.assertTrue((conteos > 150).all())


class PruebasEvaluacion(unittest.TestCase):
    def test_prediccion_perfecta(self):
        y = np.arange(10)
        metricas = calcular_metricas(y, y)
        self.assertEqual(metricas["exactitud"], 1.0)
        self.assertEqual(metricas["f1_macro"], 1.0)
        self.assertEqual(np.trace(np.array(metricas["matriz_confusion"])), 10)


class PruebasModelos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        x_ent, y_ent, x_pru, y_pru = cargar_mnist()
        cls.X, cls.y = submuestra_estratificada(x_ent, y_ent, 1500)
        cls.Xp, cls.yp = x_pru[:300], y_pru[:300]

    def test_todos_los_modelos_entrenan_y_predicen(self):
        for clave in CLASES_MODELOS:
            with self.subTest(modelo=clave):
                modelo = crear_modelo(clave, **({"epocas": 2} if clave in ("cnn", "mlp") else {}))
                modelo.entrenar(self.X, self.y)
                probabilidades = modelo.probabilidades(self.Xp)
                self.assertEqual(probabilidades.shape, (300, 10))
                np.testing.assert_allclose(probabilidades.sum(axis=1), 1.0, atol=1e-4)
                self.assertGreater((modelo.predecir(self.Xp) == self.yp).mean(), 0.5)

    def test_arquitectura_coincide_con_parametros_reales(self):
        for clave in ("cnn", "mlp"):
            with self.subTest(modelo=clave):
                modelo = crear_modelo(clave, epocas=1)
                modelo.entrenar(self.X[:200], self.y[:200])
                self.assertEqual(modelo.arquitectura()["parametros_totales"], modelo.total_parametros())

    def test_guardar_y_cargar_da_las_mismas_predicciones(self):
        import tempfile

        for clave in CLASES_MODELOS:
            with self.subTest(modelo=clave):
                modelo = crear_modelo(clave, **({"epocas": 1} if clave in ("cnn", "mlp") else {}))
                modelo.entrenar(self.X[:500], self.y[:500])
                with tempfile.TemporaryDirectory() as carpeta:
                    ruta = Path(carpeta) / "m.joblib"
                    modelo.guardar(ruta)
                    recuperado = type(modelo).cargar(ruta)
                np.testing.assert_array_equal(modelo.predecir(self.Xp), recuperado.predecir(self.Xp))


if __name__ == "__main__":
    unittest.main()
