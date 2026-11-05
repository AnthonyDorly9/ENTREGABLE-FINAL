(function () {
  const { el, api, avisar } = App;
  const modelos = App.modelos();
  const CORTO = Object.fromEntries(modelos.map((m) => [m.clave, m.corto]));
  const $ = (id) => document.getElementById(id);
  const POR_PAGINA = 24;
  const MAXIMO_ENTRENAR = 20;
  const CLAVE_NUEVAS = "trazo-imagenes-nuevas";
  const JSON_POST = (cuerpo) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
  let actual = null;
  let banco = { formularios: [], numeros: [] };
  let basura = [];
  let pestana = "numeros";
  let visibles = POR_PAGINA;
  let entrenando = false;
  const seleccion = new Set();
  let nuevas = new Set();
  try { nuevas = new Set(JSON.parse(sessionStorage.getItem(CLAVE_NUEVAS) || "[]")); } catch (e) { /* sin memoria de la pestaña */ }

  function guardarNuevas() {
    try { sessionStorage.setItem(CLAVE_NUEVAS, JSON.stringify([...nuevas])); } catch (e) { /* sin memoria de la pestaña */ }
  }
  const esNueva = (carpeta, x) => nuevas.has(carpeta + "/" + x.nombre);
  const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

  function mostrarFormulario(f) {
    actual = f;
    $("zona-formulario").hidden = false;
    $("imagen-formulario").src = f.imagen;
    $("titulo-formulario").textContent = `${f.titulo}: ${f.campos.length} ${f.campos.length === 1 ? "campo" : "campos"} con ${f.campos.reduce((a, c) => a + c.largo, 0)} dígitos.`;
    $("lectura").replaceChildren();
    $("leer-formulario").disabled = false;
    $("zona-formulario").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* Boton que corrige a los modelos que se equivocaron y muestra el antes y despues en el contenedor indicado. */
  function botonCorregir(hayErrores, accion, idContenedor) {
    if (!hayErrores) {
      return el("p", { clase: "insignia ok", estilo: { "margin-top": "16px" }, texto: "Todos los modelos acertaron todo: no hay nada que corregir." });
    }
    const boton = el("button", { type: "button", clase: "boton boton-verde", estilo: { "margin-top": "16px" }, texto: "Corregir a los modelos que se equivocaron" });
    boton.addEventListener("click", async () => {
      boton.disabled = true;
      boton.replaceChildren(el("span", { clase: "cargando" }), " Entrenando a los que fallaron…");
      try {
        const informe = await accion(boton);
        $(idContenedor).replaceChildren(App.tablaCorreccion(informe));
        if (informe.version_nueva) {
          avisar(`Listo: ahora usas la versión ${informe.version_nueva}.`, "ok");
          const insignia = document.querySelector(".insignia-version strong");
          if (insignia) insignia.textContent = informe.version_nueva;
          boton.textContent = "Ya corregidos (" + informe.version_nueva + ")";
        } else {
          avisar(informe.mensaje, "info", 7000);
          boton.disabled = false;
          boton.textContent = "Corregir a los modelos que se equivocaron";
        }
        $(idContenedor).scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (e) {
        avisar(e.message, "error", 7000);
        boton.disabled = false;
        boton.textContent = "Corregir a los modelos que se equivocaron";
      }
    });
    return boton;
  }

  async function leer() {
    const boton = $("leer-formulario");
    boton.disabled = true;
    boton.replaceChildren(el("span", { clase: "cargando" }), " Leyendo…");
    try {
      const r = await App.lento(`/api/ficticios/leer/${actual.token}`, null, { boton });
      const filas = r.campos.map((c) => el("tr", null,
        el("th", { scope: "row" }, el("div", { estilo: { "font-weight": "700" }, texto: c.etiqueta }), el("img", { src: c.recorte, alt: "Recorte del campo " + c.etiqueta, clase: "recorte-campo" })),
        el("td", null, el("strong", { clase: "valor-real", texto: c.valor })),
        modelos.map((m) => { const p = c.por_modelo[m.clave]; return el("td", null, el("span", { clase: "celda-cambio " + (p.correcto ? "mejora" : "empeora"), texto: p.numero, "aria-label": `${m.nombre}: ${p.numero}, ${p.correcto ? "correcto" : "incorrecto"}` })); })));
      $("lectura").replaceChildren(el("div", { clase: "tarjeta" },
        el("h2", { texto: "Lo que leyó cada modelo", estilo: { "margin-bottom": "12px" } }),
        el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-informe tabla-lectura" },
          el("caption", { clase: "solo-lectores", texto: "Valor real y lectura de cada modelo por campo" }),
          el("thead", null, el("tr", null, el("th", { scope: "col", texto: "Campo" }), el("th", { scope: "col", texto: "Valor real" }),
            modelos.map((m) => el("th", { scope: "col", title: m.nombre, estilo: { "--color": m.color } }, el("span", { clase: "modelo-nombre" }, el("span", { clase: "punto" }), CORTO[m.clave]))))),
          el("tbody", null, filas))),
        el("h3", { texto: "Resumen", estilo: { margin: "20px 0 10px" } }),
        el("div", { clase: "chips" }, r.resumen.map((x) => {
          const m = modelos.find((mm) => mm.clave === x.modelo);
          return el("span", { clase: "chip-modelo", estilo: { "--color": m.color } }, m.nombre, el("small", { texto: `${x.campos_ok}/${x.campos} campos · ${x.digitos_ok}/${x.digitos} dígitos` }));
        })),
        botonCorregir(r.resumen.some((x) => x.digitos_ok < x.digitos), (boton) => App.ejecutarTarea("/api/tareas/ficticios-corregir", { token: actual.token }, { boton }), "resultado-correccion-lectura"),
        el("div", { id: "resultado-correccion-lectura", estilo: { "margin-top": "16px" }, "aria-live": "polite" })));
    } catch (e) { avisar(e.message, "error"); } finally {
      boton.disabled = false;
      boton.textContent = "Leer con todos los modelos";
    }
  }

  /* ---------- Galería ---------- */
  function listaActual() {
    const nivel = $("filtro-nivel").value;
    const antiguas = $("orden-galeria").value === "antiguas";
    return (banco[pestana] || []).filter((x) => !nivel || x.nivel === nivel).map((x, i) => [x, i]).sort(([a, i], [b, j]) => (antiguas
      ? a.creada - b.creada
      : (esNueva(pestana, b) - esNueva(pestana, a)) || (b.creada - a.creada)) || (i - j)).map(([x]) => x);
  }

  function cambiarPestana(clave) {
    if (pestana !== clave) seleccion.clear();
    pestana = clave;
    visibles = POR_PAGINA;
  }

  function pintarPestanas() {
    $("pestanas-galeria").replaceChildren(...[["numeros", `Números escritos (${banco.numeros.length})`], ["formularios", `Formularios (${banco.formularios.length})`]].map(([clave, texto]) => el("button", {
      type: "button", clase: "segmento", texto, "aria-pressed": String(pestana === clave),
      en: { click: () => { cambiarPestana(clave); pintarGaleria(); } } })));
  }

  async function abrir(elemento) {
    try {
      const ruta = pestana === "numeros" ? "/api/ficticios/numero" : "/api/ficticios/ejemplo";
      mostrarFormulario(await App.lento(ruta, JSON_POST({ nombre: elemento.nombre })));
    } catch (e) { avisar(e.message, "error"); }
  }

  /* Barra que aparece al marcar imagenes: entrenar a los modelos con ellas o mandarlas a la basura. */
  function actualizarBarra() {
    const n = seleccion.size;
    $("barra-seleccion").hidden = n === 0;
    $("texto-seleccion").textContent = pestana === "formularios"
      ? `${plural(n, "formulario elegido", "formularios elegidos")}. Para entrenar con uno, ábrelo con «Ver lectura».`
      : plural(n, "imagen elegida", "imágenes elegidas");
    $("mandar-basura").textContent = `Mandar a la basura (${n})`;
    const entrenar = $("entrenar-elegidas");
    entrenar.hidden = pestana === "formularios";
    if (entrenando) return;
    entrenar.disabled = n > MAXIMO_ENTRENAR;
    entrenar.textContent = n > MAXIMO_ENTRENAR ? `Para entrenar, máximo ${MAXIMO_ENTRENAR} (tienes ${n})` : `Entrenar a todos los modelos (${n})`;
  }

  function pintarAvisoNuevas() {
    const cuantas = (carpeta) => banco[carpeta].filter((x) => esNueva(carpeta, x)).length;
    const numeros = cuantas("numeros"), formularios = cuantas("formularios");
    $("aviso-nuevas").hidden = numeros + formularios === 0;
    $("texto-aviso-nuevas").textContent = `✨ Se crearon ${plural(numeros + formularios, "imagen nueva", "imágenes nuevas")}`
      + (formularios ? ` (${plural(numeros, "número", "números")} y ${plural(formularios, "formulario", "formularios")})` : "")
      + ". Están primeras en la galería, con la etiqueta «Nueva».";
    const aqui = pestana === "numeros" ? numeros : formularios;
    $("elegir-nuevas").hidden = aqui === 0;
    $("elegir-nuevas").textContent = `Elegir las ${aqui} nuevas`;
  }

  function tarjetaImagen(x, carpeta) {
    const nombreLeido = x.texto ? "número " + x.texto : x.nombre;
    const boton = el("button", { type: "button", clase: "elegir-imagen", "aria-pressed": String(seleccion.has(x.nombre)), "aria-label": `Marcar ${nombreLeido}` },
      el("span", { clase: "palomita", "aria-hidden": "true", texto: "✓" }),
      esNueva(carpeta, x) ? el("span", { clase: "etiqueta-nueva", texto: "Nueva" }) : null,
      el("img", { src: `/ficticios-img/${carpeta}/${x.nombre}?ancho=${carpeta === "formularios" ? 320 : 240}`, alt: x.texto ? `Número ${x.texto}` : x.nombre, loading: "lazy" }),
      el("span", { clase: "pie-ejemplo" }, el("strong", { texto: x.texto || x.tipo }),
        el("span", { clase: "nivel nivel-" + ({ "Fácil": "facil", "Normal": "normal", "Difícil": "dificil", "Muy difícil": "muydificil" }[x.nivel] || "normal"), texto: x.nivel })));
    const tarjeta = el("div", { clase: "ejemplo" + (carpeta === "formularios" ? " forma" : "") + (seleccion.has(x.nombre) ? " marcada" : "") }, boton,
      el("button", { type: "button", clase: "boton boton-pequeno ver-lectura", texto: "Ver lectura", "aria-label": `Ver qué lee cada modelo en ${nombreLeido}`, en: { click: () => abrir(x) } }));
    boton.addEventListener("click", () => {
      const marcada = !seleccion.has(x.nombre);
      if (marcada) seleccion.add(x.nombre); else seleccion.delete(x.nombre);
      tarjeta.classList.toggle("marcada", marcada);
      boton.setAttribute("aria-pressed", String(marcada));
      actualizarBarra();
    });
    return tarjeta;
  }

  function pintarGaleria() {
    pintarPestanas();
    const lista = listaActual();
    const carpeta = pestana;
    $("resumen-galeria").textContent = `${banco.numeros.length} fotos de números y ${banco.formularios.length} formularios listos para practicar. Toca para abrir la galería.`;
    $("galeria-ejemplos").replaceChildren(...lista.slice(0, visibles).map((x) => tarjetaImagen(x, carpeta)));
    $("mostrar-mas").hidden = visibles >= lista.length;
    pintarAvisoNuevas();
    actualizarBarra();
  }

  async function cargarBanco() {
    const o = await api("/api/ficticios/opciones");
    banco = o.banco;
    const existentes = new Set(["numeros", "formularios"].flatMap((c) => banco[c].map((x) => c + "/" + x.nombre)));
    nuevas = new Set([...nuevas].filter((n) => existentes.has(n)));
    for (const nombre of [...seleccion]) if (!existentes.has(pestana + "/" + nombre)) seleccion.delete(nombre);
    pintarGaleria();
  }

  /* ---------- Ventana «Crear imágenes»: tipo, dificultad (obligatoria) y cantidad ---------- */
  const elegidoEn = (grupo) => { const b = document.querySelector(`#ventana-crear [data-grupo="${grupo}"] [aria-pressed="true"]`); return b ? b.dataset.valor : null; };

  function revisarVentanaCrear() {
    const falta = !elegidoEn("nivel");
    $("crear-imagenes").disabled = falta;
    $("falta-dificultad").hidden = !falta;
  }

  function abrirVentanaCrear() {
    document.querySelectorAll('#ventana-crear [data-grupo="nivel"] .opcion-crear').forEach((b) => b.setAttribute("aria-pressed", "false"));
    revisarVentanaCrear();
    $("ventana-crear").showModal();
  }

  async function crearImagenes() {
    const tipo = elegidoEn("tipo"), nivel = elegidoEn("nivel"), cantidad = Number(elegidoEn("cantidad"));
    if (!nivel) return;
    const boton = $("crear-imagenes");
    boton.disabled = true;
    boton.replaceChildren(el("span", { clase: "cargando" }), " Creando…");
    try {
      const r = await App.lento("/api/ficticios/ampliar", JSON_POST({ cantidad, tipo, nivel }), { boton });
      nuevas = new Set(["numeros", "formularios"].flatMap((c) => r.nuevas[c].map((n) => c + "/" + n)));
      guardarNuevas();
      cambiarPestana(tipo === "formularios" ? "formularios" : "numeros");
      $("orden-galeria").value = "nuevas";
      $("filtro-nivel").value = "";
      await cargarBanco();
      $("ventana-crear").close();
      $("aviso-nuevas").scrollIntoView({ behavior: "smooth", block: "center" });
      avisar(tipo === "formularios" ? `Listo: ${plural(r.formularios, "formulario nuevo", "formularios nuevos")}.`
        : tipo === "cuadriculado" ? `Listo: ${plural(r.cuadriculadas, "foto de número", "fotos de números")} en hoja cuadriculada o rayada.`
          : `Listo: ${plural(r.numeros, "foto de número nueva", "fotos de números nuevas")}.`, "ok");
    } catch (e) { avisar(e.message, "error", 7000); } finally {
      boton.textContent = "Crear";
      revisarVentanaCrear();
    }
  }

  function elegirNuevas() {
    const lista = banco[pestana].filter((x) => esNueva(pestana, x));
    lista.forEach((x) => seleccion.add(x.nombre));
    $("orden-galeria").value = "nuevas";
    $("filtro-nivel").value = "";
    visibles = Math.max(visibles, lista.length);
    pintarGaleria();
  }

  /* ---------- Basura de imágenes ---------- */
  function ponerVersion(version) {
    const insignia = document.querySelector(".insignia-version strong");
    if (insignia && version) insignia.textContent = version;
  }

  /* Boton que pide una segunda pulsacion antes de borrar algo para siempre. */
  function conConfirmacion(boton, texto, accion) {
    boton.addEventListener("click", () => {
      if (boton.dataset.confirmar !== "1") {
        boton.dataset.confirmar = "1";
        boton.textContent = "¿Seguro? Se borra para siempre. Pulsa otra vez";
        setTimeout(() => { boton.dataset.confirmar = ""; boton.textContent = texto; }, 5000);
        return;
      }
      boton.dataset.confirmar = "";
      boton.textContent = texto;
      accion();
    });
    return boton;
  }

  async function accionBasura(pedido, mensaje) {
    try {
      const r = await pedido();
      await Promise.all([cargarBanco(), cargarBasura()]);
      avisar(mensaje(r), "ok", 6000);
    } catch (e) { avisar(e.message, "error", 7000); }
  }

  function pintarBasura() {
    $("lista-basura-imagenes").replaceChildren(...basura.map((x) => {
      const cuerpo = { carpeta: x.carpeta, nombres: [x.nombre] };
      return el("li", { clase: "version-fila" },
        el("img", { clase: "mini-basura", src: `/ficticios-img/${x.carpeta}/${x.nombre}?ancho=120&basura=1`, alt: "", loading: "lazy" }),
        el("div", { clase: "version-info" }, el("strong", { texto: x.texto }), el("small", { texto: x.carpeta === "numeros" ? "Foto de número" : "Formulario" })),
        el("button", { type: "button", clase: "boton boton-pequeno", texto: "Restaurar",
          en: { click: () => accionBasura(() => api("/api/ficticios/basura/restaurar", JSON_POST(cuerpo)), () => "Restauré la imagen: ya está otra vez en la galería.") } }),
        conConfirmacion(el("button", { type: "button", clase: "boton boton-pequeno boton-peligro-suave", texto: "Borrar para siempre" }), "Borrar para siempre",
          () => accionBasura(() => api("/api/ficticios/basura/borrar-para-siempre", JSON_POST(cuerpo)), () => "Borré la imagen para siempre.")));
    }));
    $("basura-imagenes-vacia").hidden = basura.length > 0;
    $("vaciar-basura-imagenes").hidden = basura.length === 0;
    $("contador-basura-imagenes").hidden = basura.length === 0;
    $("contador-basura-imagenes").textContent = String(basura.length);
  }

  async function cargarBasura() {
    basura = (await api("/api/ficticios/basura")).basura;
    pintarBasura();
  }

  function mandarALaBasura() {
    const nombres = [...seleccion];
    accionBasura(() => api("/api/ficticios/quitar", JSON_POST({ carpeta: pestana, nombres })).then((r) => { seleccion.clear(); return r; }),
      (r) => `Mandé ${plural(r.quitadas.length, "imagen", "imágenes")} a la basura. Puedes restaurarlas desde el botón «Basura».`);
  }

  /* ---------- Entrenar con las imágenes elegidas ---------- */
  function pintarEntrenamiento(r) {
    const chips = r.marcador.map((f) => {
      const m = modelos.find((x) => x.clave === f.modelo);
      return el("div", { clase: "chip-modelo", estilo: { "--color": m.color } }, m.nombre, el("small", { texto: `${f.digitos_ok}/${f.digitos} dígitos${f.digitos_ok < f.digitos ? " · se equivocó" : ""}` }));
    });
    $("tarjeta-entrenamiento").hidden = false;
    $("resultado-practica").replaceChildren(
      el("h3", { texto: `Los siete modelos leyeron ${plural(r.fotos, "imagen", "imágenes")}`, estilo: { "margin-bottom": "10px" } }),
      el("div", { clase: "chips", estilo: { "margin-bottom": "16px" } }, chips),
      r.correccion ? App.tablaCorreccion(r.correccion) : el("p", { clase: "insignia ok", texto: r.mensaje }),
      el("p", { estilo: { color: "var(--tinta-suave)", "margin-top": "12px", "font-size": "0.9rem" } }, "Estas imágenes quedan guardadas como una tanda en ", el("a", { href: "/", texto: "Leer formulario" }), "."));
    if (r.correccion) ponerVersion(r.correccion.version_nueva);
    $("tarjeta-entrenamiento").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function entrenarElegidas() {
    const boton = $("entrenar-elegidas");
    entrenando = true;
    boton.disabled = true;
    boton.replaceChildren(el("span", { clase: "cargando" }), " Entrenando…");
    try {
      const r = await App.ejecutarTarea("/api/tareas/ficticios-entrenar", { nombres: [...seleccion] }, { boton });
      seleccion.clear();
      pintarEntrenamiento(r);
      const version = r.correccion && r.correccion.version_nueva;
      avisar(version ? `Listo: ahora usas la versión ${version}.` : (r.correccion ? r.correccion.mensaje : r.mensaje), version ? "ok" : "info", 7000);
    } catch (e) {
      avisar(e.message, "error", 7000);
    } finally {
      entrenando = false;
      pintarGaleria();
    }
  }

  (async function iniciar() {
    $("leer-formulario").addEventListener("click", leer);
    $("filtro-nivel").addEventListener("change", () => { visibles = POR_PAGINA; pintarGaleria(); });
    $("orden-galeria").addEventListener("change", () => { visibles = POR_PAGINA; pintarGaleria(); });
    $("mostrar-mas").addEventListener("click", () => { visibles += POR_PAGINA; pintarGaleria(); });
    $("abrir-crear").addEventListener("click", abrirVentanaCrear);
    $("cancelar-crear").addEventListener("click", () => $("ventana-crear").close());
    $("crear-imagenes").addEventListener("click", crearImagenes);
    $("ventana-crear").addEventListener("click", (e) => {
      const boton = e.target.closest(".opcion-crear");
      if (!boton) return;
      boton.parentElement.querySelectorAll(".opcion-crear").forEach((b) => b.setAttribute("aria-pressed", String(b === boton)));
      revisarVentanaCrear();
    });
    $("elegir-nuevas").addEventListener("click", elegirNuevas);
    $("cerrar-aviso-nuevas").addEventListener("click", () => { nuevas.clear(); guardarNuevas(); pintarGaleria(); });
    $("quitar-marcas").addEventListener("click", () => { seleccion.clear(); pintarGaleria(); });
    $("mandar-basura").addEventListener("click", mandarALaBasura);
    $("entrenar-elegidas").addEventListener("click", entrenarElegidas);
    $("abrir-basura-imagenes").addEventListener("click", () => {
      const panel = $("panel-basura-imagenes");
      panel.hidden = !panel.hidden;
      $("abrir-basura-imagenes").setAttribute("aria-expanded", String(!panel.hidden));
    });
    conConfirmacion($("vaciar-basura-imagenes"), "Vaciar la basura",
      () => accionBasura(() => api("/api/ficticios/basura/vaciar", { method: "POST" }), (r) => `Vacié la basura: ${plural(r.borradas, "imagen borrada", "imágenes borradas")}.`));
    try { await Promise.all([cargarBanco(), cargarBasura()]); } catch (e) { avisar(e.message, "error"); }
    if (nuevas.size) $("acordeon-galeria").open = true;
    const tarea = await App.tareaDeLaUrl();
    if (!tarea || (tarea.tipo !== "corregir" && tarea.tipo !== "entrenar")) return;
    if (tarea.estado === "error") { avisar(tarea.error, "error", 8000); return; }
    if (tarea.tipo === "entrenar") { pintarEntrenamiento(tarea.resultado); return; }
    $("tarjeta-entrenamiento").hidden = false;
    $("resultado-practica").replaceChildren(el("h3", { texto: "Resultado de la corrección que dejaste en marcha", estilo: { "margin-bottom": "10px" } }), App.tablaCorreccion(tarea.resultado));
    $("tarjeta-entrenamiento").scrollIntoView({ behavior: "smooth", block: "start" });
    ponerVersion(tarea.resultado.version_nueva);
  })();
})();
