from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, List

import psycopg2
import psycopg2.extensions
from psycopg2.extras import DictCursor as dict_row

from mcp.server.fastmcp import Context, FastMCP


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

    def execute_query(self, query_str: str) -> List[Dict[str, Any]]:
        with self.conn.cursor(cursor_factory=dict_row) as cur:
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

    def execute_non_query(self, query_str: str) -> Dict[str, Any]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(query_str)

                self.conn.commit()

                return {"success": True, "message": "Consulta ejecutada correctamente"}

        except Exception as e:
            self.conn.rollback()
            return {"success": False, "error": str(e)}

    def list_tables(self) -> List[str]:
        query = """

        SELECT table_name
        FROM information_schema.tables

        WHERE table_schema = 'public'
        ORDER BY table_name
        """

        result = self.execute_query(query_str=str(query))

        return [row["table_name"] for row in result["rows"]]

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        query = f"""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns


        WHERE table_name = '{table_name}'
        """

        return self.execute_query(query)

    def create_table(self, table_name: str, columns: str) -> Dict[str, Any]:
        query = f"CREATE TABLE {table_name} ({columns})"

        return self.execute_non_query(query)

    def insert_record(
        self, table_name: str, columns: str, values: str
    ) -> Dict[str, Any]:
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({values})"

        return self.execute_non_query(query)


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


@mcp.tool(name="list_tables", description="Listar todas las tablas en la base de datos")
async def list_tables(ctx: Context) -> List[str]:
    """
    Obtiene una lista de todas las tablas disponibles en la base de datos PostgreSQL.

    Esta función consulta el esquema 'public' de la base de datos para obtener
    los nombres de todas las tablas existentes, ordenadas alfabéticamente.

    Returns:
        List[str]: Lista con los nombres de las tablas en la base de datos.
                  Si no hay tablas, retorna una lista con un mensaje indicativo.
                  En caso de error, retorna una lista con el mensaje de error.

    """
    try:
        context_app: AppContext = ctx.request_context.lifespan_context

        tables = context_app.db.list_tables()

        if not tables:
            return ["No hay tablas en la base de datos."]

        return tables

    except Exception as e:
        print(f"❌ Error al listar tablas: {e}")
        return [f"Error: {str(e)}"]


@mcp.tool(name="execute_query", description="Ejecuta una consulta SELECT a PostgreSQL")
async def execute_query(query: str, ctx: Context) -> dict:
    """
    Ejecuta una consulta SELECT en la base de datos PostgreSQL.


    Esta función permite ejecutar consultas de lectura (SELECT) de forma segura,
    limitando los resultados a 50 filas para evitar sobrecarga de memoria.


    Args:
        query (str): Consulta SQL SELECT a ejecutar. Debe comenzar con 'SELECT'
                    (no distingue mayúsculas/minúsculas).

    Returns:
        dict: Diccionario con la estructura:
              - 'columns': Lista con los nombres de las columnas
              - 'rows': Lista de diccionarios, cada uno representa una fila
              - 'error': Mensaje de error si ocurre algún problema


    Raises:
        Retorna un diccionario con 'error' si:
        - La consulta no es un SELECT
        - Ocurre un error durante la ejecución

    """
    try:
        context_app: AppContext = ctx.request_context.lifespan_context

        if not query.strip().lower().startswith("select"):
            return {"error": "Solo se permiten consultas SELECT por seguridad."}

        return context_app.db.execute_query(query)

    except Exception as e:
        return {"error": str(e)}


@mcp.tool(
    name="get_table_info",
    description="Obtener información de la estructura de una tabla",
)
async def get_table_info(table_name: str, ctx: Context) -> List[Dict[str, Any]]:
    """
    Obtiene información detallada sobre la estructura de una tabla específica.

    Esta función consulta el esquema de información de PostgreSQL para obtener
    detalles sobre las columnas de una tabla, incluyendo tipos de datos,
    restricciones de nulidad y valores por defecto.

    Args:
        table_name (str): Nombre de la tabla de la cual obtener información.

    Returns:
        List[Dict[str, Any]]: Lista de diccionarios, cada uno representa una columna con:
                             - 'column_name': Nombre de la columna
                             - 'data_type': Tipo de dato PostgreSQL
                             - 'is_nullable': Si permite valores nulos ('YES'/'NO')
                             - 'column_default': Valor por defecto de la columna
                             En caso de error, retorna una lista con un diccionario de error.
    """
    try:
        context_app: AppContext = ctx.request_context.lifespan_context

        return context_app.db.get_table_info(table_name)

    except Exception as e:
        return [{"error": f"Error obteniendo información de tabla: {str(e)}"}]


@mcp.tool(
    name="create_table",
    description="Crear una nueva tabla en la base de datos",
)
async def create_table(table_name: str, columns: str, ctx: Context) -> Dict[str, Any]:
    """
    Crea una nueva tabla en la base de datos PostgreSQL.

    Esta función ejecuta una sentencia CREATE TABLE con las especificaciones
    de columnas proporcionadas. La operación se realiza dentro de una transacción
    que se revierte automáticamente en caso de error.

    Args:
        table_name (str): Nombre de la nueva tabla a crear.
        columns (str): Definición de las columnas en formato SQL estándar.

                      Ejemplo: "id SERIAL PRIMARY KEY, nombre VARCHAR(100) NOT NULL, edad INTEGER"


    Returns:

        Dict[str, Any]: Diccionario con el resultado de la operación:
                       - 'success': True si la operación fue exitosa, False en caso contrario

                       - 'message': Mensaje descriptivo del resultado (si exitoso)
                       - 'error': Descripción del error (si falló)

    Note:
        - La tabla se crea en el esquema 'public' por defecto
        - Si la tabla ya existe, retornará un error
        - Todas las restricciones y tipos de datos deben ser válidos en PostgreSQL
    """
    try:
        context_app: AppContext = ctx.request_context.lifespan_context

        result = context_app.db.create_table(table_name, columns)

        if result["success"]:
            return {
                "success": True,
                "message": f"Tabla '{table_name}' creada correctamente",
            }
        else:
            return {"success": False, "error": result["error"]}
    except Exception as e:
        return {"success": False, "error": f"Error creando tabla: {str(e)}"}


@mcp.tool(
    name="insert_record",
    description="Insertar un registro en una tabla",
)
async def insert_record(
    table_name: str, columns: str, values: str, ctx: Context
) -> Dict[str, Any]:
    """
    Inserta un nuevo registro en una tabla existente de la base de datos.

    Esta función ejecuta una sentencia INSERT INTO con los valores especificados.
    La operación se realiza dentro de una transacción que se revierte automáticamente
    en caso de error, manteniendo la integridad de los datos.

    Args:
        table_name (str): Nombre de la tabla donde insertar el registro.
        columns (str): Nombres de las columnas separadas por comas.
                      Ejemplo: "nombre, edad, email"
        values (str): Valores a insertar en el mismo orden que las columnas.
                     Los strings deben estar entre comillas simples.
                     Ejemplo: "'Nombre', 30, 'nombre@email.com'"

    Returns:
        Dict[str, Any]: Diccionario con el resultado de la operación:
                       - 'success': True si la inserción fue exitosa, False en caso contrario
                       - 'message': Mensaje descriptivo del resultado (si exitoso)
                       - 'error': Descripción del error (si falló)

    Note:
        - La tabla debe existir previamente
        - Los tipos de datos deben coincidir con la definición de la tabla
        - Las restricciones de la tabla (NOT NULL, UNIQUE, etc.) se aplicarán
        - Los valores de texto deben estar entre comillas simples
        - Para valores nulos, usar la palabra NULL sin comillas
    """
    try:
        context_app: AppContext = ctx.request_context.lifespan_context
        result = context_app.db.insert_record(table_name, columns, values)

        if result["success"]:
            return {
                "success": True,
                "message": f"Registro insertado correctamente en '{table_name}'",
            }
        else:
            return {"success": False, "error": result["error"]}

    except Exception as e:
        return {"success": False, "error": f"Error insertando registro: {str(e)}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
