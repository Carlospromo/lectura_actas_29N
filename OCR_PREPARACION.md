# Preparación OCR de actas de mesa — versión provisional

Actualizado: 17 de octubre de 2026. Alcance confirmado por el promotor: **actas de escrutinio de mesa para Congreso**. No se procesan actas CERA provinciales ni actas de Senado.

## Identificación del ejemplo recibido

La imagen facilitada en el chat mide **555 × 742 píxeles**, está en PNG y tiene SHA-256 `7b0ec209347596ed32c3055fc3d523d0be6aa49d803073a03fbeab0424aedf2a`. En su cabecera se lee «Junta Electoral Provincial» y «Acta de escrutinio para la votación de los residentes ausentes en el extranjero». Es una **plantilla CERA de Junta Provincial**, sin cifras escritas, distinta de un acta de escrutinio de mesa. No es una muestra de rendimiento OCR, ni una fuente para calcular resultados. La imagen original permanece fuera del repositorio.

El [anexo 9 de la Orden INT/316/2023](https://www.boe.es/eli/es/o/2023/03/29/int316) enumera por separado A.E.M. (acta de escrutinio de mesa, DIN A4 o A3), A.E.J. CERA (Junta, voto exterior) y A.E.J. (Junta, escrutinio definitivo). Estos modelos históricos sirven para distinguir familias documentales; ninguno acredita el formulario aplicable a la elección prevista de 2026. El ejemplo adjunto queda como **caso negativo de clasificación**, no como plantilla de recortes para las mesas.

## Modelo de mesa de 2023 aportado después

El promotor entregó una imagen en blanco de **acta de escrutinio de mesa A.E.M. de 2023** (PNG, 1871 × 2667 píxeles, SHA-256 `9c673965eb4f8644f34ac652f19dcf4dba0ed40fa225ab7718bd2a5a54d579e3`). Se conserva como [fixture de plantilla](tests/fixtures/aem_2023_blank.png) para que los ensayos geométricos sean reproducibles. No contiene resultados ni datos personales. Su pie indica que la casilla «Isla» sólo aparece en Illes Balears y Canarias; también advierte que los textos «papeletas» y «candidatos» corresponden a otras modalidades. Para **Congreso**, el objetivo son votos por candidatura y votos nulos/en blanco.

La plantilla provisional `aem-2023-blank-reference-v1` delimita la identidad (provincia, isla opcional, municipio o EATIM, distrito, sección y mesa), los bloques de censo/certificaciones, participación e interventores, nulos y blancos, y **40 renglones** con candidatura, votos en letra y votos en número. El contrato OCR añade electores según listas, certificaciones de alta y corrección, total electores, votantes censados e interventores no censados. Conserva el texto de votos «en letra» por separado del entero «en número»; aún no interpreta automáticamente las palabras. Las igualdades impresas `(1+2)` y `(A+B)` producen avisos de revisión si se contradicen; las certificaciones de corrección no se suman a `(1+2)`. Los nombres y firmas de asistentes quedan fuera de las regiones de lectura. El tratamiento territorial de EATIM deberá contrastarse con el catálogo aplicable, sin asumir que sea un municipio distinto.

`python -m app.ocr_layout tests/fixtures/aem_2023_blank.png` devuelve en JSON el cotejo geométrico y las coordenadas de bloques y filas. El cotejo acepta la página original alineada y una reducción a media resolución; rechaza una página girada, totalmente blanca o negra. La imagen CERA aportada antes también dio `geometry_match=false` en una prueba manual, pero esto **no demuestra** sensibilidad ni especificidad con otras actas. **Sólo funciona con una página ya rectificada al formato de referencia**; una fotografía móvil con perspectiva, recortes o una variante A3 necesita detección y registro previos. El cotejo de cuadrícula no lee texto ni acredita el tipo documental por sí solo. Las coordenadas de esta imagen de 2023 no se activarán automáticamente para el formulario de 2026.

## Contrato de extracción preparado

`app.ocr_contract` define tipos documentales `mesa_congreso`, `mesa_senado`, `mesa_unknown_chamber`, `cera_provincial` y `unknown`. El modelo A.E.M. aportado no imprime «Congreso» en el título, de modo que su encabezado/código puede indicar **mesa con cámara aún no acreditada**; una nota al pie que menciona Senado no basta para reclasificarlo como Senado. La clasificación es conservadora y sólo trabaja sobre **texto que proporcionará un OCR futuro**; hoy no ejecuta reconocimiento de texto sobre fotografías. El extractor simulado guarda `unknown` y cifras ausentes. El servidor exige al revisor confirmar explícitamente que la imagen es un acta de mesa de Congreso antes de validar; la confirmación humana no equivale a una clasificación automática verificada.

Cada casilla numérica se representa como `value` (entero positivo), `zero` (cero explícito), `blank` (casilla vista vacía), `absent` (campo no localizado) o `illegible` (campo visible pero no legible). Ninguna de estas categorías se convierte silenciosamente en otra. Una propuesta OCR puede generar incidencias de tipo documental, candidaturas incompletas, dato ilegible o suma distinta; **no se reescriben los números para cuadrar**. La revisión humana y el original archivado siguen siendo obligatorios.

## Flujo de OCR a implementar sobre el modelo aprobado de mesa

1. Conservar imagen original y metadatos de integridad. Obtener consentimiento de captura sólo para la mesa asignada.
2. Identificar tipo documental y variante de página antes de extraer cifras. `unknown` y CERA se desvían a revisión y no deben validarse como acta de mesa.
3. Evaluar rotación, perspectiva, reflejos, desenfoque, resolución, cortes y páginas faltantes. Guardar una versión optimizada separada; no sobrescribir el original.
4. Revisar las regiones de lectura provisionales de 2023 contra el modelo de mesa aprobado, con variantes A4/A3 y posibles anexos. Leer identidad de mesa, cifras generales y votos por candidatura; omitir nombres, DNI y firmas si no son necesarios.
5. Asociar filas OCR con el catálogo activo de candidaturas de la circunscripción. No crear candidaturas a partir de texto OCR ni asumir el orden de 2023.
6. Registrar proveedor, versión de modelo, configuración, texto/respuesta original, regiones y estado de cada campo. Mostrar al revisor cifra propuesta y región de imagen, manteniendo entrada manual.
7. Ejecutar reglas del modelo aprobado y comparar todos los campos críticos. Una suma correcta no valida por sí sola el acta.

## Ensayo y criterios antes de activar OCR real

- Reunir fotografías autorizadas de actas de mesa de Congreso: móvil, iluminación, escritura, copias, provincias, A4/A3, páginas incompletas y casos conflictivos. Guardar la procedencia y separar entrenamiento/ajuste de un conjunto reservado de evaluación.
- Etiquetar de forma independiente identidad, tipo, cada cifra, vacío, cero, ausente e ilegible. Incluir actas CERA y de otros tipos como negativos. No usar esta plantilla en blanco para medir exactitud de cifras.
- Comparar Gemini, Azure Document Intelligence y Google Document AI sobre las mismas imágenes y etiquetas. Medir exactitud por campo, exactitud de acta completa, falsos aceptados, clasificación errónea, tiempo de revisión, coste e incidencias por calidad. Las confianzas declaradas por cada proveedor se calibrarán frente a esas etiquetas.
- Probar cambios de escala, rotación, perspectiva, reflejos, recortes, varias fotos del mismo documento y reintentos. La aceptación se fijará con muestras y umbrales acordados antes de activar resultados reales; todavía no hay una tasa de precisión demostrada.

## Verificación realizada

Las pruebas del contrato rechazan decimales, negativos implícitos, ceros mal etiquetados y valores dentro de casillas vacías; distinguen `zero`, `blank`, `absent` e `illegible`. También comprueban que el encabezado transcrito del ejemplo CERA no se clasifique como acta de mesa y que una suma contradictoria quede marcada sin modificación. La prueba de API comprueba que la validación de Congreso exige confirmación del tipo documental. Las pruebas geométricas comprueban la procedencia por SHA-256, seis campos de identidad, 40 filas, exclusión de la columna de firmas y alineación a dos escalas. Son pruebas de estructura y flujo, **no pruebas de precisión OCR sobre fotografías**.
