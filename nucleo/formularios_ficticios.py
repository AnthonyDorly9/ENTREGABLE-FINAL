"""Generador de datos ficticios: numeros y formularios "escritos a mano" armados con digitos de MNIST
y degradados para parecer fotos (sombras, ruido, desenfoque, inclinacion)."""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .configuracion import SEMILLA

TIPOS_FORMULARIO = {
    "inscripcion": ("Formulario de inscripción", [
        ("Código de estudiante", 6), ("Edad", 2), ("Teléfono", 9), ("Año de ingreso", 4)]),
    "pago": ("Comprobante de pago", [
        ("N.º de factura", 6), ("Monto", 4), ("Cuotas", 1), ("Referencia", 8)]),
    "solicitud": ("Solicitud de servicio", [
        ("N.º de solicitud", 5), ("Documento de identidad", 8), ("Cantidad", 2), ("Teléfono", 9)]),
}

ANCHO_FORMULARIO = 1000
ALTO_FILA = 130
ALTO_ENCABEZADO = 200

# Colores en BGR (orden de OpenCV).
COLORES_CUADRICULA = [
    (60, 60, 60), (140, 140, 140), (230, 180, 130), (160, 80, 20), (230, 200, 90), (170, 220, 160),
    (60, 130, 40), (60, 60, 200), (190, 150, 240), (40, 140, 240), (150, 60, 120), (40, 80, 120),
]
COLORES_TINTA = [(30, 30, 30), (150, 50, 20), (40, 40, 200), (40, 120, 20), (110, 110, 110), (130, 40, 110)]


def _fuente(tamano):
    for nombre in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            continue
    return ImageFont.load_default(tamano)


def _recortar_tinta(capa, umbral=0.05):
    ys, xs = np.nonzero(capa > umbral)
    return capa[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


class GeneradorDigitos:
    def __init__(self, X, y, semilla=SEMILLA):
        self.imagenes = X.reshape(-1, 28, 28)
        self.indices = {d: np.flatnonzero(y == d) for d in range(10)}
        self.azar = np.random.default_rng(semilla)

    def _muestra(self, digito):
        imagen = self.imagenes[self.azar.choice(self.indices[digito])]
        return _recortar_tinta(imagen, 0.2)

    def capa_tinta(self, texto, altura=80, separacion=(6, 26), toque=0.0):
        azar = self.azar
        piezas = []
        for caracter in texto:
            base = self._muestra(int(caracter))
            alto = max(12, round(altura * azar.uniform(0.9, 1.1)))
            ancho = max(3, round(base.shape[1] * alto / base.shape[0]))
            pieza = np.clip(cv2.resize(base, (ancho, alto), interpolation=cv2.INTER_CUBIC), 0, 1)
            if alto >= 50 and azar.random() < 0.25:
                pieza = cv2.dilate(pieza, np.ones((3, 3), np.uint8))
            piezas.append(pieza)
        margen = int(altura * 0.45) + 10
        huecos = [-int(azar.integers(2, 6)) if azar.random() < toque else int(azar.integers(*separacion))
                  for _ in piezas[:-1]]
        ancho_total = sum(p.shape[1] for p in piezas) + sum(huecos) + 2 * margen
        alto_total = int(altura * 1.4) + 2 * margen
        lienzo = np.zeros((alto_total, ancho_total), np.float32)
        cursor = margen
        for i, pieza in enumerate(piezas):
            y = int((alto_total - pieza.shape[0]) / 2 + azar.uniform(-0.08, 0.08) * altura)
            zona = lienzo[y : y + pieza.shape[0], cursor : cursor + pieza.shape[1]]
            np.maximum(zona, pieza, out=zona)
            cursor += pieza.shape[1] + (huecos[i] if i < len(huecos) else 0)
        centro = (ancho_total / 2, alto_total / 2)
        inclinacion = azar.uniform(-0.2, 0.2)
        lienzo = cv2.warpAffine(lienzo, np.float32([[1, inclinacion, -inclinacion * centro[1]], [0, 1, 0]]),
                                (ancho_total, alto_total))
        rotacion = cv2.getRotationMatrix2D(centro, azar.uniform(-3, 3), 1.0)
        return cv2.warpAffine(lienzo, rotacion, (ancho_total, alto_total))

    def _efecto_foto(self, gris, dificultad):
        azar = self.azar
        alto, ancho = gris.shape
        yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float32)
        angulo = azar.uniform(0, 2 * np.pi)
        gradiente = (np.cos(angulo) * (xx / ancho - 0.5) + np.sin(angulo) * (yy / alto - 0.5))
        gris = gris * (1 + azar.uniform(0.04, 0.22) * dificultad * 2 * gradiente)
        gris = gris + azar.normal(0, 1 + 7 * dificultad, gris.shape)
        sigma = azar.uniform(0, 1.4 * dificultad + 0.3)
        if sigma > 0.3:
            gris = cv2.GaussianBlur(gris, (0, 0), sigma)
        gris = np.clip(gris, 0, 255)
        tinte = np.array([1.0, azar.uniform(0.97, 1.0), azar.uniform(0.93, 1.0)], np.float32)
        return np.clip(gris[..., None] * tinte, 0, 255).astype(np.uint8)

    def foto_numero(self, texto, dificultad=0.5, altura=None, toque=0.0):
        azar = self.azar
        tinta = self.capa_tinta(texto, altura or int(azar.integers(60, 110)), toque=toque)
        papel, color_tinta = azar.uniform(205, 248), azar.uniform(15, 80)
        return self._efecto_foto(papel - tinta * (papel - color_tinta), dificultad)

    def foto_cuadriculada(self, texto, dificultad=0.5, color_linea=None, color_tinta=None):
        """Número escrito en hoja cuadriculada o rayada: color de cuadrícula y de tinta, tamaño del cuadro,
        grosor e inclinación al azar (los colores se pueden fijar)."""
        azar = self.azar
        tinta = self.capa_tinta(texto, int(azar.integers(60, 110)), toque=0.1 if dificultad >= 0.5 else 0.0)
        alto, ancho = tinta.shape
        paso = int(azar.integers(18, 34))
        grosor = 2 if azar.random() < 0.3 + 0.4 * dificultad else 1
        grande = int(np.hypot(alto, ancho)) + 2 * paso
        papel = np.full((grande, grande, 3), azar.uniform(215, 248), np.float32)
        color_linea = tuple(float(c) for c in (color_linea or COLORES_CUADRICULA[int(azar.integers(len(COLORES_CUADRICULA)))]))
        rayada = azar.random() < 0.25
        for v in range(int(azar.integers(0, paso)), grande, paso):
            cv2.line(papel, (0, v), (grande, v), color_linea, grosor)
            if not rayada:
                cv2.line(papel, (v, 0), (v, grande), color_linea, grosor)
        angulo = azar.uniform(-1, 1) * (1 + 4 * dificultad)
        papel = cv2.warpAffine(papel, cv2.getRotationMatrix2D((grande / 2, grande / 2), angulo, 1.0), (grande, grande),
                               borderMode=cv2.BORDER_REFLECT)
        y0, x0 = (grande - alto) // 2, (grande - ancho) // 2
        papel = papel[y0 : y0 + alto, x0 : x0 + ancho]
        color_tinta = np.array(color_tinta or COLORES_TINTA[int(azar.integers(len(COLORES_TINTA)))], np.float32)
        imagen = papel * (1 - tinta[..., None]) + color_tinta * tinta[..., None]
        imagen = imagen + azar.normal(0, 1 + 5 * dificultad, imagen.shape)
        imagen = cv2.GaussianBlur(imagen, (0, 0), azar.uniform(0.3, 0.5 + dificultad))
        return np.clip(imagen, 0, 255).astype(np.uint8)

    def numero_aleatorio(self, largo):
        return "".join(str(d) for d in self.azar.integers(0, 10, size=largo))

    def formulario(self, tipo, dificultad=0.4):
        titulo, campos_definidos = TIPOS_FORMULARIO[tipo]
        azar = self.azar
        alto = ALTO_ENCABEZADO + ALTO_FILA * len(campos_definidos)
        hoja = Image.new("L", (ANCHO_FORMULARIO, alto), 255)
        pincel = ImageDraw.Draw(hoja)
        pincel.text((60, 40), titulo, fill=20, font=_fuente(38))
        pincel.text((60, 100), "Documento ficticio de prueba", fill=110, font=_fuente(22))
        pincel.line([(60, 160), (ANCHO_FORMULARIO - 60, 160)], fill=150, width=2)
        campos, cajas = [], []
        for i, (etiqueta, largo) in enumerate(campos_definidos):
            y = ALTO_ENCABEZADO + ALTO_FILA * i
            caja = (380, y, 560, 90)
            pincel.text((60, y + 28), etiqueta, fill=40, font=_fuente(26))
            pincel.rectangle([caja[0], caja[1], caja[0] + caja[2], caja[1] + caja[3]], outline=90, width=3)
            campos.append({"etiqueta": etiqueta, "valor": self.numero_aleatorio(largo), "caja": caja})
            cajas.append(caja)
        base = np.array(hoja, np.float32)
        tinta = np.zeros_like(base)
        for campo in campos:
            x, y, w, h = campo["caja"]
            capa = _recortar_tinta(self.capa_tinta(campo["valor"], altura=54, separacion=(8, 20)))
            escala = min(1.0, (w - 30) / capa.shape[1], (h - 16) / capa.shape[0])
            if escala < 1:
                capa = cv2.resize(capa, (round(capa.shape[1] * escala), round(capa.shape[0] * escala)),
                                  interpolation=cv2.INTER_AREA)
            y0 = y + (h - capa.shape[0]) // 2
            x0 = x + 15
            tinta[y0 : y0 + capa.shape[0], x0 : x0 + capa.shape[1]] = np.maximum(
                tinta[y0 : y0 + capa.shape[0], x0 : x0 + capa.shape[1]], capa)
        color_tinta = azar.uniform(20, 70)
        gris = base * (1 - tinta) + tinta * color_tinta
        return self._efecto_foto(gris, dificultad), campos
