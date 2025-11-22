#!/usr/bin/env python
"""Script to initialize the database with tables."""

import asyncio
from src.api.database import init_db

async def main():
    print("Initializing database tables...")
    try:
        await init_db()
        print("✓ Database tables created successfully!")
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
