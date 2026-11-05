"""Formularios ficticios: generarlos, abrir los ejemplos guardados y leerlos campo por campo con los siete modelos."""
import json
import os
import re
import threading
import time
import uuid
from collections import OrderedDict

import cv2
import numpy as np

from . import avance
from .configuracion import CARPETA_DATOS, CLAVES_MODELOS
from .formularios_ficticios import TIPOS_FORMULARIO, GeneradorDigitos
from .preprocesado import a_data_uri, procesar_foto
from .servicio import MAXIMO_FOTOS, ErrorUsuario

CARPETA_EJEMPLOS = CARPETA_DATOS / "ficticios"
CARPETAS_BANCO = ("numeros", "formularios")
PAPELERA = "_papelera"
MAXIMO_EN_MEMORIA = 20
NIVELES_NUMERO = [0.15, 0.35, 0.55, 0.8]
NIVELES_FORMULARIO = [0.2, 0.35, 0.5, 0.65]
# Dificultad que se elige al crear imagenes: (numeros, formularios).
NIVELES_AL_CREAR = {"facil": (0.15, 0.2), "normal": (0.35, 0.35), "dificil": (0.55, 0.5), "muy_dificil": (0.8, 0.75)}
TIPOS_AL_CREAR = ("liso", "cuadriculado", "formularios")
NOMBRE_ARCHIVO = re.compile(r"^[A-Za-z0-9_\-]+\.png$")
_candado = threading.RLock()


def _leer_etiquetas():
    ruta = CARPETA_EJEMPLOS / "etiquetas.json"
    etiquetas = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    for clave in ("formularios", "numeros", "dificultad", "creada", "basura"):
        etiquetas.setdefault(clave, {})
    for carpeta in CARPETAS_BANCO:
        etiquetas["basura"].setdefault(carpeta, {})
    return etiquetas


def _guardar_etiquetas(etiquetas):
    (CARPETA_EJEMPLOS / "etiquetas.json").write_text(json.dumps(etiquetas, ensure_ascii=False, indent=1), encoding="utf-8")


def _numeros_usados(etiquetas, carpeta, patron):
    """Numeros que ya llevan las imagenes de ese nombre; las de la basura siguen ocupando el suyo para poder restaurarlas."""
    nombres = list(etiquetas[carpeta]) + list(etiquetas["basura"][carpeta])
    return [int(m.group(1)) for n in nombres if (m := re.fullmatch(patron, n))]


def etiqueta_dificultad(valor):
    if valor is None:
        return "Normal"
    return "Fácil" if valor < 0.3 else "Normal" if valor < 0.5 else "Difícil" if valor < 0.7 else "Muy difícil"


def ampliar_banco(generador, formularios_por_tipo=0, numeros=0, cuadriculadas=0, formularios=0, nivel=None):
    """Agrega imagenes nuevas al banco de ejemplos sin tocar las que ya existen. Devuelve cuantas creo.

    `formularios` se reparte entre los tipos de formulario. Con `nivel` todas salen de esa dificultad; sin el, mezcladas.
    """
    fija_numero, fija_formulario = NIVELES_AL_CREAR.get(nivel, (None, None))
    (CARPETA_EJEMPLOS / "formularios").mkdir(parents=True, exist_ok=True)
    (CARPETA_EJEMPLOS / "numeros").mkdir(parents=True, exist_ok=True)
    etiquetas = _leer_etiquetas()
    creados = {"formularios": 0, "numeros": 0, "cuadriculadas": 0}
    ahora = time.time()
    total = cuadriculadas + numeros + formularios + formularios_por_tipo * len(TIPOS_FORMULARIO)

    def contar():
        hechas = sum(creados.values())
        avance.informar(hechas / max(1, total), f"Imagen {hechas + 1} de {total}")

    siguiente = 1 + max(_numeros_usados(etiquetas, "numeros", r"cuadriculada_(\d+)\.png"), default=0)
    for i in range(cuadriculadas):
        contar()
        dificultad = fija_numero or NIVELES_NUMERO[(siguiente + i) % len(NIVELES_NUMERO)]
        texto = generador.numero_aleatorio(int(generador.azar.integers(1, 8)))
        nombre = f"cuadriculada_{siguiente + i:03d}.png"
        cv2.imwrite(str(CARPETA_EJEMPLOS / "numeros" / nombre), generador.foto_cuadriculada(texto, dificultad))
        etiquetas["numeros"][nombre] = texto
        etiquetas["dificultad"][nombre] = dificultad
        etiquetas["creada"][nombre] = ahora
        creados["cuadriculadas"] += 1
    for posicion, tipo in enumerate(TIPOS_FORMULARIO):
        siguiente = 1 + max(_numeros_usados(etiquetas, "formularios", rf"{tipo}_(\d+)\.png"), default=0)
        repartidos = formularios // len(TIPOS_FORMULARIO) + (posicion < formularios % len(TIPOS_FORMULARIO))
        for i in range(formularios_por_tipo + repartidos):
            contar()
            dificultad = fija_formulario or NIVELES_FORMULARIO[(siguiente + i) % len(NIVELES_FORMULARIO)]
            imagen, campos = generador.formulario(tipo, dificultad)
            nombre = f"{tipo}_{siguiente + i}.png"
            cv2.imwrite(str(CARPETA_EJEMPLOS / "formularios" / nombre), imagen)
            etiquetas["formularios"][nombre] = [{**c, "caja": list(c["caja"])} for c in campos]
            etiquetas["dificultad"][nombre] = dificultad
            etiquetas["creada"][nombre] = ahora
            creados["formularios"] += 1
    siguiente = 1 + max(_numeros_usados(etiquetas, "numeros", r"numero_(\d+)\.png"), default=0)
    for i in range(numeros):
        contar()
        dificultad = fija_numero or NIVELES_NUMERO[(siguiente + i) % len(NIVELES_NUMERO)]
        texto = generador.numero_aleatorio(int(generador.azar.integers(1, 8)))
        toque = 0.25 if dificultad >= 0.7 else 0.1 if dificultad >= 0.5 else 0.0
        nombre = f"numero_{siguiente + i:03d}.png"
        cv2.imwrite(str(CARPETA_EJEMPLOS / "numeros" / nombre), generador.foto_numero(texto, dificultad, toque=toque))
        etiquetas["numeros"][nombre] = texto
        etiquetas["dificultad"][nombre] = dificultad
        etiquetas["creada"][nombre] = ahora
        creados["numeros"] += 1
    _guardar_etiquetas(etiquetas)
    return creados


class Ficticios:
    def __init__(self, servicio):
        self.servicio = servicio
        self._generador = None
        self._formularios = OrderedDict()
        self._miniaturas = OrderedDict()

    def _generar_con(self):
        if self._generador is None:
            _, _, x_pru, y_pru = self.servicio.mnist
            self._generador = GeneradorDigitos(x_pru, y_pru, semilla=int(time.time()) % 100000)
        return self._generador

    def _guardar(self, imagen, campos, tipo):
        token = uuid.uuid4().hex[:8]
        self._formularios[token] = (imagen, campos, tipo)
        while len(self._formularios) > MAXIMO_EN_MEMORIA:
            self._formularios.popitem(last=False)
        return {
            "token": token, "tipo": tipo, "titulo": TIPOS_FORMULARIO[tipo][0], "imagen": a_data_uri(imagen),
            "campos": [{"etiqueta": c["etiqueta"], "largo": len(c["valor"]), "caja": list(c["caja"])} for c in campos],
        }

    def tipos(self):
        return [{"clave": k, "titulo": v[0]} for k, v in TIPOS_FORMULARIO.items()]

    def ejemplos(self):
        return sorted(_leer_etiquetas()["formularios"])

    def banco(self):
        e = _leer_etiquetas()
        dificultad = e["dificultad"]
        creada = e["creada"]
        return {
            "formularios": [{"nombre": n, "tipo": n.rsplit("_", 1)[0], "nivel": etiqueta_dificultad(dificultad.get(n)), "dificultad": dificultad.get(n, 0.4),
                             "creada": creada.get(n, 0)}
                            for n in sorted(e["formularios"], key=lambda n: (n.rsplit("_", 1)[0], int(re.search(r"_(\d+)\.png", n).group(1))))],
            "numeros": [{"nombre": n, "texto": t, "nivel": etiqueta_dificultad(dificultad.get(n)), "dificultad": dificultad.get(n, 0.4),
                         "creada": creada.get(n, 0)}
                        for n, t in sorted(e["numeros"].items())],
        }

    def ampliar(self, cantidad, tipo="liso", nivel=None):
        """Crea imagenes nuevas de un tipo. La dificultad es obligatoria: un nivel o «mezcla»."""
        if tipo not in TIPOS_AL_CREAR:
            raise ErrorUsuario("Elige qué quieres crear: números, números en hoja cuadriculada o formularios.")
        if nivel != "mezcla" and nivel not in NIVELES_AL_CREAR:
            raise ErrorUsuario("Elige la dificultad antes de crear las imágenes.")
        try:
            cantidad = max(1, min(60, int(cantidad)))
        except (TypeError, ValueError):
            raise ErrorUsuario("La cantidad no es válida.")
        que = {"liso": "numeros", "cuadriculado": "cuadriculadas", "formularios": "formularios"}[tipo]
        with _candado:
            antes = _leer_etiquetas()
            creados = ampliar_banco(self._generar_con(), nivel=nivel, **{que: cantidad})
            etiquetas = _leer_etiquetas()
        nuevas = {carpeta: sorted(set(etiquetas[carpeta]) - set(antes[carpeta])) for carpeta in CARPETAS_BANCO}
        return {**creados, "nuevas": nuevas, "total_numeros": len(etiquetas["numeros"]), "total_formularios": len(etiquetas["formularios"])}

    # ---------- Basura de imagenes del banco ----------
    @staticmethod
    def _validar(carpeta, nombres):
        if carpeta not in CARPETAS_BANCO:
            raise ErrorUsuario("Carpeta no válida.")
        nombres = list(dict.fromkeys(str(n) for n in (nombres or [])))
        if not nombres:
            raise ErrorUsuario("Elige al menos una imagen.")
        return nombres

    def _resumen_basura(self, etiquetas, **extra):
        return {**extra, "total_numeros": len(etiquetas["numeros"]), "total_formularios": len(etiquetas["formularios"]),
                "en_basura": sum(len(etiquetas["basura"][c]) for c in CARPETAS_BANCO)}

    def quitar(self, carpeta, nombres):
        """Manda imagenes del banco a la basura: salen de la galeria pero se pueden restaurar."""
        nombres = self._validar(carpeta, nombres)
        with _candado:
            e = _leer_etiquetas()
            if any(n not in e[carpeta] for n in nombres):
                raise ErrorUsuario("Alguna de esas imágenes ya no existe. Vuelve a cargar la página.")
            destino = CARPETA_EJEMPLOS / PAPELERA / carpeta
            destino.mkdir(parents=True, exist_ok=True)
            for n in nombres:
                origen = CARPETA_EJEMPLOS / carpeta / n
                if origen.exists():
                    os.replace(origen, destino / n)
                e["basura"][carpeta][n] = {"etiqueta": e[carpeta].pop(n), "dificultad": e["dificultad"].pop(n, None),
                                           "creada": e["creada"].pop(n, None), "quitada": time.time()}
            _guardar_etiquetas(e)
        return self._resumen_basura(e, quitadas=nombres)

    def basura(self):
        e = _leer_etiquetas()
        elementos = [{"carpeta": c, "nombre": n, "texto": d["etiqueta"] if c == "numeros" else n.rsplit("_", 1)[0], "quitada": d.get("quitada", 0)}
                     for c in CARPETAS_BANCO for n, d in e["basura"][c].items()]
        return sorted(elementos, key=lambda x: -x["quitada"])

    def restaurar(self, carpeta, nombres):
        nombres = self._validar(carpeta, nombres)
        with _candado:
            e = _leer_etiquetas()
            if any(n not in e["basura"][carpeta] for n in nombres):
                raise ErrorUsuario("Esa imagen ya no está en la basura.")
            for n in nombres:
                origen = CARPETA_EJEMPLOS / PAPELERA / carpeta / n
                if origen.exists():
                    os.replace(origen, CARPETA_EJEMPLOS / carpeta / n)
                datos = e["basura"][carpeta].pop(n)
                e[carpeta][n] = datos["etiqueta"]
                for clave in ("dificultad", "creada"):
                    if datos.get(clave) is not None:
                        e[clave][n] = datos[clave]
            _guardar_etiquetas(e)
        return self._resumen_basura(e, restauradas=nombres)

    def borrar_para_siempre(self, carpeta=None, nombres=None):
        """Borra del disco imagenes que ya estan en la basura. Sin argumentos vacia toda la basura."""
        with _candado:
            e = _leer_etiquetas()
            if carpeta is None:
                pedidas = {c: list(e["basura"][c]) for c in CARPETAS_BANCO}
            else:
                pedidas = {carpeta: self._validar(carpeta, nombres)}
                if any(n not in e["basura"][carpeta] for n in pedidas[carpeta]):
                    raise ErrorUsuario("Esa imagen ya no está en la basura.")
            for c, lista in pedidas.items():
                for n in lista:
                    (CARPETA_EJEMPLOS / PAPELERA / c / n).unlink(missing_ok=True)
                    e["basura"][c].pop(n)
            _guardar_etiquetas(e)
        return self._resumen_basura(e, borradas=sum(len(lista) for lista in pedidas.values()))

    def miniatura(self, carpeta, archivo, ancho=260, de_basura=False):
        if carpeta not in ("formularios", "numeros") or not NOMBRE_ARCHIVO.match(archivo):
            raise ErrorUsuario("Imagen no válida.")
        ruta = (CARPETA_EJEMPLOS / PAPELERA if de_basura else CARPETA_EJEMPLOS) / carpeta / archivo
        if not ruta.exists():
            raise ErrorUsuario("Esa imagen no existe.")
        clave = (carpeta, archivo, ancho, ruta.stat().st_mtime, de_basura)
        if clave not in self._miniaturas:
            imagen = cv2.imread(str(ruta))
            ancho = max(80, min(700, int(ancho)))
            imagen = cv2.resize(imagen, (ancho, max(1, round(imagen.shape[0] * ancho / imagen.shape[1]))), interpolation=cv2.INTER_AREA)
            self._miniaturas[clave] = cv2.imencode(".jpg", imagen, [cv2.IMWRITE_JPEG_QUALITY, 82])[1].tobytes()
            while len(self._miniaturas) > 400:
                self._miniaturas.pop(next(iter(self._miniaturas)))
        return self._miniaturas[clave]

    def abrir_numero(self, nombre):
        e = _leer_etiquetas()
        if nombre not in e["numeros"]:
            raise ErrorUsuario("Ese ejemplo no existe.")
        imagen = cv2.imread(str(CARPETA_EJEMPLOS / "numeros" / nombre))
        alto, ancho = imagen.shape[:2]
        campos = [{"etiqueta": "Número escrito", "valor": e["numeros"][nombre], "caja": (0, 0, ancho, alto)}]
        respuesta = self._guardar(imagen, campos, "inscripcion")
        return {**respuesta, "titulo": f"Número escrito ({etiqueta_dificultad(e['dificultad'].get(nombre)).lower()})"}

    def entrenar_elegidas(self, nombres):
        """Los siete modelos leen las imagenes elegidas (como una tanda de fotos) y los que se equivocan aprenden de ellas."""
        nombres = self._validar("numeros", nombres)
        if len(nombres) > MAXIMO_FOTOS:
            raise ErrorUsuario(f"Elige como máximo {MAXIMO_FOTOS} imágenes por vez; marcaste {len(nombres)}.")
        e = _leer_etiquetas()
        if any(n not in e["numeros"] for n in nombres):
            raise ErrorUsuario("Alguna de esas imágenes ya no existe. Vuelve a cargar la página.")
        archivos = [(n, (CARPETA_EJEMPLOS / "numeros" / n).read_bytes()) for n in nombres]
        with avance.tramo(0, 0.12):
            subida = self.servicio.subir(archivos)
        textos = {str(f["id"]): e["numeros"][f["nombre"]] for f in subida["fotos"]}
        with avance.tramo(0.12, 0.3):
            lectura = self.servicio.predecir(subida["lote"], textos)
        respuesta = {"lote": subida["lote"], "fotos": len(subida["fotos"]), "marcador": lectura["marcador"], "correccion": None, "mensaje": None}
        try:
            with avance.tramo(0.3, 1):
                respuesta["correccion"] = self.servicio.corregir(subida["lote"])
        except ErrorUsuario as error:
            respuesta["mensaje"] = str(error)
        return respuesta

    def generar(self, tipo, dificultad):
        if tipo not in TIPOS_FORMULARIO:
            raise ErrorUsuario("Tipo de formulario no válido.")
        dificultad = min(0.9, max(0.05, float(dificultad)))
        imagen, campos = self._generar_con().formulario(tipo, dificultad)
        return self._guardar(imagen, campos, tipo)

    def abrir_ejemplo(self, nombre):
        etiquetas = _leer_etiquetas()["formularios"]
        if nombre not in etiquetas:
            raise ErrorUsuario("Ese ejemplo no existe.")
        imagen = cv2.imread(str(CARPETA_EJEMPLOS / "formularios" / nombre))
        campos = [{**c, "caja": tuple(c["caja"])} for c in etiquetas[nombre]]
        return self._guardar(imagen, campos, nombre.split("_")[0])

    def corregir(self, token):
        """Convierte cada campo del formulario abierto en una foto con su numero real y corrige a los modelos que fallaron."""
        if token not in self._formularios:
            raise ErrorUsuario("Ese formulario ya no está disponible. Ábrelo de nuevo.")
        imagen, campos, _ = self._formularios[token]
        archivos = []
        for i, campo in enumerate(campos, 1):
            x, y, w, h = campo["caja"]
            recorte = imagen[y + 6 : y + h - 6, x + 6 : x + w - 6]
            archivos.append((f"practica_campo_{i}.png", cv2.imencode(".png", recorte)[1].tobytes()))
        with avance.tramo(0, 0.12):
            subida = self.servicio.subir(archivos)
        textos = {str(f["id"]): campos[i]["valor"] for i, f in enumerate(subida["fotos"])}
        with avance.tramo(0.12, 0.3):
            self.servicio.predecir(subida["lote"], textos)
        with avance.tramo(0.3, 1):
            return {"lote": subida["lote"], **self.servicio.corregir(subida["lote"])}

    def leer(self, token):
        if token not in self._formularios:
            raise ErrorUsuario("Ese formulario ya no está disponible. Genera otro.")
        imagen, campos, tipo = self._formularios[token]
        modelos = self.servicio.modelos()
        resultados = []
        total = {c: {"campos_ok": 0, "digitos_ok": 0, "digitos": 0} for c in CLAVES_MODELOS}
        for posicion, campo in enumerate(campos):
            avance.informar(posicion / len(campos), f"Número {posicion + 1} de {len(campos)}: lo leen los siete modelos")
            x, y, w, h = campo["caja"]
            recorte = imagen[y + 6 : y + h - 6, x + 6 : x + w - 6]
            valor = campo["valor"]
            procesado = procesar_foto(recorte, esperado=len(valor))
            completo = len(procesado["cajas"]) == len(valor)
            por_modelo = {}
            for clave in CLAVES_MODELOS:
                if procesado["digitos"].shape[0]:
                    numero = "".join(str(d) for d in modelos[clave].predecir(procesado["digitos"]))
                else:
                    numero = ""
                aciertos = sum(a == b for a, b in zip(numero, valor)) if completo else 0
                por_modelo[clave] = {"numero": numero or "—", "correcto": completo and numero == valor}
                total[clave]["campos_ok"] += int(por_modelo[clave]["correcto"])
                total[clave]["digitos_ok"] += aciertos
                total[clave]["digitos"] += len(valor)
            resultados.append({
                "etiqueta": campo["etiqueta"], "valor": valor, "recorte": a_data_uri(recorte), "por_modelo": por_modelo,
                "recortes": [a_data_uri(cv2.resize(r, (56, 56), interpolation=cv2.INTER_NEAREST)) for r in procesado["recortes"]],
                "aviso": procesado["aviso"],
            })
        return {"campos": resultados, "resumen": [{"modelo": c, "campos": len(campos), **total[c]} for c in CLAVES_MODELOS],
                "version": self.servicio.version_activa()}
