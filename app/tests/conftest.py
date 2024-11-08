# tests/conftest.py
import os
import logging
import sys
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.core.config import Settings
from app.main import app

# Impostazione del policy del loop per compatibilità su Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(scope="session")
def event_loop():
    """
    Crea un event loop per l'intera sessione di test, garantendo la compatibilità su Windows.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Configurazione del logging di SQLAlchemy
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)  # Cambiare in DEBUG per output più dettagliato

# Caricamento delle impostazioni e creazione del motore di database di test
settings = Settings()
test_engine = create_async_engine(settings.test_database_url, echo=True)

# Creazione di una session factory per il database di test
AsyncSessionLocal = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """
    Prepara e pulisce il database di test prima e dopo ogni test.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client():
    """
    Client per effettuare richieste HTTP asincrone al server di test.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
