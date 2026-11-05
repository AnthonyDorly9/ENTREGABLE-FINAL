(function () {
  const { el, api, avisar, porcentaje } = App;
  const modelos = App.modelos();
  const info = Object.fromEntries(modelos.map((m) => [m.clave, m]));
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const CORTO = Object.fromEntries(modelos.map((m) => [m.clave, m.corto]));
  let versiones = null;

  function opcionesVersion(select, elegida) {
    select.replaceChildren(...versiones.versiones.map((v) => el("option", { value: v.id, selected: v.id === elegida, title: v.motivo,
      texto: `${v.id}${v.id === versiones.activa ? " (activa)" : ""}` })));
  }

  async function comparar() {
    const lote = $("lote").value, antes = $("version-antes").value, despues = $("version-despues").value;
    if (antes === despues) { avisar("Elige dos versiones distintas para comparar.", "error"); return; }
    try {
      const [a, b] = await Promise.all([App.lento(`/api/lote/${lote}?version=${antes}`), App.lento(`/api/lote/${lote}?version=${despues}`)]);
      pintarComparacion(a, b, antes, despues);
    } catch (e) { avisar(e.message, "error"); }
  }

  function estadoCelda(a, b) {
    if (a.acierto === b.acierto) return "igual";
    return b.acierto ? "mejora" : "empeora";
  }

  function pintarComparacion(a, b, va, vb) {
    const cuenta = Object.fromEntries(modelos.map((m) => [m.clave, { mejora: 0, empeora: 0, igual: 0 }]));
    const tarjetas = b.fotos.map((fotoB, i) => {
      const fotoA = a.fotos[i];
      if (!fotoB.completa) return null;
      const cabecera = el("tr", null, el("th", { scope: "col" }, el("span", { clase: "solo-lectores", texto: "Modelo" })),
        fotoB.digitos.map((d) => el("th", { scope: "col" }, el("div", { clase: "digito-real" }, el("img", { src: d.imagen, alt: "Dígito recortado" }), String(d.real)))));
      const filas = modelos.map((m) => el("tr", { estilo: { "--color": m.color } },
        el("th", { scope: "row" }, el("span", { clase: "modelo-nombre" }, el("span", { clase: "punto" }), m.nombre)),
        fotoB.digitos.map((dB, k) => {
          const dA = fotoA.digitos[k];
          const pa = dA.modelos[m.clave], pb = dB.modelos[m.clave];
          const estado = estadoCelda(pa, pb);
          cuenta[m.clave][estado] += 1;
          const texto = pa.predicho === pb.predicho ? String(pb.predicho) : `${pa.predicho}→${pb.predicho}`;
          const etiqueta = { mejora: "se arregló", empeora: "empeoró", igual: pb.acierto ? "sigue bien" : "sigue mal" }[estado];
          return el("td", null, el("span", { clase: "celda-cambio " + estado + (estado === "igual" ? (pb.acierto ? " bien" : " mal") : ""), texto, title: `${m.nombre}: ${etiqueta}`, "aria-label": `${m.nombre}: ${texto}, ${etiqueta}` }));
        })));
      return el("article", { clase: "tarjeta resultado-foto" },
        el("div", { clase: "foto-mini" }, el("img", { src: fotoB.url, alt: "Foto " + fotoB.nombre, loading: "lazy" }), el("strong", { texto: "Escribiste " + fotoB.texto })),
        el("div", { clase: "tabla-desplazable" }, el("table", { clase: "matriz-digitos" }, el("thead", null, cabecera), el("tbody", null, filas))));
    }).filter(Boolean);

    const total = modelos.reduce((s, m) => ({ mejora: s.mejora + cuenta[m.clave].mejora, empeora: s.empeora + cuenta[m.clave].empeora }), { mejora: 0, empeora: 0 });
    $("resumen-comparar").textContent = total.mejora + total.empeora === 0
      ? `Entre ${va} y ${vb} ningún modelo cambió de acierto en estas fotos.`
      : `De ${va} a ${vb}: ${total.mejora} ${total.mejora === 1 ? "dígito se arregló" : "dígitos se arreglaron"} y ${total.empeora} ${total.empeora === 1 ? "empeoró" : "empeoraron"}, sumando todos los modelos.`;
    $("cambios-por-modelo").replaceChildren(...modelos.map((m) => el("span", { clase: "chip-modelo", estilo: { "--color": m.color } }, m.nombre,
      el("small", { texto: `+${cuenta[m.clave].mejora} arreglados · −${cuenta[m.clave].empeora} empeorados` }))));
    $("fotos-comparar").replaceChildren(...tarjetas);
    $("resultado-comparar").hidden = false;
  }

  function pintarVersiones() {
    const filas = versiones.versiones.slice().reverse().map((v) => {
      const activa = v.id === versiones.activa;
      return el("tr", null,
        el("th", { scope: "row", texto: v.id }),
        el("td", null, v.motivo, v.detalle.actualizados && v.detalle.actualizados.length ? el("p", { clase: "motivo", texto: "Modelos actualizados: " + v.detalle.actualizados.map((c) => CORTO[c]).join(", ") }) : null),
        el("td", { texto: v.creada.replace("T", " ") }),
        el("td", { texto: modelos.map((m) => v.detalle.exactitud_prueba && v.detalle.exactitud_prueba[m.clave] !== undefined ? `${CORTO[m.clave]} ${porcentaje(v.detalle.exactitud_prueba[m.clave], 1)}` : null).filter(Boolean).join(" · ") }),
        el("td", null, activa ? el("span", { clase: "insignia ok", texto: "Activa" }) : el("button", {
          clase: "boton boton-pequeno", type: "button", texto: "Usar esta versión",
          en: { click: () => activar(v.id) } })));
    });
    $("tabla-versiones").replaceChildren(
      el("caption", { clase: "solo-lectores", texto: "Versiones de los modelos" }),
      el("thead", null, el("tr", null, ["Versión", "Qué pasó", "Fecha", "Exactitud en MNIST", ""].map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", null, filas));

    const img = $("img-versiones");
    img.classList.remove("lista");
    img.onload = () => img.classList.add("lista");
    const url = `/figura/progreso.png?t=${Date.now()}`;
    img.src = url;
    $("dl-versiones").href = url;
  }

  async function activar(id) {
    try {
      await api(`/api/versiones/${id}/activar`, { method: "POST" });
      avisar(`Ahora usas la versión ${id}. Se conserva aunque cierres la aplicación.`, "ok");
      const insignia = document.querySelector(".insignia-version strong");
      if (insignia) insignia.textContent = id;
      versiones = await api("/api/versiones");
      pintarVersiones();
    } catch (e) { avisar(e.message, "error"); }
  }

  /* ---------- Tandas de fotos y su basura ---------- */
  let lotes = [];
  let basura = [];

  const nombreLote = App.nombreTanda;
  const cuentaFotos = (l) => `${l.fotos} ${l.fotos === 1 ? "foto" : "fotos"}`;

  function actualizarBotonQuitar() {
    const n = document.querySelectorAll("#lista-lotes-quitar input:checked").length;
    $("quitar-lotes").disabled = n === 0;
    $("quitar-lotes").textContent = n ? `Mandar a la basura (${n})` : "Mandar a la basura";
    $("estado-quitar-lotes").textContent = n ? "" : "Marca una o más tandas.";
  }

  function pintarPanelBasura() {
    const marcadas = new Set(Array.from(document.querySelectorAll("#lista-lotes-quitar input:checked")).map((c) => c.value));
    $("lista-lotes-quitar").replaceChildren(...lotes.slice().reverse().map((l) => el("li", { clase: "version-fila" },
      el("label", null,
        el("input", { type: "checkbox", value: l.lote, checked: marcadas.has(l.lote), en: { change: actualizarBotonQuitar }, "aria-label": `Marcar la tanda ${nombreLote(l.lote)} para la basura` }),
        el("span", null, el("strong", { texto: nombreLote(l.lote) }), el("small", { texto: cuentaFotos(l) }))))));
    $("lista-basura-lotes").replaceChildren(...basura.slice().reverse().map((l) => {
      const borrar = el("button", { type: "button", clase: "boton boton-pequeno boton-peligro-suave", texto: "Borrar para siempre", "aria-label": `Borrar la tanda ${nombreLote(l.lote)} para siempre` });
      let espera = null;
      borrar.addEventListener("click", () => {
        if (!espera) {
          borrar.textContent = "¿Seguro? Pulsa otra vez";
          espera = setTimeout(() => { espera = null; borrar.textContent = "Borrar para siempre"; }, 4000);
          return;
        }
        clearTimeout(espera);
        accion(() => api(`/api/lotes/${l.lote}/borrar-para-siempre`, { method: "POST" }), () => `Borré la tanda ${nombreLote(l.lote)} para siempre.`);
      });
      return el("li", { clase: "version-fila" },
        el("span", { clase: "version-info" }, el("strong", { texto: nombreLote(l.lote) }), el("small", { texto: cuentaFotos(l) })),
        el("span", { clase: "acciones-fila" },
          el("button", { type: "button", clase: "boton boton-pequeno", texto: "Restaurar", "aria-label": `Restaurar la tanda ${nombreLote(l.lote)}`,
            en: { click: () => accion(() => api(`/api/lotes/${l.lote}/restaurar`, { method: "POST" }), () => `Restauré la tanda ${nombreLote(l.lote)}.`) } }),
          borrar));
    }));
    $("basura-lotes-vacia").hidden = basura.length > 0;
    $("vaciar-basura-lotes").hidden = basura.length === 0;
    $("contador-basura-lotes").hidden = basura.length === 0;
    $("contador-basura-lotes").textContent = String(basura.length);
    actualizarBotonQuitar();
  }

  /* Vuelve a leer las tandas y ajusta la pagina: con tandas y dos versiones se puede comparar; si no, se explica que falta. */
  async function refrescar(compararDeNuevo) {
    const [lista, papelera] = await Promise.all([api("/api/lotes"), api("/api/lotes/basura")]);
    lotes = lista;
    basura = papelera.basura;
    const elegida = $("lote").value;
    const puede = lotes.length > 0 && versiones.versiones.length >= 2;
    document.querySelectorAll(".solo-comparar").forEach((nodo) => { nodo.hidden = !puede; });
    $("vacio-comparar").hidden = puede;
    $("controles-comparar").hidden = !lotes.length && !basura.length;
    if (!puede) {
      $("resultado-comparar").hidden = true;
      $("vacio-comparar").querySelector("p").innerHTML = lotes.length
        ? "Todavía hay una sola versión. Corrige modelos en <a href=\"/\">Leer formulario</a> y vuelve para ver qué cambió."
        : basura.length
          ? "Todas tus tandas están en la basura. Restaura una desde el botón «Basura» o <a href=\"/\">sube fotos nuevas</a>."
          : "<a href=\"/\">Sube y lee tus primeras fotos</a>; después de corregir modelos podrás ver aquí qué cambió.";
    } else {
      $("lote").replaceChildren(...lotes.slice().reverse().map((l) => el("option", { value: l.lote, selected: l.lote === elegida, texto: `${nombreLote(l.lote)} · ${cuentaFotos(l)}` })));
      if (compararDeNuevo) comparar();
    }
    pintarPanelBasura();
  }

  async function accion(peticion, mensaje) {
    try {
      const r = await peticion();
      await refrescar(true);
      avisar(mensaje(r), "ok", 6000);
    } catch (e) { avisar(e.message, "error", 7000); }
  }

  function activarBasuraDeTandas() {
    $("abrir-basura-lotes").addEventListener("click", () => {
      const panel = $("panel-basura-lotes");
      panel.hidden = !panel.hidden;
      $("abrir-basura-lotes").setAttribute("aria-expanded", String(!panel.hidden));
      if (!panel.hidden) panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    $("quitar-lotes").addEventListener("click", () => {
      const ids = Array.from(document.querySelectorAll("#lista-lotes-quitar input:checked")).map((c) => c.value);
      if (ids.length) accion(() => api("/api/lotes/quitar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) }),
        (r) => `Mandé ${r.quitadas.length} ${r.quitadas.length === 1 ? "tanda" : "tandas"} a la basura. Puedes restaurarlas cuando quieras.`);
    });
    $("marcar-antiguas").addEventListener("click", () => {
      const cajas = Array.from(document.querySelectorAll("#lista-lotes-quitar input"));
      cajas.forEach((c, i) => { c.checked = i > 0; });
      actualizarBotonQuitar();
      if (cajas.length < 2) $("estado-quitar-lotes").textContent = "Solo tienes una tanda: es la más reciente.";
    });
    $("vaciar-basura-lotes").addEventListener("click", () => {
      const boton = $("vaciar-basura-lotes");
      if (boton.dataset.confirmar !== "1") {
        boton.dataset.confirmar = "1";
        boton.textContent = "¿Seguro? Se borran para siempre. Pulsa otra vez";
        setTimeout(() => { boton.dataset.confirmar = ""; boton.textContent = "Vaciar la basura"; }, 5000);
        return;
      }
      boton.dataset.confirmar = "";
      boton.textContent = "Vaciar la basura";
      accion(() => api("/api/lotes/vaciar-basura", { method: "POST" }), () => "Vacié la basura.");
    });
  }

  (async function iniciar() {
    try {
      versiones = await api("/api/versiones");
      pintarVersiones();
      activarBasuraDeTandas();
      const lista = versiones.versiones;
      if (lista.length >= 2) {
        opcionesVersion($("version-antes"), lista[Math.max(0, lista.findIndex((x) => x.id === versiones.activa) - 1)].id);
        opcionesVersion($("version-despues"), versiones.activa);
      }
      $("comparar").addEventListener("click", comparar);
      await refrescar(true);
    } catch (e) { avisar(e.message, "error"); }
  })();
})();
