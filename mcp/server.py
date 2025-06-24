import os

import httpx

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Demo SERVER")


@mcp.tool(name="fetch_weather", description="Fetch current weather for a city")
async def fetch_weather(city: str) -> dict:
    """Fetch current weather for a city"""

    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}/today?unitGroup=metric&include=current&key={WEATHER_API_KEY}&contentType=json"
        )

    data = resp.json()

    return data


if __name__ == "__main__":
    mcp.run(transport="stdio")
