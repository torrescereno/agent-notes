import asyncio
import os

from dotenv import load_dotenv
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI

from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv(override=True)

model = ChatOpenAI(model="deepseek-chat", base_url="https://api.deepseek.com")

server_params = StdioServerParameters(
    command="uv",
    args=["run", "server_weather.py"],
    env={"WEATHER_API_KEY": os.environ.get("WEATHER_API_KEY")},
)


async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await load_mcp_tools(session)

            agent = create_react_agent(model, tools)

            print(agent.get_graph(xray=True).draw_ascii())

            agent_response = await agent.ainvoke(
                {"messages": "dime el clima actual de tokyo"}
            )

            print(agent_response)


if __name__ == "__main__":
    asyncio.run(main())
