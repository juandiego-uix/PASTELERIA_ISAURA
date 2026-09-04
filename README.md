# Isaura Cerpa

Aplicación web de repostería artesanal reconstruida con Flask, Supabase y un frontend estático responsive.

## Desarrollo local

1. Crea un proyecto en Supabase y ejecuta [`supabase/schema.sql`](supabase/schema.sql).
2. Crea el bucket público `productos` si la migración no lo creó.
3. Copia `.env.example` a `.env` y completa las variables. La clave `SUPABASE_SERVICE_ROLE_KEY` solo debe existir en el servidor.
4. Instala dependencias: `python3 -m pip install -r api/requirements.txt`.
5. Ejecuta Flask: `flask --app api.index run --debug`.

La tienda está en `/` y el panel protegido en `/admin.html`. En Vercel, configura las mismas variables como Environment Variables y despliega desde la raíz.

## Seguridad y operación

- Las consultas privadas pasan por el backend con la service role key; nunca se expone al navegador.
- Las entradas se validan en servidor y las respuestas usan códigos HTTP explícitos.
- Cambia `ADMIN_PASSWORD` y genera `ADMIN_SESSION_SECRET` antes de producción.
- El frontend conserva imágenes históricas en `public/uploads`; los nuevos productos usan el bucket de Supabase.
