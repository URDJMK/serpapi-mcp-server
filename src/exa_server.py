from typing import Annotated, Optional, Dict, Any, List, Union
from mcp.server import Server
from mcp.shared.exceptions import McpError
from mcp.server.stdio import stdio_server
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
    Tool,
    ErrorData,
    INVALID_PARAMS,
    INTERNAL_ERROR,
    METHOD_NOT_FOUND,
)
from pydantic import BaseModel, Field
import aiohttp
import asyncio
import os
from datetime import datetime
import json

REQUEST_CANCELLED = "request_cancelled"

# Pydantic models for request/response
class SearchArgs(BaseModel):
    """Arguments for Exa search."""
    query: Annotated[str, Field(description="Search query")]
    num_results: Annotated[
        int,
        Field(
            default=10,
            description="Number of results to return",
            gt=0,
            lt=50,
        ),
    ]
    include_domains: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="List of domains to specifically include in search results",
        ),
    ] = None
    exclude_domains: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="List of domains to specifically exclude from search results",
        ),
    ] = None

# New model for GetContents endpoint
class GetContentsArgs(BaseModel):
    """Arguments for Exa getContents."""
    urls: Annotated[List[str], Field(description="List of URLs to get contents for")]
    text: Annotated[
        Union[bool, Dict[str, Any]],
        Field(
            default=True,
            description="Whether to include text content. Can be a boolean or a configuration object.",
        ),
    ] = True
    highlights: Annotated[
        Union[bool, Dict[str, Any], None],
        Field(
            default=None,
            description="Whether to include highlights. Can be a boolean or a configuration object.",
        ),
    ] = None
    summary: Annotated[
        Union[bool, Dict[str, Any], None],
        Field(
            default=None,
            description="Whether to include summary. Can be a boolean or a configuration object.",
        ),
    ] = None
    subpages: Annotated[
        int,
        Field(
            default=0,
            description="Number of subpages to crawl",
            ge=0,
        ),
    ] = 0
    subpage_target: Annotated[
        str | None,
        Field(
            default=None,
            description="Target for subpage crawling (e.g., 'references')",
        ),
    ] = None
    extras: Annotated[
        Dict[str, Any] | None,
        Field(
            default=None,
            description="Extra options for content retrieval",
        ),
    ] = None

# New model for FindSimilar endpoint
class FindSimilarArgs(BaseModel):
    """Arguments for Exa findSimilar."""
    url: Annotated[str, Field(description="URL to find similar content for")]
    num_results: Annotated[
        int,
        Field(
            default=10,
            description="Number of results to return",
            gt=0,
            lt=50,
        ),
    ] = 10
    text: Annotated[
        Union[bool, Dict[str, Any]],
        Field(
            default=True,
            description="Whether to include text content. Can be a boolean or a configuration object.",
        ),
    ] = True
    highlights: Annotated[
        Union[bool, Dict[str, Any], None],
        Field(
            default=None,
            description="Whether to include highlights. Can be a boolean or a configuration object.",
        ),
    ] = None
    summary: Annotated[
        Union[bool, Dict[str, Any], None],
        Field(
            default=None,
            description="Whether to include summary. Can be a boolean or a configuration object.",
        ),
    ] = None

class ExaSearchResult(BaseModel):
    """Single search result from Exa."""
    score: float | None = None
    title: str
    id: str
    url: str
    published_date: Annotated[str, Field(alias="publishedDate")]
    author: str | None = None
    text: str | None = None
    image: str | None = None
    favicon: str | None = None

class SearchResponseData(BaseModel):
    """The data field of the Exa search response."""
    requestId: str
    autopromptString: str
    resolvedSearchType: str
    results: list[ExaSearchResult]

class SearchResponse(BaseModel):
    """Complete response from Exa search."""
    data: SearchResponseData

    # Add property aliases for consistent naming in our code
    @property
    def request_id(self) -> str:
        return self.data.requestId

    @property
    def autoprompt_string(self) -> str:
        return self.data.autopromptString

    @property
    def resolved_search_type(self) -> str:
        return self.data.resolvedSearchType

    @property
    def results(self) -> list[ExaSearchResult]:
        return self.data.results

# New model for GetContents response
class ContentResult(BaseModel):
    """Content result for a single URL."""
    url: str
    title: str | None = None
    text: str | None = None
    highlights: List[str] | None = None
    summary: str | None = None
    favicon: str | None = None
    image: str | None = None
    published_date: str | None = None
    author: str | None = None
    error: str | None = None

class GetContentsResponse(BaseModel):
    """Response from Exa getContents endpoint."""
    results: List[ContentResult]

# New model for FindSimilar response
class FindSimilarResponse(BaseModel):
    """Response from Exa findSimilar endpoint."""
    results: List[ExaSearchResult]

class CachedSearch:
    """Store recent searches."""
    def __init__(self, query: str, response: SearchResponse):
        self.query = query
        self.response = response
        self.timestamp = datetime.now().isoformat()

class ExaServer:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.exa.ai"
        self.endpoints = {
            "SEARCH": "/search",
            "CONTENTS": "/contents",
            "FIND_SIMILAR": "/findSimilar"
        }
        self.default_num_results = 10
        self.max_cached_searches = 5
        self.recent_searches: list[CachedSearch] = []
        self.timeout = aiohttp.ClientTimeout(total=30)

    async def search(self, args: SearchArgs) -> SearchResponse:
        """Perform search request to Exa API matching TypeScript implementation."""
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "x-api-key": self.api_key
            }
            
            # Match the TypeScript ExaSearchRequest structure
            search_request = {
                "query": args.query,
                "type": "auto",
                "numResults": args.num_results or self.default_num_results,
                "contents": {
                    "text": True
                }
            }

            try:
                async with session.post(
                    f"{self.base_url}{self.endpoints['SEARCH']}",
                    headers=headers,
                    json=search_request
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"Exa API error: {error_text}"
                        ))
                    
                    data = await response.json()
                    
                    # Wrap the response in a data field if it's not already present
                    if 'data' not in data:
                        data = {'data': data}
                    
                    try:
                        search_response = SearchResponse(**data)
                    except ValueError as e:
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"Invalid response format from Exa API: {str(e)}"
                        ))
                    
                    # Cache the successful search
                    self.recent_searches.insert(0, CachedSearch(args.query, search_response))
                    if len(self.recent_searches) > self.max_cached_searches:
                        self.recent_searches.pop()
                        
                    return search_response
                    
            except aiohttp.ClientError as e:
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"Network error while calling Exa API: {str(e)}"
                ))
            except asyncio.TimeoutError:
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message="Exa API request timed out"
                ))

    # New method for getContents endpoint
    async def get_contents(self, args: GetContentsArgs) -> GetContentsResponse:
        """Get contents for a list of URLs from Exa API."""
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "x-api-key": self.api_key
            }
            
            # Prepare request payload
            request_payload = {
                "urls": args.urls,
                "text": args.text,
            }
            
            # Add optional parameters if provided
            if args.highlights is not None:
                request_payload["highlights"] = args.highlights
            if args.summary is not None:
                request_payload["summary"] = args.summary
            if args.subpages > 0:
                request_payload["subpages"] = args.subpages
            if args.subpage_target:
                request_payload["subpageTarget"] = args.subpage_target
            if args.extras:
                request_payload["extras"] = args.extras
                
            try:
                async with session.post(
                    f"{self.base_url}{self.endpoints['CONTENTS']}",
                    headers=headers,
                    json=request_payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"Exa API error: {error_text}"
                        ))
                    
                    data = await response.json()
                    
                    try:
                        contents_response = GetContentsResponse(**data)
                        return contents_response
                    except ValueError as e:
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"Invalid response format from Exa API: {str(e)}"
                        ))
                        
            except aiohttp.ClientError as e:
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"Network error while calling Exa API: {str(e)}"
                ))
            except asyncio.TimeoutError:
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message="Exa API request timed out"
                ))

    # New method for findSimilar endpoint
    async def find_similar(self, args: FindSimilarArgs) -> FindSimilarResponse:
        """Find similar content to a URL from Exa API."""
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "x-api-key": self.api_key
            }
            
            # Prepare request payload
            request_payload = {
                "url": args.url,
                "numResults": args.num_results,
                "text": args.text,
            }
            
            # Add optional parameters if provided
            if args.highlights is not None:
                request_payload["highlights"] = args.highlights
            if args.summary is not None:
                request_payload["summary"] = args.summary
                
            try:
                async with session.post(
                    f"{self.base_url}{self.endpoints['FIND_SIMILAR']}",
                    headers=headers,
                    json=request_payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"Exa API error: {error_text}"
                        ))
                    
                    data = await response.json()
                    
                    try:
                        similar_response = FindSimilarResponse(**data)
                        return similar_response
                    except ValueError as e:
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"Invalid response format from Exa API: {str(e)}"
                        ))
                        
            except aiohttp.ClientError as e:
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"Network error while calling Exa API: {str(e)}"
                ))
            except asyncio.TimeoutError:
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message="Exa API request timed out"
                ))

    # Format methods for the new endpoints
    def format_contents_results(self, response: GetContentsResponse) -> str:
        """Format contents results into JSON string."""
        output_dict = {
            "contents_results": [
                {
                    "url": result.url,
                    "title": result.title,
                    "text": result.text if result.text else "",
                    "highlights": result.highlights if result.highlights else [],
                    "summary": result.summary if result.summary else "",
                    "published_date": result.published_date,
                    "author": result.author,
                    "error": result.error
                }
                for result in response.results
            ]
        }
        
        return json.dumps(output_dict, separators=(',', ':'))
        
    def format_similar_results(self, response: FindSimilarResponse) -> str:
        """Format similar results into JSON string."""
        output_dict = {
            "similar_results": [
                {
                    "title": result.title,
                    "url": result.url,
                    "content": result.text if result.text else "",
                    "published_date": result.published_date,
                    "author": result.author,
                    "score": result.score
                }
                for result in response.results
            ]
        }
        
        return json.dumps(output_dict, separators=(',', ':'))

    def format_results(self, response: SearchResponse) -> str:
        """Format search results into JSON string matching Tavily format."""
        output_dict = {
            "detailed_results": [
                {
                    "title": result.title,
                    "url": result.url,
                    "content": result.text if result.text else "",
                    "published_date": result.published_date,
                    "author": result.author
                }
                for result in response.results
            ]
        }
        
        return json.dumps(output_dict, separators=(',', ':'))

async def serve(api_key: str) -> None:
    """Run the Exa MCP server."""
    server = Server("mcp-exa")
    exa_server = ExaServer(api_key)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="exa_search",
                description="Search the web using Exa's AI-powered search engine. Returns relevant results with extracted content.",
                inputSchema=SearchArgs.model_json_schema(),
            ),
            Tool(
                name="exa_getcontents",
                description="Get the full contents of specific URLs. Retrieves text, highlights, summaries, and metadata from web pages.",
                inputSchema=GetContentsArgs.model_json_schema(),
            ),
            Tool(
                name="exa_findsimilar",
                description="Find web pages similar to a given URL. Useful for discovering related content and expanding research.",
                inputSchema=FindSimilarArgs.model_json_schema(),
            ),
        ]

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        return [
            Prompt(
                name="exa_search",
                description="Search the web using Exa's AI-powered search engine",
                arguments=[
                    PromptArgument(
                        name="query",
                        description="The search query",
                        required=True,
                    ),
                    PromptArgument(
                        name="num_results",
                        description="Number of results to return (default: 10)",
                        required=False,
                    ),
                ],
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            if name == "exa_search":
                args = SearchArgs(**arguments)
                response = await exa_server.search(args)
                
                return [TextContent(
                    type="text",
                    text=exa_server.format_results(response),
                )]
            elif name == "exa_getcontents":
                args = GetContentsArgs(**arguments)
                response = await exa_server.get_contents(args)
                
                return [TextContent(
                    type="text",
                    text=exa_server.format_contents_results(response),
                )]
            elif name == "exa_findsimilar":
                args = FindSimilarArgs(**arguments)
                response = await exa_server.find_similar(args)
                
                return [TextContent(
                    type="text",
                    text=exa_server.format_similar_results(response),
                )]
            else:
                raise McpError(ErrorData(
                    code=METHOD_NOT_FOUND,
                    message=f"Unknown tool: {name}"
                ))
                
        except asyncio.CancelledError:
            raise McpError(ErrorData(
                code=REQUEST_CANCELLED,
                message="Request was cancelled"
            ))
        except ValueError as e:
            raise McpError(ErrorData(
                code=INVALID_PARAMS,
                message=str(e)
            ))
        except Exception as e:
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"Unexpected error: {str(e)}"
            ))

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict | None) -> GetPromptResult:
        if not arguments or "query" not in arguments:
            raise McpError(ErrorData(
                code=INVALID_PARAMS,
                message="Query is required"
            ))

        try:
            if name == "exa_search":
                args = SearchArgs(
                    query=arguments["query"],
                    num_results=arguments.get("num_results", 10)
                )
                
                response = await exa_server.search(args)
                
                return GetPromptResult(
                    description=f"Search results for: {args.query}",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(
                                type="text",
                                text=exa_server.format_results(response)
                            ),
                        )
                    ],
                )
            else:
                raise McpError(ErrorData(
                    code=METHOD_NOT_FOUND,
                    message=f"Unknown prompt: {name}"
                ))
            
        except asyncio.CancelledError:
            raise McpError(ErrorData(
                code=REQUEST_CANCELLED,
                message="Request was cancelled"
            ))
        except Exception as e:
            return GetPromptResult(
                description=f"Error: {str(e)}",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(type="text", text=str(e)),
                    )
                ],
            )

    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)

if __name__ == "__main__":
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        raise ValueError("EXA_API_KEY environment variable is required")
        
    asyncio.run(serve(api_key))
