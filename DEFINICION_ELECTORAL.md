# Definición electoral — versión de trabajo

Actualizado: 17 de octubre de 2026. Este documento recoge decisiones del promotor y separa lo implementado de lo que depende de documentación electoral aún no recibida.

## Proceso y alcance decidido

- **Cámara operativa: Congreso de los Diputados.** La fecha 29 de noviembre de 2026 es provisional y se almacena como dato de la elección. Aún falta la convocatoria y la denominación oficial del proceso; por ello el repositorio sólo contiene una elección local **sintética**.
- **Documento operativo inicial: acta de escrutinio de mesa.** El código de API es `escrutinio`. Las actas de constitución, sesión, escrutinio de Juntas y voto CERA no están habilitadas; requieren una decisión de alcance y modelos específicos.
- **Senado queda deshabilitado para esta elección.** Existe un esquema técnico separado de votos por candidato para no aplicar las reglas de Congreso si en el futuro se incorpora otra elección. Su validación sigue siendo preliminar y no autoriza uso electoral real.
- El apoderado confirma la transcripción de su acta. Una transcripción confirmada no certifica jurídicamente el resultado. **Organización central decide las discrepancias** entre envíos que pretenden representar la misma mesa, elección, cámara y tipo documental, dejando motivo y auditoría.

## Mesa y catálogo

La identidad de mesa es `(provincia, municipio, distrito, sección, denominación)`. En importaciones nacionales, provincia es el código de dos dígitos y municipio el código de cinco dígitos que empieza por el provincial. Distrito y sección se normalizan conservando ceros iniciales; la denominación se convierte a mayúsculas. El local tiene un código externo estable dentro de provincia y municipio. Una mesa no puede cambiar silenciosamente de local entre versiones del catálogo.

El importador recibe un CSV UTF-8 con las columnas, en este orden:

```text
province_code,province_name,municipality_code,municipality_name,place_code,place_name,district,section,table_label
```

`stage` valida estructura, unicidad de mesa, coherencia de nombres, SHA-256 y procedencia declarada. Para `--scope national` exige presencia de las 52 provincias, Ceuta y Melilla incluidas. `activate` se ejecuta en una transacción, conserva la versión anterior y marca una sola versión activa por elección. Un catálogo activo limita las nuevas actas y el denominador del dashboard a sus mesas. La activación no borra mesas ni documentos anteriores. La lista de locales y mesas **aún no se ha facilitado**; el importador no certifica su carácter oficial. Los códigos y nombres territoriales deberán cotejarse con la [relación vigente del INE](https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177031&idp=1254735976614&menu=ultiDatos), y la relación de mesas con la fuente electoral aportada para este proceso.

## Campos y reglas

| Campo | Congreso operativo local | Senado técnico deshabilitado |
| --- | --- | --- |
| Identidad | Elección, mesa, cámara, tipo, versión y fotografía original | Igual |
| Resultado | Enteros no negativos por **candidatura de la circunscripción** | Enteros no negativos por **candidato de la circunscripción** |
| Blancos, nulos y total | Obligatorios en la revisión local; candidatura + blancos + nulos = total | Obligatorios; blancos + nulos ≤ total y cada candidato ≤ total. **No** se compara la suma de candidatos con el total de votantes. |
| Censo, votantes, interventores, incidencias y otras casillas | Pendiente de confirmar frente al modelo aplicable y de ampliar el formulario | Pendiente de modelo y reglas territoriales |

Las candidaturas y candidatos no se generan desde el OCR: se importarán por circunscripción cuando estén disponibles. Las reglas finales y la ubicación exacta de cada campo requieren actas reales autorizadas y el modelo aprobado para el proceso. Como referencia de categorías documentales se consultó el [anexo 9 del Real Decreto 605/1999, modificado en 2023](https://www.boe.es/buscar/doc.php?id=BOE-A-2023-8225); los [modelos de elecciones generales de 1993](https://www.boe.es/diario_boe/txt.php?id=BOE-A-1993-10935) ilustran la distinción entre votos por candidatura y por candidato, pero **no se asumen como modelo vigente de 2026**.

## Discrepancias

Una segunda revisión con distribución distinta conserva ambos documentos, imágenes y revisiones. La nueva versión queda validada como transcripción, pero fuera del cómputo; la vigente permanece en el dashboard. Organización central compara ambas imágenes y cifras y elige `accept_new` o `keep_incumbent`, con motivo obligatorio. La operación es transaccional y deja un evento de auditoría. Si la versión vigente cambia antes de decidir, la API exige revisar de nuevo. Los envíos iguales se guardan como versiones no vigentes sin abrir una discrepancia.

## Pendientes para cerrar esta definición

1. Convocatoria, fecha definitiva y denominación oficial de la elección.
2. Modelos aprobados de acta de escrutinio de mesa para esta elección y fotografías autorizadas que cubran sus variantes.
3. Fuente y formato del listado completo de locales y mesas, más cotejo del catálogo INE vigente.
4. Relación de candidaturas por circunscripción y reglas de asignación de apoderados a mesas.
5. Decidir si otros tipos de acta entran en el producto y qué campos adicionales de censo/participación son necesarios.

Hasta entonces, la aplicación sólo ofrece el recorrido local sintético y no debe presentar sus reglas como validación electoral oficial.
