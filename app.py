import functools
import json
import os
import subprocess
import sys

from flask import Flask, Response, abort, copy_current_request_context, jsonify, redirect, render_template, request, send_file

from nucleo.configuracion import (
    CARPETA_DATOS,
    CARPETA_RESULTADOS,
    CLAVES_MODELOS,
    COLORES_MODELOS,
    NOMBRES_CORTOS,
    NOMBRES_MODELOS,
    CODIGO,
    RAIZ,
)
from nucleo import graficos, informe, por_dentro
from nucleo.entrenador import Entrenador, opciones as opciones_entrenador
from nucleo.ficticios import Ficticios
from nucleo.servicio import ErrorUsuario, Servicio
from nucleo.tareas import Tareas

app = Flask(__name__, template_folder=str(CODIGO / "vistas"), static_folder=str(CODIGO / "recursos"), static_url_path="/recursos")
app.config["MAX_CONTENT_LENGTH"] = 260 * 1024 * 1024
servicio = Servicio()
tareas = Tareas(CARPETA_DATOS / "tiempos_de_tareas.json")
entrenamientos = Entrenador(servicio, tareas)
ficticios = Ficticios(servicio)

SECCIONES = [
    ("predecir", "Leer formulario", "/", "#0f766e"),
    ("graficos", "Resultados", "/graficos", "#b45309"),
    ("entrenador", "Entrenar", "/entrenador", "#2563eb"),
    ("ficticios", "Probar con ejemplos", "/ficticios", "#0f766e"),
    ("antes-despues", "Antes y después", "/antes-y-despues", "#9a6700"),
    ("por-dentro", "Por dentro", "/por-dentro", "#7c3aed"),
    ("informe", "Informe", "/informe", "#b45309"),
    ("inicio", "Resumen", "/resumen", "#475569"),
]
DISPONIBLES = [clave for clave, _, _, _ in SECCIONES]


def modelos_para_pagina():
    return [{"clave": c, "nombre": NOMBRES_MODELOS[c], "color": f"var(--m-{c})", "corto": NOMBRES_CORTOS[c]} for c in CLAVES_MODELOS]


def pagina(plantilla, activa, **contexto):
    try:
        version = servicio.version_activa()
    except ErrorUsuario:
        version = None
    return render_template(
        plantilla,
        secciones=[s for s in SECCIONES if s[0] in DISPONIBLES],
        disponibles=DISPONIBLES,
        rutas={clave: ruta for clave, _, ruta, _ in SECCIONES},
        activa=activa,
        acento=next((color for clave, _, _, color in SECCIONES if clave == activa), "#0f766e"),
        version=version,
        carpeta_datos=str(RAIZ),
        modelos=modelos_para_pagina(),
        modelos_json=json.dumps(modelos_para_pagina(), ensure_ascii=False),
        **contexto,
    )


def cargar_creditos():
    ruta = CODIGO / "recursos" / "imagenes" / "portadas" / "creditos.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def resumen_inicio():
    ruta = CARPETA_RESULTADOS / "v1" / "metricas.json"
    if not ruta.exists():
        return []
    metricas = json.loads(ruta.read_text(encoding="utf-8"))
    return [{"clave": c, "nombre": NOMBRES_MODELOS[c], "color": f"var(--m-{c})", "exactitud": metricas[c]["exactitud"]}
            for c in CLAVES_MODELOS if c in metricas]


def como_tarea(titulo, final, pagina, estimado=5, peso=None):
    """Hace que una ruta lenta corra en segundo plano, con barra de avance, cuando la página la pide con la cabecera X-Tarea.

    Sin esa cabecera responde como siempre. `peso(cuerpo)` dice el tamaño del trabajo (fotos, imágenes…) para calcular cuánto falta.
    """
    def decorar(vista):
        @functools.wraps(vista)
        def envoltura(*args, **kwargs):
            if request.headers.get("X-Tarea") != "1":
                return vista(*args, **kwargs)
            cuerpo = request.get_json(silent=True) or {}  # se lee ahora: el hilo lo usa cuando la petición ya terminó
            unidades = peso(cuerpo) if peso else 1
            trabajo = copy_current_request_context(lambda: vista(*args, **kwargs).get_json())
            return jsonify(tareas.lanzar(vista.__name__, titulo, trabajo, url=pagina, final=final, origen=request.path,
                                         estimado=estimado * max(1, unidades), peso=unidades, etiqueta="Ir a la sección"))
        return envoltura
    return decorar


def _cuantos(valor):
    try:
        return max(1, len(valor) if hasattr(valor, "__len__") else int(valor))
    except (TypeError, ValueError):
        return 1


@app.errorhandler(ErrorUsuario)
def error_usuario(error):
    return jsonify({"error": str(error)}), 400


@app.errorhandler(413)
def demasiado_grande(_):
    return jsonify({"error": "Las fotos pesan demasiado. Sube menos fotos a la vez."}), 413


@app.get("/")
def predecir():
    return pagina("predecir.html", "predecir", lote_inicial=servicio.tanda_abierta() or "")


@app.get("/predecir")
def predecir_antigua():
    return redirect("/")


@app.get("/resumen")
def inicio():
    return pagina("inicio.html", "inicio", resumen=resumen_inicio())


@app.get("/informe")
def pagina_informe():
    return pagina("informe.html", "informe")


@app.get("/api/informe/opciones")
def api_informe_opciones():
    return jsonify(informe.opciones_pagina(servicio, version_pedida()))


@app.post("/api/informe/pdf")
def api_informe_pdf():
    with servicio._candado:
        pdf = informe.generar_pdf(servicio, request.get_json(silent=True) or {})
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": "inline; filename=informe_digitos_manuscritos.pdf",
                                                              "Cache-Control": "no-store"})


@app.get("/descargar/codigo.zip")
def descargar_codigo():
    return Response(informe.zip_codigo(), mimetype="application/zip", headers={"Content-Disposition": "attachment; filename=digitos_manuscritos_codigo.zip"})


@app.get("/graficos")
def pagina_graficos():
    return pagina("graficos.html", "graficos")


@app.get("/antes-y-despues")
def pagina_antes_despues():
    return pagina("antes_despues.html", "antes-despues")


@app.get("/entrenador")
def pagina_entrenador():
    return pagina("entrenador.html", "entrenador")


@app.get("/por-dentro")
def pagina_por_dentro():
    return pagina("por_dentro.html", "por-dentro")


@app.get("/ficticios")
def pagina_ficticios():
    return pagina("ficticios.html", "ficticios", creditos=cargar_creditos())


@app.get("/foto/<int:foto_id>")
def foto(foto_id):
    return send_file(servicio.ruta_foto(foto_id), mimetype="image/png", max_age=3600)


@app.get("/foto/<int:foto_id>/digito/<int:posicion>.png")
def foto_con_digito(foto_id, posicion):
    return Response(servicio.foto_con_digito(foto_id, posicion), mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.post("/api/fotos")
def api_subir_fotos():
    archivos = [(f.filename or "foto", f.read()) for f in request.files.getlist("fotos")]
    lote = request.form.get("lote") or None
    if request.headers.get("X-Tarea") != "1":
        return jsonify(servicio.subir(archivos, lote))
    return jsonify(tareas.lanzar("subir", "Subiendo y enderezando tus fotos", lambda: servicio.subir(archivos, lote), url="/predecir",
                                 final="la subida de tus fotos", origen=request.path, estimado=2 * max(1, len(archivos)),
                                 peso=len(archivos), etiqueta="Ir a la sección"))


@app.delete("/api/fotos/<int:foto_id>")
def api_quitar_foto(foto_id):
    servicio.quitar_foto(foto_id)
    return jsonify({"ok": True})


@app.get("/api/fotos/<int:foto_id>/pasos")
def api_pasos(foto_id):
    return jsonify(servicio.pasos_foto(foto_id))


@app.post("/api/fotos/<int:foto_id>/girar")
def api_girar_foto(foto_id):
    return jsonify(servicio.girar_foto(foto_id))


@app.post("/api/predecir")
@como_tarea("Leyendo tus fotos con los siete modelos", "la lectura de tus fotos", "/", estimado=2,
            peso=lambda d: _cuantos(d.get("textos", {})))
def api_predecir():
    datos = request.get_json(silent=True) or {}
    return jsonify(servicio.predecir(datos.get("lote", ""), datos.get("textos", {})))


@app.get("/api/lote/<lote>")
@como_tarea("Leyendo la tanda con la versión elegida", "la lectura de la tanda", "/antes-y-despues", estimado=6)
def api_lote(lote):
    return jsonify(servicio.resultado_lote(lote, request.args.get("version") or None, avisar=True))


@app.post("/api/corregir")
def api_corregir():
    datos = request.get_json(silent=True) or {}
    return jsonify(servicio.corregir(datos.get("lote", ""), datos.get("modelos"), datos.get("excluir", [])))


def version_pedida():
    version = request.values.get("version") or (request.get_json(silent=True) or {}).get("version") or servicio.version_activa()
    if version not in {v["id"] for v in servicio.almacen.listar_versiones()}:
        raise ErrorUsuario("Esa versión no existe.")
    return version


@app.get("/graficos-img/<version>/<archivo>")
def imagen_grafico(version, archivo):
    if archivo not in graficos.nombres_imagenes() or version not in {v["id"] for v in servicio.almacen.listar_versiones()}:
        abort(404)
    ruta = graficos.carpeta_imagenes(version) / archivo
    if not ruta.exists():
        abort(404)
    return send_file(ruta, mimetype="image/png", max_age=0)


@app.get("/api/lote/<lote>/predicciones/<clave>.png")
def api_predicciones_lote(lote, clave):
    if clave not in CLAVES_MODELOS:
        abort(404)
    png = graficos.imagen_predicciones_lote(servicio, lote, clave, request.args.get("version") or None)
    return Response(png, mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.get("/figura/progreso.png")
def figura_progreso():
    return Response(graficos.imagen_progreso(servicio), mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.get("/figura/entrenamiento/<id_trabajo>.png")
def figura_entrenamiento(id_trabajo):
    return Response(entrenamientos.figura(id_trabajo), mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.get("/descargar/graficos.zip")
def descargar_graficos():
    version = version_pedida()
    return Response(graficos.zip_imagenes(servicio, version), mimetype="application/zip",
                    headers={"Content-Disposition": f"attachment; filename=graficos_{version}.zip"})


@app.post("/api/tareas/graficos-zip")
def api_tarea_graficos_zip():
    version = version_pedida()
    return jsonify(tareas.lanzar("graficos-zip", f"Empaquetando los gráficos de la versión {version}",
                                 lambda: ("archivo", graficos.zip_imagenes(servicio, version), "application/zip", f"graficos_{version}.zip"),
                                 url="/api/tareas/{id}/archivo", pagina="/graficos", final=f"el paquete de gráficos de la versión {version}",
                                 origen=request.path, estimado=8, etiqueta="Descargar"))


@app.post("/api/tareas/codigo-zip")
def api_tarea_codigo_zip():
    return jsonify(tareas.lanzar("codigo-zip", "Empaquetando el código",
                                 lambda: ("archivo", informe.zip_codigo(), "application/zip", "digitos_manuscritos_codigo.zip"),
                                 url="/api/tareas/{id}/archivo", pagina="/informe", final="el paquete con el código",
                                 origen=request.path, estimado=3, etiqueta="Descargar"))


@app.get("/api/graficos")
@como_tarea("Preparando los gráficos", "los gráficos", "/graficos", estimado=6)
def api_graficos():
    return jsonify(graficos.datos_graficos(servicio, version_pedida()))


@app.post("/api/graficos/generar")
def api_graficos_generar():
    version = version_pedida()
    with servicio._candado:
        return jsonify(graficos.generar(servicio, version))


@app.get("/api/matriz/imagenes")
@como_tarea("Buscando ejemplos de esa casilla", "la búsqueda de ejemplos", "/graficos", estimado=3)
def api_matriz_imagenes():
    try:
        real, predicho = int(request.args["real"]), int(request.args["predicho"])
    except (KeyError, ValueError):
        raise ErrorUsuario("Faltan los dígitos de la casilla.")
    clave = request.args.get("modelo", "")
    if clave not in CLAVES_MODELOS or not (0 <= real <= 9 and 0 <= predicho <= 9):
        raise ErrorUsuario("Modelo o dígito no válido.")
    return jsonify(graficos.imagenes_casilla(servicio, version_pedida(), clave, real, predicho))


PAGINAS_DE_RESULTADO = {"predecir": "/predecir", "ficticios": "/ficticios"}


@app.get("/api/tareas")
def api_tareas():
    return jsonify({"tareas": tareas.lista()})


@app.get("/api/tareas/<id_tarea>")
def api_tarea(id_tarea):
    return jsonify(tareas.obtener(id_tarea))


@app.post("/api/tareas/<id_tarea>/vista")
def api_tarea_vista(id_tarea):
    tareas.marcar(id_tarea, vista=True)
    return jsonify({"ok": True})


@app.post("/api/tareas/<id_tarea>/notificada")
def api_tarea_notificada(id_tarea):
    tareas.marcar(id_tarea)
    return jsonify({"ok": True})


@app.get("/api/tareas/<id_tarea>/archivo")
def api_tarea_archivo(id_tarea):
    contenido, tipo, nombre = tareas.archivo(id_tarea)
    return Response(contenido, mimetype=tipo, headers={"Content-Disposition": f"inline; filename={nombre}", "Cache-Control": "no-store"})


@app.post("/api/tareas/corregir")
def api_tarea_corregir():
    d = request.get_json(silent=True) or {}
    pagina = PAGINAS_DE_RESULTADO.get(d.get("pagina"), "/predecir")
    return jsonify(tareas.lanzar("corregir", "Corrigiendo a los modelos que se equivocaron",
                                 lambda: servicio.corregir(d.get("lote", ""), d.get("modelos"), d.get("excluir", [])), url=pagina + "?tarea={id}",
                                 final="la corrección de los modelos", origen=request.path, estimado=90))


@app.post("/api/tareas/ficticios-corregir")
def api_tarea_ficticios_corregir():
    token = (request.get_json(silent=True) or {}).get("token", "")
    return jsonify(tareas.lanzar("corregir", "Corrigiendo a los modelos con la imagen abierta", lambda: ficticios.corregir(token), url="/ficticios?tarea={id}",
                                 final="la corrección con la imagen abierta", origen=request.path, estimado=90, clave_tiempo="corregir-imagen"))


@app.post("/api/tareas/graficos")
def api_tarea_graficos():
    version = version_pedida()

    def trabajo():
        with servicio._candado:
            return graficos.generar(servicio, version)
    return jsonify(tareas.lanzar("graficos", f"Creando los gráficos de la versión {version}", trabajo, url="/graficos?tarea={id}",
                                 final=f"los gráficos de la versión {version}", origen=request.path, estimado=60))


@app.post("/api/tareas/informe")
def api_tarea_informe():
    opciones = request.get_json(silent=True) or {}

    def trabajo():
        with servicio._candado:
            pdf = informe.generar_pdf(servicio, opciones)
        return ("archivo", pdf, "application/pdf", "informe_digitos_manuscritos.pdf")
    return jsonify(tareas.lanzar("informe", "Creando el informe en PDF", trabajo, url="/informe?tarea={id}", final="el informe en PDF",
                                 origen=request.path, estimado=90))


@app.post("/api/por-dentro")
def api_por_dentro():
    return jsonify(por_dentro.activaciones(servicio, (request.get_json(silent=True) or {}).get("imagen", "")))


@app.get("/api/lotes")
def api_lotes():
    return jsonify(servicio.almacen.lotes())


@app.get("/api/lotes/basura")
def api_lotes_basura():
    return jsonify({"basura": servicio.lotes_basura()})


@app.post("/api/lotes/quitar")
def api_lotes_quitar():
    return jsonify(servicio.quitar_lotes((request.get_json(silent=True) or {}).get("ids", [])))


@app.post("/api/lotes/vaciar-basura")
def api_lotes_vaciar_basura():
    return jsonify(servicio.vaciar_basura_lotes())


@app.post("/api/lotes/<lote>/restaurar")
def api_lotes_restaurar(lote):
    return jsonify(servicio.restaurar_lote(lote))


@app.post("/api/lotes/<lote>/borrar-para-siempre")
def api_lotes_borrar(lote):
    return jsonify(servicio.borrar_lote_para_siempre(lote))


@app.get("/api/entrenador/opciones")
def api_entrenador_opciones():
    return jsonify({**opciones_entrenador(), "intentos": entrenamientos.intentos(), "version": servicio.version_activa()})


@app.post("/api/entrenador/iniciar")
def api_entrenador_iniciar():
    d = request.get_json(silent=True) or {}
    return jsonify(entrenamientos.iniciar(d.get("modelo", ""), d.get("parametros"), d.get("muestras"), d.get("modo", "entrenar")))


@app.get("/api/entrenador/ultimo")
def api_entrenador_ultimo():
    return jsonify({"trabajo": entrenamientos.ultimo()})


@app.get("/api/entrenador/estado/<id_trabajo>")
def api_entrenador_estado(id_trabajo):
    return jsonify(entrenamientos.estado(id_trabajo))


@app.post("/api/entrenador/adoptar")
@como_tarea("Guardando el modelo como versión nueva", "la versión nueva con tu modelo", "/entrenador", estimado=8)
def api_entrenador_adoptar():
    return jsonify(entrenamientos.adoptar((request.get_json(silent=True) or {}).get("id", "")))


@app.get("/api/ficticios/opciones")
def api_ficticios_opciones():
    return jsonify({"tipos": ficticios.tipos(), "ejemplos": ficticios.ejemplos(), "banco": ficticios.banco()})


@app.get("/ficticios-img/<carpeta>/<archivo>")
def imagen_ficticia(carpeta, archivo):
    try:
        ancho = int(request.args.get("ancho", 260))
    except ValueError:
        ancho = 260
    de_basura = request.args.get("basura") == "1"
    return Response(ficticios.miniatura(carpeta, archivo, ancho, de_basura), mimetype="image/jpeg",
                    headers={"Cache-Control": "no-store" if de_basura else "max-age=3600"})


@app.post("/api/ficticios/ampliar")
@como_tarea("Creando imágenes de práctica", "las imágenes nuevas", "/ficticios", estimado=0.5, peso=lambda d: _cuantos(d.get("cantidad", 20)))
def api_ficticios_ampliar():
    d = request.get_json(silent=True) or {}
    return jsonify(ficticios.ampliar(d.get("cantidad", 20), d.get("tipo", "liso"), d.get("nivel")))


@app.post("/api/ficticios/numero")
@como_tarea("Abriendo la imagen", "la imagen que abriste", "/ficticios", estimado=3)
def api_ficticios_numero():
    return jsonify(ficticios.abrir_numero((request.get_json(silent=True) or {}).get("nombre", "")))


@app.post("/api/ficticios/corregir")
def api_ficticios_corregir():
    return jsonify(ficticios.corregir((request.get_json(silent=True) or {}).get("token", "")))


@app.post("/api/tareas/ficticios-entrenar")
def api_tarea_ficticios_entrenar():
    nombres = (request.get_json(silent=True) or {}).get("nombres", [])
    return jsonify(tareas.lanzar("entrenar", "Entrenando a los modelos con las imágenes que elegiste", lambda: ficticios.entrenar_elegidas(nombres),
                                 url="/ficticios?tarea={id}", final="el entrenamiento con las imágenes que elegiste",
                                 origen=request.path, estimado=100))


@app.post("/api/ficticios/quitar")
def api_ficticios_quitar():
    d = request.get_json(silent=True) or {}
    return jsonify(ficticios.quitar(d.get("carpeta", ""), d.get("nombres", [])))


@app.get("/api/ficticios/basura")
def api_ficticios_basura():
    return jsonify({"basura": ficticios.basura()})


@app.post("/api/ficticios/basura/restaurar")
def api_ficticios_restaurar():
    d = request.get_json(silent=True) or {}
    return jsonify(ficticios.restaurar(d.get("carpeta", ""), d.get("nombres", [])))


@app.post("/api/ficticios/basura/borrar-para-siempre")
def api_ficticios_borrar():
    d = request.get_json(silent=True) or {}
    return jsonify(ficticios.borrar_para_siempre(d.get("carpeta", ""), d.get("nombres", [])))


@app.post("/api/ficticios/basura/vaciar")
def api_ficticios_vaciar_basura():
    return jsonify(ficticios.borrar_para_siempre())


@app.post("/api/ficticios/generar")
@como_tarea("Creando el formulario", "el formulario nuevo", "/ficticios", estimado=3)
def api_ficticios_generar():
    d = request.get_json(silent=True) or {}
    return jsonify(ficticios.generar(d.get("tipo", ""), d.get("dificultad", 0.4)))


@app.post("/api/ficticios/ejemplo")
@como_tarea("Abriendo el formulario", "el formulario que abriste", "/ficticios", estimado=3)
def api_ficticios_ejemplo():
    return jsonify(ficticios.abrir_ejemplo((request.get_json(silent=True) or {}).get("nombre", "")))


@app.get("/api/ficticios/leer/<token>")
@como_tarea("Leyendo la imagen con los siete modelos", "la lectura de la imagen", "/ficticios", estimado=6)
def api_ficticios_leer(token):
    return jsonify(ficticios.leer(token))


@app.post("/api/carpeta-datos")
def api_carpeta_datos():
    """Abre en el explorador de archivos la carpeta donde se guardan las fotos, la base de datos y las versiones.

    La app corre en el propio PC de la persona, asi que abrirla aqui es lo mismo que hacerlo con el explorador.
    """
    origen = request.headers.get("Origin")
    if origen and origen.rstrip("/") != request.host_url.rstrip("/"):
        abort(403)
    que = (request.get_json(silent=True) or {}).get("que", "datos")
    carpeta = RAIZ / "datos" / "fotos_usuario" if que == "fotos" else RAIZ
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(str(carpeta))
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(carpeta)])
    except OSError:
        raise ErrorUsuario("No se pudo abrir la carpeta. Está en: " + str(carpeta))
    return jsonify({"carpeta": str(carpeta)})


def _solo_desde_esta_pagina():
    """Estas acciones solo las puede pedir la propia pagina de Trazo, no otro sitio web abierto en el navegador."""
    origen = request.headers.get("Origin")
    if origen and origen.rstrip("/") != request.host_url.rstrip("/"):
        abort(403)


@app.post("/api/tanda/nueva")
def api_tanda_nueva():
    """«Empezar una tanda nueva»: se cierra la anterior."""
    _solo_desde_esta_pagina()
    servicio.cerrar_tanda()
    return jsonify({"ok": True})


@app.get("/api/salud")
def api_salud():
    """Responde si la aplicación está en marcha."""
    return jsonify({"aplicacion": "trazo"})


@app.get("/api/versiones")
def api_versiones():
    return jsonify(servicio.listar_versiones())


@app.get("/api/versiones/basura")
def api_versiones_basura():
    return jsonify({"basura": [{"id": v["id"], "motivo": v["motivo"], "creada": v["creada"]} for v in servicio.versiones_basura()]})


@app.post("/api/versiones/quitar")
def api_versiones_quitar():
    return jsonify(servicio.quitar_versiones((request.get_json(silent=True) or {}).get("ids", [])))


@app.post("/api/versiones/vaciar-basura")
def api_versiones_vaciar_basura():
    return jsonify(servicio.vaciar_basura())


@app.post("/api/versiones/<id_version>/restaurar")
def api_versiones_restaurar(id_version):
    return jsonify(servicio.restaurar_version(id_version))


@app.post("/api/versiones/<id_version>/borrar-para-siempre")
def api_versiones_borrar(id_version):
    return jsonify(servicio.borrar_para_siempre(id_version))


@app.post("/api/versiones/<id_version>/activar")
def api_activar_version(id_version):
    return jsonify(servicio.activar_version(id_version))


@app.get("/api/explicacion/<int:digito_id>/<clave>")
def api_explicacion(digito_id, clave):
    return jsonify(servicio.explicar_digito(digito_id, clave))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
