import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://testuser:testpassword@172.17.0.1:5432/main_db')
    
    # Add columns to users table
    await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE')
    await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token VARCHAR(255)')
    await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token_expires_at TIMESTAMP WITH TIME ZONE')
    
    # Create email_verification_tokens table
    await conn.execute('''
    CREATE TABLE IF NOT EXISTS email_verification_tokens (
        token VARCHAR(255) PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        used BOOLEAN NOT NULL DEFAULT FALSE
    )
    ''')
    
    # Create plans table
    await conn.execute('''
    CREATE TABLE IF NOT EXISTS plans (
        id SERIAL PRIMARY KEY,
        name VARCHAR(50) NOT NULL,
        tier VARCHAR(20) NOT NULL,
        credit_amount NUMERIC(10, 2) NOT NULL,
        price NUMERIC(10, 2) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        description VARCHAR(255),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    )
    ''')
    
    # Create subscriptions table
    await conn.execute('''
    CREATE TABLE IF NOT EXISTS subscriptions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        plan_id INTEGER NOT NULL REFERENCES plans(id),
        start_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        renewal_date TIMESTAMP WITH TIME ZONE NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
        last_renewal_date TIMESTAMP WITH TIME ZONE
    )
    ''')
    
    # Add fields to credit_transactions for plan relationship
    await conn.execute('ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS plan_id INTEGER REFERENCES plans(id)')
    await conn.execute('ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS subscription_id INTEGER REFERENCES subscriptions(id)')
    
    # Add basic plans
    await conn.execute('''
    INSERT INTO plans (name, tier, credit_amount, price, is_active, description)
    VALUES 
        ('Basic Plan', 'basic', 100.00, 9.99, true, 'Entry-level plan with 100 credits per month'),
        ('Standard Plan', 'standard', 500.00, 29.99, true, 'Standard plan with 500 credits per month'),
        ('Premium Plan', 'premium', 1500.00, 79.99, true, 'Premium plan with 1500 credits per month')
    ON CONFLICT (id) DO NOTHING
    ''')
    
    await conn.close()
    print("Database migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(run())