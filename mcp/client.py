import asyncio
import os
from typing import AsyncGenerator
from uuid import uuid4

from dotenv import load_dotenv
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI

from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState, StateGraph
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


async def stream_graph_response(
    input: MessagesState, graph: StateGraph, config: dict = {}
) -> AsyncGenerator[str, None]:
    async for message_chunk, _ in graph.astream(
        input=input, stream_mode="messages", config=config
    ):
        if isinstance(message_chunk, AIMessageChunk):
            if message_chunk.response_metadata:
                finish_reason = message_chunk.response_metadata.get("finish_reason", "")
                if finish_reason == "tool_calls":
                    yield "\n\n"

            if message_chunk.tool_call_chunks:
                tool_chunk = message_chunk.tool_call_chunks[0]

                tool_name = tool_chunk.get("name", "")
                args = tool_chunk.get("args", "")

                if tool_name:
                    tool_call_str = f"\n\n< TOOL CALL: {tool_name} >\n\n"
                if args:
                    tool_call_str = args

                yield tool_call_str
            else:
                yield message_chunk.content
            continue


async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await load_mcp_tools(session)

            memory = MemorySaver()

            agent = create_react_agent(model, tools, checkpointer=memory)

            print(agent.get_graph(xray=True).draw_ascii())

            thread = {"configurable": {"thread_id": uuid4()}}

            while True:
                user_input = input("\n\nUSER: ")

                if user_input in ["quit", "exit"]:
                    break

                print("\n ----  USER  ---- \n\n", user_input)
                print("\n ----  ASSISTANT  ---- \n\n")

                async for response in stream_graph_response(
                    input=MessagesState(messages=[HumanMessage(content=user_input)]),
                    graph=agent,
                    config=thread,
                ):
                    print(response, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
