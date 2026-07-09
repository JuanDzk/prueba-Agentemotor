# AgenteMotor — Spec del MVP

## Cómo entendí el problema

María tiene 280 clientes activos y los gestiona desde un Excel frágil. El problema real no es el Excel en sí — es que la ventana de 30 días post-vencimiento para renovar sin perder historial convierte cada póliza en un elemento con urgencia comercial dinámica que cambia cada día. Una herramienta útil tiene que reflejar esa urgencia en tiempo real y permitir registrar acciones sobre cada póliza sin fricción.

El flujo crítico es: **ver qué pólizas necesitan atención hoy → contactar al cliente → registrar qué pasó.**

---

## Qué decidí construir

### Incluido

**Dashboard unificado (`GET /api/dashboard`)**
Una sola vista con todas las pólizas del asesor, clasificadas por urgencia comercial en tiempo real. Incluye datos del cliente, aseguradora, fecha de vencimiento, días restantes/transcurridos, estado y última gestión registrada.

**Registro de gestiones (`POST /api/attempts`)**
Permite registrar observaciones de contacto sobre cualquier póliza. Cada registro queda con timestamp y se refleja de inmediato en el dashboard como "última gestión".

**Clasificación temporal en memoria**
El estado `preventiva / crítica / perdida` se calcula en cada request sobre la fecha de vencimiento real. No se persiste en la BD para evitar datos obsoletos.

**Frontend operativo de pantalla única**
Dashboard con filtros por estado, KPIs de conteo, modal de gestión con acceso directo a WhatsApp del cliente (normalización `+57`), skeleton loading y feedback visual de errores.

### Excluido

| Módulo | Justificación |
|--------|---------------|
| Autenticación | No aporta al flujo crítico. Añade fricción sin validar la lógica de negocio. |
| Registro de clientes | El problema es gestionar pólizas existentes, no onboarding. |
| Docker | Prohibido explícitamente como requisito. |
| Paginación | Fuera del scope del MVP con los datos semilla actuales. |

---

## Supuestos

- Un asesor gestiona todas las pólizas del sistema (sin multitenancy en este MVP).
- Los datos de clientes y pólizas entran al sistema mediante seed dinámico; en producción vendrían de un proceso de sincronización con las aseguradoras.
- `expiration_date` siempre llega en formato ISO (`YYYY-MM-DD`) desde la BD.
- El teléfono del cliente puede o no incluir el prefijo `57`; el frontend lo normaliza.

---

## Modelo de datos

```sql
clients (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    phone TEXT NOT NULL
)

policies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       INTEGER NOT NULL REFERENCES clients(id),
    insurer         TEXT NOT NULL,
    expiration_date TEXT NOT NULL   -- ISO: YYYY-MM-DD
)

contact_attempts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id    INTEGER NOT NULL REFERENCES policies(id),
    attempt_date TEXT NOT NULL,     -- ISO datetime
    observation  TEXT NOT NULL
)
```

**Por qué no hay columna `status`:** El estado es una función de `expiration_date` y la fecha actual. Persistirlo crearía datos obsoletos al día siguiente sin ningún proceso que los actualice.

---

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/dashboard` | Todas las pólizas con clasificación temporal y última gestión |
| `POST` | `/api/attempts` | Registrar intento de contacto sobre una póliza |
| `GET` | `/docs` | Documentación interactiva automática (FastAPI/Swagger) |

---

## Lógica de clasificación

```
diff = expiration_date - today

diff >= 0        → preventiva   (aún vigente, renovar pronto)
-30 <= diff < 0  → crítica      (vencida, dentro de la ventana de 30 días)
diff < -30       → perdida      (fuera de la ventana, nueva contratación)
```

Orden del dashboard: **crítica → preventiva → perdida** (por impacto comercial inmediato).

---

## Mitigación del antipatrón N+1

El endpoint `/api/dashboard` consolida toda la información en una sola query con `INNER JOIN` y subconsulta correlacionada para el último contacto. Alternativa descartada: consulta separada por póliza para cliente + intentos (N+1 clásico del snippet de code review).

---

## Trade-offs considerados

**Archivo único vs. módulos separados:** Elegí archivo único. El scope no justifica separación y un evaluador puede leer el proyecto completo sin navegar entre archivos. En producción separaría en `routers/`, `models/`, `db/`.

**Vanilla JS vs. React:** Sin estado compartido complejo ni build step necesario. La pantalla única con fetch nativo es más directa y sin dependencias.

**SQL crudo vs. ORM:** Control total sobre las queries, sin abstracción que oculte el N+1. En un proyecto más grande usaría SQLAlchemy con sesiones manejadas por dependency injection de FastAPI.

---

## Tiempo de desarrollo

| Fase | Tiempo |
|------|--------|
| Análisis y diseño de BD | 2h 30m |
| Backend (FastAPI + endpoints) | 45m |
| Frontend (dashboard + modal) | 1h |
| Tests + documentación | 45m |
| **Total** | **5h** |