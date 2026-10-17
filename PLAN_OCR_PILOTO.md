# Piloto de lectura de actas de mesa

Actualizado: 17 de octubre de 2026. Alcance: Congreso, acta de escrutinio de mesa. La plantilla A.E.M. de 2023 es **referencia provisional**; no autoriza reconocimiento ni cómputo automático de actas de 2026.

## Entrega A — geometría de fotografías (prototipo sintético verificado)

1. Detectar el contorno de una hoja completa sobre fondo contrastado y estimar cuatro esquinas. Aceptación: rechazar fondo sin hoja, hoja recortada o cuadrilátero ambiguo.
2. Rectificar perspectiva y probar las cuatro orientaciones. Aceptación: el mapa de 2023 recupera su cuadrícula y los 40 renglones en fotos sintéticas giradas y con perspectiva.
3. Producir una imagen derivada en memoria, conservando siempre el original. Aceptación: SHA-256 de los bytes originales invariable y metadatos de rectificación devueltos. La persistencia privada del derivado y de los motivos de rechazo queda para D.
4. Medir errores de registro con esquinas conocidas de las transformaciones sintéticas. Aceptación piloto: error medio de esquinas ≤ 2 % del lado corto y `geometry_match=true` en los casos declarados soportados. Estos umbrales no son una promesa para fotos reales.

## Entrega B — muestras y etiquetas

1. Reunir fotografías autorizadas de actas de mesa **rellenadas**, con variación de móviles, luz, inclinación, escritura y provincias; excluir CERA y otros formularios salvo como negativos de clasificación. No introducir nombres, DNI o firmas en etiquetas OCR.
2. Definir un manifiesto por imagen: procedencia autorizada, versión de formulario, identidad de mesa, campos numéricos, casilla vacía/cero/ilegible, 40 filas posibles y calidad observada. Separar un conjunto de evaluación reservado antes de ajustar el algoritmo.
3. Revisar etiquetas por dos personas en los campos críticos o resolver desacuerdos con evidencia. Aceptación: cada cifra evaluada tiene una etiqueta trazable y una imagen original accesible sólo a autorizados.

## Entrega C — lectura comparada

1. Implementar adaptadores de proveedores tras configurar cuentas y costes. Enviar únicamente regiones necesarias, asociar filas con candidaturas activas y conservar respuesta original, versión y configuración.
2. Medir por separado detección de tipo, rectificación, lectura por campo, acta completamente correcta, falsos aceptados, coste y tiempo de revisión. No sustituir ausentes por cero ni cuadrar sumas automáticamente.
3. Elegir proveedor y umbrales con el conjunto reservado. Aceptación: tasas y coste observados, errores críticos revisados y circuito manual completo para casos no legibles.

## Entrega D — integración controlada

1. Incorporar imagen rectificada como derivado privado, separado del original; ejecución en trabajador durable y recuperable, sin OCR en HTTP.
2. Mostrar propuestas y recortes al revisor. La validación humana, permisos y resolución central de discrepancias siguen vigentes.
3. Ensayar carga y recuperación antes de activar una elección real. No activar automáticamente el mapa de 2023 para 2026; comparar el modelo aprobado y versionar sus cambios.

## Dependencias y estado

- A se ensayó con la plantilla en blanco y deformaciones sintéticas: perspectiva, giros de 90° y 180°, fondo sin hoja y hoja recortada. Las pruebas locales pasan y el error medio de esquinas está por debajo del 2 % del lado corto en el caso sintético declarado. [CI 39031985243](https://github.com/Carlospromo/lectura_actas_29N/actions/runs/39031985243) pasó 25 pruebas y el recorrido Compose con reinicio para el commit `e163861`. El prototipo exige hoja completa sobre fondo contrastado y coteja la cuadrícula de 2023; aún no está probado con fotografías de móvil, variantes A3, reflejos o desenfoque. **No mide precisión OCR.**
- B requiere actas rellenas cuya utilización esté autorizada. La muestra y los umbrales de calidad se acordarán con evidencia, sin fingir datos electorales.
- C requiere proveedor y presupuesto. D requiere el modelo oficial aplicable, seguridad y pruebas de operación.
- Comando reproducible: `py -3.13 -m pytest -q tests/test_ocr_rectify.py`. Para inspección local: `py -3.13 -m app.ocr_rectify RUTA_IMAGEN --output RUTA_DERIVADO.png`; nunca usar el mismo nombre para entrada y salida. El resultado JSON incluye hash del original, rotación, esquinas y versión de plantilla. No se activa en el trabajador operativo.
- Siguiente tarea concreta: obtener un pequeño lote autorizado de actas de mesa de Congreso rellenadas y fotos difíciles, crear el manifiesto de B y separar antes de ajustes las imágenes reservadas de evaluación. Sólo después se compararán proveedores y umbrales.
