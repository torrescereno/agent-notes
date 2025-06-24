import os
import asyncio
from typing import List, Dict, Any, Optional
import httpx
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from mcp.server.fastmcp import FastMCP
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass


class Database:
    """Clase para manejar la conexión a PostgreSQL con psycopg v3 y un pool de conexiones asíncrono."""

    def __init__(self):
        self.pool: Optional[AsyncConnectionPool] = None

    async def connect(self):
        """Inicializa el pool de conexiones asíncrono."""
        if self.pool:
            return
            
        conninfo = " ".join([
            f"host={os.getenv('DB_HOST', 'localhost')}",
            f"port={int(os.getenv('DB_PORT', '5432'))}",
            f"user={os.getenv('DB_USER', 'admin')}",
            f"password={os.getenv('DB_PASSWORD', 'admin123')}",
            f"dbname={os.getenv('DB_NAME', 'mcp')}",
        ])
        
        try:
            self.pool = AsyncConnectionPool(conninfo=conninfo, min_size=1, max_size=10, open=True)
            print("✅ Pool de conexiones asíncrono a PostgreSQL creado.")
        except Exception as e:
            print(f"❌ Error creando el pool de conexiones: {e}")
            raise
    
    async def disconnect(self):
        """Cierra el pool de conexiones."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            print("🔌 Pool de conexiones a PostgreSQL cerrado.")

    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        """Ejecuta una consulta (SELECT) y retorna una lista de diccionarios."""
        if not self.pool:
            raise RuntimeError("El pool de conexiones no está inicializado.")
            
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(query, args or ())
                return await cursor.fetchall()

    async def execute_command(self, command: str, *args) -> str:
        """Ejecuta un comando (INSERT, UPDATE, DELETE)."""
        if not self.pool:
            raise RuntimeError("El pool de conexiones no está inicializado.")

        async with self.pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(command, args or ())
                return cursor.statusmessage or "Comando ejecutado."

    async def create_table(self, table_name: str, columns: str) -> str:
        query = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})"
        return await self.execute_command(query)
    
    async def insert_record(self, table_name: str, data: Dict[str, Any]) -> str:
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        values = tuple(data.values())
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        return await self.execute_command(query, *values)
    
    async def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        query = """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = %s
        """
        return await self.execute_query(query, table_name)
    
    async def list_tables(self) -> List[str]:
        query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
        """
        result = await self.execute_query(query)
        return [row['table_name'] for row in result]


@dataclass
class AppContext:
    db: Database


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Gestiona el ciclo de vida de la aplicación con el pool de conexiones asíncrono."""
    db = Database()
    await db.connect()
    try:
        yield AppContext(db=db)
    finally:
        await db.disconnect()


mcp = FastMCP("Demo SERVER", lifespan=app_lifespan)


@mcp.tool(name="fetch_weather", description="Fetch current weather for a city")
async def fetch_weather(city: str) -> dict:
    """Fetch current weather for a city"""
    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
    
    if not WEATHER_API_KEY:
        return {"error": "WEATHER_API_KEY no está configurada"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}/today?unitGroup=metric&include=current&key={WEATHER_API_KEY}&contentType=json"
        )
    return resp.json()


@mcp.tool(name="list_tables", description="Listar todas las tablas en la base de datos")
async def list_tables() -> List[str]:
    """Listar todas las tablas disponibles en la base de datos"""
    try:
        ctx = mcp.get_context()
        db = ctx.request_context.lifespan_context.db
        tables = await db.list_tables()
        if not tables:
            return ["No hay tablas en la base de datos."]
        return tables
    except Exception as e:
        print(f"❌ Error al listar tablas: {e}")
        return [f"Error: {str(e)}"]


@mcp.tool(name="test_connection", description="Probar la conexión a la base de datos PostgreSQL")
async def test_connection() -> str:
    """Probar la conexión a PostgreSQL y mostrar información básica"""
    print("🔍 Probando conexión a PostgreSQL...")
    
    try:
        ctx = mcp.get_context()
        db = ctx.request_context.lifespan_context.db
        print("✅ Conexión exitosa!")
        
        result = await db.execute_query("SELECT version()")
        version = result[0]['version'] if result else "No se pudo obtener la versión"
        
        tables = await db.list_tables()
        
        return f"✅ Conexión exitosa!\nVersión: {version}\nTablas encontradas: {len(tables)}"
        
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return f"❌ Error de conexión: {str(e)}"


@mcp.tool(name="create_test_table", description="Crear una tabla de prueba para verificar la funcionalidad")
async def create_test_table() -> str:
    """Crear una tabla de prueba simple"""
    print("🏗️  Creando tabla de prueba...")
    
    try:
        ctx = mcp.get_context()
        db = ctx.request_context.lifespan_context.db
        
        await db.create_table(
            "test_table",
            "id SERIAL PRIMARY KEY, name VARCHAR(100), created_at TIMESTAMP DEFAULT NOW()"
        )
        
        await db.insert_record(
            "test_table",
            {"name": "Registro de prueba"}
        )
        
        tables = await db.list_tables()
        
        return f"✅ Tabla de prueba creada exitosamente!\nTablas en la base de datos: {tables}"
        
    except Exception as e:
        print(f"❌ Error creando tabla de prueba: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool(name="create_table", description="Crear una nueva tabla en la base de datos")
async def create_table(table_name: str, columns: str) -> str:
    """Crea una nueva tabla con las columnas especificadas."""
    try:
        ctx = mcp.get_context()
        db = ctx.request_context.lifespan_context.db
        return await db.create_table(table_name, columns)
    except Exception as e:
        return f"Error creando tabla: {str(e)}"


@mcp.tool(name="insert_record", description="Insertar un registro en una tabla")
async def insert_record(table_name: str, data: Dict[str, Any]) -> str:
    """Insertar un registro en la tabla especificada
    
    Args:
        table_name: Nombre de la tabla
        data: Diccionario con los datos a insertar
    """
    try:
        ctx = mcp.get_context()
        db = ctx.request_context.lifespan_context.db
        return await db.insert_record(table_name, data)
    except Exception as e:
        return f"Error insertando registro: {str(e)}"


@mcp.tool(name="execute_query", description="Ejecutar una consulta SQL personalizada")
async def execute_query(query: str) -> List[Dict[str, Any]]:
    """Ejecutar una consulta SQL personalizada
    
    Args:
        query: Consulta SQL a ejecutar
    """
    try:
        ctx = mcp.get_context()
        db = ctx.request_context.lifespan_context.db
        return await db.execute_query(query)
    except Exception as e:
        return [{"error": f"Error ejecutando consulta: {str(e)}"}]


@mcp.tool(name="get_table_info", description="Obtener información de la estructura de una tabla")
async def get_table_info(table_name: str) -> List[Dict[str, Any]]:
    """Obtener información detallada de la estructura de una tabla
    
    Args:
        table_name: Nombre de la tabla
    """
    try:
        ctx = mcp.get_context()
        db = ctx.request_context.lifespan_context.db
        return await db.get_table_info(table_name)
    except Exception as e:
        return [{"error": f"Error obteniendo información de tabla: {str(e)}"}]


