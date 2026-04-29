# SAP Report

Aplicacion de escritorio en `Tkinter` para operar reportes y validaciones entre `SAP HANA`, `PostgreSQL` y `MySQL`.

El proyecto no es solo un exportador de Excel. Hoy concentra cuatro flujos operativos:

- `Ejecutar reporte`: genera los reportes base SAP/TUTATI y el archivo de comparacion.
- `Validar Articulos`: ejecuta una migracion previa en PostgreSQL y luego abre URLs de validacion en navegador.
- `Validar Igv`: cruza SAP, MySQL y PostgreSQL para actualizar articulos, ejecutar SPs de movimiento y marcar documentos en SAP.
- `Prestamo` y `Revisar Hilos`: consultas operativas de apoyo desde la UI.

## Objetivo

Centralizar en una sola herramienta de escritorio:

- ejecucion de consultas por rango de fechas;
- exportacion de resultados a Excel;
- comparaciones entre fuentes heterogeneas;
- validaciones operativas que antes se hacian manualmente;
- acciones de soporte sobre SAP y bases auxiliares.

## Arquitectura

El proyecto usa una separacion por capas sencilla y mantenible:

- `src/sap_report/ui/`: interfaz `Tkinter`, formularios, ventanas auxiliares y eventos de botones.
- `src/sap_report/application/`: orquestacion de casos de uso (`ReportService`).
- `src/sap_report/domain/`: logica de dominio reutilizable, por ejemplo conversiones `fecha <-> CUID`.
- `src/sap_report/infrastructure/config.py`: carga de configuracion, defaults y deteccion de placeholders en `.env`.
- `src/sap_report/infrastructure/db/`: repositorios por motor (`SAP HANA`, `PostgreSQL`, `MySQL`) y sus queries SQL.
- `src/sap_report/infrastructure/export/`: escritura y actualizacion de archivos Excel.
- `app.py`: launcher rapido para desarrollo.
- `src/sap_report/__main__.py`: entrada para ejecucion como modulo.

La composicion principal se hace en [main.py](C:/Proyectos/SAP/src/sap_report/main.py).

## Requisitos

- Python `>= 3.11`
- Windows
- Acceso de red a las bases configuradas
- Navegador Chrome o Brave para el flujo `Validar Articulos`

Dependencias principales:

- `pandas`
- `openpyxl`
- `psycopg2-binary`
- `pymysql`
- `hdbcli`
- `python-dotenv`
- `tkcalendar`

## Instalacion

Instalacion editable recomendada:

```powershell
pip install -e .
```

Alternativa simple:

```powershell
pip install -r requirements.txt
```

## Ejecucion

Modo recomendado:

```powershell
python -m sap_report
```

Con entrypoint del paquete:

```powershell
sap-report
```

Modo rapido para desarrollo:

```powershell
python app.py
```

## Configuracion

La configuracion se lee desde `.env`. Puedes usar `.env.example` como plantilla base.

El comportamiento actual es mixto:

- Si el `.env` contiene valores completos, la aplicacion arranca directo.
- Si faltan variables o tienen placeholder tipo `????`, la app solicita solo esos campos al iniciar.
- Los valores ingresados por popup se usan en memoria para esa ejecucion; no reescriben el `.env`.

### Variables obligatorias o esperadas

PostgreSQL:

- `PG_HOST` o `DB_HOST`
- `PG_NAME` o `DB_NAME`
- `PG_USER` o `DB_USER`
- `PG_PASSWORD` o `DB_PASSWORD`
- `PG_PORT` o `DB_PORT` (`5432` por defecto)
- `PG_SSLMODE` o `DB_SSLMODE` (`require` por defecto)
- `PG_CONNECT_TIMEOUT` o `DB_CONNECT_TIMEOUT` (`10` por defecto)

SAP HANA:

- `SAP_HANA_HOST` (`172.31.28.162` por defecto)
- `SAP_HANA_PORT` (`30015` por defecto)
- `SAP_HANA_USER`
- `SAP_HANA_PASSWORD`
- `SAP_HANA_ENCRYPT`
- `SAP_HANA_SSL_VALIDATE_CERTIFICATE`
- `SAP_HANA_SSL_TRUST_STORE`
- `SAP_HANA_SSL_KEY_STORE_PASSWORD`
- `SAP_HANA_CONNECT_TIMEOUT`

MySQL:

- `MYSQL_HOST`
- `MYSQL_NAME`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_PORT` (`3306` por defecto)
- `MYSQL_CONNECT_TIMEOUT` (`10` por defecto)

Salidas:

- `SAP_OUTPUT_PATH` (`OUTPUT/SAP.xlsx`)
- `PG_OUTPUT_PATH` (`OUTPUT/TUTATI.xlsx`)
- `COMPARACION_OUTPUT_PATH` (`OUTPUT/COMPARACION.xlsx`)

Parametros generales:

- `REINTENTOS_CONEXION` (`5`)
- `ESPERA_REINTENTO_SEGUNDOS` (`10`)
- `FECHA_INICIO`
- `FECHA_FIN`
- `UI_WIDTH`
- `UI_HEIGHT`

### Nota importante sobre rutas de salida

Si usas rutas relativas como `OUTPUT/SAP.xlsx`, el archivo se genera relativo al directorio desde el que ejecutas la app. Si necesitas un comportamiento estable para usuarios finales o un `.exe`, conviene usar rutas absolutas.

## Flujo de la interfaz

La ventana principal expone cinco acciones:

- `Probar conexion`: valida conectividad a `SAP`, `PostgreSQL` y `MySQL` sin ejecutar reportes pesados.
- `Validar Articulos`: ejecuta `migrar_OC` en PostgreSQL para ayer y anteayer, luego consulta SAP y abre URLs de validacion en navegador.
- `Validar Igv`: toma documentos desde SAP, cruza con MySQL, valida articulos IGV en SAP, ejecuta updates y SPs operativos, y muestra los `U_BOT_DOCENTRY` evaluados en una ventana copiable.
- `Revisar Hilos`: muestra el conteo de hilos pendientes en una tabla auxiliar.
- `Prestamo`: recibe una lista manual de `U_BOT_DOCENTRY`, cruza MySQL y SAP, y muestra diferencias positivas de stock en una tabla copiable.
- `Ejecutar reporte`: corre el proceso principal de exportacion y comparacion por rango de fechas.

## Proceso principal

El boton `Ejecutar reporte` hace lo siguiente:

1. Ejecuta `SAP.sql` por lotes diarios.
2. Exporta el resultado a `SAP.xlsx`.
3. Ejecuta `sap_nc.sql` y agrega la pestana `Acumulado_NC` en `SAP.xlsx`.
4. Ejecuta `TUTATI.sql` por lotes diarios.
5. Exporta el resultado a `TUTATI.xlsx`.
6. Ejecuta `tutati_nc.sql` y agrega la pestana `Acumulado_NC` en `TUTATI.xlsx`.
7. Si ambas fuentes salieron bien, genera `COMPARACION.xlsx` con:
   - `Comparacion`
   - `Comparacion_NC`

Cada hoja de comparacion contiene tres bloques en una misma pestaña:

- `RESUMEN`
- `FALTANTES`
- `DIFERENCIAS`

La comparacion de montos usa umbral `0.12`.

## Archivos SQL

Queries principales:

- [SAP.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/SAP.sql)
- [sap_nc.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/sap_nc.sql)
- [TUTATI.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/TUTATI.sql)
- [tutati_nc.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/tutati_nc.sql)

Queries operativos:

- [validar_articulos.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/validar_articulos.sql)
- [validar_igv_sap.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/validar_igv_sap.sql)
- [validar_igv_sap_items.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/validar_igv_sap_items.sql)
- [validar_igv_update_comercial.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/validar_igv_update_comercial.sql)
- [validar_igv_update_pedral.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/validar_igv_update_pedral.sql)
- [validar_igv_update_hilos.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/validar_igv_update_hilos.sql)
- [validar_igv_mysql_docs.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/validar_igv_mysql_docs.sql)
- [validar_igv_mysql_items.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/validar_igv_mysql_items.sql)
- [validar_igv_mysql_pendientes_orders.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/validar_igv_mysql_pendientes_orders.sql)
- [validar_igv_mysql_pendientes_rmas.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/validar_igv_mysql_pendientes_rmas.sql)
- [migrar_OC.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/migrar_OC.sql)
- [prestamo_stock.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/prestamo_stock.sql)
- [revisar_hilos.sql](C:/Proyectos/SAP/src/sap_report/infrastructure/db/queries/revisar_hilos.sql)

Reglas de parametrizacion:

- SAP usa placeholders `{{fecha_inicio}}`, `{{fecha_fin}}`, `{{items_in}}`, `{{docentries_in}}`, etc.
- PostgreSQL y MySQL mezclan placeholders manuales renderizados por la app con parametros SQL segun el caso.

## Salidas Excel

`SAP.xlsx`

- Hoja principal con el resultado de `SAP.sql`
- Hoja `Acumulado_NC`

`TUTATI.xlsx`

- Hoja principal con el resultado de `TUTATI.sql`
- Hoja `Acumulado_NC`

`COMPARACION.xlsx`

- Hoja `Comparacion`
- Hoja `Comparacion_NC`

Las ventanas auxiliares de `Prestamo`, `Revisar Hilos` y `U_BOT_DOCENTRY evaluados` no generan archivos adicionales; se muestran en pantalla y permiten copiar datos.

## Empaquetado

Para desarrollo, el launcher rapido sigue siendo [app.py](C:/Proyectos/SAP/app.py). Para distribucion o automatizacion, la forma mas limpia es usar el paquete:

```powershell
python -m sap_report
```

El proyecto ya expone el script `sap-report` en [pyproject.toml](C:/Proyectos/SAP/pyproject.toml).

Si vas a generar un `.exe`, ten en cuenta:

- la app depende de acceso de red a las bases;
- los archivos SQL deben viajar con el paquete;
- las rutas relativas de salida dependen del directorio de ejecucion;
- el `.env` externo sigue siendo la opcion mas simple, aunque la app ya soporta pedir credenciales faltantes por popup.

## Desarrollo y pruebas

Pruebas actuales:

```powershell
pytest
```

La cobertura automatizada todavia es baja. Hoy existen pruebas unitarias basicas en `tests/unit`, pero los flujos principales dependen bastante de integraciones reales con base de datos.

## Observaciones operativas

- El proceso principal trabaja por lotes diarios para reducir riesgo de timeouts.
- Si una de las fuentes falla en `Ejecutar reporte`, la app intenta continuar con la otra y reporta el error por separado.
- Si fallan SAP y PostgreSQL al mismo tiempo, el proceso principal termina con error global.
- `Validar Articulos` y `Validar Igv` no son solo consultas: ejecutan acciones operativas sobre otros sistemas.
- `Prestamo` filtra solo diferencias positivas (`Cantidad_MYSQL - Stock_SAP > 0`).

## Estructura resumida

```text
SAP/
|-- app.py
|-- pyproject.toml
|-- README.md
|-- src/
|   `-- sap_report/
|       |-- __main__.py
|       |-- main.py
|       |-- logging_config.py
|       |-- application/
|       |-- domain/
|       |-- infrastructure/
|       `-- ui/
`-- tests/
```
