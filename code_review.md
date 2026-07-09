# Auditoría de Código y Revisión Arquitectónica: Migración de Flask a FastAPI

Este documento presenta la revisión técnica del snippet original basado en Flask y detalla cómo las deficiencias críticas identificadas fueron resueltas en la arquitectura asíncrona de alto rendimiento implementada para **AgenteMotor**.

---

## 1. Problema de Rendimiento Crítico: Consulta N+1

### Hallazgo en Código Técnico
En el snippet de Flask original, el backend consulta primero las pólizas vencidas mediante un `SELECT` general. Posteriormente, itera sobre los resultados utilizando un ciclo estructural `for policy in expired:`. Dentro de este ciclo, se realizan de forma imperativa dos consultas adicionales a la base de datos por cada fila:
1. Un `SELECT` para obtener los datos individuales del cliente asociado.
2. Un `SELECT COUNT(*)` para cuantificar el histórico de intentos de contacto.

### Impacto en el Negocio de María
Bajo una carga real basada en los 280 clientes del portafolio actual de María, este diseño fuerza al servidor a ejecutar un total de $1 + (280 \times 2) = 561$ viajes individuales de ida y vuelta (*round-trips*) a la base de datos para renderizar una única solicitud del Tablero. El impacto real en el día a día se traduce en:
* Bloqueos en la interfaz visual, latencias que superan los varios segundos por petición y la pérdida potencial de clientes debido a demoras operativas críticas durante llamadas telefónicas simultáneas.

### Solución Implementada en el Nuevo Diseño
Se erradicó por completo el antipatrón de consulta N+1 consolidando el flujo en una **única consulta SQL indexada y combinada** dentro del endpoint `/api/dashboard`:
* Se utiliza un `INNER JOIN` explícito para acoplar la tabla de pólizas con la de clientes en un solo viaje de datos.
* Se integra una subconsulta correlacionada optimizada (`LIMIT 1` ordenado de forma descendente) para extraer de inmediato la última observación de gestión sin realizar conteos iterativos. La complejidad temporal pasó de $\mathcal{O}(N)$ consultas a $\mathcal{O}(1)$.

---

## 2. Bloqueo de E/S Síncrono (I/O Blocking)

### Hallazgo en Código Técnico
El código heredado utiliza el conector nativo `sqlite3`, el cual carece de soporte nativo para primitivas asíncronas de manejo de eventos. Cada operación de lectura o escritura en el archivo de base de datos congela por completo el hilo único de ejecución del proceso de Flask, impidiendo la concurrencia.

### Impacto en el Negocio de María
Si María expande su equipo e incorpora múltiples asesores comerciales trabajando en paralelo sobre la plataforma, el sistema se comportará como un cuello de botella físico. La API procesará las peticiones de forma estrictamente secuencial; la consulta de un asesor retrasará de forma obligatoria las llamadas web del resto del equipo, induciendo fallos de conexión por *timeout*.

### Solución Implementada en el Nuevo Diseño
La nueva arquitectura se fundamenta en un ecosistema enteramente asíncrono basado en **FastAPI (ASGI)** y **`aiosqlite`**:
* Todas las llamadas operativas a la base de datos se ejecutan suspendiendo la corrutina mediante `await` sin bloquear el bucle de eventos (*event loop*).
* El servidor de producción puede procesar miles de peticiones simultáneas, garantizando que el equipo de trabajo experimente respuestas inmediatas en tiempo real de forma paralela.

---

## 3. Inestabilidad del Estado del Negocio: Reglas de Negocio "Hardcodeadas"

### Hallazgo en Código Técnico
La segmentación del riesgo comercial se calcula de forma estática en la capa de persistencia mediante la instrucción condicional: `priority = 'urgent' if days_overdue > 7 else 'normal'`. 

### Impacto en el Negocio de María
Este cálculo arbitrario viola los parámetros comerciales del sector y desatiende la regulación colombiana vigente, la cual dictamina una ventana formal de gracia de hasta 30 días para pólizas vencidas antes de proceder a la cancelación automática de la cobertura. Clasificar erróneamente una póliza con 8 días de vencimiento como "pérdida de oportunidad" o sesgar las de baja prioridad genera:
* Pérdida real de comisiones por renovación.
* Una gestión comercial deficiente basada en datos falsos.

### Solución Implementada en el Nuevo Diseño
Se extrajo la lógica de negocio de las consultas directas y se encapsuló en funciones puras de Python (`classify_policy` y `status_sort_key`). El sistema calcula el estado en tiempo real basándose en deltas matemáticos exactos alineados con la operación real:
* **Preventiva**: $\ge 0$ días.
* **Crítica**: Ventana legal de gracia de entre $-1$ y $-30$ días.
* **Perdida**: Vencimientos severos superando los $-30$ días.

---

## 4. Falta de Manejo de Errores y Fuga de Conexiones

### Hallazgo en Código Técnico
El snippet de Flask inicializa la conexión y el cursor directamente en el cuerpo de la función sin implementar estructuras de control defensivas como bloques `try/except/finally` o manejadores de contexto regulados.

### Impacto en el Negocio de María
Si una consulta SQL falla por corrupción de datos o el archivo se bloquea en la mitad de la ejecución del ciclo `for`, la función aborta de forma abrupta. Al no alcanzar nunca la línea de cierre de conexión, el socket del archivo queda abierto en memoria. Tras un par de fallos consecutivos, el servidor agota su límite máximo de descriptores de archivos (*file descriptors*), provocando la caída catastrófica e irreversible de toda la infraestructura.

### Solución Implementada en el Nuevo Diseño
* Se implementaron bloques `try/except` explícitos mapeados a excepciones específicas (`aiosqlite.Error`) para transformar fallos internos en respuestas HTTP 500 claras y semánticas, protegiendo al frontend de comportamientos erráticos.
* Se estructuró un manejador de contexto asíncrono exclusivo (`async with get_db_session()`) que asegura de forma matemática que, sin importar si la consulta tiene éxito o lanza una excepción, el canal de la base de datos se cerrará de forma segura liberando los recursos del sistema operativo Nobara.