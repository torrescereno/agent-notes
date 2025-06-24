import os
from typing import List, Dict, Any, Optional
import httpx
import asyncpg
from mcp.server.fastmcp import FastMCP
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass


class Database:
    """Clase para manejar la conexión a PostgreSQL"""
    
    def __init__(self, connection: asyncpg.Connection):
        self.connection = connection
    
    @classmethod
    async def connect(cls) -> 'Database':
        """Crear una nueva conexión a la base de datos"""
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "5432"))
        user = os.getenv("DB_USER", "admin")
        password = os.getenv("DB_PASSWORD", "admin123")
        database = os.getenv("DB_NAME", "mcp")
        
        try:
            connection = await asyncpg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database
            )
            print(f"✅ Conexión exitosa a PostgreSQL en {host}:{port}/{database}")
            return cls(connection)
        except Exception as e:
            print(f"❌ Error conectando a PostgreSQL: {e}")
            raise
    
    async def disconnect(self):
        """Cerrar la conexión a la base de datos"""
        if self.connection:
            await self.connection.close()
            print("🔌 Conexión a PostgreSQL cerrada")
    
    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        """Ejecutar una consulta SQL y retornar resultados como lista de diccionarios"""
        try:
            rows = await self.connection.fetch(query, *args)
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"❌ Error ejecutando consulta: {e}")
            raise
    
    async def execute_command(self, command: str, *args) -> str:
        """Ejecutar un comando SQL (INSERT, UPDATE, DELETE)"""
        try:
            result = await self.connection.execute(command, *args)
            return f"Comando ejecutado exitosamente: {result}"
        except Exception as e:
            print(f"❌ Error ejecutando comando: {e}")
            raise
    
    async def create_table(self, table_name: str, columns: str) -> str:
        """Crear una nueva tabla"""
        query = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})"
        return await self.execute_command(query)
    
    async def insert_record(self, table_name: str, data: Dict[str, Any]) -> str:
        """Insertar un registro en una tabla"""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(f'${i+1}' for i in range(len(data)))
        values = list(data.values())
        
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        return await self.execute_command(query, *values)
    
    async def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Obtener información de la estructura de una tabla"""
        query = """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = $1
        ORDER BY ordinal_position
        """
        return await self.execute_query(query, table_name)
    
    async def list_tables(self) -> List[str]:
        """Listar todas las tablas en la base de datos"""
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
    """Manage application lifecycle with type-safe context"""
    db = await Database.connect()
    try:
        yield AppContext(db=db)
    finally:
        await db.disconnect()


# Pass lifespan to server
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

    data = resp.json()
    return data


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


@mcp.tool(name="list_tables", description="Listar todas las tablas en la base de datos")
async def list_tables() -> List[str]:
    """Listar todas las tablas disponibles en la base de datos"""
    print("🔍 Iniciando list_tables...")
    
    try:
        ctx = mcp.get_context()
        db = ctx.request_context.lifespan_context.db
        print("📋 Ejecutando consulta para listar tablas...")
        tables = await db.list_tables()
        print(f"✅ Tablas encontradas: {tables}")
        
        if not tables:
            print("ℹ️  No se encontraron tablas en la base de datos")
            return ["No hay tablas en la base de datos"]
        
        return tables
    except Exception as e:
        print(f"❌ Error al listar tablas: {e}")
        return [f"Error al listar tablas: {str(e)}"]


@mcp.tool(name="create_table", description="Crear una nueva tabla en la base de datos")
async def create_table(table_name: str, columns: str) -> str:
    """Crear una nueva tabla con las columnas especificadas
    
    Args:
        table_name: Nombre de la tabla
        columns: Definición de columnas (ej: 'id SERIAL PRIMARY KEY, name VARCHAR(100), created_at TIMESTAMP DEFAULT NOW()')
    """
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


if __name__ == "__main__":
    mcp.run(transport="stdio")
