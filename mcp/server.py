import os

import httpx

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Demo SERVER")


@mcp.tool(name="Weather Fetcher")
async def fetch_weather(city: str) -> dict:
    """Fetch current weather for a city"""

    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

    resp = httpx.get(
        f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}/today?unitGroup=metric&include=current&key={WEATHER_API_KEY}&contentType=json"
    )

    return resp.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
