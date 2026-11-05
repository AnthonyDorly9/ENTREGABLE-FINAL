(function () {
  const App = (window.App = {});

  App.el = function (etiqueta, atributos, ...hijos) {
    const nodo = document.createElement(etiqueta);
    for (const [nombre, valor] of Object.entries(atributos || {})) {
      if (valor === null || valor === undefined || valor === false) continue;
      if (nombre === "clase") nodo.className = valor;
      else if (nombre === "estilo") for (const [k, v] of Object.entries(valor)) nodo.style.setProperty(k, v);
      else if (nombre === "en") for (const [evento, funcion] of Object.entries(valor)) nodo.addEventListener(evento, funcion);
      else if (nombre === "texto") nodo.textContent = valor;
      else nodo.setAttribute(nombre, valor === true ? "" : valor);
    }
    for (const hijo of hijos.flat()) {
      if (hijo === null || hijo === undefined || hijo === false) continue;
      nodo.append(hijo.nodeType ? hijo : document.createTextNode(String(hijo)));
    }
    return nodo;
  };

  // Nombre de una tanda con su fecha y hora exacta (lote_2026-09-20_143651 → «20/09/2026 · 14:36:51»), para no
  // confundir tandas del mismo día. Si dos tandas empezaron en el mismo segundo, la segunda lleva «(2)».
  App.nombreTanda = function (lote) {
    const m = /^lote_(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})(b*)$/.exec(lote || "");
    if (!m) return String(lote || "").replace("lote_", "");
    return `${m[3]}/${m[2]}/${m[1]} · ${m[4]}:${m[5]}:${m[6]}` + (m[7] ? ` (${m[7].length + 1})` : "");
  };

  /* Si una peticion corriente tarda mas de lo normal, la campana de arriba avisa de que la aplicacion esta trabajando. */
  const lentas = new Map();
  let serieLentas = 0;
  const SIN_AVISO = /^\/api\/(tareas|entrenador\/estado)/;

  App.api = async function (url, opciones) {
    const clave = ++serieLentas;
    const callada = SIN_AVISO.test(url) || (opciones && opciones.headers && opciones.headers["X-Tarea"]);
    const reloj = callada ? null : setTimeout(() => {
      lentas.set(clave, { id: "lenta-" + clave, estado: "en_curso", titulo: "Trabajando", progreso: null, falta: null, paso: null, creada: 0 });
      repintar();
    }, 1200);
    try {
      let respuesta;
      try {
        respuesta = await fetch(url, opciones);
      } catch (e) {
        throw new Error("No se pudo conectar con el servidor. ¿Sigue abierta la aplicación?");
      }
      let datos = null;
      try { datos = await respuesta.json(); } catch (e) { /* respuesta sin JSON */ }
      if (!respuesta.ok) throw new Error((datos && datos.error) || "Algo salió mal (" + respuesta.status + ").");
      return datos;
    } finally {
      clearTimeout(reloj);
      if (lentas.delete(clave)) repintar();
    }
  };

  App.avisar = function (texto, tipo, ms) {
    const contenedor = document.getElementById("avisos");
    const aviso = App.el("div", { clase: "aviso " + (tipo || ""), texto });
    contenedor.append(aviso);
    setTimeout(() => {
      aviso.classList.add("saliendo");
      setTimeout(() => aviso.remove(), 220);
    }, ms || 4600);
  };

  App.avisarConEnlace = function (texto, href, etiqueta, ms, alTocar) {
    const contenedor = document.getElementById("avisos");
    const enlace = App.el("a", { href, clase: "enlace-aviso", texto: etiqueta, en: alTocar ? { click: alTocar } : null });
    const aviso = App.el("div", { clase: "aviso ok con-enlace" }, App.el("span", { texto }), enlace);
    contenedor.append(aviso);
    setTimeout(() => { aviso.classList.add("saliendo"); setTimeout(() => aviso.remove(), 220); }, ms || 14000);
    try {
      if ("Notification" in window && Notification.permission === "granted" && document.hidden) new Notification(texto);
    } catch (e) { /* sin notificaciones del sistema */ }
  };

  /* ---------- Tareas en segundo plano ----------
     Los procesos largos corren en el servidor y cuentan cuanto llevan, en que paso van y cuanto falta.
     - Arriba, la campana: un anillo que se llena; al tocarla se abre la lista de tareas con su barra.
     - En la seccion de la tarea, el boton que la lanzo se va llenando con el porcentaje.
     - Al terminar: si la persona esta en la seccion de la tarea, ve el resultado ahi y la campana se limpia sola, sin sonido;
       si esta en otra seccion, suena un aviso y queda en la campana hasta «Ver resultado» o hasta entrar a esa seccion. */
  const crear = App.el;
  const aqui = location.pathname;
  const tareasLocales = new Map();
  const vistasEnMarcha = new Set();
  const alEntrar = fetch("/api/tareas").then((r) => r.json()).catch(() => ({ tareas: [] }));
  let sondeo = null;
  let sondeando = false;
  let ultimas = [];
  let firmaPanel = "";
  /* Tareas que acaban de terminar: se ven un instante al 100 % antes del aviso «Ya terminamos». */
  const recienAcabadas = new Map();

  App.tiempo = function (segundos) {
    if (segundos === null || segundos === undefined) return "";
    const s = Math.max(1, Math.round(segundos));
    if (s < 60) return `falta ${s} s`;
    const m = Math.floor(s / 60);
    return m < 60 ? `falta ${m} min ${String(s % 60).padStart(2, "0")} s` : `falta ${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
  };
  const medida = (t) => t.progreso !== null && t.progreso !== undefined;
  const porciento = (t) => (medida(t) ? Math.floor(t.progreso * 100) + " %" : "");

  /* Aviso sonoro de tres segundos: cuatro notas suaves que suben. Lo genera el navegador, sin archivos. */
  let audio = null;
  function prepararAudio() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume().catch(() => {});
    } catch (e) { audio = null; }
    return audio;
  }
  document.addEventListener("pointerdown", prepararAudio, { once: true });
  document.addEventListener("keydown", prepararAudio, { once: true });

  App.sonarAviso = function () {
    if (!prepararAudio()) return;
    const tocar = () => {
      const inicio = audio.currentTime + 0.05;
      [[659.25, 0], [830.61, 0.45], [987.77, 0.9], [1318.51, 1.35]].forEach(([frecuencia, cuando]) => {
        const nota = audio.createOscillator();
        const volumen = audio.createGain();
        nota.type = "sine";
        nota.frequency.value = frecuencia;
        volumen.gain.setValueAtTime(0.0001, inicio + cuando);
        volumen.gain.exponentialRampToValueAtTime(0.22, inicio + cuando + 0.03);
        volumen.gain.exponentialRampToValueAtTime(0.0001, inicio + cuando + 1.6);
        nota.connect(volumen).connect(audio.destination);
        nota.start(inicio + cuando);
        nota.stop(inicio + cuando + 1.65);
      });
    };
    if (audio.state === "running") tocar();
    else audio.resume().then(tocar).catch(() => {});
  };

  /* El boton que lanzo la tarea se llena de color con el porcentaje; debajo, el paso y lo que falta. */
  function pintarBoton(boton, t) {
    if (!boton || !boton.isConnected) return;
    if (!boton._avance) {
      const linea = crear("span", { clase: "linea-avance" }, crear("span", { clase: "paso-avance" }), crear("span", { clase: "falta-avance" }));
      boton._avance = { hijos: [...boton.childNodes], linea, apagado: boton.disabled,
        titulo: crear("span", { clase: "titulo-avance" }), pct: crear("strong", { clase: "pct-avance" }) };
    }
    const partes = boton._avance;
    /* Si la pagina repinto el boton mientras tanto, se vuelve a poner el avance. */
    if (!boton.contains(partes.linea)) boton.replaceChildren(partes.titulo, partes.pct, partes.linea);
    boton.classList.add("llenandose");
    boton.setAttribute("aria-busy", "true");
    boton.disabled = true;
    boton.classList.toggle("sin-medida", !medida(t));
    boton.style.setProperty("--avance", medida(t) ? t.progreso : 0);
    partes.titulo.textContent = t.titulo;
    partes.pct.textContent = porciento(t);
    partes.linea.children[0].textContent = t.paso || "";
    partes.linea.children[1].textContent = App.tiempo(t.falta);
    /* La linea de debajo nunca se sale de la pantalla: si el texto es largo baja a otro renglon y el boton le deja sitio. */
    const caja = boton.getBoundingClientRect();
    const libre = window.innerWidth - caja.left - 20;
    const haciaLaDerecha = libre >= 240 || libre >= caja.right - 20;
    partes.linea.style.left = haciaLaDerecha ? "4px" : "auto";
    partes.linea.style.right = haciaLaDerecha ? "auto" : "4px";
    partes.linea.style.maxWidth = Math.max(160, haciaLaDerecha ? libre : caja.right - 20) + "px";
    boton.style.marginBottom = partes.linea.offsetHeight + 12 + "px";
  }

  function soltarBoton(boton) {
    if (!boton || !boton._avance) return;
    boton.classList.remove("llenandose", "sin-medida");
    boton.style.removeProperty("--avance");
    boton.style.removeProperty("margin-bottom");
    boton.removeAttribute("aria-busy");
    boton.disabled = boton._avance.apagado;
    boton.replaceChildren(...boton._avance.hijos);
    boton._avance = null;
  }

  const botonDe = (t) => (t.origen ? document.querySelector(`[data-tarea="${t.origen}"]`) : null);

  /* Al terminar, el botón se llena hasta 100 % un instante antes de volver a ser botón: así se ve que acabó. */
  async function llenarYSoltar(boton, t) {
    if (boton && boton._avance && boton.isConnected && t.estado !== "error") {
      pintarBoton(boton, { ...t, progreso: 1, falta: null, paso: "Listo" });
      await new Promise((listo) => setTimeout(listo, 700));
    }
    soltarBoton(boton);
  }

  function barraTarea(t) {
    return crear("span", { clase: "pista-tarea" + (medida(t) ? "" : " sin-medida"), role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100",
      "aria-valuenow": medida(t) ? String(Math.floor(t.progreso * 100)) : null, "aria-label": t.titulo },
      crear("span", { clase: "relleno-tarea", estilo: { "--avance": medida(t) ? t.progreso : 0 } }));
  }

  function filaTarea(t) {
    if (t.estado === "en_curso") {
      return crear("div", { clase: "fila-tarea", "data-id": t.id },
        crear("strong", { clase: "titulo-tarea", texto: t.titulo }), crear("span", { clase: "paso-tarea", texto: t.paso || "" }), barraTarea(t),
        crear("span", { clase: "pie-tarea" }, crear("strong", { clase: "pct-tarea", texto: porciento(t) || "Trabajando…" }), crear("span", { clase: "falta-tarea", texto: App.tiempo(t.falta) })));
    }
    if (t.estado === "error") {
      return crear("div", { clase: "fila-tarea con-error", "data-id": t.id },
        crear("strong", { texto: `No se pudo terminar ${t.final || t.titulo}` }), crear("span", { clase: "paso-tarea", texto: t.error || "" }),
        crear("button", { type: "button", clase: "enlace-tarea", texto: "Quitar aviso", en: { click: () => { App.silenciarTarea(t.id); t.vista = true; repintar(); } } }));
    }
    return crear("div", { clase: "fila-tarea lista", "data-id": t.id },
      crear("strong", { texto: `Ya terminamos: ${t.final || t.titulo}` }),
      crear("a", { clase: "enlace-tarea", href: t.url || t.pagina || "#", texto: t.etiqueta || "Ver resultado", en: { click: () => App.silenciarTarea(t.id) } }));
  }

  function actualizarFila(fila, t) {
    fila.querySelector(".paso-tarea").textContent = t.paso || "";
    fila.querySelector(".pct-tarea").textContent = porciento(t) || "Trabajando…";
    fila.querySelector(".falta-tarea").textContent = App.tiempo(t.falta);
    const pista = fila.querySelector(".pista-tarea");
    pista.classList.toggle("sin-medida", !medida(t));
    if (medida(t)) pista.setAttribute("aria-valuenow", String(Math.floor(t.progreso * 100)));
    pista.firstChild.style.setProperty("--avance", medida(t) ? t.progreso : 0);
  }

  const campana = document.getElementById("campana");
  const botonCampana = document.getElementById("boton-campana");
  const panelTareas = document.getElementById("panel-tareas");
  function abrirPanel(abierto) {
    if (!panelTareas) return;
    panelTareas.hidden = !abierto;
    botonCampana.setAttribute("aria-expanded", String(abierto));
  }
  if (botonCampana) {
    botonCampana.addEventListener("click", () => abrirPanel(panelTareas.hidden));
    document.addEventListener("click", (e) => { if (!panelTareas.hidden && !campana.contains(e.target)) abrirPanel(false); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !panelTareas.hidden) { abrirPanel(false); botonCampana.focus(); } });
  }

  function pintarCampana(visibles) {
    const punto = document.getElementById("punto-tareas");
    const enMarcha = visibles.filter((t) => t.estado === "en_curso");
    const conError = visibles.some((t) => t.estado === "error");
    if (punto) {
      punto.hidden = visibles.length === 0;
      punto.className = "punto-tareas " + (enMarcha.length ? "en-curso" : conError ? "" : "lista");
    }
    if (!campana) return;
    campana.hidden = visibles.length === 0;
    if (!visibles.length) { abrirPanel(false); firmaPanel = ""; return; }

    const primera = enMarcha.find(medida) || enMarcha[0];
    const anillo = document.getElementById("anillo-tareas");
    const texto = document.getElementById("texto-campana");
    botonCampana.className = "boton-campana " + (primera ? (medida(primera) ? "" : "sin-medida") : conError ? "con-error" : "lista");
    anillo.style.setProperty("--avance", primera ? (medida(primera) ? primera.progreso : 0) : 1);
    let partes;
    if (primera) {
      partes = [crear("strong", { texto: porciento(primera) || "Trabajando…" }), crear("span", { clase: "falta-campana", texto: App.tiempo(primera.falta) }),
        enMarcha.length > 1 ? crear("span", { clase: "cuenta-campana", texto: `${enMarcha.length} tareas` }) : null];
      botonCampana.setAttribute("aria-label", `${primera.titulo}: ${porciento(primera) || "trabajando"}. ${App.tiempo(primera.falta)}. Abrir la lista de tareas`);
    } else {
      const frase = conError ? "No se pudo terminar" : visibles.length === 1 ? "Ya terminamos" : `${visibles.length} terminadas`;
      partes = [crear("strong", { texto: frase })];
      botonCampana.setAttribute("aria-label", frase + ". Abrir la lista de tareas");
    }
    texto.replaceChildren(...partes.filter(Boolean));

    /* La lista solo se rehace cuando cambian sus filas: asi las barras avanzan sin saltos. */
    const firma = visibles.map((t) => t.id + ":" + t.estado).join("|");
    if (firma !== firmaPanel) {
      firmaPanel = firma;
      panelTareas.replaceChildren(...visibles.map(filaTarea));
    } else {
      for (const t of enMarcha) {
        const fila = panelTareas.querySelector(`[data-id="${t.id}"]`);
        if (fila) actualizarFila(fila, t);
      }
    }
  }

  function pintarMenu(visibles) {
    const contenedor = document.getElementById("tareas-menu");
    if (!contenedor) return;
    contenedor.hidden = visibles.length === 0;
    contenedor.replaceChildren(...visibles.map((t) => t.estado === "en_curso"
      ? crear("div", { clase: "tarea-menu en-curso" }, crear("span", { texto: t.titulo }),
          crear("strong", { texto: [porciento(t) || "Trabajando…", App.tiempo(t.falta)].filter(Boolean).join(" · ") }))
      : crear("div", { clase: "tarea-menu " + (t.estado === "error" ? "con-error" : "lista") },
          crear("span", { texto: t.estado === "error" ? `No se pudo terminar ${t.final || t.titulo}` : `Ya terminamos: ${t.final || t.titulo}` }),
          t.estado === "error" ? null : crear("a", { href: t.url || t.pagina || "#", texto: t.etiqueta || "Ver resultado", en: { click: () => App.silenciarTarea(t.id) } }))));
  }

  /* Una tarea recien lanzada no se muestra hasta pasado un instante: las que acaban enseguida no hacen parpadear la campana. */
  function repintar() {
    const ahora = Date.now() / 1000;
    const llenas = [];
    for (const [id, cuando] of recienAcabadas) {
      const t = ultimas.find((u) => u.id === id);
      if (t && Date.now() - cuando < 900) llenas.push({ ...t, estado: "en_curso", progreso: 1, falta: null, paso: "Listo" });
      else recienAcabadas.delete(id);
    }
    if (llenas.length) setTimeout(repintar, 950);
    const visibles = [...lentas.values()].concat(llenas, ultimas.filter((t) => !recienAcabadas.has(t.id) && (t.estado === "en_curso"
      ? ahora - t.creada > 0.7
      : !t.vista && !tareasLocales.has(t.id))));
    pintarCampana(visibles);
    pintarMenu(visibles);
  }

  async function entregar(t, local) {
    try {
      if (t.estado === "error") { await App.api(`/api/tareas/${t.id}/vista`, { method: "POST" }); local.rechazar(new Error(t.error)); return; }
      const detalle = await App.api(`/api/tareas/${t.id}`);
      await App.api(`/api/tareas/${t.id}/vista`, { method: "POST" });
      local.resolver({ ...(detalle.resultado || {}), _tarea: t.id });
    } catch (e) { local.rechazar(e); }
  }

  function avisarFin(t, enSuSeccion) {
    if (t.estado === "error") {
      App.avisar(`No se pudo terminar ${t.final || t.titulo}. ${t.error}`, "error", 12000);
    } else if (!enSuSeccion || (t.url || "").includes("?tarea=")) {
      App.avisarConEnlace(`Ya terminamos: ${t.final || t.titulo}.`, t.url || t.pagina || "#", t.etiqueta || "Ver resultado", null, () => App.silenciarTarea(t.id));
    } else {
      App.avisar(`Ya terminamos: ${t.final || t.titulo}.`, "ok", 7000);
    }
    if (!enSuSeccion) App.sonarAviso();
  }

  async function sondear() {
    sondeo = null;
    sondeando = true;
    let datos;
    try { datos = await App.api("/api/tareas"); } catch (e) { sondeando = false; sondeo = setTimeout(sondear, 5000); return; }
    for (const t of datos.tareas) {
      const local = tareasLocales.get(t.id);
      if (t.estado === "en_curso") {
        vistasEnMarcha.add(t.id);
        pintarBoton((local && local.boton) || botonDe(t), t);
        continue;
      }
      if (local) {
        tareasLocales.delete(t.id);
        if (vistasEnMarcha.delete(t.id) && t.estado === "terminado") recienAcabadas.set(t.id, Date.now());
        await llenarYSoltar(local.boton || botonDe(t), t);
        t.vista = true;
        await entregar(t, local);
        continue;
      }
      if (vistasEnMarcha.delete(t.id)) {
        if (t.estado === "terminado") recienAcabadas.set(t.id, Date.now());
        await llenarYSoltar(botonDe(t), t);
      }
      const enSuSeccion = t.pagina === aqui;
      /* Una carga corta que nadie espera ya (la persona cambio de seccion enseguida) no merece aviso. */
      if (!t.notificada && t.estado === "terminado" && t.etiqueta === "Ir a la sección" && t.terminada - t.creada < 3) {
        await App.api(`/api/tareas/${t.id}/vista`, { method: "POST" }).catch(() => {});
        t.notificada = true;
        t.vista = true;
        continue;
      }
      if (!t.notificada) {
        await App.api(`/api/tareas/${t.id}/notificada`, { method: "POST" }).catch(() => {});
        t.notificada = true;
        avisarFin(t, enSuSeccion);
      }
      if (enSuSeccion && !t.vista) {
        await App.api(`/api/tareas/${t.id}/vista`, { method: "POST" }).catch(() => {});
        t.vista = true;
      }
    }
    ultimas = datos.tareas;
    repintar();
    sondeando = false;
    if (tareasLocales.size || datos.tareas.some((t) => t.estado === "en_curso")) sondeo = setTimeout(sondear, 1000);
  }

  function asegurarSondeo(ms) {
    if (!sondeo && !sondeando) sondeo = setTimeout(sondear, ms || 800);
  }

  function esperar(tarea, extra) {
    const boton = (extra && extra.boton) || null;
    return new Promise((resolver, rechazar) => {
      tareasLocales.set(tarea.id, { resolver, rechazar, boton });
      if (boton) pintarBoton(boton, tarea);
      asegurarSondeo(300);
    });
  }

  /* Lanza una tarea y devuelve una promesa con su resultado (solo si la persona sigue en esta pagina).
     Con `extra.boton`, ese boton se va llenando mientras dura. */
  App.ejecutarTarea = async function (url, cuerpo, extra) {
    const tarea = await App.api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo || {}) });
    return esperar(tarea, extra);
  };

  /* Igual que App.api, pero para rutas que pueden tardar: corren como tarea, con barra de avance y aviso al terminar. */
  App.lento = async function (url, opciones, extra) {
    const pedido = { ...(opciones || {}) };
    pedido.headers = { ...(pedido.headers || {}), "X-Tarea": "1" };
    const tarea = await App.api(url, pedido);
    if (!tarea || !tarea.id || !tarea.estado || tarea.progreso === undefined) return tarea;
    return esperar(tarea, extra);
  };

  /* Prepara un archivo como tarea y lo descarga cuando esta listo. */
  App.descargarTarea = async function (url, cuerpo, extra) {
    const r = await App.ejecutarTarea(url, cuerpo, extra);
    const enlace = crear("a", { href: `/api/tareas/${r._tarea}/archivo`, download: r.nombre || "" });
    document.body.append(enlace);
    enlace.click();
    enlace.remove();
    return r;
  };

  /* Devuelve la tarea terminada que hay que mostrar al entrar: la de «Ver resultado» (?tarea=ID) o, si la persona
     entro a la seccion por el menu, la ultima de esta seccion que aun no vio. La marca como vista. */
  App.tareaDeLaUrl = async function () {
    let id = new URLSearchParams(location.search).get("tarea");
    if (!id) {
      const pendiente = (await alEntrar).tareas.filter((t) => t.estado === "terminado" && !t.vista && (t.url || "").startsWith(aqui + "?tarea=")).pop();
      if (!pendiente) return null;
      id = pendiente.id;
    }
    try {
      const tarea = await App.api(`/api/tareas/${id}`);
      await App.api(`/api/tareas/${id}/vista`, { method: "POST" });
      history.replaceState(null, "", location.pathname);
      return tarea;
    } catch (e) {
      App.avisar(e.message, "error");
      return null;
    }
  };

  App.silenciarTarea = function (id) {
    if (id) App.api(`/api/tareas/${id}/vista`, { method: "POST" }).catch(() => {});
  };

  asegurarSondeo();

  App.porcentaje = function (valor, decimales) {
    return (valor * 100).toFixed(decimales === undefined ? 1 : decimales).replace(".", ",") + " %";
  };

  /* Tabla ordenada con el resultado de corregir modelos: solo los que aprendieron, y aparte los que no necesitaron cambios. */
  App.tablaCorreccion = function (informe) {
    const { el, porcentaje } = App;
    const modelos = App.modelos();
    const info = Object.fromEntries(modelos.map((m) => [m.clave, m]));
    const r = informe.resumen;
    const entrenados = informe.informe.filter((i) => i.entrenado);
    const sinCambios = informe.informe.filter((i) => !i.entrenado);
    const conReserva = entrenados.some((i) => i.reserva_antes);
    const conAnteriores = entrenados.some((i) => i.anteriores_antes);
    const par = (antes, despues) => {
      if (!antes || !despues) return "—";
      return el("span", { clase: despues[0] > antes[0] ? "sube" : despues[0] < antes[0] ? "baja" : "" }, `${antes[0]}/${antes[1]} → ${despues[0]}/${despues[1]}`);
    };
    const nombreModelo = (m) => el("span", { clase: "modelo-nombre" }, el("span", { clase: "punto" }), m.nombre);

    const columnas = ["Modelo", "Resultado", "Aciertos en estas imágenes"].concat(conReserva ? ["Fotos reservadas"] : [], ["Exactitud en MNIST"], conAnteriores ? ["Dígitos de tandas anteriores"] : []);
    const filas = entrenados.map((i) => {
      const m = info[i.modelo];
      const estado = i.aceptado
        ? el("span", { clase: "insignia ok", texto: `Mejoró · ${i.corregidos} ${i.corregidos === 1 ? "dígito corregido" : "dígitos corregidos"}` })
        : el("span", { clase: "insignia mal", texto: "No se guardó" });
      const celdas = [
        el("th", { scope: "row" }, nombreModelo(m)),
        el("td", null, estado, !i.aceptado && i.motivo ? el("p", { clase: "motivo", texto: i.motivo }) : null),
        el("td", { clase: "num" }, par(i.entrenamiento_antes, i.entrenamiento_despues)),
      ];
      if (conReserva) celdas.push(el("td", { clase: "num" }, par(i.reserva_antes, i.reserva_despues)));
      celdas.push(el("td", { clase: "num" }, i.mnist_antes !== undefined
        ? el("span", { clase: i.mnist_despues > i.mnist_antes ? "sube" : i.mnist_despues < i.mnist_antes ? "baja" : "" }, `${porcentaje(i.mnist_antes, 2)} → ${porcentaje(i.mnist_despues, 2)}`) : "—"));
      if (conAnteriores) celdas.push(el("td", { clase: "num" }, par(i.anteriores_antes, i.anteriores_despues)));
      return el("tr", { estilo: { "--color": m.color } }, celdas);
    });

    const reservadas = r.digitos_reserva
      ? ` y se comprobó con ${r.digitos_reserva} dígitos${r.nombres_reserva && r.nombres_reserva.length ? ` de ${r.nombres_reserva.length === 1 ? "la foto reservada" : "las fotos reservadas"} (${r.nombres_reserva.join(", ")})` : " que no usaron para aprender"}`
      : "";
    return el("div", { clase: "resultado-correccion" },
      el("h3", { texto: informe.version_nueva ? `Listo: nueva versión ${informe.version_nueva}` : "Sin cambios" }),
      el("p", { clase: "resumen-correccion", texto: informe.version_nueva
        ? `Aprendieron de ${r.digitos_entrenamiento} dígitos${reservadas}. La versión ${informe.version_nueva} ya está activa y se conserva aunque cierres la aplicación.`
        : informe.mensaje }),
      filas.length ? el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-informe tabla-correccion" },
        el("caption", { clase: "solo-lectores", texto: "Antes y después de la corrección, por modelo" }),
        el("thead", null, el("tr", null, columnas.map((t) => el("th", { scope: "col", texto: t })))),
        el("tbody", null, filas))) : null,
      sinCambios.length ? el("div", { clase: "sin-cambios" },
        el("span", { texto: "Sin cambios porque no se equivocaron:" }),
        sinCambios.map((i) => el("span", { clase: "mini-chip", estilo: { "--color": info[i.modelo].color } }, el("span", { clase: "punto" }), info[i.modelo].corto || info[i.modelo].nombre))) : null);
  };

  App.modelos = function () {
    const nodo = document.getElementById("datos-modelos");
    return nodo ? JSON.parse(nodo.textContent) : [];
  };

  /* Menu hamburguesa: se abre y se cierra para que la pagina ocupe todo el ancho. */
  const menu = document.getElementById("menu");
  const abrir = document.getElementById("abrir-menu");
  const velo = document.getElementById("velo-menu");
  const cerrar = document.getElementById("cerrar-menu");
  function cambiarMenu(abierto, devolverFoco) {
    menu.classList.toggle("abierto", abierto);
    if (velo) velo.classList.toggle("abierto", abierto);
    if (abrir) abrir.setAttribute("aria-expanded", String(abierto));
    if (abierto && cerrar) cerrar.focus();
    if (!abierto && devolverFoco && abrir) abrir.focus();
  }
  const cerrarMenu = (devolverFoco) => cambiarMenu(false, devolverFoco === true);
  if (abrir) {
    abrir.addEventListener("click", () => cambiarMenu(!menu.classList.contains("abierto")));
    if (cerrar) cerrar.addEventListener("click", () => cerrarMenu(true));
    if (velo) velo.addEventListener("click", () => cerrarMenu(false));
    menu.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => cerrarMenu(false)));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && menu.classList.contains("abierto")) cerrarMenu(true); });
  }

  const botonDatos = document.getElementById("abrir-datos");
  if (botonDatos) {
    botonDatos.addEventListener("click", async () => {
      try {
        const r = await App.api("/api/carpeta-datos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ que: "datos" }) });
        App.avisar("Abrí la carpeta de tus datos: " + r.carpeta, "ok", 7000);
      } catch (e) { App.avisar(e.message, "error", 9000); }
    });
  }

  const botonTema = document.getElementById("cambiar-tema");
  function temaActual() {
    return document.documentElement.dataset.tema || (matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro");
  }
  function pintarTema() {
    if (botonTema) botonTema.textContent = temaActual() === "oscuro" ? "Claro" : "Oscuro";
  }
  if (botonTema) {
    botonTema.addEventListener("click", () => {
      const nuevo = temaActual() === "oscuro" ? "claro" : "oscuro";
      document.documentElement.dataset.tema = nuevo;
      try { localStorage.setItem("tema", nuevo); } catch (e) { /* almacenamiento no disponible */ }
      pintarTema();
      document.dispatchEvent(new CustomEvent("tema-cambiado"));
    });
    pintarTema();
  }
})();
