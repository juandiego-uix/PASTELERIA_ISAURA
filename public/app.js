const state = {
  products: JSON.parse(localStorage.getItem("isaura-products") || "[]"),
  favorites: JSON.parse(localStorage.getItem("isaura-favorites") || "[]"),
};
const BUSINESS_WHATSAPP = "573215457378";
const $ = (selector) => document.querySelector(selector);
const imageUrl = (product) => product.image_url || `/uploads/${encodeURIComponent(product.imagen || "")}`;
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#039;", '"': "&quot;" }[char])); }
function toast(message) { const element = $("#toast"); element.textContent = message; element.classList.add("show"); setTimeout(() => element.classList.remove("show"), 2800); }
async function api(path, options = {}) { const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options }); const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body.error || "No se pudo completar la solicitud"); return body; }
function renderProducts() {
  const query = $("#searchInput").value.toLowerCase().trim();
  const products = state.products.filter((product) => `${product.nombre} ${product.categoria}`.toLowerCase().includes(query));
  $("#catalog-status").textContent = products.length ? `${products.length} ${products.length === 1 ? "creación disponible" : "creaciones disponibles"}` : "No encontramos resultados con esa búsqueda.";
  $("#products").innerHTML = products.map((product, index) => `<article class="product-card" style="animation-delay:${index * 50}ms"><div class="product-image"><img loading="lazy" src="${imageUrl(product)}" alt="${escapeHtml(product.nombre)}"></div><div class="product-info"><div><p class="product-category">${escapeHtml(product.categoria)}</p><h3>${escapeHtml(product.nombre)}</h3></div><div class="product-actions"><button class="like ${state.favorites.includes(product.nombre) ? "active" : ""}" data-favorite="${escapeHtml(product.nombre)}" aria-label="Marcar como favorito">♥</button></div></div></article>`).join("");
}
function renderSelection() {
  $("#favorite-count").textContent = state.favorites.length; $("#fab-count").textContent = state.favorites.length;
  $("#favorite-list").innerHTML = state.favorites.length ? state.favorites.map((name, index) => `<div class="favorite-row"><span>${escapeHtml(name)}</span><button class="remove" data-remove="${index}">Quitar</button></div>`).join("") : "<p class='status'>Aún no has elegido ningún postre.</p>";
  localStorage.setItem("isaura-favorites", JSON.stringify(state.favorites)); renderProducts();
}
function openFavorites(open) { $("#favorites-panel").classList.toggle("open", open); $("#favorites-panel").setAttribute("aria-hidden", String(!open)); $("#scrim").hidden = !open; }
async function loadProducts() { try { const response = await api("/api/products"); state.products = response.data || []; localStorage.setItem("isaura-products", JSON.stringify(state.products)); renderSelection(); } catch (error) { $("#catalog-status").textContent = "No pudimos cargar el catálogo. Revisa la configuración de Supabase."; toast(error.message); } }
$("#searchInput").addEventListener("input", renderProducts); $("#btnVerTodos").addEventListener("click", () => { $("#searchInput").value = ""; renderProducts(); }); $("#open-favorites").addEventListener("click", () => openFavorites(true)); $("#close-favorites").addEventListener("click", () => openFavorites(false)); $("#scrim").addEventListener("click", () => openFavorites(false));
$("#products").addEventListener("click", (event) => { const favorite = event.target.closest("[data-favorite]"); if (!favorite) return; const name = favorite.dataset.favorite; state.favorites = state.favorites.includes(name) ? state.favorites.filter((item) => item !== name) : [...state.favorites, name]; renderSelection(); });
$("#favorite-list").addEventListener("click", (event) => { const remove = event.target.closest("[data-remove]"); if (remove) { state.favorites.splice(Number(remove.dataset.remove), 1); renderSelection(); } });
$("#send-favorites-whatsapp").addEventListener("click", () => { if (!state.favorites.length) { toast("Elige al menos un favorito"); return; } const message = `Hola Isaura, me interesan estos productos:\n\n${state.favorites.map((name) => { const product = state.products.find((item) => item.nombre === name); const image = product ? new URL(imageUrl(product), window.location.origin).href : ""; return `• ${name}${product?.categoria ? ` (${product.categoria})` : ""}${image ? `\nImagen: ${image}` : ""}`; }).join("\n\n")}`; window.open(`https://wa.me/${BUSINESS_WHATSAPP}?text=${encodeURIComponent(message)}`, "_blank", "noopener"); });
if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
loadProducts();
