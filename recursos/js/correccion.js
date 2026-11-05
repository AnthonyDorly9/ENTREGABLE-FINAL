(function () {
  const { el, api, avisar, porcentaje } = App;
  const modelos = App.modelos();
  const infoModelo = Object.fromEntries(modelos.map((m) => [m.clave, m]));
  const CORTO = Object.fromEntries(modelos.map((m) => [m.clave, m.corto]));
  const contenedor = document.getElementById("correccion");
  const zonaInforme = el("div", { id: "informe-correccion" });
  const zonaPanel = el("div", { id: "panel-correccion" });
  contenedor.append(zonaInforme, zonaPanel);
  let ultimoInforme = null;

  document.addEventListener("resultados-listos", (e) => montarPanel(e.detail));

  function erroresPorModelo(datos) {
    const conteo = Object.fromEntries(modelos.map((m) => [m.clave, 0]));
    const digitos = [];
    for (const foto of datos.fotos) {
      if (!foto.completa) continue;
      for (const d of foto.digitos) {
        const fallos = modelos.filter((m) => d.modelos[m.clave] && d.modelos[m.clave].acierto === false);
        fallos.forEach((m) => conteo[m.clave]++);
        if (fallos.length) digitos.push({ ...d, fallos, foto: foto.nombre });
      }
    }
    return { conteo, digitos };
  }

  function montarPanel(datos) {
    const { conteo, digitos } = erroresPorModelo(datos);
    const fotosCompletas = datos.fotos.filter((f) => f.completa).length;
    const conErrores = modelos.filter((m) => conteo[m.clave] > 0);

    if (!digitos.length) {
      zonaPanel.replaceChildren(el("section", { clase: "tarjeta", estilo: { "margin-top": "22px" } },
        el("h3", { texto: "Corregir a los que fallaron" }),
        el("p", { clase: "vacio", texto: fotosCompletas
          ? "Todos los modelos acertaron todos los dígitos de estas fotos. No hay nada que corregir."
          : "Ninguna foto tiene la misma cantidad de dígitos que escribiste, así que no se puede comparar todavía." })));
      return;
    }

    const reservadas = fotosCompletas >= 3 ? Math.max(1, Math.round(0.3 * fotosCompletas)) : 0;
    const marcasModelo = {};
    const marcasDigito = {};

    const chips = el("div", { clase: "chips", role: "group", "aria-label": "Modelos que van a aprender" },
      modelos.map((m) => {
        const n = conteo[m.clave];
        const caja = el("input", { type: "checkbox", checked: n > 0, disabled: n === 0, "aria-label": `Entrenar ${m.nombre}` });
        marcasModelo[m.clave] = caja;
        return el("label", { clase: "chip-modelo" + (n === 0 ? " apagado" : ""), estilo: { "--color": m.color } },
          caja, m.nombre, el("small", { texto: n === 0 ? "acertó todo" : `${n} ${n === 1 ? "error" : "errores"}` }));
      }));

    const galeria = el("div", { clase: "errores-galeria" }, digitos.map((d) => {
      const caja = el("input", { type: "checkbox", checked: true, "aria-label": `Usar el dígito ${d.real} de ${d.foto} para aprender` });
      marcasDigito[d.id] = caja;
      return el("label", { clase: "error-tile" },
        el("div", { clase: "fila-tile" }, el("img", { src: d.imagen, alt: `Dígito ${d.real}` }),
          el("div", null, el("strong", { texto: "Era " + d.real }), el("small", { texto: d.foto }))),
        el("div", { clase: "quien-fallo" }, d.fallos.map((m) =>
          el("span", { clase: "fallo", estilo: { "--color": m.color }, texto: `${CORTO[m.clave]} → ${d.modelos[m.clave].predicho}` }))),
        el("span", { clase: "usar" }, caja, "Usar para aprender"));
    }));

    const boton = el("button", { clase: "boton boton-verde", type: "button", id: "boton-corregir", "data-tarea": "/api/tareas/corregir", texto: "Entrenar a los que fallaron" });
    boton.addEventListener("click", () => corregir(datos, boton, marcasModelo, marcasDigito));

    zonaPanel.replaceChildren(el("section", { clase: "tarjeta correccion", estilo: { "margin-top": "22px" } },
      el("div", { clase: "seccion-titulo" },
        el("h2", { texto: "Corregir a los que fallaron" }),
        el("p", { texto: `${conErrores.length} ${conErrores.length === 1 ? "modelo se equivocó" : "modelos se equivocaron"} en ${digitos.length} ${digitos.length === 1 ? "dígito" : "dígitos"}. ` +
          "Cada uno aprende de sus errores con variantes de cada dígito y repasa ejemplos de MNIST y de tus correcciones anteriores para no olvidar nada." +
          (reservadas ? ` Dejo ${reservadas} ${reservadas === 1 ? "foto" : "fotos"} sin usar para comprobar que de verdad aprendieron.` : " Con menos de 3 fotos no se reserva ninguna para comprobar.") })),
      el("h3", { texto: "¿Quiénes aprenden?", estilo: { "font-size": "1rem", margin: "4px 0 10px" } }), chips,
      el("h3", { texto: "Dígitos donde hubo errores", estilo: { "font-size": "1rem", margin: "20px 0 4px" } }),
      el("p", { texto: "Si escribiste mal algún número, quita la marca y ese dígito no se usará.", estilo: { color: "var(--tinta-suave)", "margin-bottom": "12px" } }),
      galeria,
      el("div", { clase: "acciones-correccion" }, boton,
        el("span", { clase: "estado", texto: "Tarda unos segundos por modelo. Solo se guarda lo que mejora sin perder lo aprendido." }))));
  }

  async function corregir(datos, boton, marcasModelo, marcasDigito) {
    const elegidos = Object.entries(marcasModelo).filter(([, c]) => c.checked && !c.disabled).map(([k]) => k);
    if (!elegidos.length) { avisar("Marca al menos un modelo para entrenar.", "error"); return; }
    const excluir = Object.entries(marcasDigito).filter(([, c]) => !c.checked).map(([id]) => Number(id));
    boton.disabled = true;
    boton.replaceChildren(el("span", { clase: "cargando" }), " Entrenando…");
    try {
      const informe = await App.ejecutarTarea("/api/tareas/corregir", { lote: datos.lote, modelos: elegidos, excluir, pagina: "predecir" }, { boton });
      ultimoInforme = informe;
      pintarInforme(informe);
      if (informe.version_nueva) {
        avisar(`Listo: ahora usas la versión ${informe.version_nueva}.`, "ok");
        const insignia = document.querySelector(".insignia-version strong");
        if (insignia) insignia.textContent = informe.version_nueva;
        document.dispatchEvent(new CustomEvent("mostrar-resultados", { detail: informe.resultado }));
      } else {
        avisar(informe.mensaje, "info", 7000);
        boton.disabled = false;
        boton.textContent = "Entrenar a los que fallaron";
      }
      zonaInforme.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      avisar(e.message, "error", 7000);
      boton.disabled = false;
      boton.textContent = "Entrenar a los que fallaron";
    }
  }

  function pintarInforme(informe) {
    zonaInforme.replaceChildren(el("section", { clase: "tarjeta", estilo: { "margin-top": "22px" }, tabindex: "-1" }, App.tablaCorreccion(informe)));
  }

  /* Si la persona llega desde el aviso «Ya terminamos», se muestra el resultado de esa correccion. */
  App.tareaDeLaUrl().then((tarea) => {
    if (!tarea || tarea.tipo !== "corregir") return;
    if (tarea.estado === "error") { avisar(tarea.error, "error", 8000); return; }
    const informe = tarea.resultado;
    document.getElementById("resultados").hidden = false;
    if (informe.resultado) document.dispatchEvent(new CustomEvent("mostrar-resultados", { detail: informe.resultado }));
    pintarInforme(informe);
    if (informe.version_nueva) {
      const insignia = document.querySelector(".insignia-version strong");
      if (insignia) insignia.textContent = informe.version_nueva;
    }
    zonaInforme.scrollIntoView({ behavior: "smooth", block: "start" });
  });
})();
