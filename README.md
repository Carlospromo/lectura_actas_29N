# Actas 29N — primera fase local

**Entorno de desarrollo con datos sintéticos.** La elección, dos mesas, dos candidaturas y cuatro usuarios de prueba no corresponden a datos ni resultados reales. La fecha prevista se guarda en `elections.event_date`.

## Requisitos y arranque

Docker Desktop/Engine con Compose. Desde la raíz del repositorio:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

Abrir <http://localhost:8001>. El servicio de almacenamiento privado local usa el puerto 9000 para las subidas firmadas. El dashboard sólo se muestra a usuarios con permiso. Para parar sin borrar datos: `docker compose down`. Para reanudar: `docker compose up -d`. Los volúmenes `pgdata` y `objects` mantienen datos e imágenes. **No usar `down -v` si se desean conservar.**

## Recorrido

1. Iniciar como **Apoderado A**, código `TEST-ONLY-2026`. Es autenticación de prueba exclusiva de `APP_ENV=development`.
2. Seleccionar mesa A y una foto JPEG/PNG. La API crea documento y URL temporal; el navegador envía la foto directamente al servicio de almacenamiento; la API comprueba el objeto y encola.
3. Esperar unos segundos y pulsar **Actualizar**. Abrir el envío, comprobar que es un acta de escrutinio de **mesa de Congreso**, marcar la confirmación e introducir las cifras manualmente. El extractor simulado propone valores ausentes y nunca inventa votos.
4. Validar. Cerrar sesión y entrar como **Organización** para consultar resultados validados.
5. Crear otra acta de la misma mesa con distribución diferente e igual total. Se guarda como nueva versión y se indica discrepancia. **Organización** ve ambas imágenes y cifras, decide qué versión queda vigente y registra un motivo. Hasta esa decisión, el dashboard conserva la versión previa. Un envío rechazado conserva la evidencia y no suma votos.
6. Reiniciar `docker compose restart` y comprobar que documentos e imágenes siguen accesibles.

Las cuentas de prueba: 1 Apoderado A (mesa 1), 2 Apoderado B (mesa 2), 3 Organización (resultados), 4 Supervisor (ambas mesas y resultados). Los teléfonos y el SMS no están conectados. No se incluye ninguna cuenta de producción.

## Definición electoral y catálogo

La elección prevista cubre **solo Congreso**, con fecha todavía provisional. El único documento habilitado en el recorrido local es el acta de escrutinio de mesa. La [definición electoral](DEFINICION_ELECTORAL.md) describe campos, reglas, procedencia y decisiones pendientes. Senado tiene tablas y validación diferenciadas, pero está deshabilitado para esta elección.

El importador recibe un CSV UTF-8 con la cabecera exacta indicada en la definición electoral. No hay catálogo nacional precargado ni descarga automática de mesas. El comando `python -m app.election create --name "NOMBRE DEL PROCESO" --event-date AAAA-MM-DD` registra explícitamente una elección con fecha provisional, solo Congreso y acta de escrutinio de mesa; `update-date ID --event-date AAAA-MM-DD --date-confirmed` confirma una fecha después. La elección `1` es **solo sintética**. Para ensayar una importación sintética en desarrollo:

```powershell
py -3.13 -m app.catalog stage .\ruta\catalogo_sintetico.csv --election-id 1 --version ensayo-1 --source-name "Archivo sintético de prueba" --scope synthetic
py -3.13 -m app.catalog list
py -3.13 -m app.catalog activate ID_DEVUELTO_POR_STAGE
```

En Compose, ejecute los mismos comandos con `docker compose exec api python -m app.catalog ...` y coloque primero el CSV en un volumen o cópielo al contenedor. La activación es atómica; no borra versiones ni documentos. Para un catálogo nacional se usa `--scope national`, una elección no sintética y la procedencia declarada con `--source-name` y `--source-url`; exige las 52 provincias. El archivo debe conciliarse manualmente con las fuentes del proceso antes de activarlo. Si el mismo identificador de mesa cambia de local, la activación se detiene para revisión.

### Archivos de referencia aportados

Los Excel de 2023 y 2026 se importan **separados de las mesas operativas**. El primero aporta la jerarquía territorial y las identidades históricas de mesa; carece de locales. Los 52 registros con municipio `999` son voto exterior. El segundo dice «Censo de consulta» y se guarda como referencia provincial provisional, no como censo definitivo. No se importan resultados ni candidaturas de 2023. En este equipo, con la base configurada:

```powershell
py -3.13 -m app.reference_import history 'C:\Users\cpoza\Downloads\G2023julio_mesas_OK.xlsx' --version 2023-jul-provided
py -3.13 -m app.reference_import census 'C:\Users\cpoza\Downloads\Elecgral_2026_cc_tab3 (2).xlsx' --version 2026-consulta-provided
py -3.13 -m app.reference_import list
```

Cada importación verifica su estructura y cifras, registra SHA-256 y es idempotente para el mismo archivo. La verificación se hizo en una base SQLite aislada; los Excel originales permanecen en `Downloads` y no se incluyen en el repositorio. Para usar PostgreSQL, configure `DATABASE_URL` y haga accesibles los archivos al proceso importador. La documentación detallada de procedencia y límites está en [DEFINICION_ELECTORAL.md](DEFINICION_ELECTORAL.md).

El [CSV de controles provinciales de 2023](data/reference/2023_province_controls.csv) transcribe las cifras comunicadas de municipios, distritos, secciones, mesas y locales. Para conciliar las cuatro primeras con el maestro histórico:

```powershell
py -3.13 -m app.reference_controls 'C:\Users\cpoza\Downloads\G2023julio_mesas_OK.xlsx'
```

La salida JSON enumera cualquier discrepancia provincial. Los 22.706 locales sólo constan como recuento provincial y no se pueden cotejar por local con ese Excel. La decisión de cobertura es **parcial priorizada**; faltan criterios de prioridad y el listado 2026 de locales/mesas. Estos controles de 2023 no alimentan el dashboard operativo.

### Candidaturas de Congreso por circunscripción

La migración `004` añade un importador versionado. Recibe CSV UTF-8 con cabecera exacta `constituency_code,candidacy_code,candidacy_name`. Para un proceso nacional exige las 52 circunscripciones; los códigos de candidatura deben ser únicos dentro de cada provincia. `stage` conserva procedencia y SHA-256, pero **no activa** el archivo. En desarrollo puede ensayarse con un proceso sintético y `--scope synthetic`:

```powershell
py -3.13 -m app.candidacy_import stage .\ruta\candidaturas_sinteticas.csv --election-id ID --version ensayo-1 --source-name "Archivo sintético de prueba" --scope synthetic
py -3.13 -m app.candidacy_import list
py -3.13 -m app.candidacy_import activate ID_DEVUELTO_POR_STAGE
```

Para una elección no sintética se usa `--scope national`, tras cotejar la fuente y la versión aplicable. La activación exige que aún no existan actas de Congreso de esa elección; cambiar candidaturas con actas creadas requiere un procedimiento de reconciliación todavía pendiente. La API `GET /api/candidacies?table_id=...&election_id=...` devuelve las candidaturas activas de la mesa autorizada. No se han importado ni activado candidaturas reales de 2026; las de 2023 tampoco se trasladan automáticamente.

## Pruebas

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 -m pytest -q
docker compose config
```

La suite usa SQLite temporal para probar las reglas de API y prueba el servicio de almacenamiento en disco. La integración PostgreSQL y almacenamiento tras reinicio se ejecuta en GitHub Actions. Para revisar datos reales de desarrollo:

La [ejecución de integración 39009920269](https://github.com/Carlospromo/lectura_actas_29N/actions/runs/39009920269) pasó subida, extracción simulada, validación, dashboard y lectura de imagen tras reiniciar todos los servicios.

```powershell
docker compose exec db psql -U actas -d actas -c "select status,count(*) from documents group by status;"
docker compose logs worker
```

## Diseño y límites actuales

- API FastAPI, migración SQL inicial, PostgreSQL, servicio de archivos privado local y trabajador separado con cola durable en PostgreSQL. No hay OCR dentro de una petición HTTP. El almacenamiento local usa firmas HMAC; se sustituirá por Cloud Storage para producción.
- Estados y envíos persisten. Una restricción parcial impide dos versiones vigentes por mesa/proceso. Los resultados se calculan sólo con versiones validadas vigentes.
- La extracción local es simulada; los valores se introducen manualmente. Congreso usa candidaturas sintéticas. El importador versionado y el esquema técnico de Senado están disponibles; faltan catálogo y modelos aplicables, autenticación SMS, OCR real, despliegue y métricas de producción, descritos en [PLAN.md](PLAN.md).
- `APP_ENV=production` impide el arranque hasta implementar y configurar autenticación y almacenamiento de producción. No reutilizar claves locales fuera del equipo de desarrollo.
- El catálogo de ejemplo contiene únicamente dos mesas sintéticas. No debe usarse para estimar cobertura española.
- La [preparación OCR](OCR_PREPARACION.md) documenta el contrato de campos y las pruebas estructurales. El ejemplo de acta CERA recibido se usa sólo para evitar confundirlo con un acta de mesa; no hay OCR real ni medición de precisión sobre fotografías.
