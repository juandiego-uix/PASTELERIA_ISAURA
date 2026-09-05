const select = (selector) => document.querySelector(selector);
let dashboard = { orders: [], products: [], metrics: {} };
let notifiedOrders = new Set(JSON.parse(localStorage.getItem("isaura-alerted-orders") || "[]"));

function showToast(message) {
  const toast = select("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 3000);
}

async function api(path, options = {}) {
  const headers = {
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers || {}),
  };
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || "Solicitud no válida");
  return body;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>\'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#039;", '"': "&quot;",
  }[character]));
}

function openModal(id) {
  const modal = select(`#${id}`);
  if (modal && !modal.open) modal.showModal();
}

function closeModal(id, reset = true) {
  const modal = select(`#${id}`);
  if (!modal) return;
  if (reset) modal.querySelector("form")?.reset();
  if (modal.open) modal.close();
}

function daysUntil(dateValue) {
  const delivery = new Date(`${dateValue}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.ceil((delivery - today) / 86400000);
}

function requestNotifications() {
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
}

function renderAlerts() {
  const alerts = dashboard.orders.filter((order) => {
    const days = daysUntil(order.fecha);
    return order.estado !== "Entregado" && days <= 3;
  });
  select("#alerts").innerHTML = alerts.map((order) => {
    const days = daysUntil(order.fecha);
    const label = days < 0 ? "Entrega vencida" : days === 0 ? "Entrega hoy" : `Faltan ${days} día${days === 1 ? "" : "s"}`;
    return `<article class="alert"><div><strong>${escapeHtml(label)}: ${escapeHtml(order.nombre_cliente)}</strong><small>${escapeHtml(order.descripcion)} · ${escapeHtml(order.fecha)} a las ${escapeHtml(order.hora)}</small></div><button class="detail-button" data-detail="${order.id}">Ver detalles</button></article>`;
  }).join("");
  alerts.forEach((order) => {
    const days = daysUntil(order.fecha);
    if (days <= 3 && !notifiedOrders.has(order.id)) {
      requestNotifications();
      if ("Notification" in window && Notification.permission === "granted") new Notification("Pedido próximo", { body: `${order.nombre_cliente}: entrega ${order.fecha}` });
      notifiedOrders.add(order.id);
    }
  });
  localStorage.setItem("isaura-alerted-orders", JSON.stringify([...notifiedOrders]));
}

function renderDashboard() {
  const metrics = dashboard.metrics;
  select("#metrics").innerHTML = `
    <div class="metric"><span>Pedidos pendientes hoy</span><strong>${metrics.pending_today}</strong></div>
    <div class="metric"><span>Entregados este mes</span><strong>${metrics.delivered_month}</strong></div>
    <div class="metric"><span>Productos publicados</span><strong>${dashboard.products.length}</strong></div>`;
  select("#orders-table").innerHTML = dashboard.orders.map((order) => {
    const days = daysUntil(order.fecha);
    const warning = order.estado !== "Entregado" && days <= 3 ? "warning" : "";
    return `<tr>
      <td class="delivery-date ${warning}"><strong>${escapeHtml(order.fecha)}</strong><br><small>${escapeHtml(order.hora)}</small></td>
      <td><strong>${escapeHtml(order.nombre_cliente)}</strong><br><small>${escapeHtml(order.contacto)}</small></td>
      <td><span class="payment-badge">${escapeHtml(order.tipo_pago)}</span><br><small>Abono: $${Number(order.abono || 0).toLocaleString("es-CO")} · Total: $${Number(order.precio || 0).toLocaleString("es-CO")}</small></td>
      <td><select class="status-select" data-status="${order.id}">${["Pendiente", "En Preparación", "Entregado"].map((status) => `<option ${status === order.estado ? "selected" : ""}>${status}</option>`).join("")}</select></td>
      <td class="row-actions"><button class="detail-button" data-detail="${order.id}" type="button">Ver detalles</button><button class="danger" data-delete-order="${order.id}" type="button">Eliminar</button></td>
    </tr>`;
  }).join("") || `<tr><td colspan="5">No hay pedidos todavía.</td></tr>`;
  select("#products-list").innerHTML = dashboard.products.map((product) => `<article class="admin-product"><img src="${product.image_url || `/uploads/${encodeURIComponent(product.imagen || "")}`}" alt="${escapeHtml(product.nombre)}"><strong>${escapeHtml(product.nombre)}</strong><small>${escapeHtml(product.categoria)}</small><button class="danger" data-delete-product="${product.id}" type="button">Eliminar</button></article>`).join("") || "<p>No hay productos.</p>";
  renderAlerts();
}

async function loadDashboard() {
  try { dashboard = await api("/api/admin/dashboard"); renderDashboard(); }
  catch (error) { showToast(error.message); }
}

function showAdminPanel() { select("#login-view").hidden = true; select("#admin-view").hidden = false; loadDashboard(); }

function showOrderDetails(order) {
  const days = daysUntil(order.fecha);
  const message = `Hola ${order.nombre_cliente}, te recordamos tu pedido en Isaura Cerpa.\n\nDetalle: ${order.descripcion}\nFecha: ${order.fecha}\nHora: ${order.hora}\nEstado: ${order.estado}\nPago: ${order.tipo_pago}\nAbono: $${Number(order.abono || 0).toLocaleString("es-CO")}\nTotal: $${Number(order.precio || 0).toLocaleString("es-CO")}`;
  select("#order-details").innerHTML = `<div class="details-grid"><div class="detail-item"><strong>Cliente</strong><span>${escapeHtml(order.nombre_cliente)}</span></div><div class="detail-item"><strong>Contacto</strong><span>${escapeHtml(order.contacto)}</span></div><div class="detail-item"><strong>Entrega</strong><span>${escapeHtml(order.fecha)} · ${escapeHtml(order.hora)} (${days < 0 ? "vencido" : `faltan ${days} días`})</span></div><div class="detail-item"><strong>Estado del pedido</strong><span>${escapeHtml(order.estado)}</span></div><div class="detail-item"><strong>Estado de pago</strong><span>${escapeHtml(order.tipo_pago)}</span></div><div class="detail-item"><strong>Importes</strong><span>Abono: $${Number(order.abono || 0).toLocaleString("es-CO")} · Total: $${Number(order.precio || 0).toLocaleString("es-CO")}</span></div><div class="detail-item detail-full"><strong>Descripción</strong><span>${escapeHtml(order.descripcion)}</span></div></div>`;
  select("#whatsapp-alert").href = `https://wa.me/${String(order.contacto || "").replace(/\D/g, "")}?text=${encodeURIComponent(message)}`;
  openModal("details-dialog");
}

select("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    const result = await api("/api/auth/login", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) });
    if (result.success !== true) throw new Error(result.error || "Credenciales no válidas");
    window.location.replace("/admin.html?view=dashboard");
  } catch (error) { select("#login-error").textContent = error.message; button.disabled = false; }
});

async function restoreSession() { try { if ((await api("/api/auth/session")).success) showAdminPanel(); } catch { /* El login permanece visible. */ } }
restoreSession();

select("#logout").addEventListener("click", () => { window.location.replace("/admin.html"); });
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => closeModal(button.dataset.close)));
document.querySelectorAll("dialog").forEach((modal) => modal.addEventListener("click", (event) => { if (event.target === modal) closeModal(modal.id); }));
document.addEventListener("keydown", (event) => { if (event.key === "Escape") document.querySelectorAll("dialog[open]").forEach((modal) => closeModal(modal.id)); });

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => { document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active")); tab.classList.add("active"); select("#orders-panel").hidden = tab.dataset.tab !== "orders"; select("#products-panel").hidden = tab.dataset.tab !== "products"; }));
select("#new-order").addEventListener("click", () => openModal("order-dialog"));
select("#new-product").addEventListener("click", () => openModal("product-dialog"));

select("#order-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; try { const result = await api("/api/admin/orders", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) }); dashboard.orders.push(result.data); form.reset(); closeModal("order-dialog", false); renderDashboard(); showToast("Pedido guardado"); } catch (error) { showToast(error.message); } });
select("#product-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; try { const result = await api("/api/admin/products", { method: "POST", body: new FormData(form) }); dashboard.products.unshift(result.data); form.reset(); closeModal("product-dialog", false); renderDashboard(); showToast("Producto guardado"); } catch (error) { showToast(error.message); } });

select("#orders-table").addEventListener("change", async (event) => { if (!event.target.dataset.status) return; try { await api(`/api/admin/orders/${event.target.dataset.status}`, { method: "PATCH", body: JSON.stringify({ estado: event.target.value }) }); const order = dashboard.orders.find((item) => String(item.id) === event.target.dataset.status); if (order) order.estado = event.target.value; renderDashboard(); showToast("Estado actualizado"); } catch (error) { showToast(error.message); } });

document.addEventListener("click", async (event) => { const detailId = event.target.dataset.detail; if (detailId) { const order = dashboard.orders.find((item) => String(item.id) === detailId); if (order) showOrderDetails(order); return; } const orderId = event.target.dataset.deleteOrder; const productId = event.target.dataset.deleteProduct; if (!orderId && !productId) return; if (!window.confirm("¿Eliminar este registro?")) return; try { const resource = orderId ? "orders" : "products"; await api(`/api/admin/${resource}/${orderId || productId}`, { method: "DELETE" }); if (orderId) dashboard.orders = dashboard.orders.filter((item) => String(item.id) !== orderId); else dashboard.products = dashboard.products.filter((item) => String(item.id) !== productId); renderDashboard(); showToast("Registro eliminado"); } catch (error) { showToast(error.message); } });
