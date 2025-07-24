import os

import httpx
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP

load_dotenv(override=True)

# Aplicaciones conversacionales (chatbots, asistentes) que necesitan memoria entre interacciones
mcp = FastMCP("stateful server")

# Procesamiento de requests independientes con streaming
# mcp = FastMCP("StatelessServer", stateless_http=True)

# APIs REST tradicionales sin streaming
# mcp = FastMCP("StatelessServer", stateless_http=True, json_response=True)


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
    mcp.run(transport="streamable-http")
