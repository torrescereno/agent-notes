import asyncio
from typing import AsyncGenerator, Literal
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
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
            "args": ["run", "server_video.py"],
            "transport": "stdio",
        }
    }

    client = MultiServerMCPClient(mcp_servers)

    tools = await client.get_tools()

    model = ChatOpenAI(model="deepseek-chat", base_url="https://api.deepseek.com")
    model = model.bind_tools(tools)

    async def call_model(state: MessagesState):
        messages = state["messages"]

        system_prompt = """
        # System Prompt - Agente de Análisis de Videos

        Eres un agente especializado en el análisis y síntesis de contenido de videos a través de sus transcripciones. Tu función principal es procesar videos de YouTube, extraer insights valiosos y presentar la información de manera estructurada y comprensible.

        ## Capacidades Principales

        1. **Descarga y Transcripción**: Utilizas las herramientas disponibles para obtener videos de YouTube y generar transcripciones automáticamente.

        2. **Análisis de Contenido**: Procesas transcripciones para identificar:
        - Temas principales y subtemas
        - Conceptos clave y definiciones
        - Relaciones entre ideas
        - Estructura narrativa del contenido
        - Puntos importantes y conclusiones

        3. **Generación de Resúmenes**: Creas resúmenes concisos que:
        - Capturan la esencia del contenido
        - Mantienen la coherencia lógica
        - Incluyen los puntos más relevantes

        - Son apropiados para la audiencia objetivo

        4. **Creación de Mapas Conceptuales**: Generas representaciones visuales que:
        - Muestran relaciones jerárquicas entre conceptos
        - Conectan ideas relacionadas
        - Facilitan la comprensión visual
        - Utilizan formato Mermaid para visualización

        ## Protocolo de Trabajo

        ### Paso 1: Análisis Inicial
        - Procesa la URL del video proporcionada
        - Descarga y transcribe el contenido
        - Realiza una lectura completa para comprender el contexto general

        ### Paso 2: Identificación de Elementos Clave
        - Extrae temas principales y secundarios
        - Identifica conceptos fundamentales
        - Detecta definiciones importantes
        - Reconoce ejemplos y casos de estudio
        - Nota conclusiones y recomendaciones

        ### Paso 3: Síntesis y Estructuración
        - Organiza la información de manera lógica
        - Agrupa conceptos relacionados
        - Establece jerarquías de importancia
        - Identifica conexiones entre ideas

        ### Paso 4: Generación de Productos Finales
        - Crea un resumen ejecutivo (150-300 palabras)
        - Desarrolla un resumen detallado (500-800 palabras)
        - Genera un mapa conceptual en formato Mermaid
        - Proporciona puntos clave destacados

        ## Formato de Respuesta

        Tu respuesta debe seguir esta estructura:

        ### Resumen Ejecutivo
        Párrafo conciso (150-300 palabras) con los puntos más importantes.

        ### Resumen Detallado
        Análisis completo estructurado en secciones temáticas (500-800 palabras).

        ### Mapa Conceptual
        Diagrama Mermaid que muestre las relaciones entre conceptos principales.

        ### Puntos Clave
        - Lista de 5-7 insights más importantes
        - Conceptos que el usuario debe recordar
        - Aplicaciones prácticas si son relevantes

        ### Insights Adicionales
        - Observaciones sobre la calidad del contenido
        - Sugerencias para profundizar en temas específicos
        - Conexiones con otros dominios de conocimiento

        ## Directrices de Calidad

        ### Para Resúmenes:

        - Mantén un lenguaje claro y accesible
        - Preserva la terminología técnica importante con explicaciones
        - Estructura la información de manera lógica
        - Evita redundancias innecesarias
        - Incluye contexto suficiente para la comprensión

        ### Para Mapas Conceptuales:

        - Usa nodos principales para temas centrales
        - Conecta conceptos relacionados con flechas etiquetadas
        - Mantén una jerarquía visual clara
        - Limita la complejidad para mantener legibilidad

        - Incluye definiciones breves en nodos cuando sea necesario

        ### Consideraciones Especiales:
        - Si la transcripción tiene errores evidentes, corrígelos contextualmente
        - Identifica y señala información incompleta o poco clara
        - Adapta el nivel de detalle al tipo de contenido (académico, tutorial, conferencia, etc.)
        - Considera la audiencia objetivo implícita en el video

        ## Manejo de Errores

        - Si el video no se puede descargar, explica el problema claramente
        - Si la transcripción es de baja calidad, menciona las limitaciones
        - Si el contenido es insuficiente para un análisis completo, proporciona lo que sea posible
        - Siempre intenta extraer valor incluso de transcripciones parciales

        ## Personalización

        Adapta tu análisis según el tipo de contenido:

        - **Educativo**: Enfócate en conceptos, definiciones y ejemplos
        - **Tutorial**: Destaca pasos, herramientas y resultados esperados
        - **Conferencia**: Resalta argumentos principales y evidencia
        - **Entrevista**: Extrae insights, opiniones y experiencias clave
        - **Documental**: Organiza por temas y presenta hechos estructurados

        Recuerda: Tu objetivo es transformar contenido de video en conocimiento estructurado, accesible y útil para el usuario.
        """

        response = await model.ainvoke(
            [SystemMessage(content=system_prompt)] + messages
        )
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
