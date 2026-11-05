"""Descarga MNIST (70 000 digitos manuscritos) a datos/mnist/mnist.npz si todavia no existe."""
import urllib.request

from nucleo.configuracion import CARPETA_DATOS

URL = "https://storage.googleapis.com/tensorflow/tf-keras-datasets/mnist.npz"


def main():
    destino = CARPETA_DATOS / "mnist" / "mnist.npz"
    if destino.exists():
        print(f"Ya existe: {destino}")
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    print("Descargando MNIST (11 MB)...")
    urllib.request.urlretrieve(URL, destino)
    print(f"Listo: {destino}")


if __name__ == "__main__":
    main()
