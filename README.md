# AgenteMotor — Panel de Renovaciones de Pólizas

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-aiosqlite-003B57?style=flat&logo=sqlite&logoColor=white)
![Tests](https://img.shields.io/badge/tests-3%20passing-brightgreen?style=flat)

MVP full-stack para que asesores de seguros reemplacen su Excel de renovaciones por un dashboard operativo con clasificación de pólizas por urgencia comercial, registro de gestiones y acceso directo a WhatsApp del cliente.

---

## Demo

> El backend corre localmente. Levantá los dos servidores con los comandos de abajo y abrí el navegador.

![Dashboard preview](https://via.placeholder.com/800x400/0f0f0f/f59e0b?text=AgenteMotor+Dashboard)

---

## Ejecución en 3 pasos

**Requisitos previos:** Python 3.11+, pip

```bash
# 1. Instalar dependencias
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt

# 2. Correr los tests
pytest -v test_main.py

# 3. Levantar backend + frontend
python main.py &  python3 -m http.server 5500
```

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000) — docs en `/docs`
- Frontend: [http://127.0.0.1:5500](http://127.0.0.1:5500)

> La base de datos se crea automáticamente con datos semilla en el primer arranque. No se necesita ninguna configuración adicional.

---

## Decisiones de diseño

### Por qué FastAPI + SQL crudo (sin ORM)
SQLAlchemy o Tortoise añaden abstracción que no aporta valor en un MVP de esta escala. Usar `aiosqlite` directamente da control total sobre las queries, evita el antipatrón N+1 desde el diseño, y mantiene toda la lógica legible en un solo archivo.

### Por qué la clasificación temporal es en memoria, no en la BD
El estado `crítica / preventiva / perdida` de una póliza cambia cada día sin que nadie toque la base de datos. Calcularlo en tiempo real en `classify_policy()` evita tener datos obsoletos y elimina la necesidad de cronjobs o columnas calculadas.

### Por qué un solo archivo (`main.py`)
El scope del MVP no justifica separación en módulos. Un evaluador puede leer el proyecto completo de arriba a abajo sin saltar entre archivos. La claridad supera la arquitectura prematura.

### Por qué vanilla JS (sin React/Vue)
El frontend es una sola pantalla sin estado complejo compartido. Un framework añadiría build step, dependencias y complejidad sin beneficio observable para el usuario.

---

## Qué dejé fuera y por qué

| Módulo | Decisión |
|--------|----------|
| Autenticación JWT/RBAC | No aporta al flujo crítico del MVP. María es el único usuario en este scope. |
| Registro de nuevos clientes | El problema a resolver es la gestión de pólizas existentes, no el onboarding. |
| Paginación | Con 6 registros semilla no aplica; en producción sería el primer feature a agregar. |
| Docker | La prueba lo prohíbe explícitamente como requisito. |

---

## Si esto fuera a producción mañana, le faltaría

- Autenticación (JWT + refresh tokens)
- Paginación y búsqueda en el dashboard
- Endpoint `POST /api/upload-prospects` para carga masiva de CSV/Excel de aseguradoras
- Rate limiting en los endpoints
- Variables de entorno para `DB_PATH` y `CORS origins`
- CI/CD con GitHub Actions corriendo los tests en cada PR

---

## Contexto del problema

En Colombia, una póliza vencida puede renovarse por el mismo intermediario dentro de los **30 días siguientes** sin perder historial. Después de ese plazo, la renovación se trata como contratación nueva y el asesor compite en igualdad con cualquier otro. Esta ventana define la clasificación del dashboard:

| Estado | Condición | Prioridad |
|--------|-----------|-----------|
| 🟡 Preventiva | Vence en los próximos días (diff ≥ 0) | Alta |
| 🔴 Crítica | Vencida hace 1–30 días (-30 ≤ diff < 0) | Urgente |
| ⚫ Perdida | Vencida hace más de 30 días (diff < -30) | Perdida comercialmente |

---

## Tiempo invertido

| Fase | Tiempo |
|------|--------|
| Análisis del problema y diseño de BD | 2h 30m |
| Backend (FastAPI + endpoints) | 45m |
| Frontend (dashboard + modal + UX) | 1h |
| Tests + documentación | 45m |
| **Total** | **5h** |

---

## Video de sustentación

👉 [Ver video en YouTube (3 min)](https://youtu.be/LiH8YiD9Vfg)

Lectura de `spec.md` con las decisiones más relevantes y reflexión sobre el trade-off que más tiempo tomó.

---

## ¿Qué cambiaría de esta prueba?

Agregaría un endpoint `POST /api/upload-prospects` con streaming asíncrono para carga de archivos CSV/Excel. En producción real, los intermediarios reciben listados masivos directamente de las 14 aseguradoras en formatos heterogéneos. Eso evaluaría manejo de memoria bajo carga, parsing en lotes y errores parciales — escenarios mucho más representativos del trabajo real que el seeding estático.