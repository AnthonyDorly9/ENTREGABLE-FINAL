import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class PruebasScripts(unittest.TestCase):
    def test_la_sintaxis_de_todos_los_scripts_es_valida(self):
        scripts = sorted((RAIZ / "recursos" / "js").glob("*.js"))
        self.assertTrue(scripts)
        for ruta in scripts:
            with self.subTest(script=ruta.name):
                try:
                    resultado = subprocess.run(["node", "--check", str(ruta)], capture_output=True, text=True)
                except FileNotFoundError:
                    self.skipTest("node no esta instalado")
                self.assertEqual(resultado.returncode, 0, resultado.stderr)


if __name__ == "__main__":
    unittest.main()
