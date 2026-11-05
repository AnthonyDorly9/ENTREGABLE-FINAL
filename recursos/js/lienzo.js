(function () {
  /* Lienzo de dibujo: trazo blanco sobre fondo negro, con mouse, lápiz o dedo. */
  App.lienzo = function (canvas, alCambiar) {
    const ctx = canvas.getContext("2d");
    let dibujando = false;
    let hayTrazo = false;
    let temporizador = null;

    function limpiar() {
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      hayTrazo = false;
    }
    function punto(e) {
      const r = canvas.getBoundingClientRect();
      return [(e.clientX - r.left) * (canvas.width / r.width), (e.clientY - r.top) * (canvas.height / r.height)];
    }
    function empezar(e) {
      e.preventDefault();
      canvas.setPointerCapture(e.pointerId);
      dibujando = true;
      hayTrazo = true;
      clearTimeout(temporizador);
      ctx.strokeStyle = "#fff";
      ctx.fillStyle = "#fff";
      ctx.lineWidth = 22;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      const [x, y] = punto(e);
      ctx.beginPath();
      ctx.arc(x, y, 11, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(x, y);
    }
    function mover(e) {
      if (!dibujando) return;
      e.preventDefault();
      const [x, y] = punto(e);
      ctx.lineTo(x, y);
      ctx.stroke();
    }
    function terminar() {
      if (!dibujando) return;
      dibujando = false;
      if (alCambiar) temporizador = setTimeout(alCambiar, 450);
    }
    canvas.style.touchAction = "none";
    canvas.addEventListener("pointerdown", empezar);
    canvas.addEventListener("pointermove", mover);
    canvas.addEventListener("pointerup", terminar);
    canvas.addEventListener("pointercancel", terminar);
    limpiar();
    return { limpiar, vacio: () => !hayTrazo, imagen: () => canvas.toDataURL("image/png") };
  };
})();
