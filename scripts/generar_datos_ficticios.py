"""Agrega formularios y numeros ficticios "escritos a mano" a datos/ficticios/ con sus etiquetas reales.

No borra lo que ya existe: cada ejecucion suma imagenes nuevas de distintos niveles de dificultad.
"""
import argparse

from nucleo.datos import cargar_mnist
from nucleo.formularios_ficticios import GeneradorDigitos
from nucleo.ficticios import CARPETA_EJEMPLOS, ampliar_banco


def main():
    analizador = argparse.ArgumentParser()
    analizador.add_argument("--formularios-por-tipo", type=int, default=6, help="formularios nuevos de cada tipo")
    analizador.add_argument("--numeros", type=int, default=120, help="fotos de numeros nuevas")
    analizador.add_argument("--semilla", type=int, default=2024)
    argumentos = analizador.parse_args()

    _, _, x_pru, y_pru = cargar_mnist()
    creados = ampliar_banco(GeneradorDigitos(x_pru, y_pru, semilla=argumentos.semilla), argumentos.formularios_por_tipo, argumentos.numeros)
    print(f"Agregados {creados['formularios']} formularios y {creados['numeros']} numeros en {CARPETA_EJEMPLOS}")


if __name__ == "__main__":
    main()
