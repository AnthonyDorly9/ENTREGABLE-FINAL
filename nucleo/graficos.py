"""Datos y graficos (imagenes PNG) de la seccion de graficos: metricas por version, matriz de confusion, mapa PCA."""
import base64
import json
import zipfile
import io

import cv2
import numpy as np
from sklearn.decomposition import PCA

from . import avance, figuras
from .configuracion import CARPETA_RESULTADOS, CLAVES_MODELOS, NOMBRES_MODELOS, SEMILLA
from .evaluacion import evaluar_modelo
from .explicacion import uri_digito

MUESTRA_MAPA = 2500
IMAGENES_FIJAS = ["metricas", "curvas", "validacion", "velocidad"]


def _ruta(version, nombre):
    return CARPETA_RESULTADOS / version / nombre


def carpeta_imagenes(version):
    return _ruta(version, "graficos")


def nombres_imagenes():
    return ([f"{n}.png" for n in IMAGENES_FIJAS] + [f"matriz_{c}.png" for c in CLAVES_MODELOS] + [f"mapa_{c}.png" for c in CLAVES_MODELOS]
            + [f"predicciones_{c}.png" for c in CLAVES_MODELOS])


def _leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def _escribir(ruta, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")


def metricas_de(version):
    """Metricas guardadas de una version; los tiempos de entrenamiento inicial se toman de v1 si faltan."""
    metricas = _leer(_ruta(version, "metricas.json"))
    if metricas is None:
        return None
    inicial = _leer(_ruta("v1", "metricas.json")) or {}
    for clave, m in metricas.items():
        for campo in ("segundos_entrenamiento", "muestras_entrenamiento"):
            if campo not in m and campo in inicial.get(clave, {}):
                m[campo] = inicial[clave][campo]
    return metricas


def calcular_metricas(servicio, version):
    """Evalua los siete modelos de una version con las 10 000 imagenes de prueba de MNIST y guarda el resultado."""
    _, _, x_pru, y_pru = servicio.mnist
    anterior = metricas_de(version) or _leer(_ruta("v1", "metricas.json")) or {}
    resultado = {}
    for turno, (clave, modelo) in enumerate(servicio.modelos(version).items()):
        avance.informar(turno / len(CLAVES_MODELOS), f"Midiendo el modelo {turno + 1} de {len(CLAVES_MODELOS)}: {NOMBRES_MODELOS[clave]}")
        metricas = evaluar_modelo(modelo, x_pru, y_pru)
        for campo in ("segundos_entrenamiento", "muestras_entrenamiento"):
            if campo in anterior.get(clave, {}):
                metricas[campo] = anterior[clave][campo]
        metricas["hiperparametros"] = modelo.parametros
        resultado[clave] = metricas
    _escribir(_ruta(version, "metricas.json"), resultado)
    return resultado


def calcular_mapa(servicio, version):
    _, _, x_pru, y_pru = servicio.mnist
    generador = np.random.default_rng(SEMILLA)
    indices = np.sort(generador.choice(len(y_pru), MUESTRA_MAPA, replace=False))
    coordenadas = PCA(n_components=2, random_state=SEMILLA).fit_transform(x_pru)[indices]
    errores = {c: (m.predecir(x_pru[indices]) != y_pru[indices]).astype(int).tolist()
               for c, m in servicio.modelos(version).items()}
    mapa = {
        "x": np.round(coordenadas[:, 0], 2).tolist(),
        "y": np.round(coordenadas[:, 1], 2).tolist(),
        "digito": y_pru[indices].tolist(),
        "errores": errores,
    }
    _escribir(_ruta(version, "mapa_pca.json"), mapa)
    return mapa


def ejemplos_predicciones(servicio, metricas, clave, errores=2):
    """Dígitos de prueba de MNIST para la galería «Real / Predijo» de un modelo: un acierto de cada dígito y `errores`
    equivocaciones, tomados de las predicciones ya guardadas en las métricas (semilla fija, siempre los mismos)."""
    _, _, x_pru, y_pru = servicio.mnist
    m = metricas[clave]
    predichos = y_pru.copy()
    predichos[m["indices_error"]] = m["predicciones_error"]
    generador = np.random.default_rng(SEMILLA)
    aciertos = [np.flatnonzero((y_pru == d) & (predichos == d)) for d in range(10)]
    elegidos = [int(generador.choice(a)) for a in aciertos if len(a)]
    fallos = np.asarray(m["indices_error"], int)
    elegidos += [int(i) for i in generador.choice(fallos, min(errores, len(fallos)), replace=False)]
    return x_pru[elegidos], y_pru[elegidos], predichos[elegidos]


def imagen_predicciones_lote(servicio, lote, clave, version=None):
    """Galería «Real / Predijo» de un modelo con todos los dígitos de una tanda que tienen número escrito (PNG para descargar)."""
    if clave not in CLAVES_MODELOS:
        raise ValueError(f"Modelo desconocido: {clave}")
    digitos, origenes = [], []
    for numero, foto in enumerate(servicio.resultado_lote(lote, version)["fotos"], 1):
        for posicion, d in enumerate(foto["digitos"], 1):
            if d["real"] is not None and clave in d["modelos"]:
                digitos.append(d)
                origenes.append(f"Foto {numero} · dígito {posicion}")
    imagenes = [cv2.imdecode(np.frombuffer(base64.b64decode(d["imagen"].split(",", 1)[1]), np.uint8), cv2.IMREAD_GRAYSCALE) for d in digitos]
    return figuras.fig_predicciones(imagenes, [d["real"] for d in digitos], [d["modelos"][clave]["predicho"] for d in digitos], origenes)


def hay_metricas(version):
    return _ruta(version, "metricas.json").exists()


def hay_imagenes(version):
    carpeta = carpeta_imagenes(version)
    return all((carpeta / n).exists() for n in nombres_imagenes())


def generar_imagenes(servicio, version):
    """Crea todas las imagenes PNG de una version a partir de sus metricas (calculando el mapa PCA si falta)."""
    metricas = metricas_de(version)
    mapa = _leer(_ruta(version, "mapa_pca.json")) or calcular_mapa(servicio, version)
    carpeta = carpeta_imagenes(version)
    carpeta.mkdir(parents=True, exist_ok=True)
    avance.informar(0, "Dibujando las primeras imágenes")
    (carpeta / "metricas.png").write_bytes(figuras.fig_metricas(metricas))
    (carpeta / "curvas.png").write_bytes(figuras.fig_curvas(_leer(_ruta("v1", "curvas_entrenamiento.json")) or {}))
    (carpeta / "validacion.png").write_bytes(figuras.fig_validacion(_leer(_ruta("v1", "validacion_cruzada.json")) or {}))
    (carpeta / "velocidad.png").write_bytes(figuras.fig_velocidad(metricas))
    total = 4 + 3 * len(CLAVES_MODELOS)
    for turno, clave in enumerate(CLAVES_MODELOS):
        avance.informar((4 + 3 * turno) / total, f"Dibujando la imagen {5 + 3 * turno} de {total}: {NOMBRES_MODELOS[clave]}")
        (carpeta / f"matriz_{clave}.png").write_bytes(figuras.fig_matriz(metricas[clave]["matriz_confusion"], clave))
        (carpeta / f"mapa_{clave}.png").write_bytes(figuras.fig_mapa(mapa, clave))
        (carpeta / f"predicciones_{clave}.png").write_bytes(figuras.fig_predicciones(*ejemplos_predicciones(servicio, metricas, clave)))


def _versiones_para_progreso(servicio):
    return [{"id": v["id"], "exactitud_prueba": v["detalle"].get("exactitud_prueba", {})} for v in servicio.almacen.listar_versiones()]


def imagen_progreso(servicio):
    return figuras.fig_progreso(_versiones_para_progreso(servicio))


def datos_graficos(servicio, version):
    metricas = metricas_de(version)
    versiones = servicio.almacen.listar_versiones()
    base = {
        "version": version,
        "versiones": [{"id": v["id"], "motivo": v["motivo"], "creada": v["creada"],
                       "actualizados": v["detalle"].get("actualizados", [])} for v in versiones],
        "listo": False,
    }
    if metricas is None:
        return base
    if not hay_imagenes(version):
        generar_imagenes(servicio, version)
    carpeta = carpeta_imagenes(version)
    sello = int(max((carpeta / n).stat().st_mtime for n in nombres_imagenes()))
    url = lambda nombre: f"/graficos-img/{version}/{nombre}.png?v={sello}"
    modelos = {}
    for clave in CLAVES_MODELOS:
        m = metricas[clave]
        modelos[clave] = {k: m[k] for k in ("exactitud", "precision_macro", "recall_macro", "f1_macro", "ms_por_muestra",
                                            "por_clase", "matriz_confusion") if k in m}
        modelos[clave]["segundos_entrenamiento"] = m.get("segundos_entrenamiento")
        modelos[clave]["muestras_entrenamiento"] = m.get("muestras_entrenamiento")
        modelos[clave]["hiperparametros"] = m.get("hiperparametros", {})
    base.update({
        "listo": True,
        "modelos": modelos,
        "validacion_cruzada": _leer(_ruta("v1", "validacion_cruzada.json")) or {},
        "arquitecturas": {c: m.arquitectura() for c, m in servicio.modelos(version).items()},
        "imagenes": {
            "metricas": url("metricas"), "curvas": url("curvas"), "validacion": url("validacion"), "velocidad": url("velocidad"),
            "matriz": {c: url(f"matriz_{c}") for c in CLAVES_MODELOS},
            "mapa": {c: url(f"mapa_{c}") for c in CLAVES_MODELOS},
            "predicciones": {c: url(f"predicciones_{c}") for c in CLAVES_MODELOS},
        },
    })
    return base


def generar(servicio, version):
    with avance.tramo(0, 0.55):
        calcular_metricas(servicio, version)
    avance.informar(0.55, "Calculando el mapa de errores")
    calcular_mapa(servicio, version)
    with avance.tramo(0.7, 1):
        generar_imagenes(servicio, version)
    return datos_graficos(servicio, version)


def zip_imagenes(servicio, version):
    if not hay_imagenes(version):
        generar_imagenes(servicio, version)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre in nombres_imagenes():
            zf.write(carpeta_imagenes(version) / nombre, nombre)
        zf.writestr("progreso_versiones.png", imagen_progreso(servicio))
    return buffer.getvalue()


def imagenes_casilla(servicio, version, clave, real, predicho, limite=16):
    metricas = _leer(_ruta(version, "metricas.json"))
    if metricas is None or clave not in metricas:
        return {"total": 0, "imagenes": []}
    _, _, x_pru, y_pru = servicio.mnist
    m = metricas[clave]
    if real == predicho:
        return {"total": int(m["matriz_confusion"][real][real]), "imagenes": [], "acierto": True}
    indices = [i for i, p in zip(m["indices_error"], m["predicciones_error"]) if y_pru[i] == real and p == predicho]
    return {"total": len(indices), "acierto": False,
            "imagenes": [{"indice": int(i), "uri": uri_digito(x_pru[i], 5)} for i in indices[:limite]]}
