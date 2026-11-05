"""Tareas en segundo plano: procesos largos que siguen corriendo aunque la persona cambie de seccion.

Cada tarea tiene un estado (en_curso, terminado o error) y su resultado queda guardado hasta que se ve.
Mientras corre, cuenta cuanto lleva (de 0 a 1), en que paso va y cuantos segundos le faltan.
"""
import json
import math
import threading
import time
import traceback
import uuid
from collections import OrderedDict

from . import avance
from .servicio import ErrorUsuario

CAMPOS_PUBLICOS = ("id", "tipo", "titulo", "final", "estado", "mensaje", "creada", "terminada", "error", "url", "notificada", "vista",
                   "pagina", "origen", "etiqueta")
# Entre un paso y el siguiente, la barra sigue avanzando sola, como mucho este trozo, al ritmo que llevaba la tarea.
ADELANTO = 0.25
# Sin pasos ni tiempo recordado la barra no pasa de aqui hasta que la tarea termina de verdad.
TOPE = 0.95
# Ritmo mas rapido que se supone al seguir avanzando sola: segundos que tardaria la tarea entera.
MINIMO_SEGUNDOS = 4.0


class Tareas:
    MAXIMO = 40

    def __init__(self, ruta_tiempos=None):
        """`ruta_tiempos`: archivo donde se recuerda cuanto tardo cada clase de tarea, para calcular cuanto falta."""
        self._tareas = OrderedDict()
        self._candado = threading.Lock()
        self._ruta_tiempos = ruta_tiempos
        self._tiempos = {}
        if ruta_tiempos and ruta_tiempos.exists():
            try:
                self._tiempos = {k: float(v) for k, v in json.loads(ruta_tiempos.read_text(encoding="utf-8")).items()}
            except (ValueError, OSError, AttributeError):
                self._tiempos = {}

    def crear(self, tipo, titulo, url=None, final=None, pagina=None, origen=None, estimado=None, peso=1, clave_tiempo=None,
              etiqueta="Ver resultado"):
        """Registra una tarea en curso. `url` puede llevar {id} y es a donde lleva el aviso «Ver resultado».

        `pagina` es la seccion a la que pertenece; `origen`, la ruta que la lanzo (para pintar el boton que la pidio).
        `estimado` son los segundos que suele tardar la primera vez; despues se usa lo que tardo de verdad.
        `peso` es el tamaño del trabajo (fotos, imagenes…): el tiempo recordado se guarda por unidad.
        """
        id_tarea = uuid.uuid4().hex[:10]
        url = (url or "").replace("{id}", id_tarea)
        clave_tiempo = clave_tiempo or tipo
        peso = max(1.0, float(peso or 1))
        tarea = {"id": id_tarea, "tipo": tipo, "titulo": titulo, "final": final or titulo, "estado": "en_curso", "mensaje": "Trabajando…",
                 "creada": time.time(), "terminada": None, "error": None, "url": url, "pagina": pagina or url.split("?")[0],
                 "origen": origen, "etiqueta": etiqueta, "notificada": False, "vista": False, "resultado": None, "archivo": None,
                 "avance": 0.0, "paso": None, "fuente": None, "clave_tiempo": clave_tiempo, "peso": peso,
                 "cuando_avance": None, "mostrado": 0.0}
        with self._candado:
            recordado = self._tiempos.get(clave_tiempo)
            tarea["previsto"] = recordado * peso if recordado else (float(estimado) if estimado else None)
            self._tareas[id_tarea] = tarea
            while len(self._tareas) > self.MAXIMO:
                self._tareas.popitem(last=False)
        return tarea

    def avanzar(self, id_tarea, fraccion, paso=None):
        """Anota por donde va la tarea. El avance nunca retrocede."""
        with self._candado:
            tarea = self._tareas.get(id_tarea)
            if not tarea or tarea["estado"] != "en_curso":
                return
            nuevo = max(tarea["avance"], min(1.0, max(0.0, float(fraccion))))
            if nuevo > tarea["avance"]:
                tarea["cuando_avance"] = time.time()
            tarea["avance"] = nuevo
            if paso:
                tarea["paso"] = paso

    def enlazar(self, id_tarea, fuente):
        """`fuente()` devuelve (fraccion, paso): para procesos que ya llevan su propia cuenta, como el entrenador."""
        with self._candado:
            tarea = self._tareas.get(id_tarea)
            if tarea:
                tarea["fuente"] = fuente

    def terminar(self, id_tarea, resultado=None, error=None, archivo=None):
        with self._candado:
            tarea = self._tareas.get(id_tarea)
            if not tarea:
                return
            tarea.update(estado="error" if error else "terminado", terminada=time.time(), error=error, resultado=resultado,
                         archivo=archivo, mensaje="Listo" if not error else error, fuente=None)
            if not error:
                por_unidad = (tarea["terminada"] - tarea["creada"]) / tarea["peso"]
                anterior = self._tiempos.get(tarea["clave_tiempo"])
                self._tiempos[tarea["clave_tiempo"]] = por_unidad if anterior is None else 0.5 * anterior + 0.5 * por_unidad
                self._guardar_tiempos()

    def _guardar_tiempos(self):
        if not self._ruta_tiempos:
            return
        try:
            self._ruta_tiempos.parent.mkdir(parents=True, exist_ok=True)
            self._ruta_tiempos.write_text(json.dumps(self._tiempos, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass  # sin el archivo solo se pierde el calculo de «cuanto falta» de la proxima vez

    def lanzar(self, tipo, titulo, funcion, url=None, final=None, **opciones):
        tarea = self.crear(tipo, titulo, url, final, **opciones)

        def correr():
            avance.escuchar(lambda fraccion, paso: self.avanzar(tarea["id"], fraccion, paso))
            try:
                salida = funcion()
                if isinstance(salida, tuple) and salida and salida[0] == "archivo":
                    _, contenido, tipo_mime, nombre = salida
                    self.terminar(tarea["id"], resultado={"archivo": True, "nombre": nombre, "bytes": len(contenido)}, archivo=(contenido, tipo_mime, nombre))
                else:
                    self.terminar(tarea["id"], resultado=salida)
            except ErrorUsuario as error:
                self.terminar(tarea["id"], error=str(error))
            except Exception:
                traceback.print_exc()
                self.terminar(tarea["id"], error="Algo salió mal al procesar. Inténtalo de nuevo.")
            finally:
                avance.escuchar(None)

        threading.Thread(target=correr, daemon=True).start()
        return self.publica(tarea)

    @staticmethod
    def _medir(tarea):
        """Devuelve (progreso, falta, paso): progreso de 0 a 1 o None si aun no se sabe; falta en segundos o None."""
        if tarea["estado"] != "en_curso":
            return 1.0, 0, None
        real, paso = tarea["avance"], tarea["paso"]
        if tarea["fuente"]:
            try:
                fraccion, texto = tarea["fuente"]()
                real, paso = max(real, min(1.0, max(0.0, float(fraccion or 0)))), texto or paso
            except Exception:
                pass
        ahora = time.time()
        pasado = ahora - tarea["creada"]
        previsto = tarea["previsto"]
        por_tiempo = min(TOPE, pasado / previsto) if previsto else None
        if real <= 0 and por_tiempo is None:
            return None, None, paso
        if real <= 0:
            # La tarea no cuenta pasos: avanza solo por el tiempo que suele tardar
            progreso = por_tiempo
        else:
            # Entre un aviso y el siguiente sigue avanzando al ritmo que llevaba, frenando antes del final del tramo
            cuando = tarea["cuando_avance"] or ahora
            # Con un piso de segundos: si los primeros pasos fueron instantaneos, la barra no se dispara
            segundos_por_unidad = max(MINIMO_SEGUNDOS, (cuando - tarea["creada"]) / real)
            hueco = max(0.0, min(ADELANTO, TOPE - real))
            sigue = hueco * (1 - math.exp(-(ahora - cuando) / (segundos_por_unidad * max(hueco, 0.01)))) if hueco else 0.0
            progreso = real + sigue
            if por_tiempo is not None:
                progreso = max(progreso, min(por_tiempo, real + hueco))
        # Lo que ya se mostro no retrocede aunque el calculo cambie
        progreso = min(max(progreso, tarea.get("mostrado", 0.0)), 0.99)
        tarea["mostrado"] = progreso
        if real >= 0.1 and pasado >= 1:
            falta = pasado * (1 - real) / real
        elif previsto:
            falta = previsto - pasado
        else:
            falta = None
        if falta is not None:
            falta = max(1, int(round(falta))) if falta > 0 else None
        return progreso, falta, paso

    @classmethod
    def publica(cls, tarea):
        progreso, falta, paso = cls._medir(tarea)
        return {**{campo: tarea[campo] for campo in CAMPOS_PUBLICOS}, "progreso": progreso, "falta": falta, "paso": paso}

    def lista(self):
        with self._candado:
            return [self.publica(t) for t in list(self._tareas.values())[-20:]]

    def obtener(self, id_tarea):
        with self._candado:
            tarea = self._tareas.get(id_tarea)
            if not tarea:
                raise ErrorUsuario("Esa tarea ya no está disponible.")
            return {**self.publica(tarea), "resultado": tarea["resultado"]}

    def marcar(self, id_tarea, vista=False):
        with self._candado:
            tarea = self._tareas.get(id_tarea)
            if tarea:
                tarea["notificada"] = True
                if vista:
                    tarea["vista"] = True

    def archivo(self, id_tarea):
        with self._candado:
            tarea = self._tareas.get(id_tarea)
            if not tarea or not tarea["archivo"]:
                raise ErrorUsuario("Ese archivo ya no está disponible.")
            return tarea["archivo"]
