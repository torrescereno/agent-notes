import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import psycopg2
import psycopg2.extensions
import psycopg2.extras

from mcp.server.fastmcp import FastMCP, Context


@dataclass
class Database:
    conn: psycopg2.extensions.connection

    @classmethod
    async def connect(cls) -> "Database":
        conn = psycopg2.connect(
            host="localhost", database="postgres", user="admin", password="admin123"
        )
        return cls(conn)

    async def disconnect(self) -> None:
        self.conn.close()

    def query(self, query_str: str) -> dict:
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query_str)

            if cur.description is None:
                return {"error": "La consulta no devolvió resultados (no es SELECT)"}

            columns = [desc.name for desc in cur.description]
            rows = cur.fetchall()
            rows_dict = [dict(row) for row in rows]

            return {
                "columns": columns,
                "rows": rows_dict[:50],
            }


@dataclass
class AppContext:
    db: Database


@asynccontextmanager
async def app_lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
    db = await Database.connect()

    try:
        yield AppContext(db=db)
    finally:
        await db.disconnect()


mcp = FastMCP("Demo SERVER", lifespan=app_lifespan)


@mcp.tool(name="execute_query", description="Ejecuta una consulta SELECT a PostgreSQL")
async def execute_query(query: str, ctx: Context) -> dict:
    db: AppContext = ctx.request_context.lifespan_context.db

    if not query.strip().lower().startswith("select"):
        return {"error": "Solo se permiten consultas SELECT por seguridad."}
    try:
        return db.query(query)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(
    name="fetch_weather",
    description="Consulta el clima actual de una ciudad usando la API de Visual Crossing.",
)
async def fetch_weather(city: str) -> dict:
    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
    if not WEATHER_API_KEY:
        return {"error": "WEATHER_API_KEY no está configurada"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}/today?unitGroup=metric&include=current&key={WEATHER_API_KEY}&contentType=json"
        )
    return resp.json()


if __name__ == "__main__":
    mcp.run()
