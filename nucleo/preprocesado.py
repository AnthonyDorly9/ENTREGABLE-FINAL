import base64
import re

import cv2
import numpy as np

LADO_MAXIMO = 1000
# Las fotos se guardan con mas detalle que el que se usa para segmentar: sirve para hacer zoom en numeros chicos o lejanos.
LADO_GUARDADO = 2000
ALTURA_COMODA = 45
GIROS = (None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE)
# Con 0,08 ninguna foto derecha de las pruebas se volteo por error; mas bajo endereza mas fotos de cabeza pero voltea
# algunas derechas (el 6 y el 9, o el 0, 1 y 8, se ven igual de cabeza). Para esas queda el boton «Girar».
MARGEN_GIRO = 0.08


def decodificar_imagen(datos):
    imagen = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        raise ValueError("No se pudo leer la imagen")
    return limitar_tamano(imagen, LADO_GUARDADO)


def limitar_tamano(imagen, lado_maximo=LADO_MAXIMO):
    alto, ancho = imagen.shape[:2]
    escala = lado_maximo / max(alto, ancho)
    if escala < 1:
        imagen = cv2.resize(imagen, (round(ancho * escala), round(alto * escala)), interpolation=cv2.INTER_AREA)
    return imagen


def a_gris(imagen):
    """Pasa a gris. Si hay cuadricula de un color distinto a la tinta, usa el canal (azul, verde o rojo) donde la
    cuadricula casi desaparece y la tinta sigue oscura."""
    if imagen.ndim != 3:
        return imagen.copy()
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    binaria = binarizar(normalizar_iluminacion(gris))
    lineas = cv2.bitwise_and(cv2.bitwise_or(_lineas_largas(binaria, True), _lineas_largas(binaria, False)), binaria)
    if np.count_nonzero(lineas) < 50:
        return gris
    distancia = cv2.distanceTransform(binaria, cv2.DIST_L2, 3)
    radio = float(np.median(distancia[lineas > 0]))
    if not np.isfinite(radio) or radio > min(binaria.shape) / 8:
        return gris
    tinta = distancia > radio + 1.5
    cerca_de_tinta = cv2.dilate(tinta.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    linea_fina = (lineas > 0) & (distancia <= radio + 0.5) & ~cerca_de_tinta
    papel = binaria == 0
    if tinta.sum() < 20 or linea_fina.sum() < 50 or papel.sum() < 50:
        return gris
    candidatos = [gris] + [imagen[..., c] for c in range(3)]
    puntajes = []
    for canal in candidatos:
        fondo = float(np.median(canal[papel]))
        contraste_tinta = fondo - float(np.median(canal[tinta]))
        contraste_linea = fondo - float(np.median(canal[linea_fina]))
        puntajes.append(contraste_tinta - max(0.0, contraste_linea))
    mejor = int(np.argmax(puntajes))
    if mejor == 0 or puntajes[mejor] < puntajes[0] + 20:
        return gris
    return candidatos[mejor].copy()


def normalizar_iluminacion(gris):
    """Divide por el fondo estimado para quitar sombras y dejar el papel casi blanco."""
    if np.median(gris) < 110:
        gris = 255 - gris
    lado = max(15, min(gris.shape) // 12) | 1
    fondo = cv2.medianBlur(cv2.dilate(gris, np.ones((lado, lado), np.uint8)), lado * 2 + 1)
    normalizada = cv2.divide(gris, np.maximum(fondo, 1), scale=255)
    return cv2.normalize(normalizada, None, 0, 255, cv2.NORM_MINMAX)


def binarizar(normalizada):
    _, binaria = cv2.threshold(normalizada, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binaria


def _lineas_largas(binaria, horizontal):
    """Marca las rectas de una hoja cuadriculada o rayada: cruzan casi toda la foto o, si estan torcidas, salen por un borde."""
    alto, ancho = binaria.shape
    largo_total = ancho if horizontal else alto
    tramo = max(15, largo_total // 20)
    if horizontal:
        engrosada = cv2.dilate(binaria, np.ones((3, 1), np.uint8))
        tramos = cv2.morphologyEx(engrosada, cv2.MORPH_OPEN, np.ones((1, tramo), np.uint8))
    else:
        engrosada = cv2.dilate(binaria, np.ones((1, 3), np.uint8))
        tramos = cv2.morphologyEx(engrosada, cv2.MORPH_OPEN, np.ones((tramo, 1), np.uint8))
    cantidad, etiquetas, estadisticas, _ = cv2.connectedComponentsWithStats(tramos, connectivity=8)
    elegidas = []
    for i in range(1, cantidad):
        x, y, w, h, area = estadisticas[i]
        largo = w if horizontal else h
        toca_borde = x == 0 or y == 0 or x + w == ancho or y + h == alto
        if largo >= 0.8 * largo_total or (toca_borde and largo >= max(tramo, 0.1 * largo_total) and area <= 6 * largo):
            elegidas.append(i)
    return np.where(np.isin(etiquetas, elegidas), 255, 0).astype(np.uint8)


def quitar_cuadricula(binaria):
    """Borra las lineas finas de hojas cuadriculadas o rayadas sin tocar los trazos, mas gruesos, del digito."""
    lineas = cv2.bitwise_and(cv2.bitwise_or(_lineas_largas(binaria, True), _lineas_largas(binaria, False)), binaria)
    if not lineas.any():
        return binaria
    distancia = cv2.distanceTransform(binaria, cv2.DIST_L2, 3)
    radio = float(np.median(distancia[lineas > 0]))
    if not np.isfinite(radio) or radio > min(binaria.shape) / 8:
        return binaria
    lado = 2 * int(np.ceil(radio + 2)) + 1
    # Lo mas grueso que una linea es trazo; los cruces de la cuadricula tambien engordan, pero son puntos chicos.
    nucleos = (distancia > radio + 1.5).astype(np.uint8)
    cantidad, etiquetas, estadisticas, _ = cv2.connectedComponentsWithStats(nucleos, connectivity=8)
    grandes = [i for i in range(1, cantidad)
               if max(estadisticas[i, cv2.CC_STAT_WIDTH], estadisticas[i, cv2.CC_STAT_HEIGHT]) >= 2 * lado]
    nucleos = np.where(np.isin(etiquetas, grandes), 255, 0).astype(np.uint8)
    gruesos = cv2.dilate(nucleos, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (lado, lado)))
    quitar = cv2.bitwise_and(lineas, cv2.bitwise_not(gruesos))
    limpia = cv2.bitwise_and(binaria, cv2.bitwise_not(quitar))
    limpia = cv2.morphologyEx(limpia, cv2.MORPH_CLOSE, np.ones((5, 1), np.uint8))
    limpia = cv2.morphologyEx(limpia, cv2.MORPH_CLOSE, np.ones((1, 5), np.uint8))
    return cv2.morphologyEx(limpia, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def _unir(a, b):
    x = min(a[0], b[0])
    y = min(a[1], b[1])
    return (x, y, max(a[0] + a[2], b[0] + b[2]) - x, max(a[1] + a[3], b[1] + b[3]) - y)


def _solape_horizontal(a, b):
    izquierda = max(a[0], b[0])
    derecha = min(a[0] + a[2], b[0] + b[2])
    return max(0, derecha - izquierda) / max(1, min(a[2], b[2]))


def _unir_fragmentos(cajas):
    """Une trazos de un mismo digito (la barra del 5, las ramas del 4) que se superponen en horizontal."""
    cajas = list(cajas)
    cambio = True
    while cambio:
        cambio = False
        for i in range(len(cajas)):
            for j in range(i + 1, len(cajas)):
                if _solape_horizontal(cajas[i], cajas[j]) >= 0.5:
                    cajas[i] = _unir(cajas[i], cajas[j])
                    del cajas[j]
                    cambio = True
                    break
            if cambio:
                break
    return cajas


def ordenar_cajas(cajas):
    """Orden de lectura: por filas de arriba abajo y, dentro de cada fila, de izquierda a derecha."""
    if not cajas:
        return []
    altura = np.median([c[3] for c in cajas])
    filas = []
    for caja in sorted(cajas, key=lambda c: c[1] + c[3] / 2):
        centro = caja[1] + caja[3] / 2
        if filas and abs(centro - filas[-1]["centro"]) < 0.6 * altura:
            filas[-1]["cajas"].append(caja)
            filas[-1]["centro"] = np.mean([c[1] + c[3] / 2 for c in filas[-1]["cajas"]])
        else:
            filas.append({"centro": centro, "cajas": [caja]})
    return [c for fila in filas for c in sorted(fila["cajas"], key=lambda c: c[0])]


def detectar_cajas(binaria):
    alto, ancho = binaria.shape
    cantidad, _, estadisticas, _ = cv2.connectedComponentsWithStats(binaria, connectivity=8)
    # Minimo bajo para no perder numeros chicos o lejanos; las manchas sueltas caen luego por ser mucho mas bajas que los digitos.
    area_minima = max(12, 0.00003 * alto * ancho)
    candidatas = []
    for i in range(1, cantidad):
        x, y, w, h, area = estadisticas[i]
        if area < area_minima or h < 6:
            continue
        if w > 0.8 * ancho or h > 0.8 * alto or w > 5 * h:
            continue
        candidatas.append((int(x), int(y), int(w), int(h)))
    cajas = _unir_fragmentos(candidatas)
    if cajas:
        mayor = max(c[3] for c in cajas)
        cajas = [c for c in cajas if c[3] >= 0.3 * mayor]
    return ordenar_cajas(cajas)


def _mismo_renglon(a, b):
    return abs((a[1] + a[3] / 2) - (b[1] + b[3] / 2)) < 0.6 * max(a[3], b[3])


def _ajustar_caja(binaria, caja):
    x, y, w, h = caja
    ys, xs = np.nonzero(binaria[y : y + h, x : x + w])
    if len(xs) == 0:
        return caja
    return (x + int(xs.min()), y + int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))


def _dividir_caja(binaria, caja):
    """Parte una caja por el valle mas profundo de su proyeccion vertical (digitos pegados)."""
    x, y, w, h = caja
    proyeccion = (binaria[y : y + h, x : x + w] > 0).sum(axis=0).astype(np.float32)
    proyeccion = np.convolve(proyeccion, np.ones(3) / 3, mode="same")
    inicio, fin = int(w * 0.25), max(int(w * 0.75), int(w * 0.25) + 1)
    corte = inicio + int(np.argmin(proyeccion[inicio:fin]))
    izquierda = _ajustar_caja(binaria, (x, y, corte, h))
    derecha = _ajustar_caja(binaria, (x + corte, y, w - corte, h))
    return izquierda, derecha


def ajustar_cantidad(binaria, cajas, esperado):
    """Fusiona o divide cajas hasta llegar a la cantidad de digitos que escribio el usuario."""
    cajas = list(cajas)
    while len(cajas) > esperado and len(cajas) > 1:
        pares = [(i, cajas[i + 1][0] - (cajas[i][0] + cajas[i][2])) for i in range(len(cajas) - 1)
                 if _mismo_renglon(cajas[i], cajas[i + 1])]
        if not pares:
            break
        i = min(pares, key=lambda p: p[1])[0]
        cajas[i : i + 2] = [_unir(cajas[i], cajas[i + 1])]
    while len(cajas) < esperado:
        anchas = [(i, c[2] / max(1, c[3])) for i, c in enumerate(cajas)]
        if not anchas:
            break
        i, relacion = max(anchas, key=lambda a: a[1])
        if relacion < 0.6:
            break
        cajas[i : i + 1] = list(_dividir_caja(binaria, cajas[i]))
    return ordenar_cajas(cajas)


def caja_a_mnist(binaria, caja):
    """Recorta un digito y lo deja como MNIST: lado mayor de 20 px, centrado por centro de masa en 28x28."""
    x, y, w, h = caja
    recorte = binaria[y : y + h, x : x + w]
    escala = 20.0 / max(w, h)
    tamano = (max(1, round(w * escala)), max(1, round(h * escala)))
    reducido = cv2.resize(recorte, tamano, interpolation=cv2.INTER_AREA)
    lienzo = np.zeros((28, 28), np.uint8)
    y0, x0 = (28 - tamano[1]) // 2, (28 - tamano[0]) // 2
    lienzo[y0 : y0 + tamano[1], x0 : x0 + tamano[0]] = reducido
    momentos = cv2.moments(lienzo)
    if momentos["m00"] > 0:
        dx = 14 - momentos["m10"] / momentos["m00"]
        dy = 14 - momentos["m01"] / momentos["m00"]
        lienzo = cv2.warpAffine(lienzo, np.float32([[1, 0, dx], [0, 1, dy]]), (28, 28))
    return lienzo


def digitos_desde_cajas(binaria, cajas):
    recortes = [caja_a_mnist(binaria, c) for c in cajas]
    if not recortes:
        return np.zeros((0, 784), np.float32), []
    return np.stack(recortes).reshape(-1, 784).astype(np.float32) / 255.0, recortes


def dibujar_cajas(imagen, cajas):
    salida = imagen.copy() if imagen.ndim == 3 else cv2.cvtColor(imagen, cv2.COLOR_GRAY2BGR)
    for numero, (x, y, w, h) in enumerate(cajas, 1):
        cv2.rectangle(salida, (x, y), (x + w, y + h), (0, 160, 255), 2)
        cv2.putText(salida, str(numero), (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 160, 255), 2)
    return salida


def procesar_foto(imagen, esperado=None):
    """Ejecuta todo el preprocesado: gris, iluminacion, binarizacion, sin cuadricula y segmentacion en digitos de 28x28.

    Si los digitos salen chicos (numero lejano), recorta esa zona de la foto con todo su detalle y la procesa otra vez.
    """
    resultado = _procesar_una(imagen, esperado)
    cajas = resultado["cajas"]
    if not cajas:
        return resultado
    altura = float(np.median([c[3] for c in cajas]))
    if altura >= ALTURA_COMODA:
        return resultado
    alto, ancho = imagen.shape[:2]
    factor = max(alto, ancho) / max(resultado["pasos"]["original"].shape[:2])
    margen = 1.5 * altura
    x0 = max(0, int((min(c[0] for c in cajas) - margen) * factor))
    y0 = max(0, int((min(c[1] for c in cajas) - margen) * factor))
    x1 = min(ancho, int((max(c[0] + c[2] for c in cajas) + margen) * factor))
    y1 = min(alto, int((max(c[1] + c[3] for c in cajas) + margen) * factor))
    recorte = imagen[y0:y1, x0:x1]
    if min(recorte.shape[:2]) < 20:
        return resultado
    lado = max(recorte.shape[:2])
    objetivo = min(LADO_MAXIMO, lado * ALTURA_COMODA * 2 / altura / factor)
    if objetivo > lado:
        recorte = cv2.resize(recorte, None, fx=objetivo / lado, fy=objetivo / lado, interpolation=cv2.INTER_CUBIC)
    ampliado = _procesar_una(recorte, esperado)
    if not ampliado["cajas"] or (esperado and len(ampliado["cajas"]) != esperado and len(cajas) == esperado):
        return resultado
    return ampliado


def girar(imagen, giro):
    return imagen if giro is None else cv2.rotate(imagen, giro)


def orientar(imagen, confianza):
    """Busca si la foto esta girada (90, 180 o 270 grados) y devuelve (giro, imagen derecha).

    Primero elige la direccion: de lado, los digitos quedan uno encima de otro y se juntan en una sola caja, asi que
    la posicion correcta es la que separa mas digitos. Despues, entre derecha y de cabeza (o entre los dos lados),
    se queda con la que el modelo lee con mas seguridad. Solo gira si hay una razon clara, para no estropear las
    fotos que ya estan derechas. `confianza(digitos)` devuelve la probabilidad del digito elegido por el modelo.
    """
    cantidades, puntajes = [], []
    for giro in GIROS:
        resultado = procesar_foto(girar(imagen, giro))
        cantidades.append(len(resultado["cajas"]))
        if not resultado["cajas"]:
            puntajes.append(-np.inf)
            continue
        seguridad = np.log(np.clip(confianza(resultado["digitos"]), 1e-6, 1)) / 3
        acostados = np.mean([c[2] / max(1, c[3]) > 1.8 for c in resultado["cajas"]])
        puntajes.append(float(seguridad.mean()) - 0.3 * float(acostados))
    derecha, de_lado = max(cantidades[0], cantidades[2]), max(cantidades[1], cantidades[3])
    if de_lado > derecha:
        mejor = 1 if puntajes[1] >= puntajes[3] else 3
    elif derecha > de_lado or derecha == 0:
        mejor = 2 if puntajes[2] > puntajes[0] + MARGEN_GIRO else 0
    else:
        mejor = int(np.argmax(puntajes))
        if puntajes[mejor] <= puntajes[0] + MARGEN_GIRO:
            mejor = 0
    if mejor == 0:
        return None, imagen
    return GIROS[mejor], girar(imagen, GIROS[mejor])


def _procesar_una(imagen, esperado=None):
    imagen = limitar_tamano(imagen)
    gris = a_gris(imagen)
    iluminada = normalizar_iluminacion(gris)
    binaria = quitar_cuadricula(binarizar(iluminada))
    cajas = detectar_cajas(binaria)
    detectados = len(cajas)
    ajustado = False
    if esperado and detectados != esperado:
        cajas = ajustar_cantidad(binaria, cajas, esperado)
        ajustado = True
    digitos, recortes = digitos_desde_cajas(binaria, cajas)
    aviso = None
    if esperado and len(cajas) != esperado:
        aviso = f"Se encontraron {len(cajas)} dígitos y escribiste {esperado}. Revisa la foto o los recortes."
    elif ajustado:
        aviso = f"Se detectaron {detectados} dígitos y escribiste {esperado}; se ajustaron los recortes."
    return {
        "pasos": {
            "original": imagen,
            "gris": gris,
            "iluminacion": iluminada,
            "binaria": binaria,
            "segmentacion": dibujar_cajas(imagen, cajas),
        },
        "cajas": cajas,
        "binaria": binaria,
        "digitos": digitos,
        "recortes": recortes,
        "cantidad_detectada": detectados,
        "aviso": aviso,
    }


def dibujo_a_vector(data_uri):
    """Convierte un dibujo del lienzo (trazo blanco sobre negro, PNG en base64) en un digito MNIST de 784 valores."""
    coincidencia = re.match(r"data:image/(?:png|jpeg|webp);base64,(.+)$", data_uri or "", re.S)
    if not coincidencia:
        raise ValueError("No se pudo leer el dibujo.")
    try:
        datos = base64.b64decode(coincidencia.group(1), validate=False)
    except ValueError:
        raise ValueError("No se pudo leer el dibujo.")
    imagen = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_GRAYSCALE)
    if imagen is None:
        raise ValueError("No se pudo leer el dibujo.")
    binaria = np.where(imagen > 60, 255, 0).astype(np.uint8)
    puntos = cv2.findNonZero(binaria)
    if puntos is None or len(puntos) < 30:
        raise ValueError("Dibuja un dígito primero.")
    caja = cv2.boundingRect(puntos)
    return caja_a_mnist(binaria, caja).reshape(784).astype(np.float32) / 255.0


def a_data_uri(imagen):
    correcto, buffer = cv2.imencode(".png", imagen)
    if not correcto:
        raise ValueError("No se pudo codificar la imagen")
    return "data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")
