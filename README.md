# Isaura Cerpa · Repostería Artesanal

<p align="center">
	<img src="public/uploads/Gemini_Generated_Image_i3dgegi3dgegi3dg.png" alt="Isaura Cerpa" width="180">
</p>

<p align="center"><strong>Una vitrina digital elegante para postres hechos con intención.</strong></p>

<p align="center">
	<a href="https://github.com/juandiego-uix/PASTELERIA_ISAURA/actions"><img src="https://img.shields.io/github/actions/workflow/status/juandiego-uix/PASTELERIA_ISAURA/ci.yml?label=CI&style=flat-square" alt="CI"></a>
	<img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
	<img src="https://img.shields.io/badge/Flask-3.1-000000?style=flat-square&logo=flask&logoColor=white" alt="Flask">
	<img src="https://img.shields.io/badge/Supabase-Postgres-3ECF8E?style=flat-square&logo=supabase&logoColor=white" alt="Supabase">
	<img src="https://img.shields.io/badge/Vercel-ready-000000?style=flat-square&logo=vercel&logoColor=white" alt="Vercel">
</p>

Aplicación web de producción para **Isaura Cerpa**, una pastelería artesanal. El proyecto reemplaza la implementación PHP original por una arquitectura serverless moderna: Flask como API, Supabase como plataforma de datos y almacenamiento, y un frontend estático responsive sin dependencias de framework.

## Experiencia

- Catálogo dinámico con búsqueda por nombre y categoría.
- Selección de favoritos persistida en el navegador.
- Carrito persistente, checkout con ítems y precios, y PWA instalable.
- Métricas financieras con Chart.js, estados de pago e inventario de insumos.
- Recibos PDF y webhook preparado para Twilio, Meta Cloud API o un gateway propio.
- Roles operativos, producción diaria, seguimiento público, reportes financieros y trazabilidad de inventario.
- Estados de carga, errores visibles y validación en cliente y servidor.
- Diseño mobile-first con HTML semántico, CSS Grid/Flexbox y tipografía editorial.

## Funciones ERP

- Supabase Auth con roles `administrador`, `produccion`, `ventas` y `solo_lectura`.
- Estados de pedido: `Pendiente`, `Confirmado`, `En producción`, `Listo`, `Entregado` y `Cancelado`.
- Historial de estados, notas internas, reprogramación, checklist y token de seguimiento público.
- Inventario con recetas, costos unitarios, vencimientos y movimientos de entrada, salida, ajuste y devolución.
- Descuento y reposición automática de insumos mediante triggers PostgreSQL.
- Producción diaria, etiquetas imprimibles, gastos, cuentas por cobrar, utilidad neta y exportación CSV.
- Variantes, adicionales, productos destacados, disponibilidad y descuentos.
- Mensajería por Meta WhatsApp Cloud API, Twilio o webhook firmado.
- Sentry para errores del backend, PWA instalable y diseño responsive para teléfonos y tablets.

## API ERP

| Método | Ruta | Acceso | Propósito |
| --- | --- | --- | --- |
| `GET` | `/api/track/:token` | Público | Seguimiento limitado de un pedido |
| `GET/PATCH` | `/api/admin/orders/:id/lifecycle` | Por rol | Ciclo operativo del pedido |
| `GET` | `/api/admin/orders/:id/history` | Por rol | Historial de cambios |
| `GET` | `/api/admin/production/today` | Producción | Cola de preparación diaria |
| `POST` | `/api/admin/inventory/movements` | Admin/Producción | Ajustar inventario |
| `GET/POST` | `/api/admin/expenses` | Admin | Gastos operativos |
| `GET` | `/api/admin/reports/summary` | Admin/Lectura | Resumen financiero |
| `GET` | `/api/admin/reports/orders.csv` | Admin/Ventas | Exportar pedidos |
| `GET` | `/api/admin/orders/:id/receipt.pdf` | Admin | Descargar recibo PDF |
| `GET` | `/api/catalog/options` | Público | Variantes y adicionales |

## Stack tecnológico

### Inventario y mensajería

Ejecuta las ampliaciones de [`supabase/schema.sql`](supabase/schema.sql) para crear `insumos`, `producto_insumos`, precios e ítems de pedido. Al registrar un pedido con `items`, un trigger de Postgres descuenta las cantidades de la receta y rechaza el pedido si no existe stock suficiente. Configura `MESSAGING_WEBHOOK_URL` para que el endpoint de proximidad entregue los pedidos próximos a tu integración de Twilio, Meta Cloud API o automatización interna.

Para activar Supabase Auth establece `SUPABASE_AUTH_ENABLED=true`, crea usuarios en Supabase Auth y registra su rol en `public.perfiles` (`administrador`, `produccion`, `ventas` o `solo_lectura`). El modo manual hasheado queda disponible únicamente como transición local cuando la bandera está desactivada.

### Observabilidad y mensajería

Configura `SENTRY_DSN` en Vercel para recibir errores y trazas del backend. Para WhatsApp usa `MESSAGING_PROVIDER=meta` con `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID` y una plantilla aprobada; para Twilio usa `MESSAGING_PROVIDER=twilio` con sus credenciales. El modo `webhook` requiere `MESSAGING_WEBHOOK_URL` y `MESSAGING_WEBHOOK_SECRET`. Todas las actualizaciones de pedidos quedan registradas en `pedido_mensajes`.

| Capa | Tecnología |
| --- | --- |
| Backend | Python 3.11+, Flask 3.1 |
| Datos | Supabase Postgres + Storage |
| Frontend | HTML5, CSS moderno, JavaScript ES Modules |
| Despliegue | Vercel Serverless Functions + Static Files |
| Operación | Variables de entorno, RLS, tokens HMAC con expiración |

## Arquitectura

```text
ISAURA/
├── api/
│   ├── index.py             # App Flask, endpoints y validaciones
│   ├── erp.py               # Roles, producción, finanzas y tracking
│   ├── notifications.py     # Meta, Twilio y webhooks firmados
│   ├── __init__.py
│   └── requirements.txt     # Dependencias fijadas
├── public/
│   ├── index.html           # Tienda pública
│   ├── app.js               # Catálogo, favoritos y pedidos
│   ├── track.html / track.js # Seguimiento público de pedidos
│   ├── admin.html           # Panel administrativo
│   ├── admin.js             # Operaciones protegidas del panel
│   ├── manifest.json         # Instalación PWA
│   ├── sw.js                 # Caché offline del app shell
│   ├── styles.css
│   ├── admin.css
│   └── uploads/             # Activos históricos de la marca
├── supabase/
│   └── schema.sql           # Tablas, índices, RLS y bucket
├── .env.example             # Contrato de configuración
└── vercel.json              # Enrutamiento serverless + estático
```

Flujo principal:

```mermaid
flowchart LR
		A[Cliente] --> B[Frontend estático]
		B --> C[API Flask /api]
		C --> D[(Supabase Postgres)]
		C --> E[(Supabase Storage)]
		B --> F[WhatsApp]
		G[Panel admin] --> C
```

## Instalación local

### 1. Requisitos

- Python 3.11 o superior.
- Una cuenta de Supabase.
- Node.js no es necesario para ejecutar el frontend.

### 2. Base de datos

1. Crea un proyecto en Supabase.
2. Ejecuta [`supabase/schema.sql`](supabase/schema.sql) en el SQL Editor.
3. Verifica que exista el bucket público `productos`.

### 3. Variables de entorno

```bash
cp .env.example .env
```

Completa `.env`:

```dotenv
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_ANON_KEY=clave-publica-de-supabase
SUPABASE_KEY=clave-service-role-solo-servidor
SUPABASE_AUTH_ENABLED=true
ADMIN_PASSWORD_HASH=scrypt:hash-generado-con-werkzeug
ADMIN_SESSION_SECRET=secreto-aleatorio-de-al-menos-32-bytes
ADMIN_SESSION_TTL=28800
RATELIMIT_STORAGE_URI=redis://default:password@tu-redis.example.com:6379/0
SENTRY_DSN=https://clave@o0.ingest.sentry.io/proyecto
SENTRY_TRACES_SAMPLE_RATE=0.05
MESSAGING_PROVIDER=meta
META_ACCESS_TOKEN=token-privado-de-meta
META_PHONE_NUMBER_ID=id-del-numero-de-whatsapp
META_TEMPLATE_NAME=pedido_actualizacion
MESSAGING_WEBHOOK_SECRET=secreto-aleatorio-para-firmar-webhooks
```

Genera el hash de la contraseña administrativa con el mismo entorno virtual:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('tu-contraseña'))"
```

En producción, `RATELIMIT_STORAGE_URI` debe apuntar a Redis/Upstash compartido; `memory://` solo sirve para desarrollo local.

`SUPABASE_KEY`, `META_ACCESS_TOKEN`, `MESSAGING_WEBHOOK_SECRET` y `ADMIN_SESSION_SECRET` nunca deben enviarse al navegador ni subirse al repositorio.

Con `SUPABASE_AUTH_ENABLED=true`, crea los usuarios en **Supabase → Authentication → Users** y asigna su rol en `public.perfiles`. La contraseña de Supabase Auth no es la `SUPABASE_ANON_KEY`.

### 4. Ejecutar Flask

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r api/requirements.txt
flask --app api.index run --debug
```

En desarrollo, sirve el frontend en otra terminal porque Flask atiende únicamente la API:

```bash
python3 -m http.server 8000 --directory public
```

Abre:

- Tienda: `http://127.0.0.1:8000/`
- Administración: `http://127.0.0.1:8000/admin.html`
- Salud de API: `http://127.0.0.1:5000/api/health`

## API principal

| Método | Ruta | Acceso | Propósito |
| --- | --- | --- | --- |
| `GET` | `/api/health` | Público | Estado del servicio |
| `GET` | `/api/products` | Público | Catálogo publicado |
| `GET` | `/api/categories` | Público | Categorías disponibles |
| `POST` | `/api/orders` | Público | Registrar pedido web |
| `POST` | `/api/auth/login` | Público | Crear sesión administrativa |
| `GET` | `/api/admin/dashboard` | Admin | Métricas y datos de gestión |
| `POST/PATCH/DELETE` | `/api/admin/products` | Admin | Gestionar productos |
| `POST/PATCH/DELETE` | `/api/admin/orders` | Admin | Gestionar pedidos |

Las respuestas de error mantienen el formato `{ "error": "mensaje" }` y usan códigos HTTP apropiados.

## Despliegue en Vercel

1. Importa el repositorio `juandiego-uix/PASTELERIA_ISAURA` en Vercel.
2. Mantén la raíz del proyecto como **Root Directory**.
3. Añade todas las variables de `.env` en **Project Settings → Environment Variables**.
4. Despliega. [`vercel.json`](vercel.json) dirige `/api/*` a Flask y sirve el frontend desde `public/`.

La clave service role solo se utiliza dentro de la función Python. El navegador recibe únicamente datos públicos y URLs de imágenes.

### Configuración de Sentry y WhatsApp

`SENTRY_DSN` se obtiene en el proyecto de Sentry, en **Settings → Client Keys (DSN)**. Selecciona la plataforma **Python** o **Flask**.

Para Meta WhatsApp Cloud API necesitas una aplicación de Meta Business, un token de acceso, el `Phone Number ID` y una plantilla aprobada. Como alternativa, configura `MESSAGING_PROVIDER=twilio` con las variables de Twilio. Si no configuras ningún proveedor, el enlace manual de WhatsApp de la tienda sigue funcionando.

### Migrar imágenes existentes

Para cargar las imágenes históricas de `public/uploads/` al bucket `productos` y crear sus registros iniciales:

```bash
python script_migracion.py
```

El script usa `SUPABASE_URL` y `SUPABASE_KEY` desde `.env`, y puede ejecutarse de nuevo sin duplicar productos por nombre.

## Seguridad y operación

- Validación de tipos, longitudes, fechas, estados, pagos y archivos en el backend.
- Consultas privadas realizadas con la clave server-side de Supabase.
- RLS habilitado en las tablas y políticas públicas limitadas al catálogo.
- Sesiones administrativas firmadas con HMAC y caducidad configurable.
- Límite de 5 MB para cargas de imágenes y tipos MIME permitidos.
- Secretos excluidos mediante `.gitignore`.

## Licencia

Proyecto privado de Isaura Cerpa. El código y los activos visuales no deben redistribuirse sin autorización.
