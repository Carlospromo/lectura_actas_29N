# Actas 29N — primera fase local

**Entorno de desarrollo con datos sintéticos.** La elección, dos mesas, dos candidaturas y cuatro usuarios de prueba no corresponden a datos ni resultados reales. La fecha prevista se guarda en `elections.event_date`.

## Requisitos y arranque

Docker Desktop/Engine con Compose. Desde la raíz del repositorio:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

Abrir <http://localhost:8000>. MinIO local usa el puerto 9000 para las subidas firmadas. El dashboard sólo se muestra a usuarios con permiso. Para parar sin borrar datos: `docker compose down`. Para reanudar: `docker compose up -d`. Los volúmenes `pgdata` y `objects` mantienen datos e imágenes. **No usar `down -v` si se desean conservar.**

## Recorrido

1. Iniciar como **Apoderado A**, código `TEST-ONLY-2026`. Es autenticación de prueba exclusiva de `APP_ENV=development`.
2. Seleccionar mesa A y una foto JPEG/PNG. La API crea documento y URL temporal; el navegador envía la foto a MinIO directamente; la API comprueba el objeto y encola.
3. Esperar unos segundos y pulsar **Actualizar**. Abrir el envío, comprobar la fotografía e introducir las cifras manualmente. El extractor simulado propone valores ausentes y nunca inventa votos.
4. Validar. Cerrar sesión y entrar como **Organización** para consultar resultados validados.
5. Crear otra acta de la misma mesa con distribución diferente e igual total. Se guarda como nueva versión y se indica discrepancia. Un envío rechazado conserva la evidencia y no suma votos.
6. Reiniciar `docker compose restart` y comprobar que documentos e imágenes siguen accesibles.

Las cuentas de prueba: 1 Apoderado A (mesa 1), 2 Apoderado B (mesa 2), 3 Organización (resultados), 4 Supervisor (ambas mesas y resultados). Los teléfonos y el SMS no están conectados. No se incluye ninguna cuenta de producción.

## Pruebas

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 -m pytest -q
docker compose config
```

La suite usa SQLite temporal y almacenamiento simulado para probar las reglas de API sin proveedores. No sustituye la prueba de integración PostgreSQL/MinIO. Para revisar datos reales de desarrollo:

```powershell
docker compose exec db psql -U actas -d actas -c "select status,count(*) from documents group by status;"
docker compose logs worker
```

## Diseño y límites actuales

- API FastAPI, migración SQL inicial, PostgreSQL, MinIO privado y trabajador separado con cola durable en PostgreSQL. No hay OCR dentro de una petición HTTP.
- Estados y envíos persisten. Una restricción parcial impide dos versiones vigentes por mesa/proceso. Los resultados se calculan sólo con versiones validadas vigentes.
- La extracción local es simulada; los valores se introducen manualmente. Congreso usa candidaturas sintéticas. Senado, catálogo oficial, importador, autenticación SMS, OCR real, despliegue y métricas de producción son fases posteriores descritas en [PLAN.md](PLAN.md).
- `APP_ENV=production` impide el arranque hasta implementar y configurar autenticación y almacenamiento de producción. No reutilizar claves locales fuera del equipo de desarrollo.
- El catálogo de ejemplo contiene únicamente dos mesas sintéticas. No debe usarse para estimar cobertura española.
