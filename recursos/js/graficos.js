(function () {
  const { el, api, avisar, porcentaje } = App;
  const modelos = App.modelos();
  const nombre = Object.fromEntries(modelos.map((m) => [m.clave, m.nombre]));
  const $ = (id) => document.getElementById(id);
  let datos = null;
  let modeloMatriz = "cnn";
  let modeloMapa = "cnn";
  let modeloPredicciones = "cnn";

  const METRICAS = [
    { nombre: "Exactitud", ayuda: "De cada 100 dígitos, cuántos acertó." },
    { nombre: "Precisión", ayuda: "Cuando el modelo dice «7», cuántas veces era de verdad un 7." },
    { nombre: "Recall", ayuda: "De todos los 7 reales, cuántos logró encontrar." },
    { nombre: "F1", ayuda: "Un solo número que equilibra precisión y recall." },
  ];
  const pct = (v, d) => porcentaje(v, d === undefined ? 1 : d);
  const coma = (v, d) => Number(v).toFixed(d).replace(".", ",");
  const ordenModelos = () => modelos.map((m) => m.clave);

  function poner(idImg, idDescarga, url, nombreArchivo) {
    const img = $(idImg);
    img.classList.remove("lista");
    img.onload = () => img.classList.add("lista");
    img.onerror = () => { img.alt = "No se pudo cargar la imagen. Pulsa «Actualizar gráficos»."; img.classList.add("lista"); };
    img.src = url;
    const enlace = $(idDescarga);
    enlace.href = url;
    if (nombreArchivo) enlace.setAttribute("download", nombreArchivo);
  }

  function selectorModelos(contenedor, actual, alElegir) {
    $(contenedor).replaceChildren(...modelos.map((m) => {
      const marcado = m.clave === actual();
      return el("button", { type: "button", role: "radio", "aria-checked": String(marcado),
        clase: "chip-modelo" + (marcado ? " elegido" : ""), estilo: { "--color": m.color }, texto: m.nombre,
        en: { click: () => alElegir(m.clave) } });
    }));
  }

  function pintarMetricas() {
    poner("img-metricas", "dl-metricas", datos.imagenes.metricas, `metricas_${datos.version}.png`);
    $("glosario").replaceChildren(...METRICAS.map((m) => el("div", { clase: "glosario-item" }, el("dt", { texto: m.nombre }), el("dd", { texto: m.ayuda }))));
    $("tabla-metricas").replaceChildren(
      el("caption", { clase: "solo-lectores", texto: "Métricas de cada modelo en el conjunto de prueba de MNIST" }),
      el("thead", null, el("tr", null, ["Modelo", "Exactitud", "Precisión", "Recall", "F1", "ms por dígito", "Dígitos con que se entrenó", "Segundos de entrenamiento"]
        .map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", null, ordenModelos().map((c) => {
        const m = datos.modelos[c];
        return el("tr", { estilo: { "--color": modelos.find((x) => x.clave === c).color } },
          el("th", { scope: "row" }, el("span", { clase: "modelo-nombre" }, el("span", { clase: "punto" }), nombre[c])),
          el("td", { texto: pct(m.exactitud, 2) }), el("td", { texto: pct(m.precision_macro, 2) }),
          el("td", { texto: pct(m.recall_macro, 2) }), el("td", { texto: pct(m.f1_macro, 2) }),
          el("td", { texto: coma(m.ms_por_muestra, 3) }),
          el("td", { texto: m.muestras_entrenamiento ? m.muestras_entrenamiento.toLocaleString("es") : "—" }),
          el("td", { texto: m.segundos_entrenamiento ? coma(m.segundos_entrenamiento, 1) : "—" }));
      })));
  }

  function pintarMatriz() {
    selectorModelos("modelo-matriz", () => modeloMatriz, (c) => { modeloMatriz = c; $("galeria-casilla").replaceChildren(); pintarMatriz(); });
    poner("img-matriz", "dl-matriz", datos.imagenes.matriz[modeloMatriz], `matriz_${modeloMatriz}_${datos.version}.png`);
    const N = datos.modelos[modeloMatriz].matriz_confusion;
    let par = { real: 0, predicho: 0, n: 0 };
    N.forEach((fila, i) => fila.forEach((v, j) => { if (i !== j && v > par.n) par = { real: i, predicho: j, n: v }; }));
    $("resumen-matriz").textContent = par.n
      ? `El error más frecuente de ${nombre[modeloMatriz]}: leyó ${par.predicho} cuando era ${par.real} (${par.n} ${par.n === 1 ? "vez" : "veces"}).`
      : `${nombre[modeloMatriz]} no cometió errores en la prueba.`;
    $("casilla-real").value = String(par.real);
    $("casilla-predicho").value = String(par.predicho);
  }

  async function verCasilla() {
    const real = Number($("casilla-real").value), predicho = Number($("casilla-predicho").value);
    const galeria = $("galeria-casilla");
    galeria.replaceChildren(el("p", { clase: "vacio" }, el("span", { clase: "cargando" }), " Buscando ejemplos…"));
    try {
      const r = await App.lento(`/api/matriz/imagenes?version=${datos.version}&modelo=${modeloMatriz}&real=${real}&predicho=${predicho}`);
      if (r.acierto) {
        galeria.replaceChildren(el("p", { texto: `${r.total} dígitos ${real} bien leídos por ${nombre[modeloMatriz]}. Elige dos dígitos distintos para ver confusiones.` }));
      } else if (!r.total) {
        galeria.replaceChildren(el("p", { texto: `Ningún ${real} se leyó como ${predicho}.` }));
      } else {
        galeria.replaceChildren(
          el("p", { estilo: { "font-weight": "700", "margin-bottom": "10px" }, texto: `Eran ${real} y ${nombre[modeloMatriz]} leyó ${predicho}: ${r.total} ${r.total === 1 ? "caso" : "casos"}${r.total > r.imagenes.length ? `, se muestran ${r.imagenes.length}` : ""}.` }),
          el("div", { clase: "galeria-fila" }, r.imagenes.map((im) => el("img", { src: im.uri, alt: `Dígito ${real} leído como ${predicho}`, loading: "lazy" }))));
      }
    } catch (e) {
      galeria.replaceChildren(el("p", { clase: "vacio", texto: e.message }));
    }
  }

  function pintarValidacion() {
    poner("img-validacion", "dl-validacion", datos.imagenes.validacion, `validacion_cruzada_${datos.version}.png`);
    const vc = datos.validacion_cruzada;
    const claves = ordenModelos().filter((c) => vc[c] && vc[c].length);
    $("detalle-cv").replaceChildren(...claves.map((c) => el("details", { clase: "tabla-detalle" },
      el("summary", null, `${nombre[c]}: probé ${vc[c].length} combinaciones de hiperparámetros`),
      el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-informe" },
        el("thead", null, el("tr", null, ["Hiperparámetros", "Exactitud promedio", "Variación", "Segundos"].map((t) => el("th", { scope: "col", texto: t })))),
        el("tbody", null, vc[c].map((r, i) => el("tr", null,
          el("td", null, Object.entries(r.parametros).map(([k, v]) => `${k} = ${String(v).replace(".", ",")}`).join(" · "), i === 0 ? el("span", { clase: "insignia ok", estilo: { "margin-left": "8px" }, texto: "Elegida" }) : null),
          el("td", { texto: pct(r.exactitud_media, 2) }), el("td", { texto: "± " + pct(r.desviacion, 2) }),
          el("td", { texto: r.segundos.toFixed(0) })))))))));
  }

  function pintarArquitecturas() {
    $("arquitecturas").replaceChildren(...ordenModelos().map((c) => {
      const a = datos.arquitecturas[c];
      const color = modelos.find((x) => x.clave === c).color;
      const resumen = a.capas ? `${a.parametros_totales.toLocaleString("es")} parámetros · ${a.capas.length} capas` : a.tipo;
      const cabecera = el("summary", null,
        el("span", { clase: "punto-grande", estilo: { background: color } }),
        el("strong", { texto: nombre[c] }), el("span", { clase: "resumen-modelo", texto: resumen }),
        el("span", { clase: "acordeon-estado", "aria-hidden": "true" }));
      let cuerpo;
      if (a.capas) {
        cuerpo = el("div", { clase: "acordeon-cuerpo" },
          el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-informe" },
            el("thead", null, el("tr", null, ["Capa", "Salida", "Activación", "Parámetros"].map((t) => el("th", { scope: "col", texto: t })))),
            el("tbody", null, a.capas.map((l) => el("tr", null, el("th", { scope: "row", texto: l.capa }), el("td", { texto: l.forma }),
              el("td", { texto: l.activacion }), el("td", { texto: l.parametros ? l.parametros.toLocaleString("es") : "—" })))))),
          el("p", { clase: "pie-arquitectura", texto: `Total: ${a.parametros_totales.toLocaleString("es")} parámetros · Optimizador: ${a.optimizador} (tasa ${String(a.tasa_aprendizaje).replace(".", ",")}) · Pérdida: ${a.funcion_perdida}` }));
      } else {
        const extra = a.parametros_totales ? [["Parámetros totales", a.parametros_totales.toLocaleString("es")]] : [];
        if (a.vectores_soporte) extra.push(["Vectores de soporte", a.vectores_soporte.toLocaleString("es")]);
        if (a.muestras_memorizadas) extra.push(["Dígitos memorizados", a.muestras_memorizadas.toLocaleString("es")]);
        cuerpo = el("div", { clase: "acordeon-cuerpo" },
          el("dl", { clase: "lista-parametros" }, [...Object.entries(a.parametros), ...extra].flatMap(([k, v]) => [el("dt", { texto: k }), el("dd", { texto: String(v).replace(".", ",") })])));
      }
      return el("details", { clase: "arquitectura" }, cabecera, cuerpo);
    }));
  }

  function pintarMapa() {
    selectorModelos("modelo-mapa", () => modeloMapa, (c) => { modeloMapa = c; pintarMapa(); });
    poner("img-mapa", "dl-mapa", datos.imagenes.mapa[modeloMapa], `mapa_${modeloMapa}_${datos.version}.png`);
  }

  function pintarPredicciones() {
    selectorModelos("modelo-predicciones", () => modeloPredicciones, (c) => { modeloPredicciones = c; pintarPredicciones(); });
    poner("img-predicciones", "dl-predicciones", datos.imagenes.predicciones[modeloPredicciones], `predicciones_${modeloPredicciones}_${datos.version}.png`);
    $("leyenda-predicciones").textContent = `Predicciones de ${nombre[modeloPredicciones]} frente a la etiqueta real (verde = correcto, rosa = incorrecto).`;
  }

  function pintarTodo() {
    pintarMetricas(); pintarMatriz(); pintarPredicciones(); poner("img-curvas", "dl-curvas", datos.imagenes.curvas, "curvas_entrenamiento.png");
    pintarValidacion(); pintarArquitecturas(); poner("img-velocidad", "dl-velocidad", datos.imagenes.velocidad, `velocidad_${datos.version}.png`);
    poner("img-progreso", "dl-progreso", `/figura/progreso.png?t=${Date.now()}`);
    pintarMapa();
  }

  function mostrar() {
    const listo = datos && datos.listo;
    $("contenido-graficos").hidden = !listo;
    $("vacio-graficos").hidden = listo;
    $("generar").textContent = listo ? "Actualizar gráficos" : "Generar gráficos";
    $("descargar-todo").hidden = !listo;
    $("descargar-todo").href = `/descargar/graficos.zip?version=${$("version").value}`;
    $("estado-graficos").textContent = listo ? `Imágenes de la versión ${datos.version}, calculadas con 10 000 dígitos de prueba de MNIST.` : "";
    if (listo) pintarTodo();
  }

  async function cargar() {
    $("estado-graficos").textContent = "Preparando las imágenes de esta versión…";
    try {
      datos = await App.lento(`/api/graficos?version=${$("version").value}`);
      mostrar();
    } catch (e) { avisar(e.message, "error"); $("estado-graficos").textContent = ""; }
  }

  async function generar() {
    const boton = $("generar");
    boton.disabled = true;
    boton.replaceChildren(el("span", { clase: "cargando" }), " Creando imágenes…");
    $("estado-graficos").textContent = "Evaluando los siete modelos con 10 000 dígitos y creando las imágenes…";
    try {
      datos = await App.ejecutarTarea("/api/tareas/graficos", { version: $("version").value }, { boton });
      mostrar();
      avisar("Imágenes actualizadas.", "ok");
    } catch (e) {
      avisar(e.message, "error", 7000);
    } finally {
      boton.disabled = false;
      $("generar").textContent = datos && datos.listo ? "Actualizar gráficos" : "Generar gráficos";
    }
  }

  /* ---------- Basura de versiones ---------- */
  let listaVersiones = null;

  function fecha(v) { return (v.creada || "").replace("T", " ").slice(0, 16); }

  async function refrescarVersiones(elegida) {
    listaVersiones = await api("/api/versiones");
    const antes = elegida || $("version").value;
    const disponibles = listaVersiones.versiones.map((x) => x.id);
    $("version").replaceChildren(...listaVersiones.versiones.map((x) => el("option", { value: x.id, selected: x.id === (disponibles.includes(antes) ? antes : listaVersiones.activa),
      texto: `${x.id}${x.id === listaVersiones.activa ? " (activa)" : ""} · ${x.motivo}` })));
    const insignia = document.querySelector(".insignia-version strong");
    if (insignia) insignia.textContent = listaVersiones.activa;
    const cantidad = listaVersiones.en_basura;
    $("contador-basura").hidden = !cantidad;
    $("contador-basura").textContent = String(cantidad);
  }

  async function pintarBasura() {
    const basura = (await api("/api/versiones/basura")).basura;
    const marcadas = new Set(Array.from(document.querySelectorAll("#lista-versiones-quitar input:checked")).map((c) => c.value));
    $("lista-versiones-quitar").replaceChildren(...listaVersiones.versiones.map((v) => {
      const inicial = v.numero === 1;
      const activa = v.id === listaVersiones.activa;
      const bloqueada = inicial || activa;
      const caja = el("input", { type: "checkbox", value: v.id, disabled: bloqueada, checked: !bloqueada && marcadas.has(v.id),
        en: { change: actualizarBotonQuitar }, "aria-label": `Marcar ${v.id} para la basura` });
      return el("li", { clase: "version-fila" + (bloqueada ? " protegida" : "") },
        el("label", null, caja, el("span", null, el("strong", { texto: v.id }), el("small", { texto: `${v.motivo} · ${fecha(v)}` }))),
        bloqueada ? el("span", { clase: "insignia", texto: inicial ? "Inicial: no se quita" : "Activa: no se quita" }) : null);
    }));
    $("lista-basura").replaceChildren(...basura.map((v) => {
      const boton = el("button", { type: "button", clase: "boton boton-pequeno", texto: "Restaurar", "aria-label": `Restaurar ${v.id}`, en: { click: () => restaurar(v.id) } });
      const borrar = el("button", { type: "button", clase: "boton boton-pequeno boton-peligro-suave", texto: "Borrar para siempre", "aria-label": `Borrar ${v.id} para siempre` });
      let espera = null;
      borrar.addEventListener("click", () => {
        if (!espera) {
          borrar.textContent = "¿Seguro? Pulsa otra vez";
          espera = setTimeout(() => { espera = null; borrar.textContent = "Borrar para siempre"; }, 4000);
          return;
        }
        clearTimeout(espera);
        borrarParaSiempre(v.id);
      });
      return el("li", { clase: "version-fila" },
        el("span", { clase: "version-info" }, el("strong", { texto: v.id }), el("small", { texto: `${v.motivo} · ${fecha(v)}` })),
        el("span", { clase: "acciones-fila" }, boton, borrar));
    }));
    $("basura-vacia").hidden = basura.length > 0;
    $("vaciar-basura").hidden = basura.length === 0;
    actualizarBotonQuitar();
  }

  function actualizarBotonQuitar() {
    const n = document.querySelectorAll("#lista-versiones-quitar input:checked").length;
    $("quitar-versiones").disabled = n === 0;
    $("quitar-versiones").textContent = n ? `Mandar a la basura (${n})` : "Mandar a la basura";
    $("estado-quitar").textContent = n ? "" : "Marca una o más versiones.";
  }

  async function accionBasura(peticion, mensaje) {
    try {
      const r = await peticion();
      await refrescarVersiones();
      await pintarBasura();
      avisar(mensaje(r), "ok", 6000);
      await cargar();
    } catch (e) { avisar(e.message, "error", 7000); }
  }

  function quitarMarcadas() {
    const ids = Array.from(document.querySelectorAll("#lista-versiones-quitar input:checked")).map((c) => c.value);
    if (!ids.length) return;
    const boton = $("quitar-versiones");
    if (boton.dataset.confirmar !== ids.join(",")) {
      boton.dataset.confirmar = ids.join(",");
      boton.textContent = `Sí, quitar ${ids.join(", ")}`;
      $("estado-quitar").textContent = "Podrás restaurarlas desde «En la basura». Pulsa otra vez para confirmar.";
      return;
    }
    boton.dataset.confirmar = "";
    accionBasura(() => api("/api/versiones/quitar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) }),
      (r) => `Mandé ${r.quitadas.join(", ")} a la basura. Puedes restaurar cuando quieras.`);
  }

  const restaurar = (id) => accionBasura(() => api(`/api/versiones/${id}/restaurar`, { method: "POST" }), () => `Restauré la versión ${id}.`);
  const borrarParaSiempre = (id) => accionBasura(() => api(`/api/versiones/${id}/borrar-para-siempre`, { method: "POST" }), () => `Borré la versión ${id} para siempre.`);

  async function abrirBasura() {
    const panel = $("panel-basura");
    const abrir = panel.hidden;
    panel.hidden = !abrir;
    $("abrir-basura").setAttribute("aria-expanded", String(abrir));
    if (abrir) {
      try { await refrescarVersiones(); await pintarBasura(); } catch (e) { avisar(e.message, "error"); }
      panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  (async function iniciar() {
    $("abrir-basura").addEventListener("click", abrirBasura);
    $("quitar-versiones").addEventListener("click", quitarMarcadas);
    $("vaciar-basura").addEventListener("click", () => {
      const boton = $("vaciar-basura");
      if (boton.dataset.confirmar !== "1") {
        boton.dataset.confirmar = "1";
        boton.textContent = "¿Seguro? Se borran para siempre. Pulsa otra vez";
        setTimeout(() => { boton.dataset.confirmar = ""; boton.textContent = "Vaciar la basura"; }, 5000);
        return;
      }
      boton.dataset.confirmar = "";
      boton.textContent = "Vaciar la basura";
      accionBasura(() => api("/api/versiones/vaciar-basura", { method: "POST" }), () => "Vacié la basura.");
    });
    const digitos = Array.from({ length: 10 }, (_, d) => el("option", { value: String(d), texto: String(d) }));
    $("casilla-real").replaceChildren(...digitos);
    $("casilla-predicho").replaceChildren(...digitos.map((o) => o.cloneNode(true)));
    $("ver-casilla").addEventListener("click", verCasilla);
    try {
      const v = await api("/api/versiones");
      listaVersiones = v;
      const tarea = await App.tareaDeLaUrl();
      const deLaTarea = tarea && tarea.tipo === "graficos" && tarea.estado === "terminado" && tarea.resultado ? tarea.resultado.version : null;
      const pedida = deLaTarea || new URLSearchParams(location.search).get("version");
      $("version").replaceChildren(...v.versiones.map((x) => el("option", { value: x.id, selected: x.id === (pedida || v.activa),
        texto: `${x.id}${x.id === v.activa ? " (activa)" : ""} · ${x.motivo}` })));
      $("contador-basura").hidden = !v.en_basura;
      $("contador-basura").textContent = String(v.en_basura);
      $("version").addEventListener("change", cargar);
      $("generar").addEventListener("click", generar);
      $("descargar-todo").addEventListener("click", async (e) => {
        e.preventDefault();
        const boton = e.currentTarget;
        if (boton.classList.contains("llenandose")) return;
        try { await App.descargarTarea("/api/tareas/graficos-zip", { version: $("version").value }, { boton }); }
        catch (error) { avisar(error.message, "error", 7000); }
      });
      await cargar();
    } catch (e) { avisar(e.message, "error"); }
  })();
})();
