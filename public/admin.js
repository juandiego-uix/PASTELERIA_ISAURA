const select = (selector) => document.querySelector(selector);
const BUSINESS_WHATSAPP = "573215457378";
let dashboard = { orders: [], products: [], metrics: {} };
let notifiedOrders = new Set(JSON.parse(localStorage.getItem("isaura-alerted-orders") || "[]"));
let dismissedAlerts = new Set(JSON.parse(localStorage.getItem("isaura-dismissed-alerts") || "[]"));
let csrfToken = "";
let cashflowChart;
let paymentChart;
let deferredInstallPrompt;

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
  if (csrfToken && options.method && !["GET", "HEAD", "OPTIONS"].includes(options.method.toUpperCase())) headers["X-CSRF-Token"] = csrfToken;
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

function money(value) {
  return `$${Number(value || 0).toLocaleString("es-CO")}`;
}

function orderWhatsAppMessage(order) {
  return `Hola Isaura,\n\nRecordatorio de pedido próximo\n\nCliente: ${order.nombre_cliente}\nContacto: ${order.contacto}\nFecha de entrega: ${order.fecha}\nHora de entrega: ${order.hora}\nEstado del pedido: ${order.estado}\nEstado de pago: ${order.tipo_pago}\nAbono: ${money(order.abono)}\nTotal: ${money(order.precio)}\nDescripción: ${order.descripcion}\n\nPor favor preparar este pedido con anticipación.\n\nIsaura Cerpa - Repostería Artesanal`;
}

function orderWhatsAppUrl(order) {
  return `https://wa.me/${BUSINESS_WHATSAPP}?text=${encodeURIComponent(orderWhatsAppMessage(order))}`;
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
    return !["Entregado", "Cancelado"].includes(order.estado) && days >= 0 && days <= 2;
  });
  select("#alerts").innerHTML = alerts.map((order) => {
    const days = daysUntil(order.fecha);
    const label = days === 0 ? "Entrega hoy" : `Faltan ${days} día${days === 1 ? "" : "s"}`;
    if (dismissedAlerts.has(String(order.id))) return "";
    return `<article class="alert"><div><strong>${escapeHtml(label)}: ${escapeHtml(order.nombre_cliente)}</strong><small>${escapeHtml(order.descripcion)} · ${escapeHtml(order.fecha)} a las ${escapeHtml(order.hora)}</small></div><div class="row-actions"><a class="detail-button" href="${orderWhatsAppUrl(order)}" target="_blank" rel="noopener">WhatsApp</a><button class="detail-button" data-detail="${order.id}" type="button">Ver detalles</button><button class="detail-button" data-dismiss-alert="${order.id}" type="button">Entendido</button></div></article>`;
  }).join("");
  alerts.forEach((order) => {
    const days = daysUntil(order.fecha);
    if (days <= 2 && !notifiedOrders.has(order.id)) {
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
    const warning = order.estado !== "Entregado" && days <= 2 ? "warning" : "";
    return `<tr>
      <td class="delivery-date ${warning}"><strong>${escapeHtml(order.fecha)}</strong><br><small>${escapeHtml(order.hora)}</small></td>
      <td><strong>${escapeHtml(order.nombre_cliente)}</strong><br><small>${escapeHtml(order.contacto)}</small></td>
      <td><span class="payment-badge">${escapeHtml(order.tipo_pago)}</span><br><small>Abono: $${Number(order.abono || 0).toLocaleString("es-CO")} · Total: $${Number(order.precio || 0).toLocaleString("es-CO")}</small></td>
      <td><select class="status-select" data-status="${order.id}">${["Pendiente", "Confirmado", "En producción", "Listo", "Entregado", "Cancelado"].map((status) => `<option ${status === order.estado ? "selected" : ""}>${status}</option>`).join("")}</select></td>
      <td class="row-actions"><button class="detail-button" data-detail="${order.id}" type="button">Ver detalles</button><button class="detail-button" data-edit-order="${order.id}" type="button">Editar</button><button class="danger" data-delete-order="${order.id}" type="button">Eliminar</button></td>
    </tr>`;
  }).join("") || `<tr><td colspan="5">No hay pedidos todavía.</td></tr>`;
  select("#products-list").innerHTML = dashboard.products.map((product) => `<article class="admin-product"><img src="${product.image_url || `/uploads/${encodeURIComponent(product.imagen || "")}`}" alt="${escapeHtml(product.nombre)}"><strong>${escapeHtml(product.nombre)}</strong><small>${escapeHtml(product.categoria)}</small><div class="row-actions"><button class="detail-button" data-edit-product="${product.id}" type="button">Editar</button><button class="danger" data-delete-product="${product.id}" type="button">Eliminar</button></div></article>`).join("") || "<p>No hay productos.</p>";
  select("#inventory-table").innerHTML = (dashboard.inventory || []).map((item) => {
    const lowStock = Number(item.stock_actual) <= Number(item.stock_minimo);
    return `<tr class="${lowStock ? "low-stock" : ""}"><td><strong>${escapeHtml(item.ingrediente)}</strong></td><td>${Number(item.stock_actual).toLocaleString("es-CO")}</td><td>${Number(item.stock_minimo).toLocaleString("es-CO")}</td><td>${escapeHtml(item.unidad)}</td><td><span class="payment-badge">${lowStock ? "Stock bajo" : "Disponible"}</span></td><td><button class="detail-button" data-edit-inventory="${item.id}" type="button">Actualizar</button></td></tr>`;
  }).join("") || `<tr><td colspan="6">No hay insumos registrados.</td></tr>`;
  renderCharts();
  renderAlerts();
}

function renderCharts() {
  if (!window.Chart) return;
  cashflowChart?.destroy(); paymentChart?.destroy();
  const labels = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
  cashflowChart = new Chart(select("#cashflow-chart"), { type: "bar", data: { labels, datasets: [{ label: "Abonos", data: dashboard.metrics.monthly_cashflow || [], backgroundColor: "#bd6e4d" }] }, options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } } });
  const payments = dashboard.metrics.payment_distribution || {};
  paymentChart = new Chart(select("#payment-chart"), { type: "doughnut", data: { labels: Object.keys(payments), datasets: [{ data: Object.values(payments), backgroundColor: ["#27352f", "#bd6e4d", "#a9b9a1"] }] }, options: { plugins: { legend: { position: "bottom" } } } });
}

function renderProduction(orders) {
  select("#production-list").innerHTML = orders.length ? orders.map((order) => `<article class="production-card"><div><strong>${escapeHtml(order.hora)} · ${escapeHtml(order.nombre_cliente)}</strong><small>${escapeHtml(order.descripcion)}</small></div><label><input type="checkbox" data-production-check="${order.id}"> Preparado</label><button class="detail-button" data-production-ready="${order.id}" type="button">Marcar listo</button></article>`).join("") : "<p class='status'>No hay pedidos para producción hoy.</p>";
}

function renderFinance(summary) {
  select("#finance-summary").innerHTML = Object.entries({ "Ventas": summary.ventas, "Abonos": summary.abonos, "Por cobrar": summary.por_cobrar, "Gastos": summary.gastos, "Utilidad neta": summary.utilidad_neta }).map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${money(value)}</strong></div>`).join("");
}

async function loadProduction() {
  try { const response = await api("/api/admin/production/today"); renderProduction(response.data || []); } catch (error) { showToast(error.message); }
}

async function loadFinance() {
  try { const response = await api("/api/admin/reports/summary"); renderFinance(response.data || {}); } catch (error) { showToast(error.message); }
}

async function loadDashboard() {
  try { dashboard = await api("/api/admin/dashboard"); renderDashboard(); }
  catch (error) { showToast(error.message); }
}

async function showAdminPanel() { select("#login-container").style.display = "none"; select("#admin-view").hidden = false; select("#install-dashboard").hidden = false; try { csrfToken = (await api("/api/auth/csrf")).token; await loadDashboard(); } catch (error) { showToast(error.message); } }

window.addEventListener("beforeinstallprompt", (event) => { event.preventDefault(); deferredInstallPrompt = event; const button = select("#install-dashboard"); if (button) button.hidden = false; });
select("#install-dashboard").addEventListener("click", async () => { if (!deferredInstallPrompt) { showToast("En iPhone: pulsa Compartir y luego Añadir a pantalla de inicio."); return; } deferredInstallPrompt.prompt(); await deferredInstallPrompt.userChoice; deferredInstallPrompt = null; select("#install-dashboard").hidden = true; });
window.addEventListener("appinstalled", () => { const button = select("#install-dashboard"); if (button) button.hidden = true; });

function showOrderDetails(order) {
  const days = daysUntil(order.fecha);
  select("#order-details").innerHTML = `<div class="details-grid"><div class="detail-item"><strong>Cliente</strong><span>${escapeHtml(order.nombre_cliente)}</span></div><div class="detail-item"><strong>Contacto</strong><span>${escapeHtml(order.contacto)}</span></div><div class="detail-item"><strong>Entrega</strong><span>${escapeHtml(order.fecha)} · ${escapeHtml(order.hora)} (${days < 0 ? "vencido" : `faltan ${days} días`})</span></div><div class="detail-item"><strong>Estado del pedido</strong><span>${escapeHtml(order.estado)}</span></div><div class="detail-item"><strong>Estado de pago</strong><span>${escapeHtml(order.tipo_pago)}</span></div><div class="detail-item"><strong>Importes</strong><span>Abono: ${money(order.abono)} · Total: ${money(order.precio)}</span></div><div class="detail-item detail-full"><strong>Descripción</strong><span>${escapeHtml(order.descripcion)}</span></div></div>`;
  select("#whatsapp-alert").href = orderWhatsAppUrl(order);
  select("#receipt-link").href = `/api/admin/orders/${order.id}/receipt.pdf`;
  select("#order-history").textContent = "Cargando historial...";
  openModal("details-dialog");
  api(`/api/admin/orders/${order.id}/history`).then((response) => {
    const history = response.data || [];
    select("#order-history").innerHTML = history.length
      ? `<strong>Historial</strong><br>${history.map((entry) => `${escapeHtml(entry.created_at || "")} · ${escapeHtml(entry.estado_anterior || "Nuevo")} → ${escapeHtml(entry.estado_nuevo)}`).join("<br>")}`
      : "Sin cambios de estado registrados.";
  }).catch(() => { select("#order-history").textContent = "No se pudo cargar el historial."; });
}

function downloadMonthlyReport() {
  const month = new Date().toISOString().slice(0, 7);
  const monthOrders = dashboard.orders.filter((order) => String(order.fecha || "").startsWith(month));
  const totalSales = monthOrders.reduce((sum, order) => sum + Number(order.precio || 0), 0);
  const totalDeposits = monthOrders.reduce((sum, order) => sum + Number(order.abono || 0), 0);
  const delivered = monthOrders.filter((order) => order.estado === "Entregado").length;
  const rows = monthOrders.map((order) => `<tr><td>${escapeHtml(order.fecha)}</td><td>${escapeHtml(order.hora)}</td><td>${escapeHtml(order.nombre_cliente)}</td><td>${escapeHtml(order.descripcion)}</td><td>${escapeHtml(order.estado)}</td><td>${escapeHtml(order.tipo_pago)}</td><td>${money(order.abono)}</td><td>${money(order.precio)}</td></tr>`).join("");
  const html = `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Informe mensual ${month}</title><style>body{font:14px Arial;color:#27352f;margin:40px}h1{font:28px Georgia}table{width:100%;border-collapse:collapse;margin-top:24px}th,td{border:1px solid #d9ddd5;padding:8px;text-align:left}th{background:#eef0eb}.summary{display:flex;gap:28px;padding:16px;background:#f7f3eb}.summary strong{display:block;font-size:20px;margin-top:5px}@media print{body{margin:18px}}</style></head><body><h1>Isaura Cerpa - Informe mensual</h1><p>Periodo: ${month}</p><section class="summary"><div>Pedidos<strong>${monthOrders.length}</strong></div><div>Ventas<strong>${money(totalSales)}</strong></div><div>Abonos<strong>${money(totalDeposits)}</strong></div><div>Entregados<strong>${delivered}</strong></div></section><table><thead><tr><th>Fecha</th><th>Hora</th><th>Cliente</th><th>Descripción</th><th>Estado</th><th>Pago</th><th>Abono</th><th>Total</th></tr></thead><tbody>${rows || "<tr><td colspan='8'>No hay pedidos en este periodo.</td></tr>"}</tbody></table></body></html>`;
  const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `informe-isaura-${month}.html`;
  link.click();
  URL.revokeObjectURL(url);
}

function openOrderEditor(order) {
  const form = select("#edit-order-form");
  Object.entries(order).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value ?? ""; });
  openModal("edit-order-dialog");
}

function openProductEditor(product) {
  const form = select("#edit-product-form");
  Object.entries(product).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value ?? ""; });
  openModal("edit-product-dialog");
}

function openInventoryEditor(item = {}) {
  const form = select("#inventory-form");
  Object.entries(item).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value ?? ""; });
  select("#inventory-dialog-title").textContent = item.id ? "Actualizar stock" : "Añadir ingrediente";
  openModal("inventory-dialog");
}

select("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    const result = await api("/api/login", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) });
    if (result.success !== true) throw new Error(result.error || "Credenciales no válidas");
    window.location.replace("/admin.html?view=dashboard");
  } catch (error) { select("#login-error").textContent = error.message; button.disabled = false; }
});

async function restoreSession() { try { if ((await api("/api/auth/session")).success) showAdminPanel(); } catch { /* El login permanece visible. */ } }
restoreSession();

if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/admin-sw.js", { scope: "/admin.html" }));

select("#logout").addEventListener("click", async () => { try { await api("/api/logout", { method: "POST" }); } finally { localStorage.clear(); window.location.replace("/admin.html"); } });
select("#download-report").addEventListener("click", downloadMonthlyReport);
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => closeModal(button.dataset.close)));
document.querySelectorAll("dialog").forEach((modal) => modal.addEventListener("click", (event) => { if (event.target === modal) closeModal(modal.id); }));
document.addEventListener("keydown", (event) => { if (event.key === "Escape") document.querySelectorAll("dialog[open]").forEach((modal) => closeModal(modal.id)); });

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => { document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active")); tab.classList.add("active"); ["orders", "products", "inventory", "production", "finance"].forEach((panel) => { select(`#${panel}-panel`).hidden = tab.dataset.tab !== panel; }); if (tab.dataset.tab === "production") loadProduction(); if (tab.dataset.tab === "finance") loadFinance(); }));
select("#new-order").addEventListener("click", () => openModal("order-dialog"));
select("#new-product").addEventListener("click", () => openModal("product-dialog"));
select("#new-inventory").addEventListener("click", () => openInventoryEditor());
select("#reload-production").addEventListener("click", loadProduction);
select("#archive-completed").addEventListener("click", async () => { if (!window.confirm("Se archivarán los pedidos Entregados o Cancelados con más de 30 días. No se borrarán. ¿Continuar?")) return; try { const response = await api("/api/admin/orders/archive-completed", { method: "POST" }); await loadDashboard(); showToast(response.message || `${response.archived || 0} pedido(s) archivado(s)`); } catch (error) { showToast(`No se pudo archivar: ${error.message}`); } });
select("#reset-finance").addEventListener("click", async () => { const confirmation = window.prompt("Esto pondrá ventas, abonos y gastos en cero, pero conservará clientes y productos. Escribe BORRAR TODO para continuar:"); if (confirmation !== "BORRAR TODO") return; if (!window.confirm("Última advertencia: se eliminarán los gastos y se pondrán en cero los importes de todos los pedidos. ¿Confirmas?")) return; try { await api("/api/admin/reports/reset", { method: "POST", body: JSON.stringify({ confirmacion: confirmation }) }); await loadDashboard(); await loadFinance(); showToast("Resumen financiero reiniciado"); } catch (error) { showToast(error.message); } });

select("#order-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; try { const result = await api("/api/admin/orders", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) }); dashboard.orders.push(result.data); form.reset(); closeModal("order-dialog", false); renderDashboard(); showToast("Pedido guardado"); } catch (error) { showToast(error.message); } });
select("#product-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; try { const result = await api("/api/admin/products", { method: "POST", body: new FormData(form) }); dashboard.products.unshift(result.data); form.reset(); closeModal("product-dialog", false); renderDashboard(); showToast("Producto guardado"); } catch (error) { showToast(error.message); } });

select("#edit-order-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; const id = form.elements.id.value; try { const payload = Object.fromEntries(new FormData(form)); delete payload.id; const result = await api(`/api/pedidos/${id}`, { method: "PUT", body: JSON.stringify(payload) }); const index = dashboard.orders.findIndex((order) => String(order.id) === id); if (index >= 0) dashboard.orders[index] = { ...dashboard.orders[index], ...(result.data || payload), id: Number(id) }; form.reset(); closeModal("edit-order-dialog", false); renderDashboard(); showToast("Pedido actualizado"); } catch (error) { showToast(error.message); } });
select("#edit-product-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; const id = form.elements.id.value; try { const payload = Object.fromEntries(new FormData(form)); delete payload.id; const result = await api(`/api/productos/${id}`, { method: "PUT", body: JSON.stringify(payload) }); const index = dashboard.products.findIndex((product) => String(product.id) === id); if (index >= 0) dashboard.products[index] = { ...dashboard.products[index], ...(result.data || payload), id: Number(id) }; form.reset(); closeModal("edit-product-dialog", false); renderDashboard(); showToast("Producto actualizado"); } catch (error) { showToast(error.message); } });
select("#inventory-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; try { const payload = Object.fromEntries(new FormData(form)); if (!payload.id) delete payload.id; const result = await api("/api/insumos", { method: "POST", body: JSON.stringify(payload) }); const saved = result.data; const index = dashboard.inventory.findIndex((item) => String(item.id) === String(saved.id)); if (index >= 0) dashboard.inventory[index] = saved; else dashboard.inventory.push(saved); dashboard.inventory.sort((left, right) => left.ingrediente.localeCompare(right.ingrediente)); form.reset(); closeModal("inventory-dialog", false); renderDashboard(); showToast("Inventario actualizado"); } catch (error) { showToast(error.message); } });

select("#orders-table").addEventListener("change", async (event) => { if (!event.target.dataset.status) return; try { await api(`/api/admin/orders/${event.target.dataset.status}`, { method: "PATCH", body: JSON.stringify({ estado: event.target.value }) }); const order = dashboard.orders.find((item) => String(item.id) === event.target.dataset.status); if (order) order.estado = event.target.value; renderDashboard(); showToast("Estado actualizado"); } catch (error) { showToast(error.message); } });

document.addEventListener("click", async (event) => { const readyId = event.target.dataset.productionReady; if (readyId) { try { await api(`/api/admin/orders/${readyId}/lifecycle`, { method: "PATCH", body: JSON.stringify({ estado: "Listo" }) }); await loadProduction(); showToast("Pedido marcado como listo"); } catch (error) { showToast(error.message); } return; } const dismissId = event.target.dataset.dismissAlert; if (dismissId) { dismissedAlerts.add(String(dismissId)); localStorage.setItem("isaura-dismissed-alerts", JSON.stringify([...dismissedAlerts])); renderAlerts(); return; } const detailId = event.target.dataset.detail; if (detailId) { const order = dashboard.orders.find((item) => String(item.id) === detailId); if (order) showOrderDetails(order); return; } const editOrderId = event.target.dataset.editOrder; if (editOrderId) { const order = dashboard.orders.find((item) => String(item.id) === editOrderId); if (order) openOrderEditor(order); return; } const editProductId = event.target.dataset.editProduct; if (editProductId) { const product = dashboard.products.find((item) => String(item.id) === editProductId); if (product) openProductEditor(product); return; } const editInventoryId = event.target.dataset.editInventory; if (editInventoryId) { const item = dashboard.inventory.find((entry) => String(entry.id) === editInventoryId); if (item) openInventoryEditor(item); return; } const orderId = event.target.dataset.deleteOrder; const productId = event.target.dataset.deleteProduct; if (!orderId && !productId) return; if (!window.confirm("¿Eliminar este registro?")) return; try { const resource = orderId ? "orders" : "products"; await api(`/api/admin/${resource}/${orderId || productId}`, { method: "DELETE" }); if (orderId) dashboard.orders = dashboard.orders.filter((item) => String(item.id) !== orderId); else dashboard.products = dashboard.products.filter((item) => String(item.id) !== productId); renderDashboard(); showToast("Registro eliminado"); } catch (error) { showToast(error.message); } });
