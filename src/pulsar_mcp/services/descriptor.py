import json 
import asyncio

from openai import AsyncOpenAI
from openai.types.chat import ParsedChatCompletion
from typing import List, Dict, Optional, Any, Tuple, Self  

from mcp import StdioServerParameters, ClientSession, stdio_client
from mcp.types import ListToolsResult

from ..types import McpStartupConfig, McpServerDescription, DescribeMcpServerResponse
from ..log import logger

class DescriptorService:
    def __init__(self, openai_api_key:str, openai_model_name:str):
        self.api_key = openai_api_key
        self.openai_model_name = openai_model_name
    
    async def __aenter__(self) -> Self:
        self.client = AsyncOpenAI(api_key=self.api_key)
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            logger.error(f"Exception in EmbeddingService context manager: {exc_value}")
            logger.exception(traceback)
    

    async def tools_to_string(self, tools_results:ListToolsResult) -> str:
        tools = []
        for tool in tools_results.tools:
            tools.append(
                json.dumps(
                    {
                        'type': 'tool',
                        'name': tool.name,
                        'description': tool.description,
                        'inputSchema': tool.inputSchema
                    }
                )
            )
        
        return "\n###\n".join(tools) if tools else "No tools available."
    
    async def enhance_query_with_llm(self, query: str) -> str:
        prompt = f"""You are a query enhancement system for semantic tool search.
        Each tool is a function with specific input and output types, a defined process, and a clear purpose.
        Transform this user query into a detailed technical description that will match tool documentation better.
        Example of tools: web_search, file reader, audio processing etc...
        Our index contains several tools(thousands) with various capabilities.

        User Query: "{query}"

        Instructions:
        1. Identify the implicit conversion or transformation needed
        2. Make explicit: input type, output type, process, and purpose
        3. Add relevant technical terms and synonyms
        4. Expand to 60-100 words
        5. DO NOT mention specific tools or brands
        6. Focus on capabilities and processes

        Enhanced Query (single paragraph, no explanations):"""
        completion_response = await self.client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt}
            ],
            model=self.openai_model_name,
            max_tokens=384
        )
        enhanced = completion_response.choices[0].message.content.strip()
        
        return enhanced

    async def enhance_tool(self, tool_name: str, tool_description: str, tool_schema: Dict[str, Any], server_name: str) -> str:
        system_prompt = """
        Generate a comprehensive tool description for semantic search and retrieval.    
        Write a detailed paragraph that explains:
            - What the tool does and its primary purpose
            - When and why to use this tool
            - Key parameters and their significance
            - Expected outcomes or return values
            - Practical use cases and scenarios
        Be specific, clear, and include relevant keywords for search matching."""
        user_prompt = f"""Server: {server_name}
        Tool Name: {tool_name}
        Description: {tool_description}
        Schema: {json.dumps(tool_schema, indent=2)}
        Generate the enhanced description.
        """

        completion_response = await self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=self.openai_model_name,
            max_tokens=512
        )
        
        return completion_response.choices[0].message.content
    
    async def describe_mcp_server(self, server_name:str, mcp_startup_config:McpStartupConfig, timeout:int=50) -> Optional[DescribeMcpServerResponse]:
        try:
            server_parameters = StdioServerParameters(
                command=mcp_startup_config.command,
                args=mcp_startup_config.args,
                env=mcp_startup_config.env
            )
        except Exception as e:
            logger.error(f"Error creating MCP server parameters: {e}")
            return
         
        try:
            async with asyncio.timeout(delay=timeout):
                async with stdio_client(server=server_parameters) as transport:
                    read, write = transport 
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        logger.info("Initialized MCP session")
                        tools_result = await session.list_tools()
                        logger.info(f"Retrieved {len(tools_result.tools)} tools from MCP server")


            mcp_description = await self.generate_description(
                server_name=server_name,
                tools_result=tools_result
            )
            return mcp_description
        except asyncio.TimeoutError:
            logger.error("Timeout while trying to describe MCP server.") 
        except Exception as e:
            logger.error(f"Error describing MCP server: {e}")
        
        return 
    
    async def generate_description(self, server_name:str, tools_result:ListToolsResult) -> DescribeMcpServerResponse:
        tools = await self.tools_to_string(tools_result)

        system_prompt = """
        Generate a concise MCP server description with:
        - title: Clear, specific sentence that describes the server
        - summary: detailed paragraph summarizing the server's purpose and functionality
        - capabilities: List of key features. do not exceed 10 items
        - limitations: 3-5 notable constraints
        Be accurate and direct.
        """

        completion_response:ParsedChatCompletion = await self.client.chat.completions.parse(
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": f"Generate a comprehensive description of the server {server_name} based on the following information."},
                        {"type": "text", "text": tools}
                    ]
                }
            ],
            model=self.openai_model_name,
            max_tokens=2048,
            response_format=McpServerDescription
        )

        server_descripton:McpServerDescription = completion_response.choices[0].message.parsed
        return DescribeMcpServerResponse(
            server_name=server_name,
            server_description=server_descripton,
            tools=tools_result
        )
   



