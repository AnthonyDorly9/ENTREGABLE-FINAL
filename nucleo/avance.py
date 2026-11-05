"""Avance de los procesos largos: el codigo que trabaja va diciendo por donde va, sin saber quien lo escucha.

La tarea en segundo plano deja un «oyente» en su hilo. Si nadie escucha (pruebas, llamadas directas), no pasa nada.
"""
import threading
from contextlib import contextmanager

_hilo = threading.local()


def escuchar(oyente):
    """Deja en este hilo la funcion que recibe (fraccion, paso). Con None se deja de escuchar."""
    _hilo.oyente = oyente
    _hilo.tramos = []


def informar(fraccion, paso=None):
    """`fraccion` va de 0 a 1 dentro del tramo abierto; `paso` es el texto que ve la persona («Modelo 3 de 7: SVM»)."""
    oyente = getattr(_hilo, "oyente", None)
    if not oyente:
        return
    fraccion = min(1.0, max(0.0, float(fraccion)))
    for inicio, fin in reversed(_hilo.tramos):
        fraccion = inicio + (fin - inicio) * fraccion
    oyente(fraccion, paso)


@contextmanager
def tramo(inicio, fin):
    """Dentro del bloque, el avance de 0 a 1 que se informe ocupa solo el trozo `inicio`-`fin` del total."""
    tramos = getattr(_hilo, "tramos", None)
    if tramos is None:
        yield
        return
    tramos.append((inicio, fin))
    try:
        yield
    finally:
        tramos.pop()
