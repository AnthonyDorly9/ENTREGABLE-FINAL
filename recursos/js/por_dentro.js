(function () {
  const { el, api, avisar, porcentaje } = App;
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const reducir = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const coma = (v, d) => Number(v).toFixed(d === undefined ? 2 : d).replace(".", ",");

  /* ---------- 1. Neurona ---------- */
  const neurona = { x: [0.8, 0.3, 0.6], w: [1.2, -0.8, 0.5], b: -0.2, tipo: "relu" };
  const activar = (z) => (neurona.tipo === "relu" ? Math.max(0, z) : 1 / (1 + Math.exp(-z)));

  function pintarNeurona() {
    const z = neurona.x.reduce((s, x, i) => s + x * neurona.w[i], 0) + neurona.b;
    const a = activar(z);
    $("formula-neurona").textContent = `z = ${neurona.x.map((x, i) => `${coma(x)}×${coma(neurona.w[i])}`).join(" + ")} + ${coma(neurona.b)} = ${coma(z)}  →  ${neurona.tipo === "relu" ? "ReLU" : "sigmoide"}(z) = ${coma(a, 3)}`;
    const c = $("lienzo-activacion");
    const ctx = c.getContext("2d");
    const [W, H] = [c.width, c.height];
    ctx.clearRect(0, 0, W, H);
    const px = (x) => ((x + 3) / 6) * W;
    const py = (y) => H - 20 - ((y + 0.2) / 3.2) * (H - 40);
    ctx.strokeStyle = css("--linea");
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, py(0)); ctx.lineTo(W, py(0)); ctx.moveTo(px(0), 0); ctx.lineTo(px(0), H); ctx.stroke();
    ctx.strokeStyle = css("--violeta");
    ctx.lineWidth = 3.5;
    ctx.beginPath();
    for (let i = 0; i <= 120; i++) {
      const x = -3 + (6 * i) / 120;
      const y = neurona.tipo === "relu" ? Math.max(0, x) : 1 / (1 + Math.exp(-x));
      i ? ctx.lineTo(px(x), py(y)) : ctx.moveTo(px(x), py(y));
    }
    ctx.stroke();
    const zc = Math.max(-3, Math.min(3, z));
    ctx.fillStyle = css("--rosa");
    ctx.strokeStyle = css("--superficie");
    ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(px(zc), py(activar(zc)), 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = css("--tinta-suave");
    ctx.font = '12px "DM Sans", sans-serif';
    ctx.fillText("z", W - 14, py(0) - 6);
    ctx.fillText("salida", px(0) + 6, 14);
  }

  function controlesNeurona() {
    const filas = [];
    for (let i = 0; i < 3; i++) {
      const sx = el("output", { texto: coma(neurona.x[i]) }), sw = el("output", { texto: coma(neurona.w[i]) });
      filas.push(el("div", { clase: "fila-neurona" },
        el("label", null, `Entrada ${i + 1}`, el("div", { clase: "rango-fila" }, el("input", { type: "range", min: 0, max: 1, step: 0.05, value: neurona.x[i],
          en: { input: (e) => { neurona.x[i] = parseFloat(e.target.value); sx.textContent = coma(neurona.x[i]); pintarNeurona(); } } }), sx)),
        el("label", null, `Peso ${i + 1}`, el("div", { clase: "rango-fila" }, el("input", { type: "range", min: -2, max: 2, step: 0.1, value: neurona.w[i],
          en: { input: (e) => { neurona.w[i] = parseFloat(e.target.value); sw.textContent = coma(neurona.w[i]); pintarNeurona(); } } }), sw))));
    }
    const sb = el("output", { texto: coma(neurona.b) });
    filas.push(el("label", null, "Sesgo", el("div", { clase: "rango-fila" }, el("input", { type: "range", min: -2, max: 2, step: 0.1, value: neurona.b,
      en: { input: (e) => { neurona.b = parseFloat(e.target.value); sb.textContent = coma(neurona.b); pintarNeurona(); } } }), sb)));
    $("controles-neurona").replaceChildren(...filas);
    $("tipo-activacion").replaceChildren(...[["relu", "ReLU"], ["sigmoide", "Sigmoide"]].map(([k, t]) => el("button", {
      type: "button", clase: "segmento", texto: t, "aria-pressed": String(neurona.tipo === k),
      en: { click: () => { neurona.tipo = k; controlesNeurona(); pintarNeurona(); } } })));
  }

  /* ---------- 2. Convolución ---------- */
  const IMAGEN = [
    "0000000000", "0111111110", "0111111110", "0000001100", "0000011000",
    "0000110000", "0001100000", "0001100000", "0001100000", "0000000000",
  ].map((f) => f.split("").map(Number));
  const FILTROS = {
    vertical: { nombre: "Bordes verticales", k: [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]] },
    horizontal: { nombre: "Bordes horizontales", k: [[-1, -2, -1], [0, 0, 0], [1, 2, 1]] },
    suave: { nombre: "Suavizado", k: [[1, 1, 1], [1, 1, 1], [1, 1, 1]].map((f) => f.map((v) => v / 9)) },
  };
  let filtro = "vertical";
  let posicion = 0;
  let reloj = null;
  let salida = [];

  function resultadoEn(f, c) {
    const k = FILTROS[filtro].k;
    let s = 0;
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) s += IMAGEN[f + i][c + j] * k[i][j];
    return s;
  }
  function tono(v, max) {
    const t = Math.min(1, Math.abs(v) / (max || 1));
    const base = v >= 0 ? "var(--violeta)" : "var(--rosa)";
    return `color-mix(in srgb, ${base} ${Math.round(t * 85)}%, var(--superficie))`;
  }
  function pintarConv() {
    $("filtros-conv").replaceChildren(...Object.entries(FILTROS).map(([k, f]) => el("button", {
      type: "button", clase: "segmento", texto: f.nombre, "aria-pressed": String(k === filtro),
      en: { click: () => { filtro = k; reiniciarConv(); } } })));
    $("conv-entrada").replaceChildren(...IMAGEN.flatMap((fila, f) => fila.map((v, c) => {
      const dentro = posicion < 64 && f >= Math.floor(posicion / 8) && f < Math.floor(posicion / 8) + 3 && c >= posicion % 8 && c < (posicion % 8) + 3;
      return el("span", { clase: "celda-rej" + (dentro ? " ventana" : ""), estilo: { background: v ? "var(--tinta)" : "var(--superficie-2)" } });
    })));
    const k = FILTROS[filtro].k;
    const maxK = Math.max(...k.flat().map(Math.abs));
    $("conv-filtro").replaceChildren(...k.flatMap((fila) => fila.map((v) => el("span", { clase: "celda-rej con-texto", estilo: { background: tono(v, maxK) }, texto: coma(v, Math.abs(v) < 1 && v !== 0 ? 2 : 0) }))));
    const maxS = Math.max(1, ...Array.from({ length: 64 }, (_, i) => Math.abs(resultadoEn(Math.floor(i / 8), i % 8))));
    $("conv-salida").replaceChildren(...Array.from({ length: 64 }, (_, i) => el("span", { clase: "celda-rej" + (i === posicion - 1 ? " ventana" : ""),
      estilo: { background: i < salida.length ? tono(salida[i], maxS) : "var(--superficie-2)" } })));
  }
  function pasoConv() {
    if (posicion >= 64) { detenerConv(); return; }
    const f = Math.floor(posicion / 8), c = posicion % 8;
    salida.push(resultadoEn(f, c));
    const k = FILTROS[filtro].k;
    const terminos = [];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) if (IMAGEN[f + i][c + j] && k[i][j]) terminos.push(`${coma(k[i][j], 0 === Math.abs(k[i][j] % 1) ? 0 : 2)}`);
    $("cuenta-conv").textContent = `Posición (${f + 1}, ${c + 1}): suma de los pesos del filtro sobre los píxeles encendidos${terminos.length ? ` (${terminos.join(" + ")})` : ""} = ${coma(salida[salida.length - 1])}`;
    posicion += 1;
    pintarConv();
    if (posicion >= 64) detenerConv();
  }
  function detenerConv() { clearInterval(reloj); reloj = null; $("jugar-conv").textContent = "Animar"; }
  function reiniciarConv() { detenerConv(); posicion = 0; salida = []; $("cuenta-conv").textContent = "Pulsa «Animar» o «Un paso»."; pintarConv(); }

  /* ---------- 3. Red completa ---------- */
  const lienzo = App.lienzo($("lienzo-red"), () => { if (!lienzo.vacio()) verRed(); });
  async function verRed() {
    if (lienzo.vacio()) { avisar("Dibuja un dígito primero.", "error"); return; }
    try {
      const r = await api("/api/por-dentro", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ imagen: lienzo.imagen() }) });
      $("capas-red").replaceChildren(
        el("div", { clase: "capa-red" }, el("h3", { texto: "Entrada" }), el("img", { src: r.entrada, alt: "Tu dibujo en 28×28", clase: "reto-mini" }),
          el("p", { texto: "Tu dibujo se recorta, se centra y se lleva a 28×28 píxeles." })),
        ...r.capas.map((c) => el("div", { clase: "capa-red" }, el("h3", { texto: c.titulo }), el("img", { src: c.uri, alt: c.titulo, clase: "mosaico" }), el("p", { texto: c.detalle }))),
        el("div", { clase: "capa-red" }, el("h3", { texto: `Salida: ${r.predicho}` }),
          el("div", { clase: "barras-prob", estilo: { "--color": "var(--m-cnn)" } }, r.probabilidades.map((p, i) => el("div", { clase: "fila" + (i === r.predicho ? " elegida" : ""), estilo: { "--valor": (p * 100).toFixed(1), "--orden": i } },
            el("span", { texto: String(i) }), el("div", { clase: "pista" }, el("div", { clase: "relleno" })), el("span", { texto: porcentaje(p, 0) })))),
          el("p", { texto: "La última capa tiene 10 neuronas, una por dígito; la más encendida es la respuesta." })));
    } catch (e) { avisar(e.message, "error"); }
  }

  /* ---------- 4. Descenso del gradiente ---------- */
  const descenso = { w: -1, pasos: 0, tasa: 0.2 };
  const perdida = (w) => 0.35 * (w - 2) * (w - 2) + 0.15;
  function pintarDescenso() {
    const c = $("lienzo-descenso");
    const ctx = c.getContext("2d");
    const [W, H] = [c.width, c.height];
    ctx.clearRect(0, 0, W, H);
    const px = (w) => ((w + 3) / 10) * W;
    const py = (l) => H - 16 - (l / 7) * (H - 32);
    ctx.strokeStyle = css("--violeta");
    ctx.lineWidth = 3.5;
    ctx.beginPath();
    for (let i = 0; i <= 100; i++) { const w = -3 + (10 * i) / 100; i ? ctx.lineTo(px(w), py(perdida(w))) : ctx.moveTo(px(w), py(perdida(w))); }
    ctx.stroke();
    const wc = Math.max(-3, Math.min(7, descenso.w));
    ctx.fillStyle = css("--rosa");
    ctx.strokeStyle = css("--superficie");
    ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(px(wc), py(Math.min(7, perdida(wc))), 9, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = css("--tinta-suave");
    ctx.font = '12px "DM Sans", sans-serif';
    ctx.fillText("peso", W - 40, H - 4);
    ctx.fillText("error", 8, 14);
    const l = perdida(descenso.w);
    $("texto-descenso").textContent = descenso.pasos ? `Paso ${descenso.pasos}: error = ${coma(l, 3)}${l < 0.16 ? " (llegó al mínimo)" : Math.abs(descenso.w) > 6 ? " (se salió: la tasa es demasiado grande)" : ""}` : `Error inicial = ${coma(l, 3)}. El mínimo está en peso = 2.`;
  }
  function pasoDescenso() {
    descenso.w -= descenso.tasa * 0.7 * (descenso.w - 2);
    descenso.pasos += 1;
    pintarDescenso();
  }

  (function iniciar() {
    controlesNeurona();
    pintarNeurona();
    pintarConv();
    $("jugar-conv").addEventListener("click", () => {
      if (reloj) { detenerConv(); return; }
      if (posicion >= 64) reiniciarConv();
      $("jugar-conv").textContent = "Pausar";
      reloj = setInterval(pasoConv, reducir ? 60 : 130);
    });
    $("paso-conv").addEventListener("click", () => { detenerConv(); pasoConv(); });
    $("reiniciar-conv").addEventListener("click", reiniciarConv);
    $("limpiar-red").addEventListener("click", () => { lienzo.limpiar(); $("capas-red").replaceChildren(el("p", { clase: "vacio", texto: "Dibuja un dígito para ver sus capas." })); });
    $("ver-red").addEventListener("click", verRed);
    $("tasa-demo").addEventListener("input", (e) => { descenso.tasa = parseFloat(e.target.value); $("valor-tasa").textContent = coma(descenso.tasa); });
    $("paso-descenso").addEventListener("click", pasoDescenso);
    $("reiniciar-descenso").addEventListener("click", () => { descenso.w = -1; descenso.pasos = 0; pintarDescenso(); });
    pintarDescenso();
    document.addEventListener("tema-cambiado", () => { pintarNeurona(); pintarDescenso(); });
  })();
})();
