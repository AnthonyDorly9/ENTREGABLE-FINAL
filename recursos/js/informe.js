(function () {
  const { el, api, avisar } = App;
  const $ = (id) => document.getElementById(id);
  const estado = { orden: [], marcadas: new Set(), textos: {}, defecto: {}, portada: "cuaderno", propia: null, tema: "violeta", fotosLote: [], urlPdf: null };
  let opciones = null;

  function recordar() {
    try {
      localStorage.setItem("informe", JSON.stringify({ titulo: $("titulo").value, subtitulo: $("subtitulo").value, autor: $("autor").value, curso: $("curso").value, tema: estado.tema, portada: estado.portada }));
    } catch (e) { /* sin almacenamiento */ }
  }
  function recuperar() {
    try {
      const g = JSON.parse(localStorage.getItem("informe") || "null");
      if (!g) return;
      for (const campo of ["titulo", "subtitulo", "autor", "curso"]) if (g[campo] !== undefined) $(campo).value = g[campo];
      if (g.tema) estado.tema = g.tema;
      if (g.portada && g.portada !== "propia") estado.portada = g.portada;
    } catch (e) { /* datos guardados no válidos */ }
  }

  function cargarPropia(archivo) {
    if (!archivo || !archivo.type.startsWith("image/")) { avisar("Elige una imagen en formato JPG o PNG.", "error"); return; }
    const url = URL.createObjectURL(archivo);
    const imagen = new Image();
    imagen.onload = () => {
      const escala = Math.min(1, 1600 / Math.max(imagen.width, imagen.height));
      const lienzo = document.createElement("canvas");
      lienzo.width = Math.max(1, Math.round(imagen.width * escala));
      lienzo.height = Math.max(1, Math.round(imagen.height * escala));
      const ctx = lienzo.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, lienzo.width, lienzo.height);
      ctx.drawImage(imagen, 0, 0, lienzo.width, lienzo.height);
      estado.propia = lienzo.toDataURL("image/jpeg", 0.88);
      estado.portada = "propia";
      URL.revokeObjectURL(url);
      pintarPortadas();
      avisar("Tu foto será la carátula del informe.", "ok");
    };
    imagen.onerror = () => { URL.revokeObjectURL(url); avisar("No se pudo abrir esa imagen. Prueba con un JPG o PNG.", "error"); };
    imagen.src = url;
  }

  function pintarPortadas() {
    const fichas = [];
    if (estado.propia) {
      fichas.push(el("div", { clase: "ficha-propia" },
        el("button", { type: "button", role: "radio", "aria-checked": String(estado.portada === "propia"), clase: "opcion-imagen" + (estado.portada === "propia" ? " elegida" : ""),
          title: "Tu foto", "aria-label": "Imagen: tu foto", en: { click: () => { estado.portada = "propia"; pintarPortadas(); recordar(); } } },
          el("img", { src: estado.propia, alt: "" })),
        el("button", { type: "button", clase: "quitar-propia", texto: "Quitar", "aria-label": "Quitar tu foto de la carátula",
          en: { click: () => { estado.propia = null; if (estado.portada === "propia") estado.portada = opciones.portadas[0] ? opciones.portadas[0].clave : "cuaderno"; pintarPortadas(); recordar(); } } })));
    }
    fichas.push(...opciones.portadas.map((p) => el("button", {
      type: "button", role: "radio", "aria-checked": String(p.clave === estado.portada), clase: "opcion-imagen" + (p.clave === estado.portada ? " elegida" : ""),
      title: p.titulo, "aria-label": "Imagen: " + p.titulo, en: { click: () => { estado.portada = p.clave; pintarPortadas(); recordar(); } } },
      el("img", { src: `/recursos/imagenes/portadas/${p.archivo}`, alt: "" }))));
    fichas.push(el("button", { type: "button", clase: "opcion-imagen subir-propia", "aria-label": "Subir mi foto para la carátula", en: { click: () => $("archivo-portada").click() } },
      el("span", { clase: "mas", texto: "+" }), el("span", { texto: "Subir mi foto" })));
    $("portadas").replaceChildren(...fichas);
    $("temas").replaceChildren(...opciones.temas.map((t) => el("button", {
      type: "button", role: "radio", "aria-checked": String(t.clave === estado.tema), clase: "muestra-color" + (t.clave === estado.tema ? " elegida" : ""),
      estilo: { "--tono": t.color }, title: t.clave, "aria-label": "Color " + t.clave, en: { click: () => { estado.tema = t.clave; pintarPortadas(); recordar(); } } })));
  }

  function mover(indice, delta) {
    const nuevo = indice + delta;
    if (nuevo < 0 || nuevo >= estado.orden.length) return;
    [estado.orden[indice], estado.orden[nuevo]] = [estado.orden[nuevo], estado.orden[indice]];
    pintarSecciones();
    const botones = $("secciones").querySelectorAll(delta < 0 ? ".subir" : ".bajar");
    if (botones[nuevo]) botones[nuevo].focus();
  }

  function pintarSecciones() {
    const info = Object.fromEntries(opciones.secciones.map((s) => [s.clave, s]));
    $("secciones").replaceChildren(...estado.orden.map((clave, i) => {
      const s = info[clave];
      const marcada = estado.marcadas.has(clave);
      const editable = el("textarea", { rows: "8", "aria-label": "Texto de " + s.titulo, value: estado.textos[clave] ?? estado.defecto[clave] ?? "",
        en: { input: (e) => { estado.textos[clave] = e.target.value; } } });
      editable.value = estado.textos[clave] ?? estado.defecto[clave] ?? "";
      return el("li", { clase: "seccion-informe" + (marcada ? "" : " apagada") },
        el("div", { clase: "seccion-informe-fila" },
          el("label", { clase: "marca-seccion" }, el("input", { type: "checkbox", checked: marcada, en: { change: (e) => { e.target.checked ? estado.marcadas.add(clave) : estado.marcadas.delete(clave); pintarSecciones(); } } }),
            el("span", null, el("strong", { texto: s.titulo }), el("small", { texto: s.descripcion }))),
          el("div", { clase: "mover" },
            el("button", { type: "button", clase: "boton boton-pequeno subir", texto: "Subir", disabled: i === 0, "aria-label": `Subir ${s.titulo}`, en: { click: () => mover(i, -1) } }),
            el("button", { type: "button", clase: "boton boton-pequeno bajar", texto: "Bajar", disabled: i === estado.orden.length - 1, "aria-label": `Bajar ${s.titulo}`, en: { click: () => mover(i, 1) } }))),
        marcada ? el("details", { clase: "editar-texto" },
          el("summary", { texto: "Editar texto" }),
          editable,
          el("button", { type: "button", clase: "boton boton-pequeno", texto: "Restaurar texto original", en: { click: () => { delete estado.textos[clave]; editable.value = estado.defecto[clave] ?? ""; } } })) : null);
    }));
  }

  function pintarFotos() {
    $("sin-fotos").hidden = estado.fotosLote.length > 0;
    $("fotos-informe").replaceChildren(...estado.fotosLote.map((f) => el("label", { clase: "foto-informe" },
      el("input", { type: "checkbox", checked: f.incluir, en: { change: (e) => { f.incluir = e.target.checked; } } }),
      el("img", { src: f.url, alt: "Foto " + f.nombre, loading: "lazy" }),
      el("span", { texto: f.texto }))));
  }

  async function cargarFotos() {
    const lote = $("lote").value;
    if (!lote) { estado.fotosLote = []; pintarFotos(); return; }
    try {
      const r = await api(`/api/lote/${lote}`);
      estado.fotosLote = r.fotos.map((f, i) => ({ id: f.id, url: f.url, nombre: f.nombre, texto: f.texto, incluir: i < 6 }));
      pintarFotos();
    } catch (e) { avisar(e.message, "error"); }
  }

  async function mostrarPdf(idTarea) {
    const respuesta = await fetch(`/api/tareas/${idTarea}/archivo`);
    if (!respuesta.ok) throw new Error("No se pudo recuperar el PDF. Genera uno nuevo.");
    const blob = await respuesta.blob();
    if (estado.urlPdf) URL.revokeObjectURL(estado.urlPdf);
    estado.urlPdf = URL.createObjectURL(blob);
    $("marco-pdf").src = estado.urlPdf;
    $("descargar-pdf").href = estado.urlPdf;
    $("vista-pdf").hidden = false;
    $("estado-informe").textContent = `PDF listo (${(blob.size / 1024 / 1024).toFixed(1).replace(".", ",")} MB).`;
    $("vista-pdf").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function generar() {
    const boton = $("generar-pdf");
    if (!estado.orden.some((c) => estado.marcadas.has(c))) { avisar("Marca al menos una sección.", "error"); return; }
    boton.disabled = true;
    boton.replaceChildren(el("span", { clase: "cargando" }), " Creando el PDF…");
    $("estado-informe").textContent = "Creando el PDF con gráficos y tablas. Puedes ir a otra sección: te aviso al terminar.";
    recordar();
    try {
      const cuerpo = {
        version: $("version").value, titulo: $("titulo").value, subtitulo: $("subtitulo").value, autor: $("autor").value, curso: $("curso").value,
        tema: estado.tema, portada: estado.portada, portada_propia: estado.portada === "propia" ? estado.propia : null, secciones: estado.orden.filter((c) => estado.marcadas.has(c)),
        textos: Object.fromEntries(Object.entries(estado.textos).filter(([c]) => estado.marcadas.has(c))),
        lote: $("lote").value || null, fotos: estado.fotosLote.filter((f) => f.incluir).map((f) => f.id),
      };
      const r = await App.ejecutarTarea("/api/tareas/informe", cuerpo, { boton });
      await mostrarPdf(r._tarea);
      avisar("PDF listo.", "ok");
    } catch (e) {
      avisar(e.message, "error", 8000);
      $("estado-informe").textContent = e.message;
    } finally {
      boton.disabled = false;
      boton.textContent = "Generar PDF";
    }
  }

  async function cargarOpciones() {
    $("estado-informe").textContent = "Preparando los textos con los datos de esta versión…";
    opciones = await api(`/api/informe/opciones?version=${$("version").value}`);
    estado.defecto = opciones.textos;
    $("estado-informe").textContent = "Cuando estés listo, genera el PDF.";
    pintarPortadas();
    pintarSecciones();
  }

  (async function iniciar() {
    recuperar();
    try {
      const v = await api("/api/versiones");
      $("version").replaceChildren(...v.versiones.map((x) => el("option", { value: x.id, selected: x.id === v.activa, texto: `${x.id}${x.id === v.activa ? " (activa)" : ""} · ${x.motivo}` })));
      opciones = await api(`/api/informe/opciones?version=${v.activa}`);
      estado.defecto = opciones.textos;
      estado.orden = opciones.secciones.map((s) => s.clave);
      estado.marcadas = new Set(estado.orden);
      if (!opciones.portadas.some((p) => p.clave === estado.portada)) estado.portada = opciones.portadas[0] ? opciones.portadas[0].clave : "cuaderno";
      pintarPortadas();
      pintarSecciones();
      $("archivo-portada").addEventListener("change", (e) => { cargarPropia(e.target.files[0]); e.target.value = ""; });
      const zona = $("zona-portada");
      ["dragenter", "dragover"].forEach((n) => zona.addEventListener(n, (e) => { e.preventDefault(); zona.classList.add("arrastrando"); }));
      ["dragleave", "drop"].forEach((n) => zona.addEventListener(n, (e) => { e.preventDefault(); zona.classList.remove("arrastrando"); }));
      zona.addEventListener("drop", (e) => cargarPropia(e.dataTransfer.files[0]));
      $("version").addEventListener("change", async () => { try { estado.textos = {}; await cargarOpciones(); } catch (e) { avisar(e.message, "error"); } });
      const lotes = await api("/api/lotes");
      $("lote").replaceChildren(...lotes.slice().reverse().map((l) => el("option", { value: l.lote, texto: `${App.nombreTanda(l.lote)} · ${l.fotos} ${l.fotos === 1 ? "foto" : "fotos"}` })));
      $("lote").addEventListener("change", cargarFotos);
      await cargarFotos();
      $("generar-pdf").addEventListener("click", generar);
      $("descargar-codigo").addEventListener("click", async (e) => {
        e.preventDefault();
        const boton = e.currentTarget;
        if (boton.classList.contains("llenandose")) return;
        try { await App.descargarTarea("/api/tareas/codigo-zip", {}, { boton }); }
        catch (error) { avisar(error.message, "error", 7000); }
      });
      App.tareaDeLaUrl().then(async (tarea) => {
        if (!tarea || tarea.tipo !== "informe") return;
        if (tarea.estado === "error") { avisar(tarea.error, "error", 8000); return; }
        try { await mostrarPdf(tarea.id); } catch (e) { avisar(e.message, "error"); }
      });
      for (const id of ["titulo", "subtitulo", "autor", "curso"]) $(id).addEventListener("change", recordar);
    } catch (e) { avisar(e.message, "error"); }
  })();
})();
