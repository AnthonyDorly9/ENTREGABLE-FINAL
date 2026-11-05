"""Entrenador: entrenar un modelo con hiperparametros elegidos, validarlo, buscar los mejores y adoptarlo como version nueva."""
import json
import threading
import time
import uuid

import numpy as np
from sklearn.model_selection import StratifiedKFold

from .aumento import aumentar
from .configuracion import CARPETA_RESULTADOS, CLAVES_MODELOS, NOMBRES_MODELOS, PARAMETROS_INICIALES, PLIEGUES, SEMILLA
from .datos import submuestra_estratificada
from .evaluacion import evaluar_modelo
from .modelos import crear_modelo
from .servicio import ErrorUsuario, COPIAS_MEMORIA_PREVIOS, MUESTRA_MEMORIA_MNIST, _aciertos
from .validacion import validacion_cruzada

MUESTRAS_DISPONIBLES = [5000, 10000, 20000, 30000]
RUTA_INTENTOS = CARPETA_RESULTADOS / "entrenador" / "intentos.json"

TASAS = [0.0005, 0.001, 0.003, 0.005, 0.01]
CONTROLES = {
    "cnn": [
        {"clave": "filtros", "tipo": "rango", "min": 4, "max": 32, "paso": 4, "etiqueta": "Filtros de la primera capa", "entero": True},
        {"clave": "tasa_aprendizaje", "tipo": "opciones", "opciones": TASAS, "etiqueta": "Tasa de aprendizaje"},
        {"clave": "epocas", "tipo": "rango", "min": 1, "max": 8, "paso": 1, "etiqueta": "Épocas", "entero": True},
        {"clave": "dropout", "tipo": "rango", "min": 0, "max": 0.5, "paso": 0.05, "etiqueta": "Dropout (olvido aleatorio)"},
    ],
    "mlp": [
        {"clave": "neuronas", "tipo": "rango", "min": 32, "max": 256, "paso": 32, "etiqueta": "Neuronas de la primera capa", "entero": True},
        {"clave": "tasa_aprendizaje", "tipo": "opciones", "opciones": TASAS, "etiqueta": "Tasa de aprendizaje"},
        {"clave": "epocas", "tipo": "rango", "min": 1, "max": 15, "paso": 1, "etiqueta": "Épocas", "entero": True},
        {"clave": "dropout", "tipo": "rango", "min": 0, "max": 0.5, "paso": 0.05, "etiqueta": "Dropout (olvido aleatorio)"},
    ],
    "svm": [
        {"clave": "C", "tipo": "opciones", "opciones": [0.5, 1, 5, 10, 20], "etiqueta": "C (rigidez de la frontera)"},
        {"clave": "gamma", "tipo": "opciones", "opciones": ["scale", 0.01, 0.02, 0.05, 0.1], "etiqueta": "Gamma (alcance de cada punto)"},
        {"clave": "componentes", "tipo": "rango", "min": 20, "max": 100, "paso": 10, "etiqueta": "Componentes PCA", "entero": True},
    ],
    "knn": [
        {"clave": "k", "tipo": "rango", "min": 1, "max": 15, "paso": 2, "etiqueta": "Vecinos (k)", "entero": True},
        {"clave": "componentes", "tipo": "rango", "min": 20, "max": 100, "paso": 10, "etiqueta": "Componentes PCA", "entero": True},
    ],
    "regresion": [
        {"clave": "C", "tipo": "opciones", "opciones": [0.01, 0.1, 1.0, 10.0], "etiqueta": "C (regularización)"},
        {"clave": "iteraciones", "tipo": "rango", "min": 50, "max": 500, "paso": 50, "etiqueta": "Iteraciones máximas", "entero": True},
    ],
    "regresion_lineal": [
        {"clave": "alpha", "tipo": "opciones", "opciones": [0.1, 1.0, 10.0, 100.0], "etiqueta": "Alpha (regularización)"},
    ],
    "kmeans": [
        {"clave": "clusteres", "tipo": "rango", "min": 10, "max": 100, "paso": 10, "etiqueta": "Número de grupos", "entero": True},
        {"clave": "componentes", "tipo": "rango", "min": 20, "max": 100, "paso": 10, "etiqueta": "Componentes PCA", "entero": True},
    ],
}


def opciones():
    return {
        "muestras": MUESTRAS_DISPONIBLES,
        "modelos": [{"clave": c, "nombre": NOMBRES_MODELOS[c], "defecto": PARAMETROS_INICIALES[c], "controles": CONTROLES[c],
                     "tiene_epocas": c in ("cnn", "mlp")} for c in CLAVES_MODELOS],
    }


def validar_parametros(clave, parametros):
    if clave not in CONTROLES:
        raise ErrorUsuario("Modelo no válido.")
    limpios = {}
    for control in CONTROLES[clave]:
        valor = parametros.get(control["clave"], PARAMETROS_INICIALES[clave][control["clave"]])
        if control["tipo"] == "opciones":
            if valor not in control["opciones"]:
                raise ErrorUsuario(f"Valor no permitido para «{control['etiqueta']}».")
        else:
            try:
                valor = int(valor) if control.get("entero") else float(valor)
            except (TypeError, ValueError):
                raise ErrorUsuario(f"«{control['etiqueta']}» debe ser un número.")
            if not control["min"] <= valor <= control["max"]:
                raise ErrorUsuario(f"«{control['etiqueta']}» debe estar entre {control['min']} y {control['max']}.")
        limpios[control["clave"]] = valor
    return limpios


class Entrenador:
    def __init__(self, servicio, tareas=None):
        self.servicio = servicio
        self.tareas = tareas
        self._trabajos = {}
        self._candado = threading.Lock()

    def iniciar(self, clave, parametros, muestras, modo):
        if modo not in ("entrenar", "validar", "buscar"):
            raise ErrorUsuario("Modo no válido.")
        if muestras not in MUESTRAS_DISPONIBLES:
            raise ErrorUsuario("Cantidad de dígitos no válida.")
        parametros = validar_parametros(clave, parametros or {})
        with self._candado:
            if any(t["estado"] == "en_curso" for t in self._trabajos.values()):
                raise ErrorUsuario("Ya hay un entrenamiento en curso. Espera a que termine.")
            trabajo = {"id": uuid.uuid4().hex[:8], "modelo": clave, "modo": modo, "parametros": parametros, "muestras": muestras,
                       "estado": "en_curso", "historial": [], "progreso": 0.0, "mensaje": "Preparando…", "resultado": None,
                       "error": None, "objeto": None, "adoptado": None}
            self._trabajos[trabajo["id"]] = trabajo
        if self.tareas:
            nombres = {"entrenar": "Entrenando", "validar": "Validando", "buscar": "Buscando los mejores hiperparámetros de"}
            finales = {"entrenar": "el entrenamiento de", "validar": "la validación de", "buscar": "la búsqueda de hiperparámetros de"}
            tarea = self.tareas.crear("entrenador", f"{nombres[modo]} {NOMBRES_MODELOS[clave]}", url=f"/entrenador?trabajo={trabajo['id']}",
                                      final=f"{finales[modo]} {NOMBRES_MODELOS[clave]}", pagina="/entrenador",
                                      origen="/api/entrenador/iniciar", estimado=60, clave_tiempo=f"entrenador-{modo}-{clave}-{muestras}")
            trabajo["tarea"] = tarea["id"]
            self.tareas.enlazar(tarea["id"], lambda: (trabajo["progreso"], trabajo["mensaje"]))
        threading.Thread(target=self._ejecutar, args=(trabajo,), daemon=True).start()
        return self.estado(trabajo["id"])

    def ultimo(self):
        """El entrenamiento mas reciente (para retomarlo si la persona volvio a la pagina)."""
        if not self._trabajos:
            return None
        return self.estado(list(self._trabajos)[-1])

    def estado(self, id_trabajo):
        trabajo = self._trabajos.get(id_trabajo)
        if not trabajo:
            raise ErrorUsuario("Ese entrenamiento ya no existe.")
        return {k: v for k, v in trabajo.items() if k != "objeto"}

    def figura(self, id_trabajo):
        from . import figuras
        trabajo = self._trabajos.get(id_trabajo)
        if not trabajo:
            raise ErrorUsuario("Ese entrenamiento ya no existe.")
        historial = list(trabajo["historial"]) if trabajo["modo"] == "entrenar" else []
        return figuras.fig_entrenamiento(historial, trabajo["modelo"])

    def _ejecutar(self, trabajo):
        try:
            {"entrenar": self._entrenar, "validar": self._validar, "buscar": self._buscar}[trabajo["modo"]](trabajo)
            trabajo["estado"] = "terminado"
            trabajo["progreso"] = 1.0
        except Exception as error:  # el trabajo corre en un hilo: se informa el fallo en vez de perderlo
            trabajo["estado"] = "error"
            trabajo["error"] = f"El entrenamiento falló: {error}"
        if self.tareas and trabajo.get("tarea"):
            self.tareas.terminar(trabajo["tarea"], resultado={"trabajo": trabajo["id"]}, error=trabajo["error"])

    def _datos(self, muestras):
        x_ent, y_ent, x_pru, y_pru = self.servicio.mnist
        X, y = submuestra_estratificada(x_ent, y_ent, muestras)
        return X, y, x_pru, y_pru

    def _entrenar(self, trabajo):
        clave, parametros = trabajo["modelo"], trabajo["parametros"]
        X, y, x_pru, y_pru = self._datos(trabajo["muestras"])
        modelo = crear_modelo(clave, **parametros)
        epocas = parametros.get("epocas")

        def registrar(registro):
            trabajo["historial"].append(registro)
            trabajo["progreso"] = registro["epoca"] / epocas
            trabajo["mensaje"] = f"Época {registro['epoca']} de {epocas}"

        trabajo["mensaje"] = "Entrenando…"
        inicio = time.perf_counter()
        modelo.entrenar(X, y, X_val=x_pru[:2000], y_val=y_pru[:2000], callback=registrar if epocas else None)
        segundos = time.perf_counter() - inicio
        trabajo["mensaje"] = "Evaluando con los 10 000 dígitos de prueba…"
        metricas = evaluar_modelo(modelo, x_pru, y_pru)
        trabajo["resultado"] = {k: metricas[k] for k in ("exactitud", "precision_macro", "recall_macro", "f1_macro", "ms_por_muestra")}
        trabajo["resultado"].update({"segundos": segundos, "muestras": len(y)})
        trabajo["objeto"] = modelo
        self._guardar_intento(trabajo)

    def _validar(self, trabajo):
        clave, parametros = trabajo["modelo"], trabajo["parametros"]
        X, y, _, _ = self._datos(5000)
        exactitudes = []
        divisor = StratifiedKFold(n_splits=PLIEGUES, shuffle=True, random_state=SEMILLA)
        for pliegue, (ent, val) in enumerate(divisor.split(X, y), 1):
            trabajo["mensaje"] = f"Pliegue {pliegue} de {PLIEGUES}"
            modelo = crear_modelo(clave, **parametros)
            modelo.entrenar(X[ent], y[ent])
            exactitudes.append(float((modelo.predecir(X[val]) == y[val]).mean()))
            trabajo["historial"].append({"pliegue": pliegue, "exactitud": exactitudes[-1]})
            trabajo["progreso"] = pliegue / PLIEGUES
        trabajo["resultado"] = {"exactitudes": exactitudes, "media": float(np.mean(exactitudes)), "desviacion": float(np.std(exactitudes))}

    def _buscar(self, trabajo):
        clave = trabajo["modelo"]
        X, y, _, _ = self._datos(5000)
        from .configuracion import GRILLAS
        total = int(np.prod([len(v) for v in GRILLAS[clave].values()]))
        hechas = []

        def avance(_, registro):
            hechas.append(registro)
            trabajo["progreso"] = len(hechas) / total
            trabajo["mensaje"] = f"Combinación {len(hechas)} de {total}"

        combinaciones = validacion_cruzada(clave, X, y, parametros_fijos={"epocas": 2} if clave in ("cnn", "mlp") else None, progreso=avance)
        trabajo["resultado"] = {"combinaciones": combinaciones, "mejor": combinaciones[0]["parametros"]}

    def _guardar_intento(self, trabajo):
        RUTA_INTENTOS.parent.mkdir(parents=True, exist_ok=True)
        intentos = self.intentos()
        r = trabajo["resultado"]
        intentos.append({"id": trabajo["id"], "modelo": trabajo["modelo"], "parametros": trabajo["parametros"], "muestras": r["muestras"],
                         "exactitud": r["exactitud"], "f1_macro": r["f1_macro"], "segundos": r["segundos"],
                         "fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "adoptado": None})
        RUTA_INTENTOS.write_text(json.dumps(intentos[-60:], ensure_ascii=False, indent=1), encoding="utf-8")

    def intentos(self):
        return json.loads(RUTA_INTENTOS.read_text(encoding="utf-8")) if RUTA_INTENTOS.exists() else []

    def adoptar(self, id_trabajo):
        """Convierte el modelo entrenado en version nueva, repasando antes tus dígitos anteriores para no perder correcciones."""
        trabajo = self._trabajos.get(id_trabajo)
        if not trabajo or trabajo["modo"] != "entrenar" or trabajo["estado"] != "terminado" or trabajo["objeto"] is None:
            raise ErrorUsuario("Ese modelo no está listo para usarse.")
        if trabajo["adoptado"]:
            raise ErrorUsuario(f"Ese modelo ya se usó en la versión {trabajo['adoptado']}.")
        servicio, clave, nuevo = self.servicio, trabajo["modelo"], trabajo["objeto"]
        with servicio._candado:
            version = servicio.version_activa()
            anterior = servicio.modelos(version)[clave]
            previos = [d for g in ("entrenamiento", "reserva") for d in servicio.almacen.digitos_con_grupo(g)]
            informe = {"anteriores_antes": None, "anteriores_despues": None}
            if previos:
                X_prev = np.stack([d["pixeles"] for d in previos])
                y_prev = np.array([d["real"] for d in previos], dtype=np.int64)
                informe["anteriores_antes"] = [_aciertos(anterior, X_prev, y_prev), len(y_prev)]
                X_aug, y_aug = aumentar(X_prev, y_prev, COPIAS_MEMORIA_PREVIOS * 3, semilla=SEMILLA)
                x_mnist, y_mnist, _, _ = servicio.mnist
                X_mem, y_mem = submuestra_estratificada(x_mnist, y_mnist, MUESTRA_MEMORIA_MNIST, semilla=SEMILLA)
                nuevo.actualizar(X_aug, y_aug, X_mem, y_mem, 1.0)
                informe["anteriores_despues"] = [_aciertos(nuevo, X_prev, y_prev), len(y_prev)]
            nueva = servicio.crear_version(f"Entrenador: {NOMBRES_MODELOS[clave]} con nuevos hiperparámetros", {clave: nuevo},
                                           {"entrenador": {"modelo": clave, "parametros": trabajo["parametros"], "muestras": trabajo["muestras"]}})
        trabajo["adoptado"] = nueva
        intentos = self.intentos()
        for intento in intentos:
            if intento["id"] == id_trabajo:
                intento["adoptado"] = nueva
        RUTA_INTENTOS.write_text(json.dumps(intentos, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"version_nueva": nueva, **informe}
