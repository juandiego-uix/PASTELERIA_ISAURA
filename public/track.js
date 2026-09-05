const form = document.querySelector("#tracking-form");
const result = document.querySelector("#tracking-result");
const escapeHtml = (value) => String(value ?? "").replace(/[&<>\'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#039;", '"': "&quot;" }[character]));
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = new FormData(form).get("token");
  result.textContent = "Consultando...";
  try {
    const response = await fetch(`/api/track/${encodeURIComponent(token)}`);
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "Pedido no encontrado");
    const order = body.data;
    result.innerHTML = `<article class="tracking-card"><p class="eyebrow">Pedido #${escapeHtml(order.id)}</p><h2>${escapeHtml(order.estado)}</h2><p>Entrega: <strong>${escapeHtml(order.fecha)} · ${escapeHtml(order.hora)}</strong></p><p>${escapeHtml(order.descripcion)}</p></article>`;
  } catch (error) {
    result.textContent = error.message;
  }
});

const queryToken = new URLSearchParams(window.location.search).get("token");
if (queryToken) {
  form.elements.token.value = queryToken;
  form.requestSubmit();
}
