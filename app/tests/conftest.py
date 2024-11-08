# tests/conftest.py
import os
import logging
import sys
import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.core.config import Settings
from httpx import AsyncClient
from app.main import app

# Imposta l’event loop policy per compatibilità su Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

@pytest.fixture(scope="session")
def event_loop():
    """
    Crea un event loop per la sessione di test, garantendo la compatibilità su Windows.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# Configura il logging di SQLAlchemy
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

# Carica le impostazioni e configura il database di test
settings = Settings()
test_engine = create_async_engine(settings.test_database_url, echo=True)

# Configura il sessionmaker per il database di test
AsyncSessionLocal = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

@pytest_asyncio.fixture(scope="function")
async def test_db():
    """
    Inizializza il database di test e cancella i dati al termine.
    """
    # Crea tutte le tabelle prima dell'inizio di ogni test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Fornisce una nuova sessione per ogni test
    async with AsyncSessionLocal() as session:
        yield session

    # Rimuove tutte le tabelle al termine del test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    """
    Client asincrono per inviare richieste di test, collegato al test_db.
    """
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
