# Trazo: lector de dígitos manuscritos para formularios

Aplicación web que lee los dígitos escritos a mano en fotos de formularios (caso práctico «TecnoForms», trabajo final PIAD-427 de SENATI)
y compara siete modelos de aprendizaje automático: red convolucional (CNN), red densa (MLP), SVM, KNN, regresión logística,
regresión lineal y K-Means.

> **Créditos y origen.** Este proyecto parte del código del proyecto *MANOESCRITA / Cifra* (repositorio `nasa-cell/MANOESCRITA`),
> usado con autorización de su autor y adaptado para este trabajo: nuevo nombre e interfaz (barra superior, página principal centrada en
> leer un formulario), se quitó la conexión por celular, el túnel, la «batalla» de modelos y el instalador de Windows, y se reorganizaron
> las carpetas. El motor de lectura y los modelos conservan la lógica del proyecto base.

## Cómo ponerla en marcha

```
pip install -r requirements.txt
python app.py
```

Después abre http://127.0.0.1:5000 en el navegador (en Windows también sirve `iniciar_aplicacion.bat`).
Los modelos entrenados (`modelos/v1/`) y el MNIST (`datos/mnist/`) ya vienen en la carpeta. Para volver a entrenarlos:

```
python -m scripts.entrenar_inicial        # entrena los siete modelos, valida y guarda la versión v1
python -m scripts.generar_datos_ficticios # formularios y números de prueba en datos/ficticios/
python -m scripts.evaluar_preprocesado    # calidad de la segmentación con datos ficticios
python -m unittest discover -s tests      # pruebas automáticas
```

## Secciones

| Sección | Qué hace |
| --- | --- |
| Leer formulario | Página principal: sube la foto de un formulario, se separan los dígitos, se leen con los siete modelos y se corrigen los que fallen. |
| Resultados | Métricas, matrices de confusión, predicciones frente a la etiqueta real, curvas y validación cruzada. |
| Entrenar | Entrena un modelo con los hiperparámetros que elijas. |
| Probar con ejemplos | Formularios y números ficticios con sus etiquetas reales. |
| Antes y después | Compara versiones de los modelos con la misma tanda de fotos. |
| Por dentro | Cómo funciona una neurona, la convolución y la red. |
| Informe | Genera el informe en PDF con los resultados. |
| Resumen | Pasos del proceso y exactitud de cada modelo. |

## Estructura

```
app.py          Rutas de la aplicación (Flask)
nucleo/         Datos, preprocesado, modelos, validación, evaluación, correcciones, gráficos e informe
scripts/        Entrenamiento, datos ficticios y descarga de MNIST
vistas/         Páginas HTML
recursos/       CSS, JavaScript, tipografías e imágenes
tests/          Pruebas automáticas
datos/          MNIST, datos ficticios y base de datos (se crea al usar la aplicación)
modelos/vN/     Modelos entrenados de cada versión
resultados/vN/  Métricas, curvas, validación cruzada y gráficos de cada versión
colab/          Cuaderno e informe con los resultados
```

## Resultados (conjunto de prueba de MNIST, 10 000 dígitos)

CNN 98,69 % · SVM 97,39 % · MLP 96,85 % · KNN 96,78 % · regresión logística 92,33 % · regresión lineal 86,25 % · K-Means 85,04 %.

## Datos

- MNIST: LeCun, Bottou, Bengio y Haffner (1998). Datos de internet.
- Los formularios ficticios se generan con dígitos de MNIST y no contienen datos de personas.
