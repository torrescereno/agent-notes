from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

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


mcp = FastMCP("server db", lifespan=app_lifespan)


@mcp.tool(name="execute_query", description="Ejecuta una consulta SELECT a PostgreSQL")
async def execute_query(query: str, ctx: Context) -> dict:
    context_app: AppContext = ctx.request_context.lifespan_context

    if not query.strip().lower().startswith("select"):
        return {"error": "Solo se permiten consultas SELECT por seguridad."}
    try:
        return context_app.db.query(query)
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
