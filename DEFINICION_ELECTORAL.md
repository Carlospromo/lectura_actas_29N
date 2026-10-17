# Definición electoral — versión de trabajo

Actualizado: 17 de octubre de 2026. Este documento recoge decisiones del promotor y separa lo implementado de lo que depende de documentación electoral aún no recibida.

## Proceso y alcance decidido

- **Cámara operativa: Congreso de los Diputados.** La fecha 29 de noviembre de 2026 es provisional y se almacena como dato de la elección. Aún falta la convocatoria y la denominación oficial del proceso; por ello el repositorio sólo contiene una elección local **sintética**.
- **Documento operativo inicial: acta de escrutinio de mesa.** El código de API es `escrutinio`. Las actas de constitución, sesión, escrutinio de Juntas y voto CERA no están habilitadas; requieren una decisión de alcance y modelos específicos.
- **Senado queda deshabilitado para esta elección.** Existe un esquema técnico separado de votos por candidato para no aplicar las reglas de Congreso si en el futuro se incorpora otra elección. Su validación sigue siendo preliminar y no autoriza uso electoral real.
- El apoderado confirma la transcripción de su acta. Una transcripción confirmada no certifica jurídicamente el resultado. **Organización central decide las discrepancias** entre envíos que pretenden representar la misma mesa, elección, cámara y tipo documental, dejando motivo y auditoría.

## Mesa y catálogo

La identidad de mesa es `(provincia, municipio, distrito, sección, denominación)`. En importaciones nacionales, provincia es el código de dos dígitos y municipio el código de cinco dígitos que empieza por el provincial. Distrito y sección se normalizan conservando ceros iniciales; la denominación se convierte a mayúsculas. El local tiene un código externo estable dentro de provincia y municipio. Una mesa no puede cambiar silenciosamente de local entre versiones del catálogo.

El importador de mesas **operativas de la elección** recibe un CSV UTF-8 con las columnas, en este orden:

```text
province_code,province_name,municipality_code,municipality_name,place_code,place_name,district,section,table_label
```

`stage` valida estructura, unicidad de mesa, coherencia de nombres, SHA-256 y procedencia declarada. Para `--scope national` exige presencia de las 52 provincias, Ceuta y Melilla incluidas, y rechaza el municipio `999`: identifica voto exterior y no un local asignable a un apoderado. `activate` se ejecuta en una transacción, conserva la versión anterior y marca una sola versión activa por elección. Un catálogo activo limita las nuevas actas y el denominador del dashboard a sus mesas. La activación no borra mesas ni documentos anteriores. La lista de **2026 con locales** aún no se ha facilitado; el importador no certifica su carácter oficial. Los códigos y nombres territoriales deberán cotejarse con la [relación vigente del INE](https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177031&idp=1254735976614&menu=ultiDatos), y la relación de mesas con la fuente electoral del proceso.

### Fuentes aportadas para avanzar el modelo

El fichero maestro de julio de 2023 tiene 60.366 registros con identidad de mesa única: **60.314 interiores y 52 registros `COD.MUN=999` de voto exterior**, uno por provincia. Aporta 19 comunidades o ciudades autónomas, 52 provincias y 8.131 municipios interiores distintos. `cod.mesa` concatena código de comunidad, provincia, municipio, distrito, sección y mesa y coincide con sus columnas en todas las filas. **No contiene código, nombre ni dirección del local electoral.** La pestaña de candidaturas y las columnas de resultados de 2023 se conservan en el archivo original, pero el importador de referencia no las ingiere ni las vincula a 2026. El SHA-256 del archivo examinado es `922ded1729972fe1d1a772a15298dc90c91bd27c0fa1827e702fdb72b50e3352`.

El promotor comunicó una [tabla provincial de control de 2023](data/reference/2023_province_controls.csv), transcrita con procedencia y límites en [su nota](data/reference/README.md): 8.131 municipios, 10.461 distritos, 36.460 secciones, 60.314 mesas interiores y **22.706 locales**. Las 52 filas suman esos totales. La conciliación con el Excel detallado coincide por provincia en las cuatro primeras medidas; el `999` exterior queda excluido. Los locales sólo tienen recuento provincial comunicado: el maestro no permite verificar cada local ni asociarlo a una mesa. La tabla es una referencia histórica, no el catálogo operativo de 2026.

El archivo censal de 2026 se titula explícitamente **«Censo de consulta»**; el promotor confirmó usarlo como referencia provisional. Contiene 52 filas provinciales que concilian con 35.958.711 residentes en España, 2.769.645 en el extranjero y 38.728.356 en total. Es una referencia provincial, no un censo por mesa ni un catálogo de locales. Su SHA-256 es `9fd6da00a3ae74946e3f3d256ce3074f8e3f44665c87eabcb1d7b33c7c58ee01`.

La migración `003` y `app.reference_import` almacenan estas dos fuentes como **instantáneas de referencia versionadas**, separadas de las mesas operativas y de los resultados. `999` se modela como ámbito `exterior` hijo de provincia, nunca como municipio real. Las denominaciones procedentes de cada archivo quedan en la instantánea; una variante de nombre no cambia silenciosamente el código ni reescribe la denominación canónica. No se han activado mesas 2023 como si fueran mesas 2026.

**Cobertura prevista: parcial y priorizada**, por decisión del promotor. El rango de 13.500–18.000 apoderados es provisional. Si se mantiene un apoderado por local cubierto, representa aproximadamente el 59,5–79,3 % de los 22.706 locales declarados en 2023; no es una meta confirmada para 2026. La priorización, el reparto por provincia y la asignación a locales/mesas se definirán con el catálogo 2026 y la capacidad disponible. Los porcentajes operativos deberán usar denominadores del catálogo activo y mostrar la parte cubierta explícitamente.

## Campos y reglas

| Campo | Congreso operativo local | Senado técnico deshabilitado |
| --- | --- | --- |
| Identidad | Elección, mesa, cámara, tipo, versión y fotografía original | Igual |
| Resultado | Enteros no negativos por **candidatura de la circunscripción** | Enteros no negativos por **candidato de la circunscripción** |
| Blancos, nulos y total | Obligatorios en la revisión local; candidatura + blancos + nulos = total | Obligatorios; blancos + nulos ≤ total y cada candidato ≤ total. **No** se compara la suma de candidatos con el total de votantes. |
| Censo, votantes, interventores, incidencias y otras casillas | Pendiente de confirmar frente al modelo aplicable y de ampliar el formulario | Pendiente de modelo y reglas territoriales |

Las candidaturas y candidatos no se generan desde el OCR: se importarán por circunscripción cuando estén disponibles. Las reglas finales y la ubicación exacta de cada campo requieren actas reales autorizadas y el modelo aprobado para el proceso. Como referencia de categorías documentales se consultó el [anexo 9 del Real Decreto 605/1999, modificado en 2023](https://www.boe.es/buscar/doc.php?id=BOE-A-2023-8225); los [modelos de elecciones generales de 1993](https://www.boe.es/diario_boe/txt.php?id=BOE-A-1993-10935) ilustran la distinción entre votos por candidatura y por candidato, pero **no se asumen como modelo vigente de 2026**.

El importador técnico de candidaturas de Congreso (`app.candidacy_import`, migración `004`) guarda CSV, versión, procedencia y SHA-256 antes de la activación explícita. Para alcance nacional exige al menos una candidatura en cada una de las 52 circunscripciones y comprueba duplicados de código o nombre dentro de cada una. La revisión obtiene la lista activa de la circunscripción de la mesa. No se permite activar otra versión una vez creadas actas de Congreso de esa elección, porque cambiar los identificadores invalidaría las transcripciones previas. **No hay candidaturas de 2026 importadas ni verificadas**; las de 2023 no se reutilizan automáticamente. Los candidatos y particularidades de Senado quedan fuera de este importador.

## Discrepancias

Una segunda revisión con distribución distinta conserva ambos documentos, imágenes y revisiones. La nueva versión queda validada como transcripción, pero fuera del cómputo; la vigente permanece en el dashboard. Organización central compara ambas imágenes y cifras y elige `accept_new` o `keep_incumbent`, con motivo obligatorio. La operación es transaccional y deja un evento de auditoría. Si la versión vigente cambia antes de decidir, la API exige revisar de nuevo. Los envíos iguales se guardan como versiones no vigentes sin abrir una discrepancia.

## Pendientes para cerrar esta definición

1. Convocatoria, fecha definitiva y denominación oficial de la elección.
2. Modelos aprobados de acta de escrutinio de mesa para esta elección y fotografías autorizadas que cubran sus variantes.
3. Listado 2026 de locales y mesas, más cotejo de sus cambios respecto de 2023 y del catálogo INE vigente. Definir criterios y responsables de prioridad para la cobertura parcial; después asignar apoderados a locales y mesas. Los registros `999` necesitarán un proceso diferenciado si se incorporan.
4. Censo definitivo que sustituya al fichero de consulta aportado, manteniendo ambos con procedencia y versión.
5. Relación definitiva de candidaturas por circunscripción y reglas de asignación de apoderados a mesas.
6. Decidir si otros tipos de acta entran en el producto y qué campos adicionales de censo/participación son necesarios.

Hasta entonces, la aplicación sólo ofrece el recorrido local sintético y no debe presentar sus reglas como validación electoral oficial.
