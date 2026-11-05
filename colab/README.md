# Cifra en Google Colab (caso TecnoForms)

Cuaderno de Google Colab que hace lo mismo que la aplicación Cifra: prepara fotos de formularios escritos a mano, separa cada dígito
y lo clasifica con siete modelos (CNN, MLP, SVM, KNN, regresión logística, regresión lineal y K-Means), con el mismo código,
los mismos hiperparámetros y la misma semilla que la aplicación.

**El cuaderno ya viene ejecutado:** todas las tablas, métricas y gráficos están guardados dentro. Se puede abrir y revisar sin volver a ejecutarlo.

## Archivos

| Archivo | Qué es |
| --- | --- |
| `cifra_tecnoforms.ipynb` | El cuaderno (21 pasos; cada uno explica qué hace y cómo funciona) |
| `Informe_Cifra_TecnoForms.pdf` | Informe generado por el cuaderno: pasos, razonamiento, algoritmos, arquitectura y resultados |
| `resultados_colab/` | Los gráficos del cuaderno en PNG (los usa el informe) |

## Cómo abrirlo en Colab

1. Entra a https://colab.research.google.com e inicia sesión con tu cuenta de Google.
2. Pestaña **Subir** → elige `cifra_tecnoforms.ipynb`.
3. Para verlo: baja por el cuaderno; los resultados ya están debajo de cada celda.
4. Para repetirlo: menú **Entorno de ejecución → Ejecutar todas** (unos 15-25 minutos; con GPU, en *Entorno de ejecución → Cambiar tipo
   de entorno*, la CNN va más rápido). Al final se descarga el informe PDF.

## Probar con tus fotos (paso 18)

1. Ejecuta la celda del paso 18: aparece **Elegir archivos**. Puedes subir una o varias fotos de números o formularios
   (cualquier color de tinta, hoja lisa, cuadriculada o rayada). Los siete modelos las leen sin que digas el número.
2. Después, en el paso 18 b, escribe en el cuadro **NUMEROS** qué número dice cada foto, en orden y separados por comas
   (por ejemplo `58302, 7194`). Es opcional.
3. Sale, como en la aplicación, una tarjeta por dígito con **Real / Predijo** y **Correcto ✓** o **Error ✗** para cada modelo, y
   **cómo lo hizo cada modelo**: dónde miró la CNN, los vecinos que votaron en KNN, los vectores de soporte de la SVM, los grupos de
   K-Means y el aporte de cada píxel en las regresiones.

## Dónde se cumple cada requisito

| Requisito | Pasos del cuaderno |
| --- | --- |
| Selección de algoritmos y comparación con KNN, SVM y otros | 9, 15 |
| Preparación de imágenes: normalización, escala de grises y segmentación | 5, 6, 7, 8 |
| Red neuronal con capas convolucionales | 9, 10, 12 |
| Entrenamiento, validación cruzada y ajuste de hiperparámetros | 11, 12 |
| Test, precisión de la clasificación, interpretación y comparación | 13, 14, 15 |
| Matriz de confusión, precisión, recall y F1 (datos de internet) | 13, 14 |
| Código de regresión, K-Means, redes neuronales y preprocesado (datos ficticios) | 4, 5, 9, 17 |
| Predicciones frente a etiquetas reales (datos de internet) | 16 |
| Arquitectura: capas, nodos, activación y optimización | 10, 12 |
| Corregir a los modelos que fallan y práctica con imágenes | 19, 20 |
| Informe con pasos, razonamiento, algoritmos y resultados | 21 y el PDF |

Datos de internet: MNIST (se descarga solo, 11 MB). Datos ficticios: formularios y números armados en el cuaderno con dígitos de MNIST.
