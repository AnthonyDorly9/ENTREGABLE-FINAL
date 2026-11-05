import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import numpy as np

from .configuracion import CARPETA_DATOS

RUTA_BD = CARPETA_DATOS / "base_de_datos" / "aplicacion.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS versiones (
    id TEXT PRIMARY KEY, numero INTEGER, creada TEXT, motivo TEXT, activa INTEGER DEFAULT 0, detalle TEXT
);
CREATE TABLE IF NOT EXISTS fotos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, lote TEXT, archivo TEXT, nombre TEXT, texto TEXT, aviso TEXT, creada TEXT
);
CREATE TABLE IF NOT EXISTS digitos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, foto_id INTEGER, posicion INTEGER, real INTEGER, pixeles BLOB, grupo TEXT
);
CREATE TABLE IF NOT EXISTS predicciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, digito_id INTEGER, version TEXT, modelo TEXT,
    predicho INTEGER, confianza REAL, probs TEXT
);
CREATE INDEX IF NOT EXISTS idx_pred ON predicciones (digito_id, version, modelo);
"""


def ahora():
    return datetime.now().isoformat(timespec="seconds")


class Almacen:
    def __init__(self, ruta=RUTA_BD):
        self.ruta = ruta
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.conexion() as con:
            con.executescript(ESQUEMA)
            columnas = {f["name"] for f in con.execute("PRAGMA table_info(versiones)").fetchall()}
            if "eliminada" not in columnas:
                con.execute("ALTER TABLE versiones ADD COLUMN eliminada INTEGER DEFAULT 0")
            columnas_fotos = {f["name"] for f in con.execute("PRAGMA table_info(fotos)").fetchall()}
            if "eliminada" not in columnas_fotos:
                con.execute("ALTER TABLE fotos ADD COLUMN eliminada INTEGER DEFAULT 0")

    @contextmanager
    def conexion(self):
        con = sqlite3.connect(self.ruta)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def registrar_version(self, id_version, numero, motivo, detalle=None, activar=True):
        with self.conexion() as con:
            if activar:
                con.execute("UPDATE versiones SET activa = 0")
            con.execute("DELETE FROM predicciones WHERE version = ?", (id_version,))  # restos de una version anterior con ese nombre
            con.execute(
                "INSERT OR REPLACE INTO versiones (id, numero, creada, motivo, activa, detalle) VALUES (?, ?, ?, ?, ?, ?)",
                (id_version, numero, ahora(), motivo, int(activar), json.dumps(detalle or {}, ensure_ascii=False)),
            )

    def actualizar_detalle_version(self, id_version, detalle):
        with self.conexion() as con:
            con.execute("UPDATE versiones SET detalle = ? WHERE id = ?", (json.dumps(detalle, ensure_ascii=False), id_version))

    def activar_version(self, id_version):
        with self.conexion() as con:
            con.execute("UPDATE versiones SET activa = 0")
            con.execute("UPDATE versiones SET activa = 1 WHERE id = ?", (id_version,))

    def version_activa(self):
        with self.conexion() as con:
            fila = con.execute("SELECT id FROM versiones WHERE activa = 1").fetchone()
        return fila["id"] if fila else None

    def listar_versiones(self, eliminadas=False):
        """Versiones visibles; con eliminadas=True devuelve las que estan en la basura."""
        with self.conexion() as con:
            filas = con.execute("SELECT * FROM versiones WHERE COALESCE(eliminada, 0) = ? ORDER BY numero", (int(eliminadas),)).fetchall()
        return [{**dict(f), "detalle": json.loads(f["detalle"] or "{}")} for f in filas]

    def siguiente_numero(self):
        """Numero de la proxima version: el menor libre, para reutilizar los huecos de las versiones borradas.

        Las que estan en la basura siguen contando como ocupadas, para poder restaurarlas sin choques de nombre.
        """
        with self.conexion() as con:
            usados = {f["numero"] for f in con.execute("SELECT numero FROM versiones").fetchall()}
        numero = 1
        while numero in usados:
            numero += 1
        return numero

    def marcar_eliminada(self, id_version, eliminada):
        with self.conexion() as con:
            con.execute("UPDATE versiones SET eliminada = ? WHERE id = ?", (int(eliminada), id_version))

    def borrar_version_para_siempre(self, id_version):
        with self.conexion() as con:
            con.execute("DELETE FROM predicciones WHERE version = ?", (id_version,))
            con.execute("DELETE FROM versiones WHERE id = ? AND COALESCE(eliminada, 0) = 1", (id_version,))

    def insertar_foto(self, lote, archivo, nombre):
        with self.conexion() as con:
            cursor = con.execute(
                "INSERT INTO fotos (lote, archivo, nombre, creada) VALUES (?, ?, ?, ?)", (lote, archivo, nombre, ahora())
            )
            return cursor.lastrowid

    def obtener_foto(self, foto_id):
        with self.conexion() as con:
            fila = con.execute("SELECT * FROM fotos WHERE id = ?", (foto_id,)).fetchone()
        return dict(fila) if fila else None

    def fotos_del_lote(self, lote):
        with self.conexion() as con:
            return [dict(f) for f in con.execute("SELECT * FROM fotos WHERE lote = ? ORDER BY id", (lote,)).fetchall()]

    def lotes(self, eliminadas=False):
        """Tandas con al menos una foto ya leida, de la mas antigua a la mas reciente; con eliminadas=True, las de la basura."""
        with self.conexion() as con:
            filas = con.execute(
                "SELECT lote, COUNT(*) AS fotos, MIN(creada) AS creada FROM fotos "
                "WHERE texto IS NOT NULL AND COALESCE(eliminada, 0) = ? GROUP BY lote ORDER BY MIN(id)", (int(eliminadas),)
            ).fetchall()
        return [dict(f) for f in filas]

    def ultimo_lote(self):
        with self.conexion() as con:
            fila = con.execute("SELECT lote FROM fotos WHERE COALESCE(eliminada, 0) = 0 ORDER BY id DESC LIMIT 1").fetchone()
        return fila["lote"] if fila else None

    def marcar_lote_eliminado(self, lote, eliminado):
        with self.conexion() as con:
            con.execute("UPDATE fotos SET eliminada = ? WHERE lote = ?", (int(eliminado), lote))

    def borrar_lote_para_siempre(self, lote):
        """Borra las fotos de una tanda que ya esta en la basura, con sus digitos y predicciones."""
        with self.conexion() as con:
            ids = [f["id"] for f in con.execute("SELECT id FROM fotos WHERE lote = ? AND COALESCE(eliminada, 0) = 1", (lote,)).fetchall()]
            for foto_id in ids:
                for digito in con.execute("SELECT id FROM digitos WHERE foto_id = ?", (foto_id,)).fetchall():
                    con.execute("DELETE FROM predicciones WHERE digito_id = ?", (digito["id"],))
                con.execute("DELETE FROM digitos WHERE foto_id = ?", (foto_id,))
                con.execute("DELETE FROM fotos WHERE id = ?", (foto_id,))

    def actualizar_foto(self, foto_id, texto, aviso):
        with self.conexion() as con:
            con.execute("UPDATE fotos SET texto = ?, aviso = ? WHERE id = ?", (texto, aviso, foto_id))

    def borrar_foto(self, foto_id):
        with self.conexion() as con:
            ids = [f["id"] for f in con.execute("SELECT id FROM digitos WHERE foto_id = ?", (foto_id,)).fetchall()]
            for digito_id in ids:
                con.execute("DELETE FROM predicciones WHERE digito_id = ?", (digito_id,))
            con.execute("DELETE FROM digitos WHERE foto_id = ?", (foto_id,))
            con.execute("DELETE FROM fotos WHERE id = ?", (foto_id,))

    def reemplazar_digitos(self, foto_id, reales, pixeles):
        """Guarda los digitos de una foto (reales puede tener None); devuelve los ids en orden."""
        with self.conexion() as con:
            for anterior in con.execute("SELECT id FROM digitos WHERE foto_id = ?", (foto_id,)).fetchall():
                con.execute("DELETE FROM predicciones WHERE digito_id = ?", (anterior["id"],))
            con.execute("DELETE FROM digitos WHERE foto_id = ?", (foto_id,))
            ids = []
            for posicion, (real, vector) in enumerate(zip(reales, pixeles)):
                imagen = np.clip(np.rint(vector * 255), 0, 255).astype(np.uint8).tobytes()
                cursor = con.execute(
                    "INSERT INTO digitos (foto_id, posicion, real, pixeles) VALUES (?, ?, ?, ?)",
                    (foto_id, posicion, real, imagen),
                )
                ids.append(cursor.lastrowid)
            return ids

    def obtener_digito(self, digito_id):
        with self.conexion() as con:
            fila = con.execute("SELECT * FROM digitos WHERE id = ?", (digito_id,)).fetchone()
        if not fila:
            return None
        datos = dict(fila)
        datos["pixeles"] = np.frombuffer(fila["pixeles"], np.uint8).astype(np.float32) / 255.0
        return datos

    def digitos_de_fotos(self, foto_ids):
        if not foto_ids:
            return []
        marcas = ",".join("?" * len(foto_ids))
        with self.conexion() as con:
            filas = con.execute(
                f"SELECT * FROM digitos WHERE foto_id IN ({marcas}) ORDER BY foto_id, posicion", list(foto_ids)
            ).fetchall()
        resultado = []
        for fila in filas:
            datos = dict(fila)
            datos["pixeles"] = np.frombuffer(fila["pixeles"], np.uint8).astype(np.float32) / 255.0
            resultado.append(datos)
        return resultado

    def digitos_con_grupo(self, grupo):
        with self.conexion() as con:
            filas = con.execute(
                "SELECT d.* FROM digitos d JOIN fotos f ON f.id = d.foto_id "
                "WHERE d.grupo = ? AND d.real IS NOT NULL AND COALESCE(f.eliminada, 0) = 0", (grupo,)).fetchall()
        return [{**dict(f), "pixeles": np.frombuffer(f["pixeles"], np.uint8).astype(np.float32) / 255.0} for f in filas]

    def marcar_grupo(self, digito_id, grupo):
        with self.conexion() as con:
            con.execute("UPDATE digitos SET grupo = ? WHERE id = ?", (grupo, digito_id))

    def guardar_predicciones(self, version, digito_ids, clave, probabilidades):
        with self.conexion() as con:
            for digito_id, probs in zip(digito_ids, probabilidades):
                con.execute("DELETE FROM predicciones WHERE digito_id = ? AND version = ? AND modelo = ?",
                            (digito_id, version, clave))
                predicho = int(np.argmax(probs))
                con.execute(
                    "INSERT INTO predicciones (digito_id, version, modelo, predicho, confianza, probs) VALUES (?, ?, ?, ?, ?, ?)",
                    (digito_id, version, clave, predicho, float(probs[predicho]), json.dumps([round(float(p), 5) for p in probs])),
                )

    def predicciones(self, digito_ids, version):
        if not digito_ids:
            return []
        marcas = ",".join("?" * len(digito_ids))
        with self.conexion() as con:
            filas = con.execute(
                f"SELECT * FROM predicciones WHERE version = ? AND digito_id IN ({marcas})", [version, *digito_ids]
            ).fetchall()
        return [{**dict(f), "probs": json.loads(f["probs"])} for f in filas]
