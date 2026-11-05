(function () {
  const { el, api, avisar, porcentaje } = App;
  const modelos = App.modelos();
  const infoModelo = Object.fromEntries(modelos.map((m) => [m.clave, m]));
  const MAXIMO = 20;
  const estado = { lote: window.LOTE_INICIAL || null, pendientes: [], ultimo: null };
  const $ = (id) => document.getElementById(id);
  const numeroValido = (t) => /^\d{1,12}$/.test(t);

  /* ---------- Subida ---------- */
  const zona = $("zona");
  const entradaFotos = $("entrada-fotos");
  const entradaCamara = $("entrada-camara");
  $("elegir-fotos").addEventListener("click", () => entradaFotos.click());
  $("usar-camara").addEventListener("click", () => entradaCamara.click());
  for (const entrada of [entradaFotos, entradaCamara]) {
    entrada.addEventListener("change", () => { subir(entrada.files); entrada.value = ""; });
  }
  ["dragenter", "dragover"].forEach((n) => zona.addEventListener(n, (e) => { e.preventDefault(); zona.classList.add("arrastrando"); }));
  ["dragleave", "drop"].forEach((n) => zona.addEventListener(n, (e) => { e.preventDefault(); zona.classList.remove("arrastrando"); }));
  zona.addEventListener("drop", (e) => subir(e.dataTransfer.files));

  function fotosEnUso() {
    return estado.pendientes.length + (estado.ultimo ? estado.ultimo.fotos.length : 0);
  }

  async function subir(lista, reintento) {
    const archivos = Array.from(lista).filter((f) => f.type.startsWith("image/") || /\.(jpe?g|png|webp|bmp)$/i.test(f.name));
    if (!archivos.length) { avisar("Elige imágenes en formato JPG o PNG.", "error"); return; }
    if (fotosEnUso() + archivos.length > MAXIMO) {
      avisar(`Máximo ${MAXIMO} fotos por tanda. Ya tienes ${fotosEnUso()}.`, "error");
      return;
    }
    const datos = new FormData();
    archivos.forEach((f) => datos.append("fotos", f));
    if (estado.lote) datos.append("lote", estado.lote);
    zona.setAttribute("aria-busy", "true");
    try {
      const r = await App.lento("/api/fotos", { method: "POST", body: datos });
      estado.lote = r.lote;
      r.fotos.forEach((f) => estado.pendientes.push({ ...f, texto: "" }));
      r.errores.forEach((e) => avisar(e, "error"));
      pintarPendientes();
      const primero = document.querySelector(".campo-numero");
      if (primero) primero.focus({ preventScroll: true });
    } catch (e) {
      if (!reintento && /ya no existe/.test(e.message)) { estado.lote = null; return subir(lista, true); }
      avisar(e.message, "error");
    } finally {
      zona.removeAttribute("aria-busy");
    }
  }


  /* ---------- Fotos pendientes ---------- */
  function pintarPendientes() {
    const cont = $("fotos");
    $("seccion-pendientes").hidden = estado.pendientes.length === 0;
    cont.replaceChildren(...estado.pendientes.map(tarjetaFoto));
    actualizarBarra();
  }

  function tarjetaFoto(foto) {
    const insignia = el("span", { clase: "insignia" });
    const pintarInsignia = () => {
      const n = foto.detectados;
      const largo = foto.texto.length;
      if (largo && largo !== n) {
        insignia.className = "insignia aviso";
        insignia.textContent = `Detecté ${n} y escribiste ${largo}: ajustaré los recortes`;
      } else {
        insignia.className = "insignia" + (largo ? " ok" : "");
        insignia.textContent = `Detecté ${n} ${n === 1 ? "dígito" : "dígitos"}`;
      }
    };
    const campo = el("input", {
      clase: "campo-numero", type: "text", inputmode: "numeric", autocomplete: "off", maxlength: "12",
      placeholder: "Escribe el número", "aria-label": "Número escrito en " + foto.nombre, value: foto.texto,
      en: {
        input: () => {
          campo.value = campo.value.replace(/\D/g, "");
          foto.texto = campo.value;
          campo.classList.toggle("invalido", foto.texto !== "" && !numeroValido(foto.texto));
          pintarInsignia();
          actualizarBarra();
        },
        keydown: (e) => {
          if (e.key !== "Enter") return;
          const campos = Array.from(document.querySelectorAll(".campo-numero"));
          const siguiente = campos[campos.indexOf(campo) + 1];
          if (siguiente) siguiente.focus();
          else if (!$("predecir").disabled) $("predecir").focus();
        },
      },
    });
    pintarInsignia();

    const panelPasos = el("div", { hidden: true });
    let cargados = false;
    const botonPasos = el("button", {
      clase: "boton boton-pequeno", type: "button", "aria-expanded": "false", texto: "Ver pasos",
      en: {
        click: async () => {
          const abierto = panelPasos.hidden;
          panelPasos.hidden = !abierto;
          botonPasos.setAttribute("aria-expanded", String(abierto));
          botonPasos.textContent = abierto ? "Ocultar pasos" : "Ver pasos";
          if (abierto && !cargados) {
            panelPasos.replaceChildren(el("span", { clase: "cargando" }));
            try {
              const datos = await api(`/api/fotos/${foto.id}/pasos`);
              cargados = true;
              panelPasos.replaceChildren(
                el("div", { clase: "pasos-foto" }, datos.pasos.map((p) =>
                  el("figure", null, el("img", { src: p.uri, alt: p.titulo, loading: "lazy" }), el("figcaption", { texto: p.titulo })))),
                el("p", { estilo: { margin: "10px 0 6px", "font-size": "0.85rem", color: "var(--tinta-suave)" }, texto: "Cada dígito se recorta y se lleva a 28×28 píxeles, centrado, como en MNIST:" }),
                el("div", { clase: "recortes-fila" }, datos.recortes.map((r) => el("img", { src: r.uri, alt: "Dígito recortado" }))),
              );
            } catch (e) {
              panelPasos.replaceChildren(el("p", { texto: e.message }));
            }
          }
        },
      },
    });

    const miniatura = el("img", { src: foto.url, alt: "Foto " + foto.nombre });
    const botonGirar = el("button", {
      clase: "boton boton-pequeno", type: "button", texto: "Girar ↻", title: "Girar la foto 90° a la derecha",
      en: { click: async () => {
        botonGirar.disabled = true;
        try {
          const r = await api(`/api/fotos/${foto.id}/girar`, { method: "POST" });
          foto.url = r.url;
          foto.detectados = r.detectados;
          miniatura.src = r.url;
          pintarInsignia();
          cargados = false;
          if (!panelPasos.hidden) { botonPasos.click(); botonPasos.click(); }  // cerrar y abrir: vuelve a pedir los pasos
        } catch (e) { avisar(e.message, "error"); } finally { botonGirar.disabled = false; }
      } },
    });

    return el("article", { clase: "tarjeta foto-tarjeta" },
      el("div", { clase: "miniatura" }, miniatura),
      el("div", { clase: "fila" }, el("span", { clase: "nombre", title: foto.nombre, texto: foto.nombre }), insignia),
      foto.girada ? el("p", { clase: "pista-texto", texto: "La enderecé porque estaba de lado o de cabeza. Si quedó mal, usa «Girar ↻»." }) : null,
      campo,
      el("div", { clase: "fila" }, botonPasos, botonGirar, el("button", {
        clase: "boton boton-pequeno boton-fantasma", type: "button", texto: "Quitar",
        en: { click: async () => {
          try {
            await api(`/api/fotos/${foto.id}`, { method: "DELETE" });
            estado.pendientes = estado.pendientes.filter((p) => p.id !== foto.id);
            pintarPendientes();
          } catch (e) { avisar(e.message, "error"); }
        } },
      })),
      panelPasos,
    );
  }

  function actualizarBarra() {
    const total = estado.pendientes.length;
    const listas = estado.pendientes.filter((p) => numeroValido(p.texto)).length;
    $("barra-accion").hidden = total === 0;
    $("estado-accion").textContent = listas === total
      ? `${total} ${total === 1 ? "foto lista" : "fotos listas"} para predecir`
      : `${listas} de ${total} fotos con número. Escribe el número de las demás.`;
    $("predecir").disabled = total === 0 || listas !== total;
  }

  /* ---------- Predecir ---------- */
  const botonPredecir = $("predecir");
  botonPredecir.addEventListener("click", async () => {
    const textos = Object.fromEntries(estado.pendientes.map((p) => [p.id, p.texto]));
    botonPredecir.disabled = true;
    botonPredecir.replaceChildren(el("span", { clase: "cargando" }), " Leyendo con todos los modelos…");
    try {
      const datos = await App.lento("/api/predecir", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lote: estado.lote, textos }),
      }, { boton: botonPredecir });
      estado.pendientes = [];
      pintarPendientes();
      mostrarResultados(datos, true);
    } catch (e) {
      avisar(e.message, "error");
    } finally {
      botonPredecir.textContent = "Predecir con todos los modelos";
      actualizarBarra();
    }
  });

  /* ---------- Resultados ---------- */
  function mostrarResultados(datos, desplazar) {
    estado.ultimo = datos;
    $("resultados").hidden = false;
    const lider = datos.marcador[0];
    $("resumen-resultados").textContent = lider && lider.digitos
      ? `${datos.fotos.length} ${datos.fotos.length === 1 ? "foto leída" : "fotos leídas"} con los modelos ${datos.version}. Va primero ${infoModelo[lider.modelo].nombre}: ${lider.digitos_ok} de ${lider.digitos} dígitos.`
      : `${datos.fotos.length} fotos leídas con los modelos ${datos.version}.`;
    $("marcador").replaceChildren(...datos.marcador.map((fila, i) => filaMarcador(fila, i)));
    $("lista-resultados").replaceChildren(...datos.fotos.map(tarjetaResultado));
    pintarGaleriaReal();
    document.dispatchEvent(new CustomEvent("resultados-listos", { detail: datos }));
    if (desplazar) $("resultados").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* Galería «Real / Predijo» de los dígitos de la tanda con el modelo elegido (desplegable, cerrado de inicio). */
  let modeloGaleria = "cnn";
  let digitosGaleria = [];
  let digitoAbierto = 0;

  /* Ventana con la foto (recuadro en el dígito) al lado de «Real / Predijo»; Anterior / Siguiente recorren la galería. */
  function abrirDigito(indice) {
    if (!digitosGaleria.length) return;
    digitoAbierto = (indice + digitosGaleria.length) % digitosGaleria.length;
    const d = digitosGaleria[digitoAbierto];
    const predicho = d.modelos[modeloGaleria].predicho;
    const bien = predicho === d.real;
    const ventana = $("ventana-digito");
    ventana.classList.toggle("incorrecto", !bien);
    $("t-ventana-digito").textContent = `Dígito ${d.numeroDigito} de la foto ${d.numeroFoto}`;
    $("ventana-digito-foto").src = `/foto/${d.fotoId}/digito/${d.posicion}.png`;
    $("ventana-digito-foto").alt = `Foto «${d.foto}» con un recuadro en el dígito ${d.numeroDigito}`;
    $("ventana-digito-estado").textContent = bien ? "Correcto ✓" : "Incorrecto ✗";
    $("ventana-digito-datos").textContent = `Real: ${d.real} · Predijo: ${predicho} (${infoModelo[modeloGaleria].nombre})`;
    $("ventana-digito-origen").textContent = `Foto ${d.numeroFoto} «${d.foto}», número escrito ${d.texto}, dígito ${d.numeroDigito}`;
    $("ventana-digito-recorte").src = d.imagen;
    $("ventana-digito-recorte").alt = `Dígito ${d.real} recortado`;
    $("ventana-digito-cuenta").textContent = `${digitoAbierto + 1} de ${digitosGaleria.length}`;
    const solo = digitosGaleria.length === 1;
    $("digito-anterior").disabled = solo;
    $("digito-siguiente").disabled = solo;
    if (!ventana.open) ventana.showModal();
  }
  $("digito-anterior").addEventListener("click", () => abrirDigito(digitoAbierto - 1));
  $("digito-siguiente").addEventListener("click", () => abrirDigito(digitoAbierto + 1));
  $("cerrar-ventana-digito").addEventListener("click", () => $("ventana-digito").close());
  $("ventana-digito").addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });
  $("ventana-digito").addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") abrirDigito(digitoAbierto - 1);
    if (e.key === "ArrowRight") abrirDigito(digitoAbierto + 1);
  });
  function pintarGaleriaReal() {
    const datos = estado.ultimo;
    const digitos = datos.fotos.flatMap((f, n) => f.digitos.map((d, p) => ({ ...d, origen: `Foto ${n + 1} · dígito ${p + 1}`, foto: f.nombre,
      fotoId: f.id, numeroFoto: n + 1, numeroDigito: p + 1, texto: f.texto })))
      .filter((d) => d.real !== null && d.modelos[modeloGaleria]);
    digitosGaleria = digitos;
    $("modelo-galeria-real").replaceChildren(...modelos.map((m) => {
      const marcado = m.clave === modeloGaleria;
      return el("button", { type: "button", role: "radio", "aria-checked": String(marcado), clase: "chip-modelo" + (marcado ? " elegido" : ""),
        estilo: { "--color": m.color }, texto: m.nombre, en: { click: () => { modeloGaleria = m.clave; pintarGaleriaReal(); } } });
    }));
    $("resumen-galeria-real").textContent = `${digitos.length} ${digitos.length === 1 ? "dígito" : "dígitos"} con el número que escribiste y lo que leyó cada modelo.`;
    $("tarjetas-real").replaceChildren(...digitos.map((d) => {
      const predicho = d.modelos[modeloGaleria].predicho;
      const bien = predicho === d.real;
      return el("button", { type: "button", clase: "tarjeta-real " + (bien ? "correcto" : "incorrecto"), title: "Ver en la foto",
        en: { click: () => abrirDigito(digitos.indexOf(d)) } },
        el("p", {}, `Real: ${d.real}`, el("br"), `Predijo: ${predicho}`, el("br"), bien ? "Correcto ✓" : "Incorrecto ✗",
          el("small", { clase: "origen-digito", title: d.foto, texto: d.origen })),
        el("span", { clase: "marco-digito" }, el("img", { src: d.imagen, alt: `Dígito ${d.real}, ${infoModelo[modeloGaleria].nombre} leyó ${predicho}`, loading: "lazy" })));
    }));
    $("leyenda-galeria-real").textContent = `Predicciones de ${infoModelo[modeloGaleria].nombre} con los dígitos de tus fotos frente al número que escribiste (verde = correcto, rosa = incorrecto).`;
    const enlace = $("dl-galeria-real");
    enlace.href = `/api/lote/${encodeURIComponent(datos.lote)}/predicciones/${modeloGaleria}.png?version=${encodeURIComponent(datos.version)}`;
    enlace.setAttribute("download", `predicciones_${modeloGaleria}_${datos.lote}.png`);
    $("acordeon-galeria-real").closest("section").hidden = digitos.length === 0;
  }

  function filaMarcador(fila, i) {
    const m = infoModelo[fila.modelo];
    const pct = fila.digitos ? (fila.digitos_ok / fila.digitos) * 100 : 0;
    const medalla = ["oro", "plata", "bronce"][i] || "";
    return el("div", { clase: "fila-marcador" + (i === 0 && fila.digitos ? " campeon" : ""), estilo: { "--color": m.color, "--valor": pct.toFixed(1), "--orden": i } },
      el("span", { clase: "medalla " + medalla, texto: String(i + 1), "aria-label": "Puesto " + (i + 1) }),
      el("span", { clase: "quien" }, el("span", { clase: "punto" }), m.nombre),
      el("div", { clase: "pista" }, el("div", { clase: "relleno" })),
      el("span", { clase: "cifras" }, el("strong", { texto: `${fila.digitos_ok}/${fila.digitos}` }), ` dígitos · ${fila.numeros_ok}/${fila.numeros} números`),
    );
  }

  function tarjetaResultado(foto, i) {
    const acertaron = Object.values(foto.por_modelo).filter((p) => p.correcto).length;
    const resumen = foto.completa
      ? el("span", { clase: "insignia " + (acertaron === modelos.length ? "ok" : acertaron === 0 ? "mal" : "aviso"),
          texto: `${acertaron} de ${modelos.length} leyeron el número completo` })
      : el("span", { clase: "insignia aviso", texto: foto.aviso || "No coincide la cantidad de dígitos" });

    let tabla;
    if (!foto.digitos.length) {
      tabla = el("p", { clase: "vacio", texto: "No se detectaron dígitos en esta foto. Prueba con más luz o acércate al número." });
    } else {
      tabla = el("div", { clase: "tabla-desplazable" }, el("table", { clase: "matriz-digitos" },
        el("thead", null, el("tr", null,
          el("th", { scope: "col" }, el("span", { clase: "solo-lectores", texto: "Modelo" })),
          foto.digitos.map((d) => el("th", { scope: "col" }, el("div", { clase: "digito-real" },
            el("img", { src: d.imagen, alt: "Dígito recortado" }), d.real === null ? "?" : String(d.real)))),
          el("th", { scope: "col", texto: "Número" }))),
        el("tbody", null, modelos.map((m) => {
          const pm = foto.por_modelo[m.clave];
          return el("tr", { estilo: { "--color": m.color } },
            el("th", { scope: "row" }, el("span", { clase: "modelo-nombre" }, el("span", { clase: "punto" }), m.nombre)),
            foto.digitos.map((d) => {
              const p = d.modelos[m.clave];
              const clase = p && p.acierto !== null ? (p.acierto ? " ok" : " mal") : "";
              const boton = el("button", {
                clase: "celda-prediccion" + clase, type: "button", texto: p ? String(p.predicho) : "?",
                "aria-label": p ? `${m.nombre} predijo ${p.predicho}${p.acierto === null ? "" : p.acierto ? " y acertó" : " y falló"}. Ver explicación` : "",
                en: { click: () => abrirExplicacion(d.id, m.clave, boton) },
              });
              return el("td", null, boton);
            }),
            el("td", { clase: "total" }, pm.numero + " ", foto.completa ? el("span", { clase: "insignia " + (pm.correcto ? "ok" : "mal"), texto: pm.correcto ? "Correcto" : "Falló" }) : null));
        }))));
    }

    return el("article", { clase: "tarjeta resultado-foto", estilo: { "--orden": i } },
      el("div", { clase: "foto-mini" },
        el("img", { src: foto.url, alt: "Foto " + foto.nombre, loading: "lazy" }),
        el("strong", { texto: "Escribiste " + foto.texto }),
        resumen),
      tabla);
  }

  /* ---------- Panel de explicación ---------- */
  const panel = $("panel");
  const velo = $("velo");
  let disparador = null;

  function abrirPanel(origen) {
    disparador = origen || null;
    panel.classList.add("abierto");
    velo.classList.add("abierto");
    panel.setAttribute("aria-hidden", "false");
    $("cerrar-panel").focus();
  }
  function cerrarPanel() {
    panel.classList.remove("abierto");
    velo.classList.remove("abierto");
    panel.setAttribute("aria-hidden", "true");
    if (disparador) disparador.focus({ preventScroll: true });
  }
  $("cerrar-panel").addEventListener("click", cerrarPanel);
  velo.addEventListener("click", cerrarPanel);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && panel.classList.contains("abierto")) cerrarPanel(); });

  async function abrirExplicacion(digitoId, clave, origen) {
    const m = infoModelo[clave];
    abrirPanel(origen);
    $("panel-titulo").textContent = m.nombre;
    $("panel-subtitulo").textContent = "Cómo llegó a su respuesta";
    $("panel-cuerpo").replaceChildren(el("p", { clase: "vacio" }, el("span", { clase: "cargando" }), " Analizando…"));
    try {
      const d = await api(`/api/explicacion/${digitoId}/${clave}`);
      const acierto = d.real === null ? null : d.predicho === d.real;
      $("panel-cuerpo").replaceChildren(
        el("div", { clase: "panel-digito" },
          el("img", { src: d.imagen, alt: "Dígito recortado" }),
          el("div", { estilo: { display: "flex", "flex-direction": "column", gap: "8px", "align-items": "flex-start" } },
            el("p", { estilo: { "font-size": "1.15rem", "font-weight": "700" }, texto: `Predijo ${d.predicho} con ${porcentaje(d.confianza, 0)}` }),
            acierto === null ? null : el("span", { clase: "insignia " + (acierto ? "ok" : "mal"), texto: acierto ? `Acertó: era ${d.real}` : `Falló: era ${d.real}` }))),
        el("div", { clase: "barras-prob", estilo: { "--color": m.color, margin: "18px 0" } },
          d.probabilidades.map((p, i) => el("div", { clase: "fila" + (i === d.predicho ? " elegida" : ""), estilo: { "--valor": (p * 100).toFixed(1), "--orden": i } },
            el("span", { texto: String(i) }), el("div", { clase: "pista" }, el("div", { clase: "relleno" })), el("span", { texto: porcentaje(p, 0) })))),
        el("p", { estilo: { "margin-bottom": "16px" }, texto: d.texto }),
        el("div", { clase: "explicacion-imagenes" }, d.imagenes.map((im) =>
          el("figure", null, el("img", { src: im.uri, alt: im.titulo }), el("figcaption", null, el("strong", { texto: im.titulo }), im.pie)))),
      );
    } catch (e) {
      $("panel-cuerpo").replaceChildren(el("p", { clase: "vacio", texto: e.message }));
    }
  }

  document.addEventListener("mostrar-resultados", (e) => mostrarResultados(e.detail, false));

  /* ---------- Nueva tanda ---------- */
  $("resultados").querySelector(".seccion-titulo").append(el("button", {
    clase: "boton boton-pequeno", type: "button", texto: "Empezar una tanda nueva", estilo: { "align-self": "flex-start", "margin-top": "6px" },
    en: { click: () => {
      estado.lote = null; estado.ultimo = null; estado.pendientes = [];
      $("resultados").hidden = true; pintarPendientes();
      pedir("/api/tanda/nueva").catch((e) => avisar(e.message, "error"));  // el servidor recuerda la tanda nueva (y el celular tambien)
      window.scrollTo({ top: 0, behavior: "smooth" });
    } },
  }));

  /* ---------- Recuperar la última tanda ---------- */
  (async function recuperar() {
    if (!estado.lote) return;
    try {
      const datos = await api(`/api/lote/${estado.lote}`);
      if (datos.fotos.length) mostrarResultados(datos, false);
    } catch (e) {
      estado.lote = null;
    }
  })();
})();
