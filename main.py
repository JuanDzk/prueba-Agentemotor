"""
AgenteMotor - MVP de Gestión de Renovaciones de Seguros
Backend: FastAPI + aiosqlite (SQL crudo) + Pydantic
Archivo único: main.py
"""

import os
import datetime
from contextlib import asynccontextmanager
from typing import Optional

import aiosqlite
import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuración global
# ---------------------------------------------------------------------------

DB_PATH = "agentemotor.db"


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class CreateContactAttempt(BaseModel):
    policy_id: int
    observation: str


class DashboardItem(BaseModel):
    policy_id: int
    client_name: str
    client_phone: str
    insurer: str
    expiration_date: str
    days_difference: int
    status: str
    last_contact: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers de base de datos
# ---------------------------------------------------------------------------

@asynccontextmanager
async def get_db_session():
    """Context manager asíncrono que abre y cierra la sesión de forma segura."""
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# DDL + Seeding inicial
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Crea tablas e inserta datos semilla dinámicos."""
    async with aiosqlite.connect(DB_PATH) as db:
        # --- Tablas ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT    NOT NULL,
                phone TEXT    NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS policies (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id       INTEGER NOT NULL REFERENCES clients(id),
                insurer         TEXT    NOT NULL,
                expiration_date TEXT    NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS contact_attempts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id    INTEGER NOT NULL REFERENCES policies(id),
                attempt_date TEXT    NOT NULL,
                observation  TEXT    NOT NULL
            )
        """)

        await db.commit()

        # --- Datos semilla dinámicos ---
        today = datetime.date.today()

        def iso(delta_days: int) -> str:
            return (today + datetime.timedelta(days=delta_days)).isoformat()

        seed_clients = [
            ("Carlos Mendoza",    "310-555-0101"),  # preventiva  +5
            ("Lucía Fernández",   "311-555-0202"),  # preventiva  +12
            ("Andrés Torres",     "312-555-0303"),  # crítica     -10
            ("Valentina Ruiz",    "313-555-0404"),  # crítica     -25
            ("Miguel Ángel Díaz", "314-555-0505"),  # perdida     -45
            ("Sara Patricia Gil", "315-555-0606"),  # perdida     -60
        ]

        seed_policies = [
            ("Sura",      +5),
            ("Bolívar",  +12),
            ("Mapfre",   -10),
            ("Allianz",  -25),
            ("Liberty",  -45),
            ("AXA",      -60),
        ]

        for idx, ((name, phone), (insurer, delta)) in enumerate(
            zip(seed_clients, seed_policies)
        ):
            cursor = await db.execute(
                "INSERT INTO clients (name, phone) VALUES (?, ?)",
                (name, phone),
            )
            client_id = cursor.lastrowid

            await db.execute(
                "INSERT INTO policies (client_id, insurer, expiration_date) VALUES (?, ?, ?)",
                (client_id, insurer, iso(delta)),
            )

        await db.commit()


# ---------------------------------------------------------------------------
# Lifespan (arranque y cierre)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manejador de ciclo de vida: inicializa la BD sólo si no existe."""
    db_exists = os.path.exists(DB_PATH)

    if not db_exists:
        print("[AgenteMotor] Base de datos no encontrada. Creando esquema e insertando datos semilla...")
        await init_db()
        print("[AgenteMotor] Inicialización completada exitosamente.")
    else:
        print("[AgenteMotor] Base de datos existente detectada. Omitiendo inicialización.")

    yield  # La aplicación corre aquí

    print("[AgenteMotor] Servidor detenido.")


# ---------------------------------------------------------------------------
# Instancia de la aplicación
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AgenteMotor API",
    description="MVP de gestión de renovaciones de seguros vehiculares.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Lógica de clasificación temporal
# ---------------------------------------------------------------------------

def classify_policy(expiration_date_str: str) -> tuple[int, str]:
    """Calcula days_difference y el estado comercial de la póliza."""
    expiration = datetime.date.fromisoformat(expiration_date_str)
    today = datetime.date.today()
    diff = (expiration - today).days

    if diff >= 0:
        status = "preventiva"
    elif diff >= -30:
        status = "critica"
    else:
        status = "perdida"

    return diff, status


def status_sort_key(item: DashboardItem) -> int:
    """Orden: crítica (0) → preventiva (1) → perdida (2)."""
    order = {"critica": 0, "preventiva": 1, "perdida": 2}
    return order.get(item.status, 99)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/dashboard",
    response_model=list[DashboardItem],
    summary="Tablero unificado de pólizas",
)
async def get_dashboard() -> list[DashboardItem]:
    """Retorna todas las pólizas con datos del cliente y su última gestión."""
    query = """
        SELECT
            p.id              AS policy_id,
            c.name            AS client_name,
            c.phone           AS client_phone,
            p.insurer         AS insurer,
            p.expiration_date AS expiration_date,
            (
                SELECT ca.observation
                FROM   contact_attempts ca
                WHERE  ca.policy_id = p.id
                ORDER  BY ca.attempt_date DESC
                LIMIT  1
            ) AS last_contact
        FROM policies p
        INNER JOIN clients c ON c.id = p.client_id
        ORDER BY p.id
    """

    try:
        async with get_db_session() as db:
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
    except aiosqlite.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar la base de datos: {exc}",
        )

    items: list[DashboardItem] = []
    for row in rows:
        diff, policy_status = classify_policy(row["expiration_date"])
        items.append(
            DashboardItem(
                policy_id=row["policy_id"],
                client_name=row["client_name"],
                client_phone=row["client_phone"],
                insurer=row["insurer"],
                expiration_date=row["expiration_date"],
                days_difference=diff,
                status=policy_status,
                last_contact=row["last_contact"],
            )
        )

    items.sort(key=status_sort_key)
    return items


@app.post(
    "/api/attempts",
    status_code=status.HTTP_201_CREATED,
    summary="Registrar intento de contacto",
)
async def create_attempt(payload: CreateContactAttempt) -> dict:
    """Almacena un nuevo intento de contacto para una póliza."""
    try:
        async with get_db_session() as db:
            # Validación de integridad referencial
            cursor = await db.execute(
                "SELECT id FROM policies WHERE id = ?",
                (payload.policy_id,),
            )
            policy = await cursor.fetchone()

            if policy is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"La póliza con id={payload.policy_id} no existe en el sistema.",
                )

            attempt_date = datetime.datetime.now().isoformat()

            await db.execute(
                """
                INSERT INTO contact_attempts (policy_id, attempt_date, observation)
                VALUES (?, ?, ?)
                """,
                (payload.policy_id, attempt_date, payload.observation),
            )
            await db.commit()

    except HTTPException:
        raise  
    except aiosqlite.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar el intento de contacto: {exc}",
        )

    return {
        "message": "Intento de contacto registrado exitosamente.",
        "policy_id": payload.policy_id,
        "attempt_date": attempt_date,
    }


# ---------------------------------------------------------------------------
# Ejecución directa
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)