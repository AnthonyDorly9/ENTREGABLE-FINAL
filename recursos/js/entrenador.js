(function () {
  const { el, api, avisar, porcentaje } = App;
  const modelos = App.modelos();
  const info = Object.fromEntries(modelos.map((m) => [m.clave, m]));
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const num = (v, d) => Number(v).toFixed(d).replace(".", ",");
  let opciones = null;
  let clave = "cnn";
  let valores = {};
  let muestras = 10000;
  let trabajo = null;
  let sondeo = null;

  function etiquetaParametro(modelo, k) {
    const m = opciones.modelos.find((x) => x.clave === modelo);
    const c = m && m.controles.find((x) => x.clave === k);
    return c ? c.etiqueta : k;
  }
  const textoParametros = (modelo, p) => Object.entries(p).map(([k, v]) => `${etiquetaParametro(modelo, k)}: ${String(v).replace(".", ",")}`).join(" · ");

  function elegirModelo(nueva) {
    clave = nueva;
    const m = opciones.modelos.find((x) => x.clave === clave);
    valores = { ...m.defecto };
    pintarControles();
  }

  function pintarControles() {
    const m = opciones.modelos.find((x) => x.clave === clave);
    $("modelo-entrenador").replaceChildren(...modelos.map((mm) => el("button", {
      type: "button", role: "radio", "aria-checked": String(mm.clave === clave), clase: "chip-modelo" + (mm.clave === clave ? " elegido" : ""),
      estilo: { "--color": mm.color }, texto: mm.nombre, en: { click: () => elegirModelo(mm.clave) } })));
    const controles = m.controles.map((c) => {
      const id = "ctl-" + c.clave;
      let campo;
      if (c.tipo === "opciones") {
        campo = el("select", { id, en: { change: (e) => { const o = c.opciones.find((x) => String(x) === e.target.value); valores[c.clave] = o; } } },
          c.opciones.map((o) => el("option", { value: String(o), selected: o === valores[c.clave], texto: String(o).replace(".", ",") })));
        return el("div", { clase: "ajuste" }, el("label", { for: id, texto: c.etiqueta }), campo);
      }
      const salida = el("output", { for: id, texto: String(valores[c.clave]).replace(".", ",") });
      campo = el("input", { id, type: "range", min: c.min, max: c.max, step: c.paso, value: valores[c.clave],
        en: { input: (e) => { valores[c.clave] = c.entero ? parseInt(e.target.value, 10) : parseFloat(e.target.value); salida.textContent = String(valores[c.clave]).replace(".", ","); } } });
      return el("div", { clase: "ajuste" }, el("label", { for: id, texto: c.etiqueta }), el("div", { clase: "rango-fila" }, campo, salida));
    });
    const selMuestras = el("select", { id: "ctl-muestras", en: { change: (e) => { muestras = Number(e.target.value); } } },
      opciones.muestras.map((n) => el("option", { value: String(n), selected: n === muestras, texto: n.toLocaleString("es") + " dígitos" })));
    controles.push(el("div", { clase: "ajuste" }, el("label", { for: "ctl-muestras", texto: "Dígitos de MNIST para entrenar" }), selMuestras));
    $("ajustes").replaceChildren(...controles);
    $("validar").disabled = false;
  }

  let ultimasEpocas = -1;
  function curvasVivas(historial, idTrabajo) {
    if (historial.length === ultimasEpocas) return;
    ultimasEpocas = historial.length;
    const img = $("img-vivo");
    img.classList.add("lista");
    img.src = `/figura/entrenamiento/${idTrabajo}.png?n=${historial.length}`;
  }

  async function iniciar(modo) {
    if (sondeo) return;
    const botones = ["entrenar", "validar", "buscar"].map($);
    botones.forEach((b) => (b.disabled = true));
    $("zona-progreso").hidden = false;
    ultimasEpocas = -1;
    $("resultado-entrenador").replaceChildren();
    $("curvas-vivo").hidden = true;
    $("mensaje-progreso").textContent = "Preparando…";
    fijarProgreso(0);
    try {
      trabajo = await api("/api/entrenador/iniciar", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modelo: clave, parametros: valores, muestras, modo }) });
      $("zona-progreso").scrollIntoView({ behavior: "smooth", block: "start" });
      sondeo = setInterval(consultar, 600);
    } catch (e) {
      avisar(e.message, "error", 7000);
      botones.forEach((b) => (b.disabled = false));
    }
  }

  function fijarProgreso(p) {
    $("relleno-progreso").style.transform = `scaleX(${Math.max(0.02, Math.min(1, p))})`;
    $("barra-progreso").setAttribute("aria-valuenow", String(Math.round(p * 100)));
  }

  async function consultar() {
    try {
      trabajo = await api(`/api/entrenador/estado/${trabajo.id}`);
    } catch (e) { clearInterval(sondeo); sondeo = null; avisar(e.message, "error"); return; }
    $("mensaje-progreso").textContent = trabajo.mensaje;
    fijarProgreso(trabajo.progreso);
    if (trabajo.modo === "entrenar" && trabajo.historial.length) {
      $("curvas-vivo").hidden = false;
      curvasVivas(trabajo.historial, trabajo.id);
    }
    if (trabajo.estado === "en_curso") return;
    clearInterval(sondeo);
    sondeo = null;
    App.silenciarTarea(trabajo.tarea);
    ["entrenar", "validar", "buscar"].forEach((i) => ($(i).disabled = false));
    if (trabajo.estado === "error") { avisar(trabajo.error, "error", 9000); $("mensaje-progreso").textContent = trabajo.error; return; }
    $("mensaje-progreso").textContent = "Listo.";
    await mostrarResultado();
    if (trabajo.modo === "entrenar") cargarIntentos();
  }

  async function mostrarResultado() {
    const r = trabajo.resultado;
    const cont = $("resultado-entrenador");
    if (trabajo.modo === "validar") {
      cont.replaceChildren(el("h3", { texto: "Validación cruzada" }),
        el("p", { texto: `Exactitud promedio ${porcentaje(r.media, 2)} (± ${porcentaje(r.desviacion, 2)}). Pliegues: ${r.exactitudes.map((v) => porcentaje(v, 1)).join(" · ")}.` }),
        el("p", { estilo: { color: "var(--tinta-suave)" }, texto: "Se entrena 5 veces con 4/5 de los dígitos y se prueba con el 1/5 restante. Si los cinco números son parecidos, el modelo es estable." }));
      return;
    }
    if (trabajo.modo === "buscar") {
      cont.replaceChildren(el("h3", { texto: "Combinaciones probadas" }),
        el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-informe" },
          el("thead", null, el("tr", null, ["Hiperparámetros", "Exactitud promedio", "Variación"].map((t) => el("th", { scope: "col", texto: t })))),
          el("tbody", null, r.combinaciones.map((c, i) => el("tr", null,
            el("td", null, textoParametros(trabajo.modelo, c.parametros), i === 0 ? el("span", { clase: "insignia ok", estilo: { "margin-left": "8px" }, texto: "Mejor" }) : null),
            el("td", { texto: porcentaje(c.exactitud_media, 2) }), el("td", { texto: "± " + porcentaje(c.desviacion, 2) })))))),
        el("div", { clase: "acciones-correccion" }, el("button", { clase: "boton boton-verde", type: "button", texto: "Aplicar los mejores a los ajustes",
          en: { click: () => { valores = { ...valores, ...r.mejor }; pintarControles(); avisar("Ajustes actualizados con la mejor combinación.", "ok"); window.scrollTo({ top: 0, behavior: "smooth" }); } } })));
      return;
    }
    let activo = null;
    try {
      const g = await api("/api/graficos");
      if (g.listo) activo = g.modelos[trabajo.modelo];
    } catch (e) { /* sin comparación */ }
    const tarjeta = (titulo, valor, previo, formato) => el("div", { clase: "dato" }, el("span", { clase: "dato-titulo", texto: titulo }),
      el("strong", { texto: formato(valor) }),
      previo === null ? null : el("small", { clase: valor >= previo ? "sube" : "baja", texto: `activo: ${formato(previo)}` }));
    cont.replaceChildren(
      el("h3", { texto: `Resultado de ${info[trabajo.modelo].nombre}` }),
      el("div", { clase: "datos-fila" },
        tarjeta("Exactitud en MNIST", r.exactitud, activo ? activo.exactitud : null, (v) => porcentaje(v, 2)),
        tarjeta("F1", r.f1_macro, activo ? activo.f1_macro : null, (v) => porcentaje(v, 2)),
        tarjeta("Segundos de entrenamiento", r.segundos, null, (v) => num(v, 1) + " s"),
        tarjeta("Dígitos usados", r.muestras, null, (v) => v.toLocaleString("es"))),
      el("p", { estilo: { color: "var(--tinta-suave)", margin: "12px 0" }, texto: "Si lo usas, se crea una versión nueva. Antes se repasan tus dígitos de tandas anteriores para que no se pierdan tus correcciones." }),
      el("div", { clase: "acciones-correccion" },
        el("button", { clase: "boton boton-verde", type: "button", id: "adoptar", texto: "Usar este modelo", en: { click: adoptar } })));
  }

  async function adoptar() {
    const boton = $("adoptar");
    boton.disabled = true;
    boton.replaceChildren(el("span", { clase: "cargando" }), " Guardando…");
    try {
      const r = await App.lento("/api/entrenador/adoptar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: trabajo.id }) }, { boton });
      const extra = r.anteriores_antes ? ` Dígitos tuyos que acierta: ${r.anteriores_antes[0]}/${r.anteriores_antes[1]} → ${r.anteriores_despues[0]}/${r.anteriores_despues[1]}.` : "";
      avisar(`Listo: ahora usas la versión ${r.version_nueva}.${extra}`, "ok", 8000);
      const insignia = document.querySelector(".insignia-version strong");
      if (insignia) insignia.textContent = r.version_nueva;
      boton.textContent = "Ya se usa (" + r.version_nueva + ")";
      cargarIntentos();
    } catch (e) {
      avisar(e.message, "error", 7000);
      boton.disabled = false;
      boton.textContent = "Usar este modelo";
    }
  }

  async function cargarIntentos() {
    const d = await api("/api/entrenador/opciones");
    const lista = d.intentos.slice().reverse();
    $("sin-intentos").hidden = lista.length > 0;
    const tabla = $("tabla-intentos");
    tabla.hidden = lista.length === 0;
    tabla.replaceChildren(
      el("caption", { clase: "solo-lectores", texto: "Entrenamientos realizados" }),
      el("thead", null, el("tr", null, ["Fecha", "Modelo", "Hiperparámetros", "Dígitos", "Exactitud", "F1", "Segundos", "Estado"].map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", null, lista.map((i) => el("tr", { estilo: { "--color": info[i.modelo].color } },
        el("td", { texto: i.fecha }),
        el("th", { scope: "row" }, el("span", { clase: "modelo-nombre" }, el("span", { clase: "punto" }), info[i.modelo].nombre)),
        el("td", { texto: textoParametros(i.modelo, i.parametros) }),
        el("td", { texto: i.muestras.toLocaleString("es") }),
        el("td", { texto: porcentaje(i.exactitud, 2) }), el("td", { texto: porcentaje(i.f1_macro, 2) }),
        el("td", { texto: num(i.segundos, 1) }),
        el("td", null, i.adoptado ? el("span", { clase: "insignia ok", texto: "Usado en " + i.adoptado }) : "—")))));
  }

  (async function arrancar() {
    try {
      opciones = await api("/api/entrenador/opciones");
      elegirModelo("cnn");
      $("entrenar").addEventListener("click", () => iniciar("entrenar"));
      $("validar").addEventListener("click", () => iniciar("validar"));
      $("buscar").addEventListener("click", () => iniciar("buscar"));
      $("estado-entrenador").textContent = `Versión activa: ${opciones.version}. Entrenar con 10 000 dígitos tarda unos segundos.`;
      cargarIntentos();
      await retomar();
    } catch (e) { avisar(e.message, "error"); }
  })();

  /* Si la persona salio de esta pagina mientras se entrenaba, al volver se retoma donde iba (o se muestra el resultado). */
  async function retomar() {
    const ultimo = (await api("/api/entrenador/ultimo")).trabajo;
    const pedido = new URLSearchParams(location.search).get("trabajo");
    if (!ultimo || !(ultimo.estado === "en_curso" || ultimo.id === pedido)) return;
    if (pedido) history.replaceState(null, "", location.pathname);
    trabajo = ultimo;
    clave = trabajo.modelo;
    valores = { ...trabajo.parametros };
    muestras = trabajo.muestras;
    pintarControles();
    $("zona-progreso").hidden = false;
    $("mensaje-progreso").textContent = trabajo.mensaje;
    fijarProgreso(trabajo.progreso);
    if (trabajo.modo === "entrenar" && trabajo.historial.length) { $("curvas-vivo").hidden = false; curvasVivas(trabajo.historial, trabajo.id); }
    if (trabajo.estado === "en_curso") {
      ["entrenar", "validar", "buscar"].forEach((i) => ($(i).disabled = true));
      sondeo = setInterval(consultar, 600);
    } else if (trabajo.estado === "error") {
      $("mensaje-progreso").textContent = trabajo.error;
      App.silenciarTarea(trabajo.tarea);
    } else {
      $("mensaje-progreso").textContent = "Listo.";
      App.silenciarTarea(trabajo.tarea);
      await mostrarResultado();
    }
  }
})();
