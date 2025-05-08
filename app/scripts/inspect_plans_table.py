import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.database import engine # Assuming this is the async engine
from sqlalchemy import text

async def inspect_plans_data():
    print("Attempting to connect to the database and fetch data from 'plans' table...")
    async with engine.connect() as conn:
        # First, get column names to print headers and access data by name
        schema_query = text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name   = 'plans'
            ORDER BY ordinal_position;
        """)
        schema_result = await conn.execute(schema_query)
        column_names = [row.column_name for row in schema_result.fetchall()]

        if not column_names:
            print("\nCould not find 'plans' table or it has no columns in the 'public' schema.")
            await engine.dispose()
            return

        # Now, fetch all data
        data_query = text("SELECT * FROM plans;")
        data_result = await conn.execute(data_query)
        rows = data_result.fetchall()

        if rows:
            print("\nData in 'plans' table:")
            print("--------------------------")
            # Print header
            header = " | ".join([f"{name:<20}" for name in column_names]) # Adjust width as needed
            print(header)
            print("-" * len(header))

            # Print rows
            for row_index, row in enumerate(rows):
                print(f"Row {row_index + 1}:")
                for col_name in column_names:
                    print(f"  {col_name}: {getattr(row, col_name)}")
                if row_index < len(rows) -1:
                    print("---") # Separator between rows
            print("--------------------------")
        else:
            print("\n'plans' table is empty or no data found.")
            
    await engine.dispose() # Cleanly close the engine connections

async def main_async():
    try:
        await inspect_plans_data()
    except Exception as e:
        print(f"\nAn error occurred during script execution: {type(e).__name__}: {e}")
        import traceback
        print("\nTraceback:")
        print(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    print("Starting plans table data inspection script...")
    asyncio.run(main_async())
    print("Plans table data inspection script finished.")