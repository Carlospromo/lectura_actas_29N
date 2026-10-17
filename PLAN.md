# Plan de desarrollo: actas 29N

Actualizado: 17 de octubre de 2026. La fecha operativa **prevista** es 29 de noviembre de 2026; `election.event_date` es un dato editable antes de operar.

## 1. Objetivo, alcance y requisitos confirmados

Plataforma privada para apoderados en España: captura móvil de fotografías, extracción propuesta, revisión humana y resultados exclusivos para usuarios autorizados. Cobertura territorial: 50 provincias más Ceuta y Melilla, importada desde un catálogo que se validará con la fuente oficial. API Python. La primera entrega ejecuta un recorrido local con datos sintéticos, sin pretensión de representar resultados electorales. No incluye proyección ni escaños.

## 2. Hipótesis y decisiones pendientes

- 13.500–18.000 apoderados es un rango provisional; mesas, actas e imágenes por persona están pendientes.
- Escenarios iniciales: 18.000, 36.000 y 61.000 imágenes/hora (5, 10 y 16,94/s de media). Probar ráfagas de 3 y 5 veces la media y tamaño configurable (base: 4 MiB). Separar tasa de recepción, OCR y demora de revisión.
- Falta fecha definitiva, dominio, cuentas de proveedores, lista autorizada de teléfonos, catálogo oficial, modelos de acta españoles, candidaturas y reglas definitivas de Congreso/Senado.
- La elección sintética local y dos mesas locales no son catálogo oficial.
- Se elige cola transaccional en PostgreSQL (`processing_jobs`) frente a Redis para reducir servicios y cerrar la brecha entre registrar el documento y encolarlo. Trabajadores separados consultan con `FOR UPDATE SKIP LOCKED`; hay plazo de arrendamiento y reintento. Validar su capacidad antes de producción.

## 3. Inspección de la referencia

`unimauro/actas-2026` (commit inspeccionado `7b6c0f5`) usa Next 16, React 19 y Supabase; licencia MIT, copyright © 2026 unimauro. Se revisaron `components/ActaForm.tsx`, `lib/validation.ts`, `lib/store.ts`, `lib/dashboard.ts`, `lib/ocr.ts`, esquema Supabase y rutas API. Son reutilizables como **inspiración** la captura móvil y separación de campos, pero sus entidades, etiquetas y validación responden al proceso peruano. No se copia código de esa referencia en esta fase. Si se copia después, conservar aviso MIT. `store.ts` limita a 500 y compara duplicados por sumas; el conflicto no se persiste. `dashboard.ts` agrega todas las actas. La extracción se ejecuta dentro de HTTP y `auth.ts` usa contraseña compartida. El prompt OCR equipara vacíos a cero y solicita nombres/DNI innecesarios para este objetivo. El esquema Supabase permite lectura pública e inserción abierta. Estas piezas se sustituyen.

## 4. Arquitectura

FastAPI sirve API y una interfaz móvil ligera. PostgreSQL conserva identidad, permisos, documentos, revisiones, trabajos y resultados. Un servicio de archivos local separado conserva imágenes en un volumen y exige URL firmada HMAC para cada PUT/GET; en producción el adaptador se sustituirá por Cloud Storage. El flujo es: autorización por mesa → documento pendiente y URL temporal → PUT directo → comprobación de objeto/tamaño/formato e integridad → trabajo durable → extracción simulada → revisión explícita → versión vigente validada y consulta agregada. La API nunca depende de ejecutar OCR dentro de HTTP.

La transacción de validación bloquea la mesa/proceso, reemplaza la versión vigente y deja los envíos previos como evidencia. Una clave de idempotencia única por usuario y petición impide duplicar un alta repetida. Una restricción parcial permite una sola versión vigente por mesa, elección, cámara y tipo. La lectura de resultados usa exclusivamente documentos vigentes validados y `SUM` en PostgreSQL, sin límite de 500.

## 5. Modelo y estados

Entidades planeadas: `elections`, `territories` (comunidad, provincia, municipio), `polling_places`, `tables` (provincia/municipio/distrito/sección/denominación), `users` y teléfono separado, `assignments`, `candidacies`, `candidates`, `documents`, `document_images`, `extractions`, `reviews`, `processing_jobs`, `document_votes` y `audit_events`. La primera migración implementa el subconjunto necesario y deja las entidades electorales ampliables. Una candidatura se configura por circunscripción. Congreso tendrá voto por candidatura; Senado por candidato con su propia validación. Nunca se exigirá que la suma de votos a candidatos del Senado sea igual al número de votantes.

Estados: `pending_upload`, `received`, `processing`, `extracted`, `pending_review`, `validated`, `rejected`, `recoverable_error`. Una discrepancia es un atributo auditable entre versiones; no sustituye ni borra un envío. Cero es entero 0; casilla vacía, dato ausente e ilegible son códigos distintos en la extracción. No se corrige ninguna cifra automáticamente.

## 6. Roles, permisos y autenticación

`apoderado`: actas de mesas asignadas; `supervisor`: actas de su ámbito asignado; `organizacion`: lectura de resultados si tiene permiso explícito; `administrador`: gestión y acceso por permisos explícitos. El servidor verifica ámbito y permiso en cada ruta y las imágenes se entregan con URL firmada corta solo tras autorizar. Los tokens de sesión son revocables. El teléfono se normalizará a E.164 y vivirá separado de las actas; la baja desactiva usuario y revoca sesiones.

En desarrollo se usan cuentas y códigos de prueba **visiblemente sintéticos**. `APP_ENV=production` rechazará arranque mientras no estén configurados proveedor de autenticación y secretos requeridos; la autenticación de prueba no podrá activarse allí. Para producción se comparan Identity Platform/Firebase y Verify de Twilio con lista blanca verificada **en nuestra API antes de solicitar SMS**. Firebase Authentication básico tiene un límite documentado de 3.000 SMS/día y 900/minuto; Identity Platform eleva el primero. Las tarifas son por SMS y requieren presupuesto para España. Twilio Verify admite límites por servicio y clave; revisar tarifas y cuotas contratadas. La elección queda pendiente de prueba real y coste. OTP por SMS acredita posesión del número, no implica doble factor.

Fuentes oficiales consultadas (17-10-2026): [límites Firebase](https://firebase.google.com/docs/auth/limits), [precios Identity Platform](https://cloud.google.com/identity-platform/pricing), [límites Twilio Verify](https://www.twilio.com/docs/verify/api/rate-limits-and-timeouts), [límites programables Twilio](https://www.twilio.com/docs/verify/api/programmable-rate-limits).

## 7. Fases y criterios de aceptación

### Fase 1: recorrido local sintético

1. Migración de datos, restricciones, semilla sintética y configuración sin secretos. Aceptación: arranque reproducible y datos persistentes.
2. Sesión de prueba revocable, rol/ámbito, mesa autorizada y dashboard con permiso explícito. Aceptación: accesos cruzados y anónimos denegados.
3. Alta idempotente, URL firmada, verificación de imagen privada y trabajo durable. Aceptación: reinicio no pierde imagen ni trabajo y retry no duplica.
4. Extractor simulado, revisión manual y validación transaccional. Aceptación: no hay autovalidación; igual total con distribución distinta genera discrepancia; rechazadas excluidas.
5. Interfaz móvil y dashboard básico. Aceptación: recorrido completo en navegador móvil.
6. Pruebas automatizadas y reinicio de servicios. Aceptación: comandos y resultados anotados abajo.

### Fase 2: datos y seguridad operativa

Importador validado de catálogos oficiales, candidaturas/candidatos, modelos Congreso/Senado, reglas específicas, historial de auditoría ampliado, importación segura de asignaciones, retención configurable. Aceptación: conciliación contra fuentes oficiales y casos de acta firmados por organización.

### Fase 3: proveedores y carga

Elegir SMS tras evaluar costes/cuotas/controles; implementar lista autorizada, límites de intentos, reenvíos y sesiones. Adaptadores Gemini, Azure Document Intelligence y Google Document AI con conjunto de evaluación reservado. Adaptar almacenamiento a GCS; pruebas de carga y operación en Cloud Run. Aceptación: ensayos de capacidad y recuperación con métricas y costes comprobados.

## 8. Pruebas y evaluación

Pruebas de API: anónimo, rol y ámbito; enteros no negativos, estructuras inválidas, estados; idempotencia y duplicados con igual total; rechazo; reemplazo/retirada de versión; imagen privada, formato y tamaño; trabajos recuperados; paginación y resultados superiores a 500. OCR: conjunto etiquetado estratificado por calidad/formato/provincia/cámara, fotos reservadas para evaluación, precisión por campo y tasa de intervención humana; registrar proveedor/modelo/configuración. Medir además tasa de actas completamente correctas, tiempo por revisión y errores críticos. No entrenar con conjunto de evaluación.

Carga: 18k/36k/61k imágenes/h con 4 MiB base: 72/144/244 GiB por hora (antes de copias y retransmisión). Ensayar picos 3×/5×, tamaño 2–10 MiB y mezcla de clientes; medir p95/p99 de autorización, subida y confirmación, tasa de error, profundidad y edad de cola, capacidad OCR y atraso de revisión. No prometer capacidad sin cuotas de SMS, almacenamiento, OCR y conexiones verificadas.

## 9. Despliegue y operación

Compose local: API, worker, PostgreSQL, servicio privado de archivos, volúmenes. Futuro: Cloud Run API/worker, Cloud SQL PostgreSQL, Cloud Storage privado y cola gestionada o Postgres si la carga lo permite. TLS en borde, secretos en gestor de secretos, IAM mínimo, copias PITR de base de datos y versionado/retención de imágenes. Métricas: HTTP, errores, cola, intentos, edad máxima, tasa de extracción y revisión, anomalías de validación. Ensayar restauración y auditar acceso a imagen. El coste se presupuestará como fórmula: imágenes × tamaño × almacenamiento/transferencia + páginas OCR × tarifa + SMS × tarifa España + DB/CPU; todavía no hay precios ni cuotas contratados. Teléfonos y evidencias tienen retención y borrado configurables tras validación legal.

## 10. Estado actual y siguiente tarea

- Inspección inicial y arquitectura: completadas. Destino sin commits ni archivos al inicio; referencia aislada fuera del directorio de trabajo.
- **Fase 1 completada y verificada en entorno local de CI.** Implementados migración/semilla sintética, API, sesión de prueba revocable, ámbito por mesa, URL firmada, comprobación de imagen y copia sellada de evidencia, cola PostgreSQL con trabajador separado, revisión manual, discrepancias, reemplazo y retirada de versión, dashboard restringido y UI adaptable. `compose.yaml` y README tienen comandos de arranque. La extracción simulada no genera cifras.
- Verificado en este equipo: `py -3.13 -m pytest -q`: 5 pruebas aprobadas (anonimato/ámbito, discrepancia con igual total, rechazo, reintento, retiro, 501 actas, revocación, almacenamiento firmado y persistencia de archivo local). `docker compose config --quiet` pasó. Compilación Python y sintaxis JavaScript pasaron. `APP_ENV=production` rechaza el arranque sin proveedores reales.
- Verificado en GitHub Actions [ejecución 39009920269](https://github.com/Carlospromo/lectura_actas_29N/actions/runs/39009920269): pruebas unitarias y `docker compose up --build -d` correctos; la prueba de integración subió una fotografía por URL firmada al servicio privado, confirmó el documento, esperó al trabajador, validó cifras, consultó el dashboard, reinició todos los servicios y volvió a leer documento, imagen y resultado. Resultado del flujo: **success**. El motor Docker de este equipo sigue inaccesible, de modo que el recorrido con PostgreSQL/Compose no se comprobó aquí.
- Vista previa: el puerto público de la API es 8001 para evitar una aplicación existente del usuario en 8000. La configuración CORS, README y prueba de integración usan `http://localhost:8001`. Se probó el flujo sintético también con SQLite y el servicio de imágenes local en ese puerto, y se abrió el dashboard en el navegador integrado.
- **Proveedores reales no verificados ni conectados**: SMS, OCR, Cloud Storage, catálogo territorial oficial, actas oficiales, candidaturas definitivas y carga. El servicio de archivos y la autenticación de prueba son sólo para desarrollo; `APP_ENV=production` impide arrancarlos.
- Siguiente tarea: importar y conciliar el catálogo territorial/electoral oficial y los modelos de acta de Congreso/Senado; después seleccionar SMS, OCR y almacenamiento de producción con pruebas de cuotas/coste.
