import time
import warnings

import joblib
import numpy as np
import torch
import torch.nn as nn
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC

from .configuracion import PARAMETROS_INICIALES, SEMILLA

MEDIA_MNIST = 0.1307
DESVIACION_MNIST = 0.3081


def _softmax(valores):
    valores = valores - valores.max(axis=1, keepdims=True)
    exponenciales = np.exp(valores)
    return exponenciales / exponenciales.sum(axis=1, keepdims=True)


class ModeloBase:
    clave = ""

    def __init__(self, **parametros):
        self.parametros = {**PARAMETROS_INICIALES[self.clave], **parametros}
        self.entrenado = False

    def entrenar(self, X, y, X_val=None, y_val=None, callback=None):
        raise NotImplementedError

    def probabilidades(self, X):
        raise NotImplementedError

    def predecir(self, X):
        return self.probabilidades(X).argmax(axis=1)

    def arquitectura(self):
        raise NotImplementedError

    def guardar(self, ruta):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, ruta, compress=3)

    @staticmethod
    def cargar(ruta):
        return joblib.load(ruta)


class RedNeuronal(ModeloBase):
    """Base de los modelos entrenados con PyTorch (CNN y MLP)."""

    def _construir(self):
        raise NotImplementedError

    def _preparar(self, lote):
        return lote

    def entrenar(self, X, y, X_val=None, y_val=None, callback=None):
        torch.manual_seed(SEMILLA)
        self.red = self._construir()
        historial = self._bucle(X, y, self.parametros["epocas"], self.parametros["tasa_aprendizaje"], X_val, y_val, callback)
        self.entrenado = True
        return historial

    def actualizar(self, X_nuevo, y_nuevo, X_memoria, y_memoria, fuerza=1.0):
        """Ajuste fino con las correcciones mezcladas con una muestra de memoria, a tasa baja para no olvidar."""
        torch.manual_seed(SEMILLA + 1)
        X = np.concatenate([X_nuevo, X_memoria])
        y = np.concatenate([y_nuevo, y_memoria])
        self._bucle(X, y, 4, self.parametros["tasa_aprendizaje"] * 0.12 * fuerza, tamano_lote=64)

    def _bucle(self, X, y, epocas, tasa, X_val=None, y_val=None, callback=None, tamano_lote=128):
        optimizador = torch.optim.Adam(self.red.parameters(), lr=tasa)
        perdida_fn = nn.CrossEntropyLoss()
        X_t, y_t = torch.from_numpy(X), torch.from_numpy(y)
        cantidad = len(y_t)
        historial = []
        for epoca in range(1, epocas + 1):
            inicio = time.perf_counter()
            self.red.train()
            orden = torch.randperm(cantidad)
            perdida_total, aciertos = 0.0, 0
            for i in range(0, cantidad, tamano_lote):
                indices = orden[i : i + tamano_lote]
                lote_x, lote_y = self._preparar(X_t[indices]), y_t[indices]
                optimizador.zero_grad()
                salida = self.red(lote_x)
                perdida = perdida_fn(salida, lote_y)
                perdida.backward()
                optimizador.step()
                perdida_total += perdida.item() * len(indices)
                aciertos += (salida.argmax(1) == lote_y).sum().item()
            registro = {
                "epoca": epoca,
                "perdida": perdida_total / cantidad,
                "exactitud": aciertos / cantidad,
                "segundos": time.perf_counter() - inicio,
            }
            if X_val is not None:
                registro["exactitud_val"] = float((self.predecir(X_val) == y_val).mean())
            historial.append(registro)
            if callback:
                callback(registro)
        self.entrenado = True
        return historial

    def probabilidades(self, X):
        self.red.eval()
        resultados = []
        with torch.no_grad():
            for i in range(0, len(X), 2048):
                lote = self._preparar(torch.from_numpy(X[i : i + 2048]))
                resultados.append(torch.softmax(self.red(lote), dim=1).numpy())
        return np.concatenate(resultados)

    def total_parametros(self):
        return int(sum(p.numel() for p in self.red.parameters()))


class ModeloCNN(RedNeuronal):
    clave = "cnn"

    def _preparar(self, lote):
        return ((lote - MEDIA_MNIST) / DESVIACION_MNIST).view(-1, 1, 28, 28)

    def _construir(self):
        f = self.parametros["filtros"]
        p = self.parametros["dropout"]
        return nn.Sequential(
            nn.Conv2d(1, f, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(f, 2 * f, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Flatten(),
            nn.Dropout(p),
            nn.Linear(2 * f * 7 * 7, 64),
            nn.ReLU(),
            nn.Dropout(p),
            nn.Linear(64, 10),
        )

    def arquitectura(self):
        f = self.parametros["filtros"]
        p = self.parametros["dropout"]
        capas = [
            ("Entrada", "imagen 28x28, 1 canal", "-", 0),
            ("Conv2D 3x3", f"{f} filtros, relleno 1 -> 28x28x{f}", "ReLU", 9 * f + f),
            ("MaxPool 2x2", f"14x14x{f}", "-", 0),
            ("Conv2D 3x3", f"{2 * f} filtros, relleno 1 -> 14x14x{2 * f}", "ReLU", 9 * f * 2 * f + 2 * f),
            ("MaxPool 2x2", f"7x7x{2 * f}", "-", 0),
            ("Aplanar", f"{2 * f * 49} valores", "-", 0),
            ("Dropout", f"p = {str(p).replace('.', ',')}", "-", 0),
            ("Densa", "64 neuronas", "ReLU", 2 * f * 49 * 64 + 64),
            ("Dropout", f"p = {str(p).replace('.', ',')}", "-", 0),
            ("Densa (salida)", "10 neuronas (dígitos 0-9)", "Softmax", 64 * 10 + 10),
        ]
        return _descripcion_arquitectura(capas, "Adam", self.parametros["tasa_aprendizaje"], "Entropía cruzada")


class ModeloMLP(RedNeuronal):
    clave = "mlp"

    def _preparar(self, lote):
        return (lote - MEDIA_MNIST) / DESVIACION_MNIST

    def _construir(self):
        n = self.parametros["neuronas"]
        p = self.parametros["dropout"]
        return nn.Sequential(
            nn.Linear(784, n),
            nn.ReLU(),
            nn.Dropout(p),
            nn.Linear(n, n // 2),
            nn.ReLU(),
            nn.Linear(n // 2, 10),
        )

    def arquitectura(self):
        n = self.parametros["neuronas"]
        p = self.parametros["dropout"]
        capas = [
            ("Entrada", "784 valores (28x28 aplanado)", "-", 0),
            ("Densa", f"{n} neuronas", "ReLU", 784 * n + n),
            ("Dropout", f"p = {str(p).replace('.', ',')}", "-", 0),
            ("Densa", f"{n // 2} neuronas", "ReLU", n * (n // 2) + n // 2),
            ("Densa (salida)", "10 neuronas (dígitos 0-9)", "Softmax", (n // 2) * 10 + 10),
        ]
        return _descripcion_arquitectura(capas, "Adam", self.parametros["tasa_aprendizaje"], "Entropía cruzada")


def _descripcion_arquitectura(capas, optimizador, tasa, perdida):
    return {
        "capas": [
            {"capa": nombre, "forma": forma, "activacion": activacion, "parametros": parametros}
            for nombre, forma, activacion, parametros in capas
        ],
        "parametros_totales": sum(c[3] for c in capas),
        "optimizador": optimizador,
        "tasa_aprendizaje": tasa,
        "funcion_perdida": perdida,
    }


class ModeloClasico(ModeloBase):
    """Base de los modelos de scikit-learn, que trabajan sobre componentes PCA."""

    usa_pca = True

    def _ajustar_pca(self, X):
        self.pca = PCA(n_components=self.parametros["componentes"], random_state=SEMILLA).fit(X)
        return self.pca.transform(X)

    def _proyectar(self, X):
        return self.pca.transform(X)

    def entrenar(self, X, y, X_val=None, y_val=None, callback=None):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._ajustar(X, y)
        self.entrenado = True
        return []

    def _ajustar(self, X, y):
        raise NotImplementedError


class ModeloKNN(ModeloClasico):
    clave = "knn"

    def _ajustar(self, X, y):
        Z = self._ajustar_pca(X)
        self.modelo = KNeighborsClassifier(
            n_neighbors=self.parametros["k"], weights="distance", n_jobs=-1
        ).fit(Z, y)

    def probabilidades(self, X):
        return self.modelo.predict_proba(self._proyectar(X))

    def actualizar(self, X_nuevo, y_nuevo, X_memoria, y_memoria, fuerza=1.0):
        """Aprender es memorizar las muestras nuevas junto a las que ya tenia."""
        anterior = self.modelo
        Z = np.concatenate([anterior._fit_X, self._proyectar(X_nuevo)])
        etiquetas = np.concatenate([anterior.classes_[anterior._y], y_nuevo])
        self.modelo = KNeighborsClassifier(n_neighbors=self.parametros["k"], weights="distance", n_jobs=-1).fit(Z, etiquetas)

    def arquitectura(self):
        return {
            "tipo": "KNN",
            "parametros": {"vecinos (k)": self.parametros["k"], "ponderación": "distancia", "componentes PCA": self.parametros["componentes"]},
            "muestras_memorizadas": int(self.modelo._fit_X.shape[0]),
        }


class ModeloSVM(ModeloClasico):
    clave = "svm"

    def _ajustar(self, X, y):
        Z = self._ajustar_pca(X)
        self.modelo = SVC(
            kernel="rbf", C=self.parametros["C"], gamma=self.parametros["gamma"],
            decision_function_shape="ovr",
        ).fit(Z, y)

    def probabilidades(self, X):
        return _softmax(2.0 * self.modelo.decision_function(self._proyectar(X)))

    def actualizar(self, X_nuevo, y_nuevo, X_memoria, y_memoria, fuerza=1.0):
        """Reentrena con los vectores de soporte anteriores (que definen la frontera), la memoria y lo nuevo."""
        anterior = self.modelo
        Z = np.concatenate([anterior.support_vectors_, self._proyectar(X_memoria), self._proyectar(X_nuevo)])
        etiquetas = np.concatenate([np.repeat(anterior.classes_, anterior.n_support_), y_memoria, y_nuevo])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.modelo = SVC(kernel="rbf", C=self.parametros["C"], gamma=self.parametros["gamma"],
                              decision_function_shape="ovr").fit(Z, etiquetas)

    def arquitectura(self):
        return {
            "tipo": "SVM",
            "parametros": {"núcleo": "RBF", "C": self.parametros["C"], "gamma": self.parametros["gamma"], "componentes PCA": self.parametros["componentes"]},
            "vectores_soporte": int(self.modelo.n_support_.sum()),
        }


class ModeloRegresion(ModeloClasico):
    clave = "regresion"

    def _ajustar(self, X, y):
        self.modelo = LogisticRegression(
            C=self.parametros["C"], max_iter=self.parametros["iteraciones"]
        ).fit(X, y)

    def _proyectar(self, X):
        return X

    def probabilidades(self, X):
        return self.modelo.predict_proba(X)

    def actualizar(self, X_nuevo, y_nuevo, X_memoria, y_memoria, fuerza=1.0):
        """Continua la optimizacion desde los pesos actuales (warm start) con lo nuevo y la memoria."""
        anterior = self.modelo
        continuado = LogisticRegression(C=self.parametros["C"], max_iter=self.parametros["iteraciones"], warm_start=True)
        continuado.coef_ = anterior.coef_.copy()
        continuado.intercept_ = anterior.intercept_.copy()
        continuado.classes_ = anterior.classes_
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            continuado.fit(np.concatenate([X_nuevo, X_memoria]), np.concatenate([y_nuevo, y_memoria]))
        self.modelo = continuado

    def arquitectura(self):
        return {
            "tipo": "Regresión logística multinomial",
            "parametros": {"C (regularización)": self.parametros["C"], "iteraciones máximas": self.parametros["iteraciones"], "solucionador": "lbfgs"},
            "parametros_totales": int(self.modelo.coef_.size + self.modelo.intercept_.size),
        }


class ModeloRegresionLineal(ModeloClasico):
    """Regresion lineal por minimos cuadrados con una salida por digito (objetivo 1 para el digito correcto y 0 para el resto).

    Guarda XtX y XtY, asi que aprender de correcciones es sumar estadisticas: exacto y sin olvidar lo anterior.
    """

    clave = "regresion_lineal"
    TEMPERATURA = 6.0

    @staticmethod
    def _con_sesgo(X):
        return np.hstack([X.astype(np.float64), np.ones((len(X), 1))])

    def _proyectar(self, X):
        return X

    def _resolver(self):
        regularizacion = self.parametros["alpha"] * np.eye(self.A.shape[0])
        regularizacion[-1, -1] = 0.0
        self.pesos = np.linalg.solve(self.A + regularizacion, self.B)

    def _ajustar(self, X, y):
        X1 = self._con_sesgo(X)
        self.A = X1.T @ X1
        self.B = X1.T @ np.eye(10)[y]
        self._resolver()

    def actualizar(self, X_nuevo, y_nuevo, X_memoria, y_memoria, fuerza=1.0):
        X1 = self._con_sesgo(X_nuevo)
        self.A = self.A + fuerza * (X1.T @ X1)
        self.B = self.B + fuerza * (X1.T @ np.eye(10)[y_nuevo])
        self._resolver()

    def probabilidades(self, X):
        return _softmax(self.TEMPERATURA * (self._con_sesgo(X) @ self.pesos))

    def arquitectura(self):
        return {
            "tipo": "Regresión lineal por mínimos cuadrados (un peso por píxel y por dígito)",
            "parametros": {"alpha (regularización)": self.parametros["alpha"], "método": "ecuación normal", "salida": "puntaje por dígito; gana el mayor"},
            "parametros_totales": int(self.pesos.size),
        }


class ModeloKMeans(ModeloClasico):
    clave = "kmeans"

    def _ajustar(self, X, y):
        Z = self._ajustar_pca(X)
        self.modelo = KMeans(
            n_clusters=self.parametros["clusteres"], n_init=3, random_state=SEMILLA
        ).fit(Z)
        self.etiqueta_cluster = np.array(
            [np.bincount(y[self.modelo.labels_ == c], minlength=10).argmax() if (self.modelo.labels_ == c).any() else 0
             for c in range(self.parametros["clusteres"])]
        )

    def probabilidades(self, X):
        distancias = self.modelo.transform(self._proyectar(X))
        minimas = np.full((len(distancias), 10), 1e6)
        for digito in range(10):
            columnas = np.flatnonzero(self.etiqueta_cluster == digito)
            if len(columnas):
                minimas[:, digito] = distancias[:, columnas].min(axis=1)
        return _softmax(-(minimas - minimas.min(axis=1, keepdims=True)))

    def actualizar(self, X_nuevo, y_nuevo, X_memoria, y_memoria, fuerza=1.0):
        """Los digitos mal asignados forman grupos nuevos, etiquetados con el digito correcto."""
        Z = self._proyectar(X_nuevo)
        cercano = self.modelo.predict(Z)
        equivocado = self.etiqueta_cluster[cercano] != y_nuevo
        centros, etiquetas = [], []
        for etiqueta in np.unique(y_nuevo[equivocado]):
            for cluster in np.unique(cercano[equivocado & (y_nuevo == etiqueta)]):
                marca = equivocado & (y_nuevo == etiqueta) & (cercano == cluster)
                centros.append(Z[marca].mean(axis=0))
                etiquetas.append(etiqueta)
        if centros:
            existentes = self.modelo.cluster_centers_
            self.modelo.cluster_centers_ = np.vstack([existentes, np.asarray(centros, dtype=existentes.dtype)])
            self.etiqueta_cluster = np.concatenate([self.etiqueta_cluster, etiquetas])

    def arquitectura(self):
        return {
            "tipo": "K-Means (no supervisado) + etiqueta por mayoría",
            "parametros": {"clústeres": self.parametros["clusteres"], "componentes PCA": self.parametros["componentes"], "inicializaciones": 3},
        }


CLASES_MODELOS = {
    "cnn": ModeloCNN,
    "mlp": ModeloMLP,
    "svm": ModeloSVM,
    "knn": ModeloKNN,
    "regresion": ModeloRegresion,
    "regresion_lineal": ModeloRegresionLineal,
    "kmeans": ModeloKMeans,
}


def crear_modelo(clave, **parametros):
    return CLASES_MODELOS[clave](**parametros)
