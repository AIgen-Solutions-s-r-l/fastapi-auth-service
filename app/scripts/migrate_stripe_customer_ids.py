import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.log.logging import logger # Assuming logger is configured similarly
from app.models.user import User
from app.models.plan import Subscription # Assuming Subscription model is here
# Add path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from app.core.database import AsyncSessionLocal, engine # Adjusted import

async def migrate_stripe_customer_ids():
    """Popola il campo stripe_customer_id per gli utenti esistenti."""
    logger.info("Inizio migrazione stripe_customer_id...")
    async with AsyncSessionLocal() as db:
        # Trova tutte le sottoscrizioni con stripe_customer_id impostato
        stmt = select(Subscription).where(Subscription.stripe_customer_id.is_not(None))
        result = await db.execute(stmt)
        subscriptions = result.scalars().all()
        
        updated_count = 0
        processed_user_ids = set()

        for subscription in subscriptions:
            if not subscription.stripe_customer_id: # Should not happen due to where clause, but good check
                logger.warning(f"Subscription {subscription.id} found with NULL stripe_customer_id despite query filter.")
                continue

            if subscription.user_id in processed_user_ids:
                logger.info(f"Utente {subscription.user_id} già processato per un'altra sottoscrizione, salto.")
                continue
            
            # Trova l'utente corrispondente
            user = await db.get(User, subscription.user_id)
            if user:
                if not user.stripe_customer_id:
                    user.stripe_customer_id = subscription.stripe_customer_id
                    db.add(user) # Mark for update
                    updated_count += 1
                    logger.info(f"Aggiornato stripe_customer_id per utente {user.id}: {subscription.stripe_customer_id}")
                elif user.stripe_customer_id != subscription.stripe_customer_id:
                    logger.warning(f"Utente {user.id} ha già stripe_customer_id {user.stripe_customer_id}, ma la sottoscrizione {subscription.id} ha {subscription.stripe_customer_id}. Non sovrascrivo.")
                else: # user.stripe_customer_id == subscription.stripe_customer_id
                    logger.info(f"Utente {user.id} ha già stripe_customer_id {user.stripe_customer_id} correttamente impostato.")
                processed_user_ids.add(user.id)
            else:
                logger.warning(f"Utente {subscription.user_id} non trovato per la sottoscrizione {subscription.id}.")
        
        if updated_count > 0:
            try:
                await db.commit()
                logger.info(f"Commit di {updated_count} aggiornamenti utenti.")
            except Exception as e:
                await db.rollback()
                logger.error(f"Errore durante il commit della migrazione: {e}", exc_info=True)
                return # Exit if commit fails
        else:
            logger.info("Nessun utente necessitava di aggiornamento per stripe_customer_id.")
            
        logger.info(f"Migrazione completata: {updated_count} utenti aggiornati.")

async def main():
    # Optional: Initialize database models if needed, though usually handled by Alembic/FastAPI startup
    # from app.core.base import Base  # Ensure all models are loaded
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all) # Be careful with this in production
    
    await migrate_stripe_customer_ids()
    await engine.dispose() # Cleanly close the connection pool

if __name__ == "__main__":
    logger.info("Esecuzione script di migrazione stripe_customer_id...")
    asyncio.run(main())
    logger.info("Script di migrazione stripe_customer_id terminato.")