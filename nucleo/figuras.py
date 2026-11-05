"""Graficos como imagenes PNG (matplotlib). Las mismas figuras se muestran en la web y se insertan en el informe PDF."""
import io

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .configuracion import CLAVES_MODELOS, COLORES_MODELOS, NOMBRES_CORTOS, NOMBRES_MODELOS

TINTA = "#16123b"
SUAVE = "#5b5780"
LINEA = "#e4dffa"
FONDO = "#ffffff"


def _porcentaje(x, _=None):
    return f"{x * 100:.0f} %"


def _coma(valor, decimales=1):
    return f"{valor:.{decimales}f}".replace(".", ",")


def _nueva(ancho, alto, filas=1, columnas=1, **opciones):
    fig = Figure(figsize=(ancho, alto), facecolor=FONDO)
    FigureCanvasAgg(fig)
    ejes = fig.subplots(filas, columnas, **opciones)
    for eje in np.atleast_1d(ejes).ravel():
        _estilo(eje)
    return fig, ejes


def _estilo(eje):
    eje.set_facecolor(FONDO)
    for lado in ("top", "right"):
        eje.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        eje.spines[lado].set_color(LINEA)
    eje.tick_params(colors=SUAVE, labelsize=9.5, length=0)
    eje.title.set_color(TINTA)
    eje.xaxis.label.set_color(SUAVE)
    eje.yaxis.label.set_color(SUAVE)
    eje.set_axisbelow(True)


def _png(fig, dpi=130):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, facecolor=FONDO)
    return buffer.getvalue()


def _barras_horizontales(eje, claves, valores, formato, limite=None):
    posiciones = np.arange(len(claves))
    eje.barh(posiciones, valores, color=[COLORES_MODELOS[c] for c in claves], height=0.68)
    eje.set_yticks(posiciones, [NOMBRES_CORTOS[c] for c in claves])
    eje.invert_yaxis()
    eje.grid(axis="x", color=LINEA, linewidth=0.8)
    maximo = limite or max(valores) * 1.25
    eje.set_xlim(0, maximo)
    for y, v in zip(posiciones, valores):
        eje.text(v + maximo * 0.012, y, formato(v), va="center", fontsize=9.5, color=TINTA, fontweight="bold")


def fig_metricas(modelos, dpi=130):
    fig, ejes = _nueva(8.6, 6.2, 2, 2)
    for eje, (clave, titulo) in zip(ejes.ravel(), [("exactitud", "Exactitud"), ("precision_macro", "Precisión"),
                                                    ("recall_macro", "Recall"), ("f1_macro", "F1")]):
        orden = sorted(CLAVES_MODELOS, key=lambda c: modelos[c][clave], reverse=True)
        _barras_horizontales(eje, orden, [modelos[c][clave] for c in orden], lambda v: _coma(v * 100) + " %", limite=1.16)
        eje.xaxis.set_major_formatter(FuncFormatter(_porcentaje))
        eje.set_xticks([0, 0.25, 0.5, 0.75, 1])
        eje.set_title(titulo, fontsize=12, fontweight="bold", loc="left")
    fig.tight_layout(h_pad=2.2, w_pad=2.4)
    return _png(fig, dpi)


def fig_aciertos_fotos(resumen, dpi=130):
    """Aciertos de cada modelo en las fotos del usuario: dígitos y números completos bien leídos.
    `resumen` es {clave: {"digitos_ok", "digitos", "numeros_ok", "numeros"}}."""
    fig, ejes = _nueva(8.6, 3.6, 1, 2)
    for eje, (ok, total, titulo) in zip(ejes, [("digitos_ok", "digitos", "Dígitos bien leídos"), ("numeros_ok", "numeros", "Números completos bien leídos")]):
        valores = {c: resumen[c][ok] / resumen[c][total] if resumen[c][total] else 0.0 for c in CLAVES_MODELOS}
        orden = sorted(CLAVES_MODELOS, key=lambda c: valores[c], reverse=True)
        _barras_horizontales(eje, orden, [valores[c] for c in orden], lambda v: _coma(v * 100, 0) + " %", limite=1.18)
        eje.xaxis.set_major_formatter(FuncFormatter(_porcentaje))
        eje.set_xticks([0, 0.25, 0.5, 0.75, 1])
        eje.set_title(titulo, fontsize=12, fontweight="bold", loc="left")
    fig.tight_layout(w_pad=2.4)
    return _png(fig, dpi)


def _matriz_chica(eje, matriz, clave, titulo):
    """Una matriz de confusión compacta (para ver los siete modelos en una sola figura)."""
    matriz = np.asarray(matriz)
    filas = matriz.sum(axis=1, keepdims=True)
    proporcion = np.divide(matriz, filas, out=np.zeros(matriz.shape, float), where=filas > 0)
    mapa = LinearSegmentedColormap.from_list("modelo", ["#ffffff", COLORES_MODELOS[clave]])
    eje.imshow(np.sqrt(proporcion), cmap=mapa, vmin=0, vmax=1)
    for i in range(10):
        for j in range(10):
            v = int(matriz[i, j])
            if not v:
                continue
            oscuro = np.sqrt(proporcion[i, j]) > 0.55
            eje.text(j, i, str(v), ha="center", va="center", fontsize=6.6 if v >= 1000 else 7.6 if v >= 100 else 8.6,
                     color="#ffffff" if oscuro else TINTA, fontweight="bold" if i != j else "normal")
    eje.set_xticks(range(10))
    eje.set_yticks(range(10))
    eje.tick_params(labelsize=8.5, colors=SUAVE, length=0)
    eje.xaxis.set_ticks_position("top")
    eje.set_title(titulo, fontsize=11, fontweight="bold", color=TINTA, loc="left", pad=18)
    for lado in eje.spines.values():
        lado.set_visible(False)


def fig_matrices(matrices, orden, subtitulos=None, dpi=160):
    """Las matrices de confusión de todos los modelos, de a cuatro por imagen (2 x 2) para que se lean bien impresas.
    Devuelve una lista de imágenes PNG. `subtitulos` opcional: {clave: texto corto} que se agrega al título de cada matriz."""
    imagenes = []
    for inicio in range(0, len(orden), 4):
        grupo = orden[inicio : inicio + 4]
        fig = Figure(figsize=(8.4, 8.6), facecolor=FONDO)
        FigureCanvasAgg(fig)
        ejes = fig.subplots(2, 2).ravel()
        for eje, clave in zip(ejes, grupo):
            extra = f" · {subtitulos[clave]}" if subtitulos and clave in subtitulos else ""
            _matriz_chica(eje, matrices[clave], clave, NOMBRES_MODELOS[clave] + extra)
        for eje in ejes[len(grupo):]:
            eje.axis("off")
            eje.text(0.04, 0.66, "Cómo leerlas", fontsize=12, fontweight="bold", color=TINTA, transform=eje.transAxes)
            eje.text(0.04, 0.54, "Fila = dígito real.\nColumna = lo que respondió el modelo.\nDiagonal = aciertos.\nFuera de la diagonal = confusiones:\n"
                     "cuanto más alto el número, peor.", fontsize=10, color=SUAVE, va="top", transform=eje.transAxes, linespacing=1.55)
        fig.tight_layout(h_pad=2.4, w_pad=2.2)
        imagenes.append(_png(fig, dpi))
    return imagenes


def fig_aciertos_por_digito(matrices, orden, dpi=150):
    """Mapa de calor detallado: qué porcentaje de cada dígito (0 a 9) acierta cada modelo."""
    valores = []
    for clave in orden:
        matriz = np.asarray(matrices[clave])
        filas = matriz.sum(axis=1)
        valores.append(np.divide(np.diag(matriz), filas, out=np.full(10, np.nan), where=filas > 0))
    valores = np.array(valores)
    fig, eje = _nueva(8.6, 0.55 * len(orden) + 1.5)
    mapa = LinearSegmentedColormap.from_list("aciertos", ["#e2447a", "#fff4d6", "#12a06a"])
    eje.imshow(np.nan_to_num(valores, nan=1.0), cmap=mapa, vmin=0.5, vmax=1.0, aspect="auto")
    for i in range(len(orden)):
        for j in range(10):
            texto = "—" if np.isnan(valores[i, j]) else _coma(valores[i, j] * 100, 1 if valores[i, j] < 0.995 else 0)
            eje.text(j, i, texto, ha="center", va="center", fontsize=8.4, color=TINTA, fontweight="bold" if valores[i, j] < 0.9 else "normal")
    eje.set_xticks(range(10), [str(d) for d in range(10)])
    eje.set_yticks(range(len(orden)), [NOMBRES_CORTOS[c] for c in orden])
    eje.xaxis.set_ticks_position("top")
    eje.set_xlabel("Dígito real", fontsize=10)
    eje.xaxis.set_label_position("top")
    eje.set_title("Porcentaje de cada dígito que acierta cada modelo (verde = bien, rosa = falla más)", fontsize=11, fontweight="bold", loc="left", pad=30)
    for lado in eje.spines.values():
        lado.set_visible(False)
    fig.tight_layout()
    return _png(fig, dpi)


def fig_predicciones(imagenes, reales, predichos, origenes=None, columnas=3, dpi=150):
    """Galería de dígitos: a la izquierda «Real / Predijo / Correcto o Incorrecto» (verde o rosa) y a la derecha la imagen.
    `imagenes`: vectores de 784 valores o imágenes en gris con la tinta clara sobre fondo oscuro (como MNIST). Sin título:
    la leyenda va debajo, en la página o en el PDF. `origenes` opcional: de dónde sale cada dígito (p. ej. «Foto 2 · dígito 3»)."""
    filas = max(1, int(np.ceil(len(imagenes) / columnas)))
    fig = Figure(figsize=(8.4, 1.38 * filas), facecolor=FONDO)
    FigureCanvasAgg(fig)
    tarjetas = np.atleast_1d(fig.subfigures(filas, columnas, wspace=0.04, hspace=0.06)).ravel()
    origenes = origenes or [None] * len(imagenes)
    for tarjeta, imagen, real, predicho, origen in zip(tarjetas, imagenes, reales, predichos, origenes):
        imagen = np.asarray(imagen, float)
        imagen = imagen.reshape(28, 28) if imagen.size == 784 else imagen
        bien = int(real) == int(predicho)
        color = "#12a06a" if bien else "#e2447a"
        tarjeta.set_facecolor("#f6f4ff")
        texto, foto = tarjeta.subplots(1, 2, width_ratios=[1.5, 1])
        texto.axis("off")
        estado = "Correcto ✓" if bien else "Incorrecto ✗"
        texto.text(0.06, 0.5, f"Real: {int(real)}\nPredijo: {int(predicho)}\n{estado}", color=color,
                   fontsize=10.5, fontweight="bold", va="center", linespacing=1.5, transform=texto.transAxes)
        if origen:
            texto.text(0.06, 0.06, origen, color=SUAVE, fontsize=8.5, va="bottom", transform=texto.transAxes)
        foto.imshow(imagen, cmap="gray_r", vmin=0, vmax=max(1.0, float(imagen.max())))
        foto.set_xticks([])
        foto.set_yticks([])
        for lado in foto.spines.values():
            lado.set_color(color)
            lado.set_linewidth(2.4)
    for tarjeta in tarjetas[len(imagenes):]:
        tarjeta.set_facecolor(FONDO)
    return _png(fig, dpi)


def fig_matriz(matriz, clave, dpi=130):
    matriz = np.asarray(matriz)
    filas = matriz.sum(axis=1, keepdims=True)
    proporcion = np.divide(matriz, filas, out=np.zeros(matriz.shape, float), where=filas > 0)
    fig, eje = _nueva(7.2, 6.6)
    mapa = LinearSegmentedColormap.from_list("modelo", ["#ffffff", COLORES_MODELOS[clave]])
    eje.imshow(np.sqrt(proporcion), cmap=mapa, vmin=0, vmax=1)
    for i in range(10):
        for j in range(10):
            v = int(matriz[i, j])
            oscuro = np.sqrt(proporcion[i, j]) > 0.55
            eje.text(j, i, str(v), ha="center", va="center", fontsize=9.5 if i != j else 10,
                     color="#ffffff" if oscuro else (TINTA if v else "#b9b4d6"), fontweight="bold" if v and i != j else "normal")
    eje.set_xticks(range(10))
    eje.set_yticks(range(10))
    eje.set_xlabel("Lo que respondió el modelo", fontsize=10.5, labelpad=8)
    eje.set_ylabel("Dígito real", fontsize=10.5, labelpad=8)
    eje.xaxis.set_ticks_position("top")
    eje.xaxis.set_label_position("top")
    eje.set_title(f"Matriz de confusión: {NOMBRES_MODELOS[clave]}", fontsize=12.5, fontweight="bold", pad=34, loc="left")
    for lado in eje.spines.values():
        lado.set_visible(False)
    fig.tight_layout()
    return _png(fig, dpi)


def fig_curvas(curvas, dpi=130):
    fig, (izq, der) = _nueva(8.6, 4.2, 1, 2)
    for clave in ("cnn", "mlp"):
        historial = curvas.get(clave) or []
        if not historial:
            continue
        epocas = [r["epoca"] for r in historial]
        color = COLORES_MODELOS[clave]
        izq.plot(epocas, [r["exactitud"] for r in historial], color=color, marker="o", linewidth=2.4, label=f"{NOMBRES_CORTOS[clave]} entrenamiento")
        if "exactitud_val" in historial[0]:
            izq.plot(epocas, [r["exactitud_val"] for r in historial], color=color, marker="o", linewidth=2.4, linestyle="--", label=f"{NOMBRES_CORTOS[clave]} validación")
        der.plot(epocas, [r["perdida"] for r in historial], color=color, marker="o", linewidth=2.4, label=f"{NOMBRES_CORTOS[clave]} entrenamiento")
    izq.set_title("Exactitud por época", fontsize=12, fontweight="bold", loc="left")
    der.set_title("Pérdida por época (menos es mejor)", fontsize=12, fontweight="bold", loc="left")
    izq.yaxis.set_major_formatter(FuncFormatter(_porcentaje))
    for eje in (izq, der):
        eje.set_xlabel("Época")
        eje.grid(color=LINEA, linewidth=0.8)
        eje.legend(frameon=False, fontsize=9, labelcolor=TINTA)
    fig.tight_layout(w_pad=3)
    return _png(fig, dpi)


def fig_validacion(vc, dpi=130):
    claves = [c for c in CLAVES_MODELOS if vc.get(c)]
    fig, eje = _nueva(8.6, 4.6)
    for i, clave in enumerate(claves):
        mejor = vc[clave][0]
        y = np.full(len(mejor["exactitud_por_pliegue"]), i) + np.linspace(-0.16, 0.16, len(mejor["exactitud_por_pliegue"]))
        eje.scatter(mejor["exactitud_por_pliegue"], y, s=70, color=COLORES_MODELOS[clave], zorder=3, label=NOMBRES_CORTOS[clave])
        eje.scatter([mejor["exactitud_media"]], [i], s=190, marker="D", facecolor="none", edgecolor=TINTA, linewidth=2, zorder=4)
        eje.text(max(mejor["exactitud_por_pliegue"]) + 0.006, i, f"{_coma(mejor['exactitud_media'] * 100)} % ± {_coma(mejor['desviacion'] * 100)}",
                 va="center", fontsize=9.5, color=TINTA)
    eje.set_yticks(range(len(claves)), [NOMBRES_CORTOS[c] for c in claves])
    eje.invert_yaxis()
    eje.xaxis.set_major_formatter(FuncFormatter(_porcentaje))
    eje.set_xlim(0.75, 1.03)
    eje.grid(axis="x", color=LINEA, linewidth=0.8)
    eje.set_xlabel("Exactitud en cada uno de los 5 pliegues (rombo = promedio)")
    eje.set_title("Validación cruzada con los mejores hiperparámetros", fontsize=12, fontweight="bold", loc="left")
    fig.tight_layout()
    return _png(fig, dpi)


def fig_velocidad(modelos, dpi=130):
    fig, (izq, der) = _nueva(8.6, 4.2, 1, 2)
    orden = sorted(CLAVES_MODELOS, key=lambda c: modelos[c]["ms_por_muestra"], reverse=True)
    _barras_horizontales(izq, orden, [modelos[c]["ms_por_muestra"] for c in orden], lambda v: _coma(v, 3) + " ms")
    izq.set_title("Milisegundos por dígito al predecir", fontsize=12, fontweight="bold", loc="left")
    con_tiempo = [c for c in CLAVES_MODELOS if modelos[c].get("segundos_entrenamiento")]
    if con_tiempo:
        orden2 = sorted(con_tiempo, key=lambda c: modelos[c]["segundos_entrenamiento"], reverse=True)
        _barras_horizontales(der, orden2, [modelos[c]["segundos_entrenamiento"] for c in orden2], lambda v: _coma(v) + " s")
    der.set_title("Segundos de entrenamiento inicial", fontsize=12, fontweight="bold", loc="left")
    fig.tight_layout(w_pad=3)
    return _png(fig, dpi)


def fig_progreso(versiones, dpi=130):
    fig, eje = _nueva(8.6, 4.4)
    ids = [v["id"] for v in versiones]
    for clave in CLAVES_MODELOS:
        valores = [(v.get("exactitud_prueba") or {}).get(clave) for v in versiones]
        puntos = [(i, x) for i, x in enumerate(valores) if x is not None]
        if not puntos:
            continue
        eje.plot([p[0] for p in puntos], [p[1] for p in puntos], color=COLORES_MODELOS[clave], marker="o", linewidth=2.4, markersize=7,
                 label=NOMBRES_CORTOS[clave])
    eje.set_xticks(range(len(ids)), ids)
    eje.set_xlim(-0.3, max(len(ids) - 0.7, 0.7))
    eje.yaxis.set_major_formatter(FuncFormatter(_porcentaje))
    eje.grid(axis="y", color=LINEA, linewidth=0.8)
    eje.set_xlabel("Versión de los modelos")
    eje.set_title("Exactitud en MNIST de cada versión (una caída significaría que olvidó lo aprendido)", fontsize=11.5, fontweight="bold", loc="left")
    eje.legend(frameon=False, ncol=6, fontsize=9.5, labelcolor=TINTA, loc="lower center", bbox_to_anchor=(0.5, -0.32))
    fig.tight_layout()
    return _png(fig, dpi)


def fig_mapa(mapa, clave, dpi=130):
    fig, eje = _nueva(9.0, 6.0)
    error = np.array(mapa["errores"][clave], bool)
    x, y = np.array(mapa["x"]), np.array(mapa["y"])
    eje.scatter(x[~error], y[~error], s=11, color="#a9a5c9", alpha=0.55, linewidths=0, label="Aciertos")
    eje.scatter(x[error], y[error], s=62, color=COLORES_MODELOS[clave], edgecolor="#ffffff", linewidth=1.3,
                label=f"Errores de {NOMBRES_CORTOS[clave]} ({int(error.sum())})", zorder=3)
    eje.set_xticks([])
    eje.set_yticks([])
    for lado in ("left", "bottom"):
        eje.spines[lado].set_visible(False)
    eje.set_title(f"Dónde se equivoca {NOMBRES_MODELOS[clave]}", fontsize=12.5, fontweight="bold", loc="left")
    eje.legend(frameon=False, fontsize=10, labelcolor=TINTA, loc="lower center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    fig.tight_layout()
    return _png(fig, dpi)


def fig_preprocesado(pasos, recortes, dpi=150):
    """Los cinco pasos del preprocesado sobre una foto de ejemplo y los digitos recortados en 28x28."""
    fig = Figure(figsize=(8.6, 4.6), facecolor=FONDO)
    FigureCanvasAgg(fig)
    rejilla = fig.add_gridspec(2, 6, height_ratios=[1.15, 1], hspace=0.3, wspace=0.12)
    titulos = [("original", "1. Foto original"), ("gris", "2. Escala de grises"), ("iluminacion", "3. Sombras corregidas"),
               ("binaria", "4. Tinta, sin cuadrícula"), ("segmentacion", "5. Dígitos segmentados")]
    posiciones = [rejilla[0, 0:2], rejilla[0, 2:4], rejilla[0, 4:6], rejilla[1, 0:2], rejilla[1, 2:4]]
    for (clave, titulo), posicion in zip(titulos, posiciones):
        eje = fig.add_subplot(posicion)
        imagen = pasos[clave]
        eje.imshow(imagen[..., ::-1] if imagen.ndim == 3 else imagen, cmap="gray", vmin=0, vmax=255)
        eje.set_title(titulo, fontsize=11, fontweight="bold", color=TINTA, loc="left")
        eje.axis("off")
    sub = rejilla[1, 4:6].subgridspec(1, max(len(recortes), 1), wspace=0.08)
    for i, recorte in enumerate(recortes):
        eje = fig.add_subplot(sub[0, i])
        eje.imshow(recorte, cmap="gray_r", vmin=0, vmax=255)
        eje.axis("off")
        if i == 0:
            eje.set_title("6. Formato MNIST (28×28)", fontsize=11, fontweight="bold", color=TINTA, loc="left")
    return _png(fig, dpi)


def fig_arquitectura_cnn(filtros=16, dpi=150):
    """Diagrama de bloques de la CNN: de la imagen de 28x28 a las 10 salidas."""
    from matplotlib.patches import FancyBboxPatch
    fig = Figure(figsize=(8.6, 2.9), facecolor=FONDO)
    FigureCanvasAgg(fig)
    eje = fig.add_axes([0, 0, 1, 1])
    eje.set_xlim(0, 100)
    eje.set_ylim(0, 30)
    eje.axis("off")
    color = COLORES_MODELOS["cnn"]
    bloques = [
        ("Imagen", "28×28×1", 6, 15, "#a9a5c9"),
        (f"Conv 3×3\n{filtros} filtros", f"28×28×{filtros}\nReLU", 8, 17, color),
        ("Pool 2×2", f"14×14×{filtros}", 5, 12, "#f0a67a"),
        (f"Conv 3×3\n{2 * filtros} filtros", f"14×14×{2 * filtros}\nReLU", 8, 14, color),
        ("Pool 2×2", f"7×7×{2 * filtros}", 5, 9, "#f0a67a"),
        ("Densa", "64 neuronas\nReLU", 8, 12, "#6c4dff"),
        ("Salida", "10 dígitos\nSoftmax", 8, 12, "#12a06a"),
    ]
    separacion = (100 - sum(b[2] for b in bloques)) / (len(bloques) + 1)
    x = separacion
    centros = []
    for titulo, detalle, ancho, alto, tono in bloques:
        y0 = 15 - alto / 2
        eje.add_patch(FancyBboxPatch((x, y0), ancho, alto, boxstyle="round,pad=0,rounding_size=1.2", facecolor=tono, edgecolor="none", alpha=0.92))
        eje.text(x + ancho / 2, 27.3, titulo, ha="center", va="center", fontsize=9.6, fontweight="bold", color=TINTA, linespacing=1.15)
        eje.text(x + ancho / 2, 2.6, detalle, ha="center", va="center", fontsize=9, color=SUAVE, linespacing=1.15)
        centros.append((x, x + ancho))
        x += ancho + separacion
    for (_, fin), (inicio, _) in zip(centros[:-1], centros[1:]):
        eje.annotate("", xy=(inicio - 0.2, 15), xytext=(fin + 0.2, 15), arrowprops=dict(arrowstyle="-|>", color=SUAVE, lw=1.4))
    return _png(fig, dpi)


def fig_entrenamiento(historial, clave, dpi=110):
    fig, (izq, der) = _nueva(9.0, 3.6, 1, 2)
    color = COLORES_MODELOS[clave]
    if historial:
        epocas = [r["epoca"] for r in historial]
        izq.plot(epocas, [r["exactitud"] for r in historial], color=color, marker="o", linewidth=2.4, label="Entrenamiento")
        if "exactitud_val" in historial[0]:
            izq.plot(epocas, [r["exactitud_val"] for r in historial], color=color, marker="o", linewidth=2.4, linestyle="--", label="Validación")
        der.plot(epocas, [r["perdida"] for r in historial], color=color, marker="o", linewidth=2.4, label="Entrenamiento")
        izq.legend(frameon=False, fontsize=9, labelcolor=TINTA)
    izq.set_title("Exactitud por época", fontsize=11.5, fontweight="bold", loc="left")
    der.set_title("Pérdida por época (menos es mejor)", fontsize=11.5, fontweight="bold", loc="left")
    izq.yaxis.set_major_formatter(FuncFormatter(_porcentaje))
    for eje in (izq, der):
        eje.set_xlabel("Época")
        eje.grid(color=LINEA, linewidth=0.8)
    fig.tight_layout(w_pad=3)
    return _png(fig, dpi)

