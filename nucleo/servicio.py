import copy
import json
import re
import shutil
import threading
from datetime import datetime

import cv2
import numpy as np

from . import avance
from .almacen import Almacen
from .aumento import aumentar
from .configuracion import CARPETA_DATOS, CARPETA_MODELOS, CARPETA_RESULTADOS, CLAVES_MODELOS, NOMBRES_MODELOS
from .datos import cargar_mnist, submuestra_estratificada
from .explicacion import explicar, uri_digito
from .modelos import ModeloBase
from .preprocesado import a_data_uri, decodificar_imagen, orientar, procesar_foto

MAXIMO_FOTOS = 20
MAXIMO_BYTES = 12 * 1024 * 1024
MAXIMO_DIGITOS = 12
CARPETA_FOTOS = CARPETA_DATOS / "fotos_usuario"

TOLERANCIA_MNIST = 0.005
COPIAS_ERROR = 20
COPIAS_ACIERTO = 3
MUESTRA_MEMORIA_MNIST = 3000
COPIAS_MEMORIA_PREVIOS = 4
FUERZAS_ACTUALIZACION = (1.0, 0.4)


def _aciertos(modelo, X, y):
    return int((modelo.predecir(X) == y).sum())


def _porcentaje(valor):
    return f"{valor * 100:.2f}".replace(".", ",") + " %"


class ErrorUsuario(ValueError):
    """Error que se le puede mostrar tal cual a la persona que usa la aplicacion."""


def _miniatura(imagen, ancho=420):
    if imagen.shape[1] > ancho:
        imagen = cv2.resize(imagen, (ancho, round(imagen.shape[0] * ancho / imagen.shape[1])), interpolation=cv2.INTER_AREA)
    return a_data_uri(imagen)


class Servicio:
    def __init__(self, almacen=None):
        self.almacen = almacen or Almacen()
        self._modelos = {}
        self._mnist = None
        self._candado = threading.Lock()
        self._asegurar_version_inicial()

    def _asegurar_version_inicial(self):
        if self.almacen.listar_versiones() or not (CARPETA_MODELOS / "v1").exists():
            return
        ruta = CARPETA_RESULTADOS / "v1" / "metricas.json"
        detalle = {}
        if ruta.exists():
            metricas = json.loads(ruta.read_text(encoding="utf-8"))
            detalle = {"exactitud_prueba": {c: m["exactitud"] for c, m in metricas.items()}}
        self.almacen.registrar_version("v1", 1, "Entrenamiento inicial con MNIST", detalle)

    @property
    def mnist(self):
        if self._mnist is None:
            self._mnist = cargar_mnist()
        return self._mnist

    def version_activa(self):
        version = self.almacen.version_activa()
        if not version:
            raise ErrorUsuario("Todavía no hay modelos entrenados. Ejecuta entrenar_inicial.py primero.")
        return version

    def modelos(self, version=None):
        version = version or self.version_activa()
        if version not in self._modelos:
            self._modelos[version] = {
                clave: ModeloBase.cargar(CARPETA_MODELOS / version / f"{clave}.joblib") for clave in CLAVES_MODELOS
            }
        return self._modelos[version]

    def olvidar_cache(self, version=None):
        if version:
            self._modelos.pop(version, None)
        else:
            self._modelos.clear()

    def subir(self, archivos, lote=None, enderezar=None):
        """`enderezar`: para cada archivo, si se endereza solo (por defecto todos). No se endereza lo que la persona
        ya giró a mano, por ejemplo en la vista previa del celular."""
        if not archivos:
            raise ErrorUsuario("No se recibió ninguna foto.")
        if lote:
            if not re.fullmatch(r"lote_[\d_-]+b*", lote) or not (CARPETA_FOTOS / lote).is_dir():
                raise ErrorUsuario("Esa tanda de fotos ya no existe. Recarga la página.")
            existentes = len(self.almacen.fotos_del_lote(lote))
        else:
            lote = datetime.now().strftime("lote_%Y-%m-%d_%H%M%S")
            while (CARPETA_FOTOS / lote).exists():
                lote += "b"
            existentes = 0
        if existentes + len(archivos) > MAXIMO_FOTOS:
            raise ErrorUsuario(f"Máximo {MAXIMO_FOTOS} fotos por tanda; ya tienes {existentes}.")
        carpeta = CARPETA_FOTOS / lote
        carpeta.mkdir(parents=True, exist_ok=True)
        fotos, errores = [], []
        for posicion, (nombre, datos) in enumerate(archivos):
            avance.informar(posicion / len(archivos), f"Foto {posicion + 1} de {len(archivos)}: revisando y enderezando")
            if len(datos) > MAXIMO_BYTES:
                errores.append(f"{nombre}: pesa más de 12 MB.")
                continue
            try:
                imagen = decodificar_imagen(datos)
            except ValueError:
                errores.append(f"{nombre}: no es una imagen válida.")
                continue
            giro = None
            if enderezar is None or posicion >= len(enderezar) or enderezar[posicion]:
                giro, imagen = self._enderezar(imagen)
            avance.informar((posicion + 0.6) / len(archivos), f"Foto {posicion + 1} de {len(archivos)}: buscando los dígitos")
            foto_id = self.almacen.insertar_foto(lote, "", nombre)
            archivo = f"foto_{foto_id:04d}.png"
            cv2.imwrite(str(carpeta / archivo), imagen)
            with self.almacen.conexion() as con:
                con.execute("UPDATE fotos SET archivo = ? WHERE id = ?", (f"{lote}/{archivo}", foto_id))
            detectados = len(procesar_foto(imagen)["cajas"])
            fotos.append({"id": foto_id, "nombre": nombre, "url": f"/foto/{foto_id}", "detectados": detectados,
                          "girada": giro is not None})
        if not fotos:
            raise ErrorUsuario(" ".join(errores))
        return {"lote": lote, "fotos": fotos, "errores": errores}

    def _enderezar(self, imagen):
        """Endereza fotos tomadas de lado o de cabeza usando la seguridad de la CNN de la version activa."""
        version = self.almacen.version_activa()
        if not version:
            return None, imagen
        cnn = self.modelos(version)["cnn"]
        return orientar(imagen, lambda X: cnn.probabilidades(X).max(axis=1))

    def girar_foto(self, foto_id):
        """«Girar»: gira la foto guardada 90 grados a la derecha, para enderezarla a mano."""
        ruta = self.ruta_foto(foto_id)
        imagen = cv2.imread(str(ruta))
        if imagen is None:
            raise ErrorUsuario("No se pudo abrir la foto.")
        imagen = cv2.rotate(imagen, cv2.ROTATE_90_CLOCKWISE)
        cv2.imwrite(str(ruta), imagen)
        detectados = len(procesar_foto(imagen)["cajas"])
        return {"id": foto_id, "url": f"/foto/{foto_id}?v={ruta.stat().st_mtime_ns}", "detectados": detectados}

    def ruta_foto(self, foto_id):
        foto = self.almacen.obtener_foto(foto_id)
        if not foto or not foto["archivo"]:
            raise ErrorUsuario("Foto no encontrada.")
        return CARPETA_FOTOS / foto["archivo"]

    def quitar_foto(self, foto_id):
        ruta = self.ruta_foto(foto_id)
        self.almacen.borrar_foto(foto_id)
        ruta.unlink(missing_ok=True)

    def pasos_foto(self, foto_id):
        foto = self.almacen.obtener_foto(foto_id)
        imagen = cv2.imread(str(self.ruta_foto(foto_id)))
        esperado = len(foto["texto"]) if foto and foto["texto"] else None
        resultado = procesar_foto(imagen, esperado)
        pasos = resultado["pasos"]
        return {
            "pasos": [
                {"clave": "original", "titulo": "1. Foto (derecha y, si el número es chico, ampliada)", "uri": _miniatura(pasos["original"])},
                {"clave": "gris", "titulo": "2. Escala de grises (o el color que oculta la cuadrícula)", "uri": _miniatura(pasos["gris"])},
                {"clave": "iluminacion", "titulo": "3. Sombras corregidas y normalizado", "uri": _miniatura(pasos["iluminacion"])},
                {"clave": "binaria", "titulo": "4. Tinta separada del papel, sin cuadrícula ni renglones", "uri": _miniatura(pasos["binaria"])},
                {"clave": "segmentacion", "titulo": "5. Dígitos segmentados", "uri": _miniatura(pasos["segmentacion"])},
            ],
            "recortes": [
                {"uri": a_data_uri(cv2.resize(r, (84, 84), interpolation=cv2.INTER_NEAREST))} for r in resultado["recortes"]
            ],
            "detectados": resultado["cantidad_detectada"],
            "aviso": resultado["aviso"],
        }

    def foto_con_digito(self, foto_id, posicion):
        """La foto tal como la leyó la aplicación (derecha y, si el número es chico, ampliada) con un recuadro en el dígito
        `posicion` (desde 0). PNG de hasta 900 píxeles de ancho."""
        foto = self.almacen.obtener_foto(foto_id)
        imagen = cv2.imread(str(self.ruta_foto(foto_id)))
        resultado = procesar_foto(imagen, len(foto["texto"]) if foto and foto["texto"] else None)
        base = resultado["pasos"]["original"].copy()
        if 0 <= posicion < len(resultado["cajas"]):
            x, y, w, h = resultado["cajas"][posicion]
            grosor = max(3, round(max(base.shape[:2]) / 160))
            margen = 2 * grosor
            cv2.rectangle(base, (x - margen, y - margen), (x + w + margen, y + h + margen), (255, 77, 108), grosor)
        if base.shape[1] > 900:
            base = cv2.resize(base, (900, round(base.shape[0] * 900 / base.shape[1])), interpolation=cv2.INTER_AREA)
        return cv2.imencode(".png", base)[1].tobytes()

    def predecir(self, lote, textos):
        fotos = {f["id"]: f for f in self.almacen.fotos_del_lote(lote)}
        if not fotos:
            raise ErrorUsuario("No hay fotos en este lote.")
        limpios = {}
        for clave, texto in textos.items():
            foto_id = int(clave)
            texto = str(texto).strip()
            if foto_id not in fotos:
                continue
            if not re.fullmatch(r"\d{1,%d}" % MAXIMO_DIGITOS, texto):
                raise ErrorUsuario(f"El número de «{fotos[foto_id]['nombre']}» debe tener entre 1 y {MAXIMO_DIGITOS} dígitos, sin espacios ni letras.")
            limpios[foto_id] = texto
        faltan = [f["nombre"] for i, f in fotos.items() if i not in limpios and not f["texto"]]
        if faltan:
            raise ErrorUsuario("Falta escribir el número de: " + ", ".join(faltan[:5]) + ("…" if len(faltan) > 5 else ""))

        version = self.version_activa()
        modelos = self.modelos(version)
        total = len(limpios)
        for posicion, (foto_id, texto) in enumerate(limpios.items()):
            # Las fotos ocupan el 85 % de la barra; el resto es armar los resultados
            base, parte = 0.85 * posicion / total, 0.85 / total
            avance.informar(base, f"Foto {posicion + 1} de {total}: separando los dígitos")
            imagen = cv2.imread(str(self.ruta_foto(foto_id)))
            resultado = procesar_foto(imagen, esperado=len(texto))
            coincide = len(resultado["cajas"]) == len(texto)
            reales = [int(c) for c in texto] if coincide else [None] * len(resultado["cajas"])
            self.almacen.actualizar_foto(foto_id, texto, resultado["aviso"])
            if not len(resultado["cajas"]):
                self.almacen.reemplazar_digitos(foto_id, [], [])
                continue
            ids = self.almacen.reemplazar_digitos(foto_id, reales, resultado["digitos"])
            for turno, (clave, modelo) in enumerate(modelos.items()):
                avance.informar(base + parte * (0.3 + 0.7 * turno / len(modelos)),
                                f"Foto {posicion + 1} de {total}: la lee {NOMBRES_MODELOS[clave]}")
                self.almacen.guardar_predicciones(version, ids, clave, modelo.probabilidades(resultado["digitos"]))
        avance.informar(0.86, "Armando los resultados")
        with avance.tramo(0.86, 1.0):
            return self.resultado_lote(lote, avisar=True)

    def asegurar_predicciones(self, lote, version, avisar=False):
        """Calcula y guarda las predicciones de una version para los digitos del lote si aun no existen."""
        fotos = [f for f in self.almacen.fotos_del_lote(lote) if f["texto"]]
        digitos = self.almacen.digitos_de_fotos([f["id"] for f in fotos])
        if not digitos:
            return
        existentes = {(p["digito_id"], p["modelo"]) for p in self.almacen.predicciones([d["id"] for d in digitos], version)}
        ids = [d["id"] for d in digitos]
        X = np.stack([d["pixeles"] for d in digitos])
        modelos = self.modelos(version)
        for turno, (clave, modelo) in enumerate(modelos.items()):
            if any((i, clave) not in existentes for i in ids):
                if avisar:
                    avance.informar(0.1 + 0.6 * turno / len(modelos), f"Leyendo la tanda con {NOMBRES_MODELOS[clave]}")
                self.almacen.guardar_predicciones(version, ids, clave, modelo.probabilidades(X))

    def resultado_lote(self, lote, version=None, avisar=False):
        """`avisar`: cuenta su avance en la barra (solo cuando es la tarea principal, no cuando otra la usa)."""
        version = version or self.version_activa()
        if version not in {v["id"] for v in self.almacen.listar_versiones()}:
            raise ErrorUsuario("Esa versión no existe.")
        self.asegurar_predicciones(lote, version, avisar)
        if avisar:
            avance.informar(0.75, "Preparando las tarjetas de cada foto")
        fotos = [f for f in self.almacen.fotos_del_lote(lote) if f["texto"]]
        digitos = self.almacen.digitos_de_fotos([f["id"] for f in fotos])
        predicciones = self.almacen.predicciones([d["id"] for d in digitos], version)
        por_digito = {}
        for p in predicciones:
            por_digito.setdefault(p["digito_id"], {})[p["modelo"]] = p
        marcador = {c: {"digitos_ok": 0, "digitos": 0, "numeros_ok": 0, "numeros": 0} for c in CLAVES_MODELOS}

        salida = []
        for foto in fotos:
            propios = [d for d in digitos if d["foto_id"] == foto["id"]]
            completo = len(propios) == len(foto["texto"]) and all(d["real"] is not None for d in propios)
            lista = []
            for d in propios:
                modelos_digito = {}
                for clave, p in por_digito.get(d["id"], {}).items():
                    orden = np.argsort(p["probs"])[::-1][:3]
                    modelos_digito[clave] = {
                        "predicho": p["predicho"],
                        "confianza": p["confianza"],
                        "top3": [[int(i), p["probs"][i]] for i in orden],
                        "acierto": (p["predicho"] == d["real"]) if d["real"] is not None else None,
                    }
                lista.append({
                    "id": d["id"], "posicion": d["posicion"], "real": d["real"],
                    "imagen": uri_digito(d["pixeles"], 4), "modelos": modelos_digito,
                })
            por_modelo = {}
            for clave in CLAVES_MODELOS:
                numero = "".join(str(d["modelos"][clave]["predicho"]) if clave in d["modelos"] else "?" for d in lista)
                aciertos = sum(1 for d in lista if d["modelos"].get(clave, {}).get("acierto"))
                correcto = completo and numero == foto["texto"]
                por_modelo[clave] = {"numero": numero, "correcto": correcto, "aciertos": aciertos}
                if completo:
                    marcador[clave]["digitos"] += len(lista)
                    marcador[clave]["digitos_ok"] += aciertos
                    marcador[clave]["numeros"] += 1
                    marcador[clave]["numeros_ok"] += int(correcto)
            salida.append({
                "id": foto["id"], "nombre": foto["nombre"], "url": f"/foto/{foto['id']}", "texto": foto["texto"],
                "aviso": foto["aviso"], "completa": completo, "digitos": lista, "por_modelo": por_modelo,
            })
        ranking = sorted(marcador.items(), key=lambda kv: (-kv[1]["digitos_ok"], -kv[1]["numeros_ok"], kv[0]))
        return {
            "lote": lote,
            "version": version,
            "fotos": salida,
            "marcador": [{"modelo": c, **datos} for c, datos in ranking],
        }

    def explicar_digito(self, digito_id, clave):
        digito = self.almacen.obtener_digito(digito_id)
        if not digito or clave not in CLAVES_MODELOS:
            raise ErrorUsuario("Dígito o modelo no encontrado.")
        return {**explicar(self.modelos()[clave], digito["pixeles"]), "digito": digito_id, "real": digito["real"],
                "imagen": uri_digito(digito["pixeles"])}

    # ---------------- tanda abierta (la que se muestra al entrar en «Predecir y corregir»)
    @property
    def _ruta_tanda_cerrada(self):
        return self.almacen.ruta.parent / "tanda_cerrada.txt"

    def tanda_abierta(self):
        """Ultima tanda con fotos, salvo que la persona ya haya pedido empezar una nueva."""
        ultimo = self.almacen.ultimo_lote()
        try:
            cerrada = self._ruta_tanda_cerrada.read_text(encoding="utf-8").strip()
        except OSError:
            cerrada = ""
        return None if ultimo and ultimo == cerrada else ultimo

    def cerrar_tanda(self):
        """«Empezar una tanda nueva»: recuerda que la ultima tanda ya esta cerrada, tambien al volver a entrar o reiniciar la app."""
        self._ruta_tanda_cerrada.write_text(self.almacen.ultimo_lote() or "", encoding="utf-8")

    def listar_versiones(self):
        return {"activa": self.almacen.version_activa(), "versiones": self.almacen.listar_versiones(),
                "en_basura": len(self.almacen.listar_versiones(eliminadas=True))}

    # ---------------- basura de versiones (recuperable)
    @staticmethod
    def _carpetas_version(id_version):
        return [(CARPETA_MODELOS / id_version, CARPETA_MODELOS / "_papelera" / id_version),
                (CARPETA_RESULTADOS / id_version, CARPETA_RESULTADOS / "_papelera" / id_version)]

    @staticmethod
    def _id_valido(id_version):
        if not re.fullmatch(r"v\d{1,6}", str(id_version)):
            raise ErrorUsuario("Versión no válida.")
        return str(id_version)

    def versiones_basura(self):
        return self.almacen.listar_versiones(eliminadas=True)

    def quitar_versiones(self, ids):
        """Manda versiones a la basura. La inicial (v1) y la activa no se pueden quitar."""
        ids = [self._id_valido(i) for i in ids]
        if not ids:
            raise ErrorUsuario("Elige al menos una versión para mandar a la basura.")
        with self._candado:
            visibles = {v["id"]: v for v in self.almacen.listar_versiones()}
            activa = self.almacen.version_activa()
            for id_version in ids:
                if id_version not in visibles:
                    raise ErrorUsuario(f"La versión {id_version} no existe o ya está en la basura.")
                if visibles[id_version]["numero"] == 1:
                    raise ErrorUsuario("La versión v1 es la inicial y sirve de base para comparar: no se puede quitar.")
                if id_version == activa:
                    raise ErrorUsuario(f"La versión {id_version} está activa. Activa otra versión antes de quitarla.")
            for id_version in ids:
                for origen, destino in self._carpetas_version(id_version):
                    if origen.exists():
                        destino.parent.mkdir(parents=True, exist_ok=True)
                        if destino.exists():
                            raise ErrorUsuario(f"Ya hay una carpeta de la versión {id_version} en la basura. Vacíala primero.")
                        shutil.move(str(origen), str(destino))
                self.almacen.marcar_eliminada(id_version, True)
                self._modelos.pop(id_version, None)
        return {"quitadas": ids, **self.listar_versiones()}

    def restaurar_version(self, id_version):
        id_version = self._id_valido(id_version)
        with self._candado:
            if id_version not in {v["id"] for v in self.almacen.listar_versiones(eliminadas=True)}:
                raise ErrorUsuario("Esa versión no está en la basura.")
            carpetas = self._carpetas_version(id_version)
            if any(normal.exists() for normal, _ in carpetas):
                raise ErrorUsuario("No se puede restaurar: ya existe una carpeta con ese nombre.")
            for normal, papelera in carpetas:
                if papelera.exists():
                    shutil.move(str(papelera), str(normal))
            self.almacen.marcar_eliminada(id_version, False)
        return self.listar_versiones()

    def borrar_para_siempre(self, id_version):
        id_version = self._id_valido(id_version)
        with self._candado:
            if id_version not in {v["id"] for v in self.almacen.listar_versiones(eliminadas=True)}:
                raise ErrorUsuario("Esa versión no está en la basura.")
            for _, papelera in self._carpetas_version(id_version):
                if papelera.exists() and papelera.parent.name == "_papelera":
                    shutil.rmtree(papelera)
            self.almacen.borrar_version_para_siempre(id_version)
        return self.listar_versiones()

    def vaciar_basura(self):
        for v in self.almacen.listar_versiones(eliminadas=True):
            self.borrar_para_siempre(v["id"])
        return self.listar_versiones()

    # ---------------- basura de tandas de fotos (recuperable)
    @staticmethod
    def _lote_valido(lote):
        if not re.fullmatch(r"lote_[\d_-]+b*", str(lote)):
            raise ErrorUsuario("Tanda de fotos no válida.")
        return str(lote)

    def lotes_basura(self):
        return self.almacen.lotes(eliminadas=True)

    def _estado_lotes(self):
        return {"lotes": self.almacen.lotes(), "basura": self.almacen.lotes(eliminadas=True)}

    def quitar_lotes(self, ids):
        """Manda tandas de fotos a la basura: dejan de verse y de servir como memoria al corregir, pero se pueden restaurar."""
        ids = [self._lote_valido(i) for i in ids]
        if not ids:
            raise ErrorUsuario("Elige al menos una tanda de fotos.")
        with self._candado:
            visibles = {l["lote"] for l in self.almacen.lotes()}
            for lote in ids:
                if lote not in visibles:
                    raise ErrorUsuario("Esa tanda no existe o ya está en la basura.")
            for lote in ids:
                self.almacen.marcar_lote_eliminado(lote, True)
        return {"quitadas": ids, **self._estado_lotes()}

    def restaurar_lote(self, lote):
        lote = self._lote_valido(lote)
        with self._candado:
            if lote not in {l["lote"] for l in self.almacen.lotes(eliminadas=True)}:
                raise ErrorUsuario("Esa tanda no está en la basura.")
            self.almacen.marcar_lote_eliminado(lote, False)
        return self._estado_lotes()

    def borrar_lote_para_siempre(self, lote):
        lote = self._lote_valido(lote)
        with self._candado:
            if lote not in {l["lote"] for l in self.almacen.lotes(eliminadas=True)}:
                raise ErrorUsuario("Esa tanda no está en la basura.")
            self.almacen.borrar_lote_para_siempre(lote)
            carpeta = CARPETA_FOTOS / lote
            if carpeta.is_dir() and carpeta.parent == CARPETA_FOTOS:
                shutil.rmtree(carpeta)
        return self._estado_lotes()

    def vaciar_basura_lotes(self):
        for l in self.almacen.lotes(eliminadas=True):
            self.borrar_lote_para_siempre(l["lote"])
        return self._estado_lotes()

    def activar_version(self, id_version):
        if id_version not in {v["id"] for v in self.almacen.listar_versiones()} or not (CARPETA_MODELOS / id_version).is_dir():
            raise ErrorUsuario("Esa versión no existe.")
        self.almacen.activar_version(id_version)
        return self.listar_versiones()

    def crear_version(self, motivo, reemplazos, extra=None):
        """Guarda una version nueva con los modelos de `reemplazos` y copia el resto de la activa; la deja activa."""
        version = self.version_activa()
        versiones = self.almacen.listar_versiones()
        actuales = self.modelos(version)
        detalle = next(v["detalle"] for v in versiones if v["id"] == version)
        _, _, x_pru, y_pru = self.mnist
        numero = self.almacen.siguiente_numero()
        nueva = f"v{numero}"
        carpeta = CARPETA_MODELOS / nueva
        carpeta.mkdir(parents=True, exist_ok=True)
        exactitud = dict(detalle.get("exactitud_prueba", {}))
        for clave in CLAVES_MODELOS:
            if clave in reemplazos:
                reemplazos[clave].guardar(carpeta / f"{clave}.joblib")
                exactitud[clave] = _aciertos(reemplazos[clave], x_pru, y_pru) / len(y_pru)
            else:
                shutil.copy2(CARPETA_MODELOS / version / f"{clave}.joblib", carpeta / f"{clave}.joblib")
                if clave not in exactitud:
                    exactitud[clave] = _aciertos(actuales[clave], x_pru, y_pru) / len(y_pru)
        self.almacen.registrar_version(nueva, numero, motivo, {"origen": version, "actualizados": sorted(reemplazos),
                                                              "exactitud_prueba": exactitud, **(extra or {})})
        self._modelos[nueva] = {c: reemplazos.get(c, actuales[c]) for c in CLAVES_MODELOS}
        return nueva

    @staticmethod
    def _elegir_reserva(ids_fotos, errores_por_modelo):
        """Con 3 fotos o mas se reserva cerca del 30 % (sin usar para entrenar) para comprobar que aprenden de verdad.

        Cada modelo con errores conserva para aprender al menos la mitad de las fotos donde fallo.
        """
        if len(ids_fotos) < 3:
            return set()
        cantidad = max(1, round(0.3 * len(ids_fotos)))
        reserva = set()
        for foto_id in sorted(ids_fotos, key=lambda i: (i * 2654435761) % 4294967296):
            if len(reserva) == cantidad:
                break
            prueba = reserva | {foto_id}
            if all(not fotos or (fotos - prueba and len(fotos - prueba) >= len(fotos) / 2)
                   for fotos in errores_por_modelo.values()):
                reserva = prueba
        return reserva

    def corregir(self, lote, modelos=None, excluir=()):
        with self._candado:
            return self._corregir(lote, list(modelos or []), {int(i) for i in excluir})

    def _corregir(self, lote, elegidos, excluir):
        version = self.version_activa()
        versiones = self.almacen.listar_versiones()
        actuales = self.modelos(version)
        detalle_actual = next(v["detalle"] for v in versiones if v["id"] == version)
        fotos = [f for f in self.almacen.fotos_del_lote(lote) if f["texto"]]
        digitos = [d for d in self.almacen.digitos_de_fotos([f["id"] for f in fotos]) if d["real"] is not None]
        if not digitos:
            raise ErrorUsuario("Primero predice con tus fotos: todavía no hay dígitos con número.")
        usables = [d for d in digitos if d["id"] not in excluir]
        if not usables:
            raise ErrorUsuario("No quedan dígitos para aprender. Vuelve a marcar alguno de los que quitaste.")
        avance.informar(0.02, "Revisando en qué se equivocó cada modelo")
        X_usables = np.stack([d["pixeles"] for d in usables])
        y_usables = np.array([d["real"] for d in usables], dtype=np.int64)
        predicho_todos = {c: m.predecir(X_usables) for c, m in actuales.items()}
        errores_por_modelo = {c: {d["foto_id"] for d, p, r in zip(usables, predicho_todos[c], y_usables) if p != r}
                              for c in CLAVES_MODELOS}
        reserva_fotos = self._elegir_reserva(sorted({d["foto_id"] for d in usables}), errores_por_modelo)
        en_reserva = np.array([d["foto_id"] in reserva_fotos for d in usables])
        entrenamiento = [d for d, r in zip(usables, en_reserva) if not r]
        reserva = [d for d, r in zip(usables, en_reserva) if r]

        X_ent, y_ent = X_usables[~en_reserva], y_usables[~en_reserva]
        X_res = X_usables[en_reserva] if reserva else None
        y_res = y_usables[en_reserva] if reserva else None
        predicho_antes = {c: p[~en_reserva] for c, p in predicho_todos.items()}
        con_errores = [c for c in CLAVES_MODELOS if (predicho_antes[c] != y_ent).any()]
        objetivo = [c for c in (elegidos or con_errores) if c in con_errores]
        if not objetivo:
            raise ErrorUsuario("Ningún modelo se equivocó en estas fotos, así que no hay nada que corregir.")

        avance.informar(0.05, "Preparando los dígitos de memoria")
        x_mnist, y_mnist, x_pru, y_pru = self.mnist
        numero = self.almacen.siguiente_numero()
        X_mem, y_mem = submuestra_estratificada(x_mnist, y_mnist, MUESTRA_MEMORIA_MNIST, semilla=numero)
        ids_lote = {d["id"] for d in digitos}
        previos = [d for grupo in ("entrenamiento", "reserva") for d in self.almacen.digitos_con_grupo(grupo)
                   if d["id"] not in ids_lote]
        X_prev0 = y_prev0 = None
        if previos:
            X_prev0 = np.stack([d["pixeles"] for d in previos])
            y_prev0 = np.array([d["real"] for d in previos], dtype=np.int64)
            X_prev, y_prev = aumentar(X_prev0, y_prev0, COPIAS_MEMORIA_PREVIOS, semilla=numero)
            X_mem, y_mem = np.concatenate([X_mem, X_prev]), np.concatenate([y_mem, y_prev])

        mnist_antes = detalle_actual.get("exactitud_prueba", {})
        informe, aceptados = [], {}
        for clave in CLAVES_MODELOS:
            actual = actuales[clave]
            errores_antes = int((predicho_antes[clave] != y_ent).sum())
            entrada = {"modelo": clave, "entrenado": clave in objetivo, "aceptado": False, "motivo": None,
                       "errores_antes": errores_antes}
            if clave not in objetivo:
                entrada["motivo"] = "No se equivocó en estas fotos: no necesita cambios."
                informe.append(entrada)
                continue
            turno = objetivo.index(clave)
            paso = f"Modelo {turno + 1} de {len(objetivo)}: {NOMBRES_MODELOS[clave]}"
            avance.informar(0.1 + 0.8 * turno / len(objetivo), paso)
            mnist_previo = mnist_antes.get(clave)
            if mnist_previo is None:
                mnist_previo = _aciertos(actual, x_pru, y_pru) / len(y_pru)
            reserva_antes = _aciertos(actual, X_res, y_res) if reserva else None
            previos_antes = _aciertos(actual, X_prev0, y_prev0) if previos else None
            malos = predicho_antes[clave] != y_ent
            X_err, y_err = aumentar(X_ent[malos], y_ent[malos], COPIAS_ERROR, semilla=numero)
            X_ok, y_ok = aumentar(X_ent[~malos], y_ent[~malos], COPIAS_ACIERTO, semilla=numero + 1)
            X_nuevo, y_nuevo = np.concatenate([X_err, X_ok]), np.concatenate([y_err, y_ok])
            motivo = None
            for intento, fuerza in enumerate(FUERZAS_ACTUALIZACION):
                avance.informar(0.1 + 0.8 * (turno + intento / len(FUERZAS_ACTUALIZACION)) / len(objetivo), paso)
                candidato = copy.deepcopy(actual)
                candidato.actualizar(X_nuevo, y_nuevo, X_mem, y_mem, fuerza)
                mnist_despues = _aciertos(candidato, x_pru, y_pru) / len(y_pru)
                errores_despues = int((candidato.predecir(X_ent) != y_ent).sum())
                previos_despues = _aciertos(candidato, X_prev0, y_prev0) if previos else None
                if mnist_despues < mnist_previo - TOLERANCIA_MNIST:
                    motivo = (f"Bajaba la exactitud en MNIST de {_porcentaje(mnist_previo)} a {_porcentaje(mnist_despues)}, "
                              "así que se mantuvo el modelo anterior para no perder lo aprendido.")
                elif previos and previos_despues < previos_antes - max(1, round(0.05 * len(y_prev0))):
                    motivo = ("Empezaba a fallar en dígitos que ya había aprendido de tandas anteriores, "
                              "así que se mantuvo el modelo anterior.")
                elif errores_despues >= errores_antes:
                    motivo = "No logró corregir ningún dígito, así que se mantuvo el modelo anterior."
                else:
                    motivo = None
                    break
            entrada.update({
                "mnist_antes": mnist_previo, "mnist_despues": mnist_despues,
                "entrenamiento_antes": [len(y_ent) - errores_antes, len(y_ent)],
                "entrenamiento_despues": [len(y_ent) - errores_despues, len(y_ent)],
                "reserva_antes": [reserva_antes, len(y_res)] if reserva else None,
                "reserva_despues": [_aciertos(candidato, X_res, y_res), len(y_res)] if reserva else None,
                "anteriores_antes": [previos_antes, len(y_prev0)] if previos else None,
                "anteriores_despues": [previos_despues, len(y_prev0)] if previos else None,
                "corregidos": errores_antes - errores_despues, "fuerza": fuerza, "motivo": motivo,
            })
            if motivo is None:
                entrada["aceptado"] = True
                aceptados[clave] = (candidato, mnist_despues)
            informe.append(entrada)

        nombres = {f["id"]: f["nombre"] for f in fotos}
        resumen = {"digitos_entrenamiento": len(entrenamiento), "digitos_reserva": len(reserva),
                   "fotos_reserva": len(reserva_fotos), "fotos": len({d["foto_id"] for d in usables}),
                   "nombres_reserva": sorted(nombres[i] for i in reserva_fotos)}
        if not aceptados:
            return {"version_anterior": version, "version_nueva": None, "informe": informe, "resumen": resumen,
                    "mensaje": "Ningún modelo mejoró sin perder lo aprendido; se conservó la versión actual."}

        avance.informar(0.92, "Guardando la versión nueva")
        nueva = f"v{numero}"
        carpeta = CARPETA_MODELOS / nueva
        carpeta.mkdir(parents=True, exist_ok=True)
        modelos_nuevos, exactitud = {}, dict(mnist_antes)
        for clave in CLAVES_MODELOS:
            if clave in aceptados:
                aceptados[clave][0].guardar(carpeta / f"{clave}.joblib")
                modelos_nuevos[clave] = aceptados[clave][0]
                exactitud[clave] = aceptados[clave][1]
            else:
                shutil.copy2(CARPETA_MODELOS / version / f"{clave}.joblib", carpeta / f"{clave}.joblib")
                modelos_nuevos[clave] = actuales[clave]
                if clave not in exactitud:
                    exactitud[clave] = _aciertos(actuales[clave], x_pru, y_pru) / len(y_pru)
        self.almacen.registrar_version(
            nueva, numero, f"Corrección con {len(entrenamiento)} dígitos de {resumen['fotos']} fotos",
            {"origen": version, "lote": lote, "actualizados": sorted(aceptados), "exactitud_prueba": exactitud,
             "informe": informe, "resumen": resumen},
        )
        self._modelos[nueva] = modelos_nuevos
        for d in entrenamiento:
            self.almacen.marcar_grupo(d["id"], "entrenamiento")
        for d in reserva:
            self.almacen.marcar_grupo(d["id"], "reserva")
        avance.informar(0.97, "Leyendo la tanda con la versión nueva")
        return {"version_anterior": version, "version_nueva": nueva, "informe": informe, "resumen": resumen,
                "resultado": self.resultado_lote(lote, nueva)}
