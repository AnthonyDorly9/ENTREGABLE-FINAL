"""Informe PDF: portada, indice, textos, tablas y graficos (imagenes) generados con los datos reales de la version elegida."""
import base64
import io
import json
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import cv2
import matplotlib
import numpy as np
from PIL import Image as ImagenPIL
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

from . import avance, figuras, graficos
from .configuracion import (CARPETA_DATOS, CARPETA_RESULTADOS, CLAVES_MODELOS, GRILLAS, MUESTRAS_ENTRENAMIENTO, NOMBRES_CORTOS,
                            NOMBRES_MODELOS, CODIGO)
from .formularios_ficticios import GeneradorDigitos
from .preprocesado import procesar_foto

CARPETA_FUENTES = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
ANCHO_PAGINA, ALTO_PAGINA = A4
MARGEN = 2 * cm
ANCHO_UTIL = ANCHO_PAGINA - 2 * MARGEN

TEMAS = {
    "violeta": ("#6c4dff", "#2a1d7a"),
    "naranja": ("#e8590c", "#7a2f05"),
    "verde": ("#0c8a5b", "#064a31"),
    "azul": ("#0a84d6", "#064a7a"),
    "rosa": ("#d6336c", "#7a1a3c"),
}

SECCIONES = [
    ("resumen", "Resumen", "Lo esencial en un párrafo: qué se hizo y qué modelo ganó."),
    ("caso", "El caso y qué se entrega", "El problema de TecnoForms y dónde se cumple cada requisito."),
    ("datos", "Datos utilizados", "De dónde salen los dígitos: MNIST, formularios ficticios y fotos reales."),
    ("preprocesado", "Preparación de las imágenes", "Enderezar, escala de grises, quitar cuadrícula, segmentación y formato MNIST."),
    ("algoritmos", "Algoritmos elegidos y por qué", "Los siete modelos comparados y sus fortalezas."),
    ("arquitectura", "Arquitectura de las redes neuronales", "Capas, activaciones, parámetros y optimizador."),
    ("entrenamiento", "Entrenamiento, validación cruzada e hiperparámetros", "Cómo se entrenó y se ajustó cada modelo."),
    ("resultados", "Resultados en el conjunto de prueba", "Exactitud, precisión, recall, F1 y velocidad."),
    ("matrices", "Matrices de confusión", "Qué dígitos se confunden entre sí."),
    ("comparacion", "Comparación e interpretación", "Por qué unos modelos ganan y otros pierden."),
    ("correcciones", "Correcciones y progreso", "Versiones, correcciones y que no se pierde lo aprendido."),
    ("fotos", "Fotos y predicciones", "Tus fotos con lo que leyó cada modelo."),
    ("conclusiones", "Conclusiones y recomendaciones", "Qué se logró y qué sigue."),
    ("codigo", "Código fuente", "Dónde está cada parte del código."),
    ("referencias", "Referencias y créditos", "Fuentes de datos, bibliografía e imágenes."),
]
CLAVES_SECCIONES = [s[0] for s in SECCIONES]


def registrar_fuentes():
    if "Informe" in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont("Informe", str(CARPETA_FUENTES / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("Informe-Negrita", str(CARPETA_FUENTES / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Informe-Cursiva", str(CARPETA_FUENTES / "DejaVuSans-Oblique.ttf")))
    pdfmetrics.registerFont(TTFont("Informe-NegritaCursiva", str(CARPETA_FUENTES / "DejaVuSans-BoldOblique.ttf")))
    pdfmetrics.registerFontFamily("Informe", normal="Informe", bold="Informe-Negrita", italic="Informe-Cursiva", boldItalic="Informe-NegritaCursiva")


def coma(valor, decimales=1):
    return f"{valor:.{decimales}f}".replace(".", ",")


def pct(valor, decimales=1):
    return coma(valor * 100, decimales) + " %"


def miles(numero):
    return f"{numero:,}".replace(",", " ")


ETIQUETAS_PARAMETROS = {"filtros": "filtros", "tasa_aprendizaje": "tasa de aprendizaje", "neuronas": "neuronas", "C": "C", "gamma": "gamma",
                        "k": "k", "clusteres": "grupos", "componentes": "componentes PCA", "epocas": "épocas", "dropout": "dropout"}


def texto_parametros(parametros):
    return "; ".join(f"{ETIQUETAS_PARAMETROS.get(k, k)} = {str(v).replace('.', ',')}" for k, v in parametros.items())


def _leer(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8")) if Path(ruta).exists() else None


def _evaluacion_preprocesado(nombre):
    """Mediciones del preprocesado. En la app instalada se prefieren las que trae el paquete (semilla), que son las de
    esta version del codigo; las de la carpeta del usuario pueden venir de una version anterior."""
    for carpeta in (CODIGO / "semilla" / "resultados" / "preprocesado", CARPETA_RESULTADOS / "preprocesado"):
        if (carpeta / nombre).exists():
            return _leer(carpeta / nombre)
    return None


def _banco_ficticio():
    etiquetas = _leer(CARPETA_DATOS / "ficticios" / "etiquetas.json") or {}
    numeros = etiquetas.get("numeros", {})
    cuadriculadas = sum(n.startswith("cuadriculada_") for n in numeros)
    return {"formularios": len(etiquetas.get("formularios", {})), "numeros": len(numeros) - cuadriculadas, "cuadriculadas": cuadriculadas}


# ---------------------------------------------------------------- datos y textos
def recopilar(servicio, version):
    if not graficos.hay_metricas(version):
        graficos.calcular_metricas(servicio, version)
    metricas = graficos.metricas_de(version)
    versiones = servicio.almacen.listar_versiones()
    return {
        "version": version,
        "metricas": metricas,
        "cv": _leer(CARPETA_RESULTADOS / "v1" / "validacion_cruzada.json") or {},
        "curvas": _leer(CARPETA_RESULTADOS / "v1" / "curvas_entrenamiento.json") or {},
        "arquitecturas": {c: m.arquitectura() for c, m in servicio.modelos(version).items()},
        "versiones": versiones,
        "preprocesado": _evaluacion_preprocesado("evaluacion.json"),
        "fotos_dificiles": _evaluacion_preprocesado("fotos_dificiles.json"),
        "banco": _banco_ficticio(),
        "creditos": _leer(CODIGO / "recursos" / "imagenes" / "portadas" / "creditos.json") or {},
        "orden": sorted(CLAVES_MODELOS, key=lambda c: -metricas[c]["exactitud"]),
        "predicciones": {c: figuras.fig_predicciones(*graficos.ejemplos_predicciones(servicio, metricas, c)) for c in CLAVES_MODELOS},
    }


def confusiones_frecuentes(matriz, cantidad=3):
    pares = [(matriz[i][j], i, j) for i in range(10) for j in range(10) if i != j and matriz[i][j] > 0]
    return sorted(pares, reverse=True)[:cantidad]


def textos_por_defecto(d):
    m, orden = d["metricas"], d["orden"]
    mejor, peor = orden[0], orden[-1]
    activa = next(v for v in d["versiones"] if v["id"] == d["version"])
    actualizados = [v for v in d["versiones"] if v["numero"] > 1]
    t = {}
    t["resumen"] = (
        "Este informe describe una aplicación web que lee dígitos escritos a mano en fotos de formularios y compara siete modelos de aprendizaje "
        "automático: una red convolucional (CNN), una red densa (MLP), una máquina de vectores de soporte (SVM), K vecinos más cercanos (KNN), "
        "regresión logística, regresión lineal y K-Means.\n\n"
        f"Con los 10 000 dígitos de prueba de MNIST, el mejor modelo fue {NOMBRES_MODELOS[mejor]} con {pct(m[mejor]['exactitud'], 2)} de exactitud, "
        f"seguido de {NOMBRES_CORTOS[orden[1]]} ({pct(m[orden[1]]['exactitud'], 2)}) y {NOMBRES_CORTOS[orden[2]]} ({pct(m[orden[2]]['exactitud'], 2)}). "
        f"El más débil fue {NOMBRES_MODELOS[peor]} con {pct(m[peor]['exactitud'], 2)}, algo esperable porque agrupa sin conocer las etiquetas.\n\n"
        "La aplicación permite corregir a los modelos que se equivocan con fotos propias. Cada corrección crea una versión nueva y solo se guarda si el "
        f"modelo no pierde exactitud en MNIST ni olvida dígitos que ya había aprendido. Este informe usa la versión {d['version']}"
        + (f", resultado de {len(actualizados)} {'corrección' if len(actualizados) == 1 else 'correcciones o ajustes'} sobre el entrenamiento inicial." if actualizados else ", el entrenamiento inicial con MNIST.")
    )
    t["caso"] = (
        "TecnoForms desarrolla soluciones tecnológicas para empresas y ha detectado la necesidad de automatizar la clasificación de formularios escritos "
        "a mano, sobre todo en educación y finanzas. El reto es extraer con precisión los dígitos que las personas anotan en formularios de inscripción, "
        "pagos y solicitudes que llegan en papel.\n\n"
        "La propuesta es un sistema de aprendizaje automático y visión por computador que reconoce dígitos manuscritos. La tabla siguiente indica dónde se "
        "cumple cada requisito del caso."
    )
    t["datos"] = (
        "Los modelos se entrenan con MNIST, el conjunto de referencia para reconocer dígitos: 70 000 imágenes de 28×28 píxeles en escala de grises "
        "(60 000 para entrenar y 10 000 para probar). Son datos de internet, con la fuente citada en las referencias.\n\n"
        "Para probar el preprocesado y la lectura de formularios completos se generan formularios ficticios a partir de dígitos de MNIST con sombras, "
        "ruido, desenfoque e inclinación, y también números escritos en hojas cuadriculadas o rayadas de distintos colores, con tinta de colores. "
        "No contienen datos de personas reales. Además, la aplicación acepta fotos reales que se usan para comparar modelos y para corregirlos."
    )
    pre = d["preprocesado"]
    t["preprocesado"] = (
        "Antes de clasificar, cada foto pasa por estos pasos: (1) si llegó de lado o de cabeza, se endereza: se prueba en las cuatro posiciones y se elige "
        "la que separa más dígitos y la CNN lee con más seguridad, solo si la diferencia es clara; (2) se reduce a 1000 píxeles de lado para trabajar "
        "(la foto se guarda con más detalle, hasta 2000); (3) se convierte a escala de grises o, si hay una cuadrícula de otro color que la tinta, al canal "
        "de color donde la cuadrícula casi desaparece; (4) se corrigen las sombras dividiendo por el fondo estimado y se normaliza el contraste; "
        "(5) se separa la tinta del papel con el umbral de Otsu; (6) se borran las líneas de hojas cuadriculadas o rayadas: rectas finas que cruzan la foto, "
        "sin tocar los trazos del dígito, que son más gruesos; (7) se segmentan los dígitos por componentes conectadas, uniendo trazos sueltos (como la barra "
        "del 5) y separando dígitos pegados cuando se conoce cuántos hay; si los dígitos salen muy chicos (número lejano), se recorta esa zona de la foto "
        "con todo su detalle y se vuelve a procesar; (8) cada dígito se recorta, se escala para que su lado mayor mida 20 píxeles y se centra por centro "
        "de masa en 28×28, igual que MNIST."
        + ("\n\nLa segmentación se probó con 150 números ficticios por nivel de dificultad: la tabla 1 muestra cuántos se separaron en la cantidad correcta "
           "de dígitos sin ayuda y sabiendo cuántos dígitos escribió la persona." if pre else "")
        + ("\n\nLa tabla 2 mide fotos difíciles simuladas: hojas cuadriculadas o rayadas, tintas de colores, fotos grandes de celular, números lejanos "
           "y fotos giradas. De cabeza el acierto es bajo a propósito: el 6 y el 9, o el 0, 1 y 8, se ven igual al revés, así que la aplicación solo "
           "voltea la foto cuando está segura y deja el botón «Girar» para hacerlo a mano." if d.get("fotos_dificiles") else "")
    )
    t["algoritmos"] = (
        "Se eligió una red convolucional como modelo principal porque detecta trazos sin importar dónde estén en la imagen. Para comparar se incluyeron "
        "un perceptrón multicapa, una SVM y KNN (los algoritmos que pide el caso), además de regresión lineal y logística y K-Means, que aportan referencias lineales "
        "y una no supervisada. Todos comparten la misma interfaz, así que se entrenan, evalúan y corrigen igual."
    )
    cnn = d["arquitecturas"]["cnn"]
    t["arquitectura"] = (
        "La CNN recibe la imagen de 28×28 y aplica dos bloques de convolución con activación ReLU y reducción por máximo (MaxPool). Después aplana el resultado, "
        f"aplica Dropout y pasa por una capa densa de 64 neuronas antes de la salida de 10 neuronas, una por dígito, con Softmax. Tiene {miles(cnn['parametros_totales'])} parámetros; "
        f"el optimizador es {cnn['optimizador']} y la función de pérdida es {cnn['funcion_perdida'].lower()}."
    )
    t["entrenamiento"] = (
        "El ajuste de hiperparámetros se hizo con validación cruzada estratificada de 5 pliegues sobre 5 000 dígitos y una búsqueda en malla por modelo "
        "(las redes se entrenaron solo 2 épocas para acelerar). Con la mejor combinación se entrenó cada modelo con un subconjunto mayor de MNIST y se evaluó una sola vez "
        "con los 10 000 dígitos de prueba, que nunca se usaron para elegir hiperparámetros. Los números de la validación cruzada son menores que los de la prueba final "
        "porque usan menos dígitos y menos épocas. La figura de validación cruzada incluye a los siete modelos; las curvas de aprendizaje solo muestran "
        "la CNN y el MLP porque son los únicos que aprenden por épocas (los demás se ajustan de una vez)."
    )
    ms = {c: m[c]["ms_por_muestra"] for c in CLAVES_MODELOS}
    lento = max(ms, key=ms.get)
    t["resultados"] = (
        "Se calcularon la exactitud (aciertos sobre total), la precisión (cuando dice un dígito, cuántas veces acierta), el recall (de todos los dígitos reales de una clase, "
        "cuántos encuentra) y el F1 (equilibrio entre ambos), promediando las diez clases por igual. "
        f"{NOMBRES_CORTOS[lento]} es el más lento al predecir ({coma(ms[lento], 3)} ms por dígito) y aun así responde en una fracción de milisegundo."
    )
    matriz = m[mejor]["matriz_confusion"]
    top = confusiones_frecuentes(matriz, 1)
    t["matrices"] = (
        "La matriz de confusión muestra en cada fila el dígito real y en cada columna lo que respondió el modelo: la diagonal son los aciertos y todo lo demás son confusiones. "
        + (f"En el mejor modelo, la confusión más frecuente es leer {top[0][2]} cuando era {top[0][1]} ({top[0][0]} veces). " if top else "")
        + "Los pares de dígitos con trazos parecidos (4 y 9, 3 y 5, 7 y 1) son los que más se confunden en todos los modelos.\n\n"
        "Se muestran las matrices de los siete modelos para compararlas lado a lado, y un mapa con el porcentaje de cada dígito que acierta cada modelo: "
        "así se ve, por ejemplo, qué dígitos le cuestan a K-Means o a la regresión lineal y cuáles lee bien cualquier modelo."
    )
    t["comparacion"] = (
        f"{NOMBRES_MODELOS[mejor]} obtiene el mejor resultado porque las capas convolucionales aprenden filtros de trazos que funcionan en cualquier posición y las capas siguientes "
        "combinan esos trazos en formas. SVM y KNN funcionan bien porque MNIST está muy ordenado: los dígitos parecidos quedan cerca en el espacio de 50 componentes principales (PCA). "
        "La regresión logística solo puede trazar fronteras rectas entre dígitos, por eso rinde menos. K-Means agrupa sin conocer las etiquetas y luego cada grupo toma el dígito más común, "
        "así que confunde los dígitos que forman grupos mezclados.\n\n"
        "En la práctica, la CNN es la mejor opción para el sistema; KNN y SVM son alternativas sólidas y fáciles de actualizar con nuevas correcciones; la regresión y K-Means sirven como referencia."
    )
    t["correcciones"] = (
        "Cuando un modelo se equivoca en tus fotos, la aplicación lo reentrena con esos dígitos (con variantes: giros, escalas y desplazamientos pequeños) mezclados con ejemplos de MNIST "
        "y de tus correcciones anteriores, a una tasa baja para no olvidar. Se reservan cerca del 30 % de las fotos sin usarlas para comprobar que aprende de verdad. "
        "Cada corrección crea una versión nueva; solo se guarda un modelo si no baja más de 0,5 puntos en MNIST ni empieza a fallar en dígitos anteriores. "
        "Las versiones anteriores se conservan y se puede volver a cualquiera."
    )
    t["fotos"] = ("Esta sección usa tus propias fotos. Primero, un gráfico con los aciertos de cada modelo en ellas, las matrices de confusión de los "
                  "siete modelos con lo que confundió cada uno y los pasos del preprocesado sobre una de tus fotos. Después, cada foto elegida con el número que escribiste, los dígitos que recortó la aplicación y lo que "
                  "leyó cada modelo con la versión " + d["version"] + ".")
    t["conclusiones"] = (
        f"Se construyó una aplicación que lee dígitos manuscritos, compara siete modelos y aprende de sus errores sin perder lo aprendido. {NOMBRES_MODELOS[mejor]} alcanzó {pct(m[mejor]['exactitud'], 2)} en MNIST.\n\n"
        "Limitaciones: MNIST no incluye la variedad de letras reales, así que con fotos propias la exactitud puede bajar; las fotos con dígitos muy pegados necesitan saber cuántos dígitos hay; "
        "las fotos de cabeza no siempre se enderezan solas (algunos números se leen igual al revés) y las hojas cuadriculadas, fotos giradas y números lejanos "
        "se midieron con fotos simuladas, no con fotos reales de la empresa. "
        "Recomendaciones: reunir más fotos reales de los formularios de la empresa, corregir a los modelos con ellas y comparar antes y después; considerar reconocimiento de campos completos y validaciones de formato "
        "(por ejemplo, un teléfono de 9 dígitos) para detectar lecturas dudosas."
    )
    t["codigo"] = (
        "El código está organizado en carpetas con nombres en español. Incluye el preprocesado de imágenes, los siete modelos (regresión lineal y logística, K-Means, redes neuronales, SVM y KNN), "
        "el generador de datos ficticios, la validación cruzada, la evaluación y las pruebas automáticas. Desde la aplicación se puede descargar todo el código en un archivo .zip."
    )
    t["referencias"] = "Fuentes de datos, bibliografía, herramientas e imágenes utilizadas en este informe."
    return t


# ---------------------------------------------------------------- estilos y piezas
class Documento(BaseDocTemplate):
    def afterFlowable(self, flowable):
        nivel = getattr(flowable, "_nivel_indice", None)
        if nivel is not None:
            texto = flowable.getPlainText()
            clave = f"sec-{self.seq.nextf('sec')}"
            self.canv.bookmarkPage(clave)
            self.canv.addOutlineEntry(texto, clave, nivel, 0)
            self.notify("TOCEntry", (nivel, texto, self.page))


class Titulo(Paragraph):
    _nivel_indice = 0


def estilos(tema):
    principal, oscuro = TEMAS.get(tema, TEMAS["violeta"])
    base = dict(fontName="Informe", textColor=colors.HexColor("#16123b"))
    return {
        "principal": colors.HexColor(principal),
        "oscuro": colors.HexColor(oscuro),
        "titulo": ParagraphStyle("titulo", fontName="Informe-Negrita", fontSize=30, leading=35, textColor=colors.white, alignment=TA_LEFT),
        "subtitulo": ParagraphStyle("subtitulo", fontName="Informe", fontSize=13.5, leading=19, textColor=colors.HexColor("#f4f1ff")),
        "portada_dato": ParagraphStyle("portada_dato", fontName="Informe", fontSize=10.5, leading=15, textColor=colors.HexColor("#16123b")),
        "credito": ParagraphStyle("credito", fontName="Informe-Cursiva", fontSize=7.5, leading=10, textColor=colors.HexColor("#5b5780"), alignment=TA_CENTER),
        "h1": ParagraphStyle("h1", fontName="Informe-Negrita", fontSize=17, leading=21, spaceBefore=6, spaceAfter=10, textColor=colors.HexColor(principal), **{k: v for k, v in base.items() if k not in ("fontName", "textColor")}),
        "h2": ParagraphStyle("h2", fontName="Informe-Negrita", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=5, textColor=colors.HexColor("#16123b")),
        "texto": ParagraphStyle("texto", fontName="Informe", fontSize=9.6, leading=14.2, spaceAfter=7, textColor=colors.HexColor("#16123b")),
        "leyenda": ParagraphStyle("leyenda", fontName="Informe-Cursiva", fontSize=8.2, leading=11.5, textColor=colors.HexColor("#5b5780"), alignment=TA_CENTER, spaceBefore=3, spaceAfter=10),
        "celda": ParagraphStyle("celda", fontName="Informe", fontSize=8.2, leading=10.8, textColor=colors.HexColor("#16123b")),
        "celda_negrita": ParagraphStyle("celda_negrita", fontName="Informe-Negrita", fontSize=8.2, leading=10.8, textColor=colors.HexColor("#16123b")),
        "celda_cabecera": ParagraphStyle("celda_cabecera", fontName="Informe-Negrita", fontSize=8.2, leading=10.8, textColor=colors.white),
        "toc1": ParagraphStyle("toc1", fontName="Informe", fontSize=10.5, leading=17, textColor=colors.HexColor("#16123b")),
    }


def parrafos(texto, e):
    return [Paragraph(escape(p.strip()).replace("\n", "<br/>"), e["texto"]) for p in (texto or "").split("\n\n") if p.strip()]


def celda(texto, e, negrita=False, cabecera=False):
    estilo = e["celda_cabecera"] if cabecera else (e["celda_negrita"] if negrita else e["celda"])
    return Paragraph(escape(str(texto)), estilo)


def tabla(cabecera, filas, anchos, e, negrita_primera=True, zebra=True):
    """Tabla con texto que se ajusta a la celda, cabecera repetida en cada pagina y filas que no se parten."""
    datos = [[celda(c, e, cabecera=True) for c in cabecera]]
    for fila in filas:
        datos.append([c if hasattr(c, "wrap") else celda(c, e, negrita=(negrita_primera and i == 0)) for i, c in enumerate(fila)])
    total = sum(anchos)
    anchos = [a * ANCHO_UTIL / total for a in anchos]
    t = Table(datos, colWidths=anchos, repeatRows=1, splitByRow=True)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), e["principal"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e4dffa")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#c9c3ea")),
    ]
    if zebra:
        for i in range(2, len(datos), 2):
            estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f7f5ff")))
    t.setStyle(TableStyle(estilo))
    t.hAlign = "LEFT"
    return t


def figura(png, ancho_cm, leyenda, e, alto_maximo_cm=20.5):
    """Inserta una imagen completa, con su proporcion, sin cortarla y sin separarla de su leyenda."""
    with ImagenPIL.open(io.BytesIO(png)) as im:
        w, h = im.size
    ancho = min(ancho_cm * cm, ANCHO_UTIL)
    alto = ancho * h / w
    if alto > alto_maximo_cm * cm:
        alto = alto_maximo_cm * cm
        ancho = alto * w / h
    imagen = Image(io.BytesIO(png), width=ancho, height=alto)
    imagen.hAlign = "CENTER"
    if not leyenda:
        return KeepTogether([imagen, Spacer(1, 8)])
    return KeepTogether([imagen, Paragraph(escape(leyenda), e["leyenda"])])


def figura_en_partes(pngs, ancho_cm, leyenda, e):
    """Una figura repartida en varias imágenes (por ejemplo las siete matrices, de a cuatro); la leyenda va en la última."""
    total = len(pngs)
    return [figura(png, ancho_cm, leyenda if i == total - 1 else "", e) for i, png in enumerate(pngs)]


def encabezado(texto, e):
    return Titulo(escape(texto), e["h1"])


def pie_y_cabecera(e, version):
    def dibujar(canvas, doc):
        canvas.saveState()
        canvas.setFont("Informe", 8)
        canvas.setFillColor(colors.HexColor("#5b5780"))
        canvas.drawString(MARGEN, 1.1 * cm, f"TecnoForms · Reconocimiento de dígitos manuscritos · modelos {version}")
        canvas.drawRightString(ANCHO_PAGINA - MARGEN, 1.1 * cm, f"Página {doc.page}")
        canvas.setStrokeColor(e["principal"])
        canvas.setLineWidth(1.6)
        canvas.line(MARGEN, ALTO_PAGINA - 1.35 * cm, MARGEN + 2.2 * cm, ALTO_PAGINA - 1.35 * cm)
        canvas.restoreState()
    return dibujar


def portada(opciones, e, d):
    """Devuelve la funcion que dibuja el fondo de la portada (banda de color e imagen completa dentro de un marco)."""
    imagen = opciones.get("portada") or "cuaderno"
    propia = opciones.get("_portada_bytes") if imagen == "propia" else None
    creditos = None if propia else d["creditos"].get(imagen)
    ruta = CODIGO / "recursos" / "imagenes" / "portadas" / creditos["archivo"] if creditos else None
    origen = ImageReader(io.BytesIO(propia)) if propia else (str(ruta) if ruta and ruta.exists() else None)

    def dibujar(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(e["principal"])
        canvas.rect(0, ALTO_PAGINA - 13.2 * cm, ANCHO_PAGINA, 13.2 * cm, stroke=0, fill=1)
        canvas.setFillColor(e["oscuro"])
        canvas.rect(0, ALTO_PAGINA - 13.2 * cm, ANCHO_PAGINA, 0.5 * cm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#ffffff"))
        canvas.setFont("Informe-Negrita", 11)
        canvas.drawString(MARGEN, ALTO_PAGINA - 2.1 * cm, "TecnoForms")
        canvas.setFont("Informe", 9.5)
        canvas.drawString(MARGEN, ALTO_PAGINA - 2.75 * cm, "Lector de dígitos manuscritos")
        if origen is not None:
            caja_x, caja_y, caja_w, caja_h = ANCHO_PAGINA - MARGEN - 7.2 * cm, ALTO_PAGINA - 12.4 * cm, 7.2 * cm, 9.8 * cm
            canvas.setFillColor(colors.white)
            canvas.roundRect(caja_x - 0.25 * cm, caja_y - 0.25 * cm, caja_w + 0.5 * cm, caja_h + 0.5 * cm, 0.35 * cm, stroke=0, fill=1)
            canvas.drawImage(origen, caja_x, caja_y, width=caja_w, height=caja_h, preserveAspectRatio=True, anchor="c", mask="auto")
            if creditos:
                canvas.setFillColor(colors.HexColor("#5b5780"))
                canvas.setFont("Informe-Cursiva", 6.6)
                titulo_imagen = creditos["titulo"] if len(creditos["titulo"]) <= 44 else creditos["titulo"][:44].rstrip() + "…"
                autor = creditos["autor"] if len(creditos["autor"]) <= 30 else creditos["autor"][:30].rstrip() + "…"
                pie = f"Imagen: «{titulo_imagen}», {autor} ({creditos['licencia']}), Wikimedia Commons"
                canvas.drawRightString(ANCHO_PAGINA - MARGEN, ALTO_PAGINA - 13.9 * cm, pie)
        canvas.restoreState()
    return dibujar


def _titulo_portada(opciones, e):
    fecha = datetime.now().strftime("%d/%m/%Y")
    ancho_texto = ANCHO_UTIL - 7.9 * cm
    filas = [Spacer(1, 4.4 * cm), Paragraph(escape(opciones.get("titulo") or "Reconocimiento de dígitos manuscritos"), ParagraphStyle("t", parent=e["titulo"], fontSize=27, leading=32)),
             Spacer(1, 0.5 * cm), Paragraph(escape(opciones.get("subtitulo") or "Clasificación automática de formularios escritos a mano"), e["subtitulo"])]
    envoltura = Table([[filas]], colWidths=[ancho_texto])
    envoltura.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    envoltura.hAlign = "LEFT"
    datos = []
    for etiqueta, valor in (("Autor", opciones.get("autor")), ("Curso o materia", opciones.get("curso")), ("Fecha", fecha)):
        if valor:
            datos.append(Paragraph(f"<font name='Informe-Negrita'>{etiqueta}:</font> {escape(str(valor))}", e["portada_dato"]))
    return [envoltura, Spacer(1, 5.1 * cm)] + datos


# ---------------------------------------------------------------- secciones
def sec_caso(e, t):
    filas = [
        ("Selección de algoritmos (red neuronal y comparación con KNN o SVM)", "Algoritmos elegidos y por qué; Resultados", "Cumplido: 7 modelos comparados"),
        ("Preparación de las imágenes: normalización, escala de grises y segmentación", "Preparación de las imágenes",
         "Cumplido, con figuras de los pasos y pruebas de fotos difíciles"),
        ("Red diseñada para aprender de las imágenes, con capas convolucionales", "Arquitectura de las redes neuronales", "Cumplido: CNN con 2 capas convolucionales"),
        ("Entrenamiento, validación cruzada y ajuste de hiperparámetros", "Entrenamiento, validación cruzada e hiperparámetros", "Cumplido: 5 pliegues y búsqueda en malla"),
        ("Conjunto de prueba, precisión, interpretación y comparación con otros modelos", "Resultados; Comparación e interpretación", "Cumplido: 10 000 dígitos de prueba"),
        ("Matriz de confusión, precisión, recall y F1", "Resultados; Matrices de confusión", "Cumplido, con datos de internet (MNIST)"),
        ("Código con regresión, K-Means, redes neuronales y preprocesado", "Código fuente", "Cumplido, con datos ficticios"),
        ("Resultados visuales de predicciones frente a etiquetas reales", "Matrices de confusión (galerías de los siete modelos); Fotos y predicciones",
         "Cumplido: dígitos con «Real / Predijo» de cada modelo"),
        ("Arquitectura de la red: capas, nodos, activación y optimizador", "Arquitectura de las redes neuronales", "Cumplido"),
        ("Informe con pasos, razonamiento, algoritmos y resultados", "Este documento", "Cumplido"),
    ]
    return [tabla(["Requisito del caso", "Dónde se cumple", "Estado"], filas, [8, 5.5, 3.5], e, negrita_primera=False)]


def texto_banco(banco):
    if not banco or not (banco["formularios"] or banco["numeros"] or banco["cuadriculadas"]):
        return "Se generan desde la aplicación"
    partes = [f"{banco['formularios']} formularios", f"{banco['numeros']} números en hoja lisa"]
    if banco["cuadriculadas"]:
        partes.append(f"{banco['cuadriculadas']} en hoja cuadriculada o rayada")
    return ", ".join(partes[:-1]) + " y " + partes[-1] + "; se generan más desde la aplicación"


def sec_datos(e, d):
    ent = MUESTRAS_ENTRENAMIENTO
    filas = [
        ("MNIST (entrenamiento)", "Entrenar y ajustar los modelos", "60 000 imágenes; se usan " + ", ".join(f"{NOMBRES_CORTOS[c]} {ent[c]:,}".replace(",", " ") for c in CLAVES_MODELOS), "Internet"),
        ("MNIST (prueba)", "Evaluar una sola vez cada versión", "10 000 imágenes", "Internet"),
        ("Formularios y números ficticios", "Probar el preprocesado y la lectura de campos", texto_banco(d.get("banco")), "Ficticio"),
        ("Fotos subidas a la aplicación", "Comparar modelos y corregirlos", "Hasta 20 fotos por tanda", "Reales"),
    ]
    return [tabla(["Fuente", "Para qué se usa", "Cantidad", "Tipo"], filas, [4, 5, 6, 2], e)]


def sec_preprocesado(e, d):
    generador = np.random.default_rng(3)
    from .datos import cargar_mnist
    _, _, x_pru, y_pru = cargar_mnist()
    g = GeneradorDigitos(x_pru, y_pru, semilla=11)
    foto = g.foto_numero("4235", dificultad=0.5)
    r = procesar_foto(foto, esperado=4)
    piezas = [figura(figuras.fig_preprocesado(r["pasos"], r["recortes"]), 16.6,
                     "Figura 1. Pasos del preprocesado sobre una foto ficticia con el número 4235: de la foto original a los cuatro dígitos en formato MNIST.", e)]
    pre = d["preprocesado"]
    if pre:
        nombres = {"limpio": "Limpio", "normal": "Normal", "dificil": "Difícil (dígitos pegados)"}
        filas = []
        for nivel, v in pre.items():
            filas.append((nombres.get(nivel, nivel), f"{v['numeros']}", pct(v["segmentacion_correcta_sin_ajuste"], 1), pct(v["segmentacion_correcta_con_cantidad_conocida"], 1),
                          pct(v["numero_completo_correcto"]["cnn"], 1)))
        piezas.append(tabla(["Dificultad", "Números", "Segmentación sin conocer la cantidad", "Segmentación conociendo la cantidad", "Número completo correcto (CNN)"], filas, [3.4, 2, 4, 4, 3.6], e))
        piezas.append(Paragraph("Tabla 1. Calidad de la segmentación con números ficticios (datos ficticios, no reales).", e["leyenda"]))
    cuadriculada = g.foto_cuadriculada("4235", 0.4, color_linea=(160, 80, 20), color_tinta=(40, 40, 200))
    r = procesar_foto(cuadriculada, esperado=4)
    piezas.append(figura(figuras.fig_preprocesado(r["pasos"], r["recortes"]), 16.6,
                         "Figura 2. El mismo número en una hoja cuadriculada azul con tinta roja: se usa el canal de color donde la cuadrícula casi "
                         "desaparece (paso 2) y se borran las líneas que quedan sin tocar los trazos (paso 4).", e))
    dificiles = d.get("fotos_dificiles")
    if dificiles:
        corto = lambda v: pct(v, 0).replace(" ", " ")  # que «90 %» no se parta en dos líneas
        filas = []
        for c in dificiles["casos"]:
            por_modelo = c.get("numero_exacto") or {"cnn": c["numero_exacto_cnn"]}
            filas.append([c["caso"], corto(c["cantidad_correcta"])] + [corto(por_modelo[m]) if m in por_modelo else "—" for m in CLAVES_MODELOS])
        cabecera_corta = {"regresion": "R. log.", "regresion_lineal": "R. lin.", "kmeans": "K-M."}
        piezas.append(tabla(["Tipo de foto", "Separó bien los dígitos"] + [cabecera_corta.get(m, NOMBRES_CORTOS[m]) for m in CLAVES_MODELOS], filas,
                            [3.9, 1.7] + [1.55] * len(CLAVES_MODELOS), e))
        piezas.append(Paragraph(f"Tabla 2. Fotos difíciles simuladas ({dificiles['casos'][0]['fotos']} por tipo, datos ficticios, no reales): "
                                f"porcentaje de números completos bien leídos por cada modelo de {dificiles.get('version', 'v1')}. "
                                "R. log. = regresión logística; R. lin. = regresión lineal; K-M. = K-Means. Las fotos giradas se enderezan solas antes de leerlas.", e["leyenda"]))
    return piezas


def sec_algoritmos(e):
    filas = [
        ("CNN (red convolucional)", "Filtros que detectan trazos y los combinan en formas.", "Muy precisa; reconoce trazos en cualquier posición.", "Necesita más cómputo para entrenar.", "Modelo principal que pide el caso."),
        ("MLP (red densa)", "Capas de neuronas que mezclan todos los píxeles.", "Sencilla y rápida de entrenar.", "No aprovecha la forma de la imagen.", "Red neuronal de referencia."),
        ("SVM (RBF)", "Traza fronteras curvas entre dígitos usando ejemplos clave.", "Muy buena con pocos datos.", "Entrenar con muchos datos es lento.", "Comparación que pide el caso."),
        ("KNN", "Busca los dígitos más parecidos que memorizó y vota.", "No entrena; aprender es memorizar.", "Guarda todos los ejemplos; predice más lento.", "Comparación que pide el caso."),
        ("Regresión logística", "Suma píxeles con un peso por dígito.", "Interpretable y muy rápida.", "Solo separa con fronteras rectas.", "Algoritmo de regresión que pide el caso."),
        ("Regresión lineal", "Ajusta por mínimos cuadrados un puntaje por dígito y gana el mayor.", "La más simple; se resuelve con una fórmula exacta.", "Trata los dígitos como valores numéricos; rinde menos.", "Regresión lineal que pide el caso."),
        ("K-Means", "Agrupa dígitos parecidos sin usar etiquetas.", "No necesita etiquetas para agrupar.", "Los grupos pueden mezclar dígitos.", "Algoritmo no supervisado que pide el caso."),
    ]
    return [tabla(["Modelo", "Cómo decide", "Fortaleza", "Limitación", "Por qué se incluyó"], filas, [3, 4.6, 3.6, 3.6, 3.4], e)]


def sec_arquitectura(e, d):
    a = d["arquitecturas"]
    piezas = [figura(figuras.fig_arquitectura_cnn(d["metricas"]["cnn"]["hiperparametros"].get("filtros", 16)), 16.6,
                     "Figura 3. Esquema de la CNN: dos bloques de convolución, una capa densa y 10 salidas.", e)]
    for clave in ("cnn", "mlp"):
        info = a[clave]
        filas = [(l["capa"], l["forma"], l["activacion"], f"{l['parametros']:,}".replace(",", " ") if l["parametros"] else "—") for l in info["capas"]]
        pie = (f"Total: {miles(info['parametros_totales'])} parámetros. Optimizador: {info['optimizador']} "
               f"(tasa de aprendizaje {str(info['tasa_aprendizaje']).replace('.', ',')}). Función de pérdida: {info['funcion_perdida']}.")
        piezas.append(KeepTogether([Paragraph(NOMBRES_MODELOS[clave], e["h2"]),
                                    tabla(["Capa", "Salida", "Activación", "Parámetros"], filas, [4, 7, 2.6, 2.6], e),
                                    Paragraph(escape(pie), e["leyenda"])]))
    filas = []
    for clave in ("svm", "knn", "regresion", "regresion_lineal", "kmeans"):
        info = a[clave]
        detalles = "; ".join(f"{k}: {str(v).replace('.', ',')}" for k, v in info["parametros"].items())
        extra = [f"vectores de soporte: {info['vectores_soporte']}"] if info.get("vectores_soporte") else []
        extra += [f"dígitos memorizados: {info['muestras_memorizadas']:,}".replace(",", " ")] if info.get("muestras_memorizadas") else []
        extra += [f"parámetros totales: {info['parametros_totales']}"] if info.get("parametros_totales") else []
        filas.append((NOMBRES_MODELOS[clave], info["tipo"], "; ".join([detalles] + extra)))
    piezas.append(KeepTogether([Paragraph("Otros modelos", e["h2"]), tabla(["Modelo", "Tipo", "Configuración"], filas, [3.4, 5, 8.6], e)]))
    return piezas


def sec_entrenamiento(e, d):
    cv = d["cv"]
    filas = []
    for c in CLAVES_MODELOS:
        if not cv.get(c):
            continue
        mejor = cv[c][0]
        malla = "; ".join(f"{ETIQUETAS_PARAMETROS.get(k, k)}: {', '.join(str(x).replace('.', ',') for x in v)}" for k, v in GRILLAS[c].items())
        elegida = texto_parametros(mejor["parametros"])
        filas.append((NOMBRES_CORTOS[c], malla, elegida, f"{pct(mejor['exactitud_media'], 2)} ± {pct(mejor['desviacion'], 2)}"))
    piezas = [tabla(["Modelo", "Valores probados", "Elegidos", "Exactitud en validación cruzada"], filas, [2.4, 7, 4, 3.6], e),
              Paragraph("Tabla 3. Búsqueda de hiperparámetros con validación cruzada de 5 pliegues (5 000 dígitos).", e["leyenda"]),
              figura(figuras.fig_validacion(cv), 16.6, "Figura 4. Exactitud de cada pliegue de la validación cruzada. Puntos juntos indican un modelo estable.", e)]
    if d["curvas"]:
        piezas.append(figura(figuras.fig_curvas(d["curvas"]), 16.6, "Figura 5. Curvas de aprendizaje de las redes neuronales durante el entrenamiento inicial.", e))
    return piezas


def sec_resultados(e, d):
    m = d["metricas"]
    filas = [(NOMBRES_MODELOS[c], pct(m[c]["exactitud"], 2), pct(m[c]["precision_macro"], 2), pct(m[c]["recall_macro"], 2), pct(m[c]["f1_macro"], 2), coma(m[c]["ms_por_muestra"], 3)) for c in d["orden"]]
    return [tabla(["Modelo", "Exactitud", "Precisión", "Recall", "F1", "ms por dígito"], filas, [5, 2.4, 2.4, 2.4, 2.4, 2.6], e),
            Paragraph("Tabla 4. Métricas en los 10 000 dígitos de prueba de MNIST (datos de internet), ordenadas de mejor a peor exactitud.", e["leyenda"]),
            figura(figuras.fig_metricas(m), 16.6, "Figura 6. Exactitud, precisión, recall y F1 de cada modelo.", e),
            figura(figuras.fig_velocidad(m), 16.6, "Figura 7. Velocidad de predicción y tiempo de entrenamiento inicial.", e)]


def sec_matrices(e, d):
    m = d["metricas"]
    mejor = d["orden"][0]
    filas = []
    for c in d["orden"]:
        top = confusiones_frecuentes(m[c]["matriz_confusion"], 3)
        filas.append((NOMBRES_CORTOS[c], "; ".join(f"real {i} leído como {j}: {n} {'vez' if n == 1 else 'veces'}" for n, i, j in top) or "sin errores"))
    matrices = {c: m[c]["matriz_confusion"] for c in d["orden"]}
    return figura_en_partes(figuras.fig_matrices(matrices, d["orden"], {c: pct(m[c]["exactitud"], 1) for c in d["orden"]}), 16.6,
                            f"Figura 8. Matrices de confusión de los siete modelos con los 10 000 dígitos de prueba de MNIST, de mejor a peor "
                            f"exactitud (en dos partes). El mejor es {NOMBRES_MODELOS[mejor]}.", e) + [
            figura(figuras.fig_aciertos_por_digito(matrices, d["orden"]), 16.6,
                   "Figura 9. Aciertos de cada modelo en cada dígito (recall por clase). Muestra qué dígitos le cuestan a cada modelo.", e),
            KeepTogether([Paragraph("Confusiones más frecuentes de cada modelo", e["h2"]),
                          tabla(["Modelo", "Tres confusiones más frecuentes"], filas, [3, 14], e)]),
            Paragraph("Predicciones frente a la etiqueta real", e["h2"]),
            Paragraph("Cada modelo con los mismos criterios: un dígito de prueba de MNIST que acertó de cada número (0 a 9) y dos en los que "
                      "se equivocó. A la izquierda el dígito real y lo que predijo; a la derecha la imagen que recibió.", e["texto"])] + [
            figura(d["predicciones"][c], 16.6, f"Figura 10{'abcdefg'[i]}. Predicciones de {NOMBRES_MODELOS[c]} frente a la etiqueta real "
                   "(verde = correcto, rosa = incorrecto).", e) for i, c in enumerate(d["orden"])]


def sec_correcciones(e, d):
    filas = []
    for v in d["versiones"]:
        det = v["detalle"]
        ex = det.get("exactitud_prueba", {})
        filas.append((v["id"], v["creada"].replace("T", " "), v["motivo"], ", ".join(NOMBRES_CORTOS[c] for c in det.get("actualizados", [])) or "—",
                      " · ".join(f"{NOMBRES_CORTOS[c]} {pct(ex[c], 1)}" for c in CLAVES_MODELOS if c in ex)))
    piezas = [tabla(["Versión", "Fecha", "Qué pasó", "Modelos actualizados", "Exactitud en MNIST"], filas, [2.0, 3.1, 4.2, 3.1, 5.6], e),
              Paragraph("Tabla 5. Versiones guardadas. Cada corrección crea una versión nueva y las anteriores se conservan.", e["leyenda"]),
              figura(graficos.figuras.fig_progreso([{"id": v["id"], "exactitud_prueba": v["detalle"].get("exactitud_prueba", {})} for v in d["versiones"]]), 16.6,
                     "Figura 11. Exactitud en MNIST por versión. Una caída significaría que el modelo olvidó lo aprendido.", e)]
    ultimo = next((v for v in reversed(d["versiones"]) if v["detalle"].get("informe")), None)
    if ultimo:
        filas = []
        for i in ultimo["detalle"]["informe"]:
            if not i.get("entrenado"):
                filas.append((NOMBRES_CORTOS[i["modelo"]], "Sin cambios", "—", "—", "—"))
                continue
            aen, den = i["entrenamiento_antes"], i["entrenamiento_despues"]
            filas.append((NOMBRES_CORTOS[i["modelo"]], "Mejoró" if i["aceptado"] else "No se guardó", f"{aen[0]}/{aen[1]} → {den[0]}/{den[1]}",
                          f"{pct(i['mnist_antes'], 2)} → {pct(i['mnist_despues'], 2)}", "" if i["aceptado"] else (i.get("motivo") or "")))
        piezas.append(KeepTogether([Paragraph(f"Última corrección (versión {ultimo['id']})", e["h2"]),
                                    tabla(["Modelo", "Estado", "Dígitos de esas fotos (aciertos)", "Exactitud en MNIST", "Motivo"], filas, [2.4, 2.4, 4, 4, 4.6], e),
                                    Paragraph("Tabla 6. Resultado de la última corrección: solo se guardan los modelos que mejoran sin perder exactitud en MNIST.", e["leyenda"])]))
    return piezas


def nombre_tanda(lote):
    """lote_2026-09-20_143651 → «20/09/2026 a las 14:36:51» (igual que en la aplicación, para no confundir tandas del mismo día)."""
    m = re.fullmatch(r"lote_(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})(b*)", lote or "")
    if not m:
        return str(lote or "").replace("lote_", "")
    return f"{m[3]}/{m[2]}/{m[1]} a las {m[4]}:{m[5]}:{m[6]}" + (f" ({len(m[7]) + 1})" if m[7] else "")


MAXIMO_GALERIA_FOTOS = 12


def _digito_png(uri):
    return base64.b64decode(uri.split(",", 1)[1])


def _resumen_fotos(e, servicio, fotos):
    """Gráficos hechos con las fotos del usuario: aciertos de cada modelo, matriz de confusión de la tanda y los pasos del
    preprocesado sobre una de sus fotos."""
    completas = [f for f in fotos if f["completa"]]
    piezas = []
    if completas:
        resumen = {c: {"digitos_ok": sum(f["por_modelo"][c]["aciertos"] for f in completas), "digitos": sum(len(f["digitos"]) for f in completas),
                       "numeros_ok": sum(f["por_modelo"][c]["correcto"] for f in completas), "numeros": len(completas)} for c in CLAVES_MODELOS}
        orden = sorted(CLAVES_MODELOS, key=lambda c: (-resumen[c]["digitos_ok"], -resumen[c]["numeros_ok"]))
        filas = [(NOMBRES_CORTOS[c], f"{resumen[c]['digitos_ok']}/{resumen[c]['digitos']}", f"{resumen[c]['numeros_ok']}/{resumen[c]['numeros']}") for c in orden]
        piezas += [figura(figuras.fig_aciertos_fotos(resumen), 16.6,
                          f"Figura 12. Aciertos de cada modelo en tus {len(completas)} fotos elegidas (fotos reales subidas a la aplicación).", e),
                   KeepTogether([tabla(["Modelo", "Dígitos bien leídos", "Números completos bien leídos"], filas, [5, 6, 6], e),
                                 Paragraph("Tabla 7. Aciertos en tus fotos, de mejor a peor.", e["leyenda"])]), Spacer(1, 6)]
        matrices = {c: np.zeros((10, 10), int) for c in CLAVES_MODELOS}
        for f in completas:
            for dg in f["digitos"]:
                for c in CLAVES_MODELOS:
                    if c in dg["modelos"]:
                        matrices[c][dg["real"], dg["modelos"][c]["predicho"]] += 1
        total = int(matrices[orden[0]].sum())
        subtitulos = {c: f"{resumen[c]['digitos_ok']}/{resumen[c]['digitos']}" for c in CLAVES_MODELOS}
        piezas += figura_en_partes(figuras.fig_matrices(matrices, orden, subtitulos), 16.6,
                                   f"Figura 13. Matrices de confusión de los siete modelos con los {total} dígitos de tu tanda, de mejor a peor "
                                   "(en dos partes). Cada fila es el dígito que escribiste y cada columna lo que leyó el modelo.", e)
        filas_errores = []
        for c in orden:
            errores = sorted(((int(matrices[c][i, j]), i, j) for i in range(10) for j in range(10) if i != j and matrices[c][i, j]), reverse=True)
            filas_errores.append((NOMBRES_CORTOS[c], "; ".join(f"leyó {j} cuando era {i} ({n} {'vez' if n == 1 else 'veces'})" for n, i, j in errores[:4])
                                  or "No se equivocó en ningún dígito"))
        piezas += [KeepTogether([tabla(["Modelo", "Sus confusiones en tus fotos"], filas_errores, [3, 14], e),
                                 Paragraph("Tabla 8. Qué confundió cada modelo en tu tanda.", e["leyenda"])]), Spacer(1, 6)]
        digitos, origen = [], {}
        for numero, f in enumerate(completas, 1):
            for posicion, dg in enumerate(f["digitos"], 1):
                digitos.append(dg)
                origen[dg["id"]] = f"Foto {numero} · dígito {posicion}"
        for i, c in enumerate(orden):
            propios = [dg for dg in digitos if c in dg["modelos"]]
            errores = [dg for dg in propios if dg["modelos"][c]["predicho"] != dg["real"]][:MAXIMO_GALERIA_FOTOS // 2]
            aciertos = [dg for dg in propios if dg["modelos"][c]["predicho"] == dg["real"]][:MAXIMO_GALERIA_FOTOS - len(errores)]
            elegidos = sorted(errores + aciertos, key=propios.index)
            if not elegidos:
                continue
            imagenes = [cv2.imdecode(np.frombuffer(_digito_png(dg["imagen"]), np.uint8), cv2.IMREAD_GRAYSCALE) for dg in elegidos]
            piezas.append(figura(figuras.fig_predicciones(imagenes, [dg["real"] for dg in elegidos], [dg["modelos"][c]["predicho"] for dg in elegidos],
                                                          [origen[dg["id"]] for dg in elegidos]),
                                 16.6, f"Figura 14{'abcdefg'[i]}. Predicciones de {NOMBRES_MODELOS[c]} con los dígitos de tus fotos frente al número que "
                                 "escribiste (verde = correcto, rosa = incorrecto). «Foto N» sigue el orden de las fotos de este informe.", e))
    for foto in fotos:
        imagen = cv2.imread(str(servicio.ruta_foto(foto["id"])))
        if imagen is None:
            continue
        r = procesar_foto(imagen, esperado=len(foto["texto"]) if foto["texto"] else None)
        if r["recortes"]:
            piezas.append(figura(figuras.fig_preprocesado(r["pasos"], r["recortes"]), 16.6,
                                 f"Figura 15. Pasos del preprocesado sobre tu foto «{escape(foto['nombre'])}» (número {escape(foto['texto'])}): "
                                 "así la vio la aplicación antes de dársela a los modelos.", e))
            break
    return piezas


def sec_fotos(e, d, servicio, opciones):
    lote = opciones.get("lote")
    ids = {int(i) for i in opciones.get("fotos", [])}
    if not lote:
        return [Paragraph("No se eligieron fotos para este informe.", e["texto"])]
    resultado = servicio.resultado_lote(lote, d["version"])
    elegidas = [f for f in resultado["fotos"] if not ids or f["id"] in ids]
    piezas = [Paragraph(f"Tanda: <font name='Informe-Negrita'>{escape(nombre_tanda(lote))}</font> · {len(elegidas)} "
                        f"{'foto elegida' if len(elegidas) == 1 else 'fotos elegidas'}.", e["texto"])]
    piezas += _resumen_fotos(e, servicio, elegidas)
    for foto in elegidas:
        ruta = servicio.ruta_foto(foto["id"])
        with ImagenPIL.open(ruta) as im:
            w, h = im.size
        ancho, alto = 6.4 * cm, 4.2 * cm
        escala = min(ancho / w, alto / h)
        imagen = Image(str(ruta), width=w * escala, height=h * escala)
        filas = []
        for c in CLAVES_MODELOS:
            pm = foto["por_modelo"][c]
            estado = "Correcto" if pm["correcto"] else ("Falló" if foto["completa"] else "No comparable")
            filas.append([celda(NOMBRES_CORTOS[c], e, negrita=True), celda(pm["numero"], e), celda(estado, e)])
        t = Table([[celda("Modelo", e, cabecera=True), celda("Leyó", e, cabecera=True), celda("Resultado", e, cabecera=True)]] + filas, colWidths=[2.7 * cm, 3.4 * cm, 3.0 * cm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), e["principal"]), ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e4dffa")),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        izquierda = [imagen, Spacer(1, 3), Paragraph(f"Número escrito: <font name='Informe-Negrita'>{escape(foto['texto'])}</font>", e["celda"])]
        recortes = [_digito_png(dg["imagen"]) for dg in foto["digitos"]]
        if recortes:
            lado = min(1.0 * cm, (6.4 * cm) / len(recortes))
            fila = Table([[Image(io.BytesIO(r), width=lado, height=lado) for r in recortes]], colWidths=[lado + 2] * len(recortes), hAlign="LEFT")
            fila.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
            izquierda += [Spacer(1, 3), Paragraph("Dígitos que recortó la aplicación (28×28):", e["celda"]), fila]
        bloque = Table([[izquierda, t]], colWidths=[7 * cm, ANCHO_UTIL - 7 * cm])
        bloque.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#c9c3ea")),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        piezas.append(KeepTogether([bloque, Spacer(1, 7)]))
    if not piezas:
        piezas = [Paragraph("Las fotos elegidas ya no están disponibles.", e["texto"])]
    return piezas


def sec_codigo(e):
    filas = [
        ("nucleo/preprocesado.py", "Enderezar fotos de lado, escala de grises o canal de color, corrección de sombras, binarización, quitar cuadrícula, "
         "zoom en números chicos, segmentación y formato MNIST.", "Preprocesado"),
        ("nucleo/modelos.py", "Los siete modelos con la misma interfaz: entrenar, predecir, actualizar y guardar.", "Redes neuronales, regresión, K-Means, SVM, KNN"),
        ("nucleo/validacion.py", "Validación cruzada de 5 pliegues con búsqueda de hiperparámetros.", "Validación cruzada"),
        ("nucleo/evaluacion.py", "Matriz de confusión, precisión, recall y F1.", "Métricas"),
        ("nucleo/formularios_ficticios.py", "Generador de números, hojas cuadriculadas o rayadas y formularios ficticios.", "Datos ficticios"),
        ("nucleo/servicio.py", "Predicción, corrección con versiones y conservación de mejoras.", "Correcciones"),
        ("nucleo/figuras.py, nucleo/informe.py", "Imágenes de los gráficos y este informe en PDF.", "Informe"),
        ("scripts/entrenar_inicial.py", "Entrena los siete modelos con MNIST y guarda los resultados.", "Entrenamiento"),
        ("scripts/evaluar_preprocesado.py, scripts/evaluar_fotos_dificiles.py",
         "Miden la segmentación y la lectura con fotos ficticias, también cuadriculadas, giradas o lejanas.", "Preprocesado"),
        ("app.py, vistas/, recursos/", "Aplicación web (Flask).", "Interfaz"),
        ("tests/", "Pruebas automáticas de datos, modelos, preprocesado (incluidas fotos difíciles), correcciones y aplicación.", "Verificación"),
    ]
    return [tabla(["Archivo", "Qué contiene", "Requisito del caso"], filas, [6.6, 7, 3.4], e)]


def sec_referencias(e, d):
    refs = [
        "LeCun, Y., Bottou, L., Bengio, Y. y Haffner, P. (1998). Gradient-based learning applied to document recognition. Proceedings of the IEEE, 86(11), 2278–2324.",
        "LeCun, Y., Cortes, C. y Burges, C. J. C. MNIST handwritten digit database. http://yann.lecun.com/exdb/mnist/",
        "Kingma, D. P. y Ba, J. (2015). Adam: a method for stochastic optimization. ICLR.",
        "Otsu, N. (1979). A threshold selection method from gray-level histograms. IEEE Transactions on Systems, Man, and Cybernetics, 9(1), 62–66.",
        "Selvaraju, R. R. et al. (2017). Grad-CAM: visual explanations from deep networks via gradient-based localization. ICCV.",
        "Herramientas: Python, PyTorch, scikit-learn, OpenCV, Flask, matplotlib y ReportLab.",
    ]
    piezas = [Paragraph(escape(r), e["texto"]) for r in refs]
    piezas.append(Paragraph("Imágenes de la aplicación (Wikimedia Commons)", e["h2"]))
    for c in d["creditos"].values():
        piezas.append(Paragraph(escape(f"«{c['titulo']}», {c['autor']} ({c['licencia']}). {c['fuente']}"), e["celda"]))
        piezas.append(Spacer(1, 3))
    return piezas


# ---------------------------------------------------------------- opciones de la pagina y entrega del codigo
def opciones_pagina(servicio, version):
    d = recopilar(servicio, version)
    portadas = [{"clave": k, "archivo": c["archivo"], "titulo": c["titulo"]} for k, c in d["creditos"].items()]
    return {
        "version": version,
        "versiones": [{"id": v["id"], "motivo": v["motivo"]} for v in d["versiones"]],
        "secciones": [{"clave": c, "titulo": t, "descripcion": desc} for c, t, desc in SECCIONES],
        "temas": [{"clave": k, "color": v[0]} for k, v in TEMAS.items()],
        "portadas": portadas,
        "textos": textos_por_defecto(d),
    }


EXTENSIONES_CODIGO = {".py", ".html", ".css", ".js", ".txt", ".md", ".json", ".woff2", ".png", ".jpg"}
CARPETAS_CODIGO = ["nucleo", "scripts", "vistas", "recursos", "tests"]


def zip_codigo():
    """Comprime el codigo fuente del proyecto (sin datos, modelos entrenados ni fotos de usuarios)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre in ("app.py", "requirements.txt", "README.md"):
            if (CODIGO / nombre).exists():
                zf.write(CODIGO / nombre, f"digitos_manuscritos/{nombre}")
        for carpeta in CARPETAS_CODIGO:
            for ruta in sorted((CODIGO / carpeta).rglob("*")):
                if ruta.is_file() and ruta.suffix in EXTENSIONES_CODIGO and "__pycache__" not in ruta.parts:
                    zf.write(ruta, f"digitos_manuscritos/{ruta.relative_to(CODIGO).as_posix()}")
    return buffer.getvalue()


def _validar(servicio, opciones):
    from .servicio import ErrorUsuario
    limpias = dict(opciones or {})
    versiones = {v["id"] for v in servicio.almacen.listar_versiones()}
    if limpias.get("version") and limpias["version"] not in versiones:
        raise ErrorUsuario("Esa versión no existe.")
    if limpias.get("tema") not in TEMAS:
        limpias["tema"] = "violeta"
    for campo, largo in (("titulo", 120), ("subtitulo", 180), ("autor", 80), ("curso", 100)):
        limpias[campo] = " ".join(str(limpias.get(campo) or "").split())[:largo]
    limpias["textos"] = {k: v[:8000] for k, v in (limpias.get("textos") or {}).items() if k in CLAVES_SECCIONES and isinstance(v, str)}
    propia = limpias.pop("portada_propia", None)
    if propia:
        coincidencia = re.match(r"data:image/(?:png|jpeg|webp);base64,(.+)$", propia, re.S)
        if not coincidencia or len(propia) > 14_000_000:
            raise ErrorUsuario("La imagen de la carátula no es válida o pesa demasiado (máximo unos 10 MB).")
        try:
            imagen = ImagenPIL.open(io.BytesIO(base64.b64decode(coincidencia.group(1))))
            imagen.load()
            imagen = imagen.convert("RGB")
            imagen.thumbnail((2400, 2400))
            salida = io.BytesIO()
            imagen.save(salida, "JPEG", quality=90)
        except Exception:
            raise ErrorUsuario("No se pudo leer la imagen de la carátula. Prueba con un JPG o PNG.")
        limpias["_portada_bytes"] = salida.getvalue()
        limpias["portada"] = "propia"
    elif limpias.get("portada") == "propia":
        limpias["portada"] = "cuaderno"
    lote = limpias.get("lote")
    if lote and (not re.fullmatch(r"lote_[\d_-]+b*", str(lote)) or not servicio.almacen.fotos_del_lote(lote)):
        limpias["lote"] = None
    try:
        limpias["fotos"] = [int(i) for i in (limpias.get("fotos") or [])][:20]
    except (TypeError, ValueError):
        limpias["fotos"] = []
    if not [s for s in limpias.get("secciones", CLAVES_SECCIONES) if s in CLAVES_SECCIONES]:
        raise ErrorUsuario("Elige al menos una sección para el informe.")
    return limpias


# ---------------------------------------------------------------- construccion
def generar_pdf(servicio, opciones):
    registrar_fuentes()
    opciones = _validar(servicio, opciones)
    version = opciones.get("version") or servicio.version_activa()
    avance.informar(0.01, "Reuniendo los datos de la versión")
    d = recopilar(servicio, version)
    e = estilos(opciones.get("tema", "violeta"))
    por_defecto = textos_por_defecto(d)
    textos = {**por_defecto, **{k: v for k, v in (opciones.get("textos") or {}).items() if isinstance(v, str) and v.strip()}}
    elegidas = [s for s in opciones.get("secciones", CLAVES_SECCIONES) if s in CLAVES_SECCIONES]
    titulos = {c: t for c, t, _ in SECCIONES}

    salida = io.BytesIO()
    doc = Documento(salida, pagesize=A4, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=2 * cm, bottomMargin=1.9 * cm,
                    title=opciones.get("titulo") or "Reconocimiento de dígitos manuscritos", author=opciones.get("autor") or "TecnoForms")
    marco_portada = Frame(MARGEN, 3.2 * cm, ANCHO_UTIL, ALTO_PAGINA - 3.2 * cm - 1 * cm, id="portada", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    marco = Frame(MARGEN, 1.9 * cm, ANCHO_UTIL, ALTO_PAGINA - 3.9 * cm, id="contenido", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="portada", frames=[marco_portada], onPage=portada(opciones, e, d)),
                          PageTemplate(id="contenido", frames=[marco], onPage=pie_y_cabecera(e, version))])

    historia = _titulo_portada(opciones, e) + [NextPageTemplate("contenido"), PageBreak()]
    indice = TableOfContents()
    indice.levelStyles = [ParagraphStyle("nivel0", parent=e["toc1"], leftIndent=0, rightIndent=0)]
    indice.dotsMinLevel = 0
    historia += [Paragraph("Índice", e["h1"]), indice, PageBreak()]

    constructores = {
        "caso": lambda: sec_caso(e, textos), "datos": lambda: sec_datos(e, d), "preprocesado": lambda: sec_preprocesado(e, d),
        "algoritmos": lambda: sec_algoritmos(e), "arquitectura": lambda: sec_arquitectura(e, d), "entrenamiento": lambda: sec_entrenamiento(e, d),
        "resultados": lambda: sec_resultados(e, d), "matrices": lambda: sec_matrices(e, d), "correcciones": lambda: sec_correcciones(e, d),
        "fotos": lambda: sec_fotos(e, d, servicio, opciones), "codigo": lambda: sec_codigo(e), "referencias": lambda: sec_referencias(e, d),
    }
    for i, clave in enumerate(elegidas):
        avance.informar(0.08 + 0.62 * i / len(elegidas), f"Sección {i + 1} de {len(elegidas)}: {titulos[clave]}")
        if i:
            historia.append(CondPageBreak(9 * cm))
        historia.append(encabezado(f"{i + 1}. {titulos[clave]}", e))
        historia += parrafos(textos.get(clave, ""), e)
        if clave in constructores:
            historia += constructores[clave]()
        historia.append(Spacer(1, 10))

    # El PDF se arma en dos pasadas (la segunda, con el indice ya numerado): cada una cuenta como media barra.
    armado = {"pasada": 1, "total": max(1, len(historia))}

    def al_armar(tipo, valor):
        if tipo == "PASS":
            armado["pasada"] = valor
        elif tipo == "SIZE_EST":
            armado["total"] = max(1, valor)
        elif tipo == "PROGRESS":
            hecho = (min(armado["pasada"], 2) - 1 + min(1, valor / armado["total"])) / 2
            avance.informar(0.7 + 0.3 * hecho, f"Armando las páginas del PDF, pasada {min(armado['pasada'], 2)} de 2")

    avance.informar(0.7, "Armando las páginas del PDF")
    doc.setProgressCallBack(al_armar)
    doc.multiBuild(historia)
    return salida.getvalue()
