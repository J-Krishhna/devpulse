import asyncio
import asyncpg
import redis

async def check_postgres():
    conn = await asyncpg.connect("postgresql://devpulse:devpulse@localhost:5432/devpulse")
    result = await conn.fetchval("SELECT version()")
    print(f"✅ Postgres connected: {result[:40]}")
    await conn.close()

def check_redis():
    r = redis.Redis.from_url("redis://localhost:6379")
    pong = r.ping()
    print(f"✅ Redis connected: {pong}")

asyncio.run(check_postgres())
check_redis()