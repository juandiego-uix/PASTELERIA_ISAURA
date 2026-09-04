const tokenKey = "isaura-admin-token";
const select = (selector) => document.querySelector(selector);
let dashboard;

function showToast(message) {
  const toast = select("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2500);
}

async function api(path, options = {}) {
  const headers = {
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    Authorization: `Bearer ${localStorage.getItem(tokenKey) || ""}`,
    ...(options.headers || {}),
  };
  const response = await fetch(path, { ...options, headers });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || "Solicitud no válida");
  return body;
}

function showAdminPanel() {
  select("#login-view").hidden = true;
  select("#admin-view").hidden = false;
  loadDashboard();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>\'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#039;", '"': "&quot;",
  }[character]));
}

function renderDashboard() {
  const metrics = dashboard.metrics;
  select("#metrics").innerHTML = `
    <div class="metric"><span>Pedidos pendientes hoy</span><strong>${metrics.pending_today}</strong></div>
    <div class="metric"><span>Entregados este mes</span><strong>${metrics.delivered_month}</strong></div>
    <div class="metric"><span>Productos publicados</span><strong>${dashboard.products.length}</strong></div>`;

  select("#orders-table").innerHTML = dashboard.orders.map((order) => `
    <tr>
      <td><strong>${order.fecha}</strong><br>${order.hora}</td>
      <td><strong>${escapeHtml(order.nombre_cliente)}</strong><br><small>${escapeHtml(order.contacto)}</small></td>
      <td>${escapeHtml(order.descripcion)}</td>
      <td>$${Number(order.precio).toLocaleString("es-CO")}<br><small>${escapeHtml(order.tipo_pago)}</small></td>
      <td><select class="status-select" data-status="${order.id}">
        ${["Pendiente", "En Preparación", "Entregado"].map((status) => `<option ${status === order.estado ? "selected" : ""}>${status}</option>`).join("")}
      </select></td>
      <td><button class="danger" data-delete-order="${order.id}">Eliminar</button></td>
    </tr>`).join("") || `<tr><td colspan="6">No hay pedidos todavía.</td></tr>`;

  select("#products-list").innerHTML = dashboard.products.map((product) => `
    <article class="admin-product">
      <img src="${product.image_url || `/uploads/${encodeURIComponent(product.imagen || "")}`}" alt="">
      <strong>${escapeHtml(product.nombre)}</strong>
      <small>${escapeHtml(product.categoria)}</small>
      <button class="danger" data-delete-product="${product.id}">Eliminar</button>
    </article>`).join("") || "<p>No hay productos.</p>";
}

async function loadDashboard() {
  try {
    dashboard = await api("/api/admin/dashboard");
    renderDashboard();
  } catch (error) {
    showToast(error.message);
  }
}

select("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  select("#login-error").textContent = "";
  try {
    const result = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    if (!result.success || !result.token) throw new Error("El servidor no devolvió una sesión válida");
    localStorage.setItem(tokenKey, result.token);
    window.location.replace("/admin.html?view=dashboard");
  } catch (error) {
    select("#login-error").textContent = error.message;
    button.disabled = false;
  }
});

if (localStorage.getItem(tokenKey)) showAdminPanel();

select("#logout").addEventListener("click", () => {
  localStorage.removeItem(tokenKey);
  window.location.replace("/admin.html");
});

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
  tab.classList.add("active");
  select("#orders-panel").hidden = tab.dataset.tab !== "orders";
  select("#products-panel").hidden = tab.dataset.tab !== "products";
}));

select("#new-order").addEventListener("click", () => select("#order-dialog").showModal());
select("#new-product").addEventListener("click", () => select("#product-dialog").showModal());

select("#order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/admin/orders", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
    event.currentTarget.closest("dialog").close();
    event.currentTarget.reset();
    await loadDashboard();
    showToast("Pedido guardado");
  } catch (error) { showToast(error.message); }
});

select("#product-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/admin/products", { method: "POST", body: new FormData(event.currentTarget) });
    event.currentTarget.closest("dialog").close();
    event.currentTarget.reset();
    await loadDashboard();
    showToast("Producto guardado");
  } catch (error) { showToast(error.message); }
});

select("#orders-table").addEventListener("change", async (event) => {
  if (!event.target.dataset.status) return;
  try {
    await api(`/api/admin/orders/${event.target.dataset.status}`, { method: "PATCH", body: JSON.stringify({ estado: event.target.value }) });
    showToast("Estado actualizado");
  } catch (error) { showToast(error.message); }
});

document.addEventListener("click", async (event) => {
  const orderId = event.target.dataset.deleteOrder;
  const productId = event.target.dataset.deleteProduct;
  if (!orderId && !productId) return;
  if (!window.confirm("¿Eliminar este registro?")) return;
  const resource = orderId ? "orders" : "products";
  try {
    await api(`/api/admin/${resource}/${orderId || productId}`, { method: "DELETE" });
    await loadDashboard();
    showToast("Registro eliminado");
  } catch (error) { showToast(error.message); }
});
