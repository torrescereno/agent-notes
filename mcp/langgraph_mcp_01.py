import asyncio
import os
from typing import AsyncGenerator, Literal
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode

load_dotenv(override=True)


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
    mcp_servers = {
        "weather": {
            "command": "uv",
            "args": ["run", "server_weather.py"],
            "env": {"WEATHER_API_KEY": os.environ.get("WEATHER_API_KEY")},
            "transport": "stdio",
        }
    }

    client = MultiServerMCPClient(mcp_servers)

    tools = await client.get_tools()

    model = ChatOpenAI(model="deepseek-chat", base_url="https://api.deepseek.com")
    model = model.bind_tools(tools)

    async def call_model(state: MessagesState):
        messages = state["messages"]
        response = await model.ainvoke(messages)
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
        messages = state["messages"]
        last_message = messages[-1]

        if last_message.tool_calls:
            return "tools"

        return END

    tool_node = ToolNode(tools=tools)

    workflow = StateGraph(MessagesState)

    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")
    workflow.add_edge("agent", END)

    memory = MemorySaver()

    graph = workflow.compile(checkpointer=memory)

    print(graph.get_graph(xray=True).draw_ascii())

    thread = {"configurable": {"thread_id": uuid4()}}

    while True:
        user_input = input("\n\nUSER: ")
        if user_input in ["quit", "exit"]:
            break

        print("\n ----  USER  ---- \n\n", user_input)
        print("\n ----  ASSISTANT  ---- \n\n")

        async for response in stream_graph_response(
            input=MessagesState(messages=[HumanMessage(content=user_input)]),
            graph=graph,
            config=thread,
        ):
            print(response, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
