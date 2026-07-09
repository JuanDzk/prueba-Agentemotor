"""
AgenteMotor - Suite de Pruebas Unitarias y de Integración
Archivo: test_main.py
Ejecución: pytest -v test_main.py
"""

import os
import pytest
import asyncio
import aiosqlite
import datetime
from httpx import AsyncClient, ASGITransport
from contextlib import asynccontextmanager

# Importamos la aplicación y la ruta base del archivo principal
import main
from main import app, DashboardItem

TEST_DB_PATH = "test_agentemotor.db"

# ---------------------------------------------------------------------------
# Fixtures y Configuración del Entorno de Pruebas
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@asynccontextmanager
async def get_test_db_session():
    """Generador de sesiones seguro para la base de datos de pruebas."""
    conn = await aiosqlite.connect(TEST_DB_PATH)
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()


async def init_test_db():
    """Inicializa el esquema DDL y datos semilla controlados para pruebas."""
    async with aiosqlite.connect(TEST_DB_PATH) as db:
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

        # Insertamos datos estáticos predecibles para aserciones exactas
        # Cliente 1: Póliza Crítica (Vencida hace 10 días)
        # Cliente 2: Póliza Preventiva (Vence en 5 días)
        today = datetime.date.today()
        critica_date = (today - datetime.timedelta(days=10)).isoformat()
        preventiva_date = (today + datetime.timedelta(days=5)).isoformat()

        await db.execute("INSERT INTO clients (id, name, phone) VALUES (1, 'Test Critico', '555-0001')")
        await db.execute("INSERT INTO clients (id, name, phone) VALUES (2, 'Test Preventivo', '555-0002')")
        
        await db.execute(f"INSERT INTO policies (id, client_id, insurer, expiration_date) VALUES (10, 1, 'Insurer A', '{critica_date}')")
        await db.execute(f"INSERT INTO policies (id, client_id, insurer, expiration_date) VALUES (20, 2, 'Insurer B', '{preventiva_date}')")
        
        await db.commit()


@pytest.fixture(autouse=True, scope="session")
async def setup_and_teardown_db():
    """Fixture de ciclo de vida que prepara y destruye el entorno de pruebas."""
    # Forzar el uso de la base de datos de prueba modificando la constante global
    main.DB_PATH = TEST_DB_PATH
    
    # Sobrescribir el context manager del módulo principal para que use la BD de test
    main.get_db_session = get_test_db_session

    # Inicializar la base de datos temporal
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        
    await init_test_db()
    
    yield  # Aquí se ejecutan los tests
    
    # Limpieza al finalizar la suite completa
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


# ---------------------------------------------------------------------------
# Casos de Prueba Críticos
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_dashboard_consistency():
    """
    Test 1: Consistencia del Dashboard (GET)
    Valida el código 200, estructura de arreglo JSON, orden comercial correcto
    y consistencia de campos dinámicos calculados (days_difference y status).
    """
    transport = ASGITransport(app=app)
    async_client = AsyncClient(transport=transport, base_url="http://test")
    
    async with async_client as ac:
        response = await ac.get("/api/dashboard")
        
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2

    # El orden comercial estricto exige 'critica' antes que 'preventiva'
    policy_critica = data[0]
    policy_preventiva = data[1]

    assert policy_critica["policy_id"] == 10
    assert policy_critica["status"] == "critica"
    assert policy_critica["days_difference"] == -10
    assert policy_critica["client_name"] == "Test Critico"

    assert policy_preventiva["policy_id"] == 20
    assert policy_preventiva["status"] == "preventiva"
    assert policy_preventiva["days_difference"] == 5
    assert policy_preventiva["client_name"] == "Test Preventivo"


@pytest.mark.anyio
async def test_create_contact_attempt_success():
    """
    Test 2: Registro Exitoso de Gestión (POST)
    Valida la correcta inserción, respuesta HTTP 201 Created y estructura
    del mensaje JSON de éxito.
    """
    transport = ASGITransport(app=app)
    async_client = AsyncClient(transport=transport, base_url="http://test")
    
    payload = {
        "policy_id": 20,
        "observation": "Se contactó al cliente por WhatsApp, confirma revisión mañana."
    }
    
    async with async_client as ac:
        response = await ac.post("/api/attempts", json=payload)
        
    assert response.status_code == 201
    data = response.json()
    assert data["policy_id"] == 20
    assert "message" in data
    assert "attempt_date" in data
    assert data["message"] == "Intento de contacto registrado exitosamente."


@pytest.mark.anyio
async def test_create_contact_attempt_integrity_failure():
    """
    Test 3: Validación de Integridad Referencial (Caso Fallido)
    Valida que al enviar un policy_id inexistente el backend responda con
    un código 404 Not Found controlado, mitigando excepciones no controladas 500.
    """
    transport = ASGITransport(app=app)
    async_client = AsyncClient(transport=transport, base_url="http://test")
    
    payload = {
        "policy_id": 9999,  # ID inexistente
        "observation": "Póliza fantasma."
    }
    
    async with async_client as ac:
        response = await ac.post("/api/attempts", json=payload)
        
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "no existe en el sistema" in data["detail"]