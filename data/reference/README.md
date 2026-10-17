# Controles provinciales 2023

`2023_province_controls.csv` transcribe la tabla de municipios, distritos, secciones, mesas y locales electorales que el promotor comunicó el 17 de octubre de 2026 como referencia de las elecciones generales de julio de 2023. Es una fuente aportada por el usuario, sin enlace oficial ni listado individual de locales en el proyecto. Las denominaciones se mantienen como fueron comunicadas; los códigos provinciales se cotejaron con el maestro detallado de 2023.

La fila TOTAL comunicada es 8.131 municipios, 10.461 distritos, 36.460 secciones, 60.314 mesas interiores y 22.706 locales. La suma de las 52 filas del CSV coincide con esos totales. `python -m app.reference_controls <fichero-maestro-2023.xlsx>` calcula por provincia las cuatro primeras medidas desde la pestaña `MESAS`, excluye los 52 registros `COD.MUN=999` de voto exterior y falla si hay discrepancias. **No puede verificar los locales**: el maestro de mesas no incluye identificadores ni direcciones de local.

Este CSV no representa mesas o locales de 2026, no se activa en la aplicación y no se utiliza como denominador del dashboard operativo. Cuando se publique el catálogo de 2026, se importará como otra versión con procedencia propia y se compararán sus cambios frente a esta referencia.
