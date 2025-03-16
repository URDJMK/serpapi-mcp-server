import os
import json
import asyncio
import aiohttp
import sys
from typing import List, Dict, Any, Union, Optional
from pydantic import BaseModel, Field, field_validator
from typing_extensions import Annotated
import pathlib
from dotenv import load_dotenv

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

REQUEST_CANCELLED = "request_cancelled"

class GoogleFinanceSearchArgs(BaseModel):
    """Arguments for Google Finance search using SerpAPI."""
    q: Annotated[
        str,
        Field(
            description="Parameter defines the query you want to search. It can be a stock, index, mutual fund, currency or futures.",
        ),
    ]
    hl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the language to use for the Google Finance search. It's a two-letter language code. (e.g., `en` for English, `es` for Spanish, or `fr` for French). Head to the Google languages page for a full list of supported Google languages.",
        ),
    ] = None
    window: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter is used for setting time range for the graph. It can be set to: `1D` - 1 Day(default), `5D` - 5 Days, `1M` - 1 Month, `6M` - 6 Months, `YTD` - Year to Date, `1Y` - 1 Year, `5Y` - 5 Years, `MAX` - Maximum",
        ),
    ] = None
    raw_json: Annotated[
        Optional[bool],
        Field(
            default=False,
            description="Return the complete raw JSON response directly from the SerpAPI server without any processing or validation. This bypasses all model validation and returns exactly what the API returns.",
        ),
    ] = False
    readable_json: Annotated[
        Optional[bool],
        Field(
            default=False,
            description="Return results in markdown-formatted text instead of JSON. Creates a structured, human-readable document with headings, bold text, and organized sections for easy reading.",
        ),
    ] = False

class StockPriceMovement(BaseModel):
    """Price movement information for a stock."""
    percentage: Optional[float] = None
    value: Optional[float] = None
    movement: Optional[str] = None  # "Up" or "Down"

class StockInfo(BaseModel):
    """Information about a stock."""
    stock: Optional[str] = None
    link: Optional[str] = None
    serpapi_link: Optional[str] = None
    name: Optional[str] = None
    price: Optional[float] = None
    price_movement: Optional[StockPriceMovement] = None
    currency: Optional[str] = None

class GoogleFinanceResponseData(BaseModel):
    """The data field of the SerpAPI Google Finance search response."""
    search_metadata: Dict[str, Any]
    search_parameters: Dict[str, Any]
    markets: Optional[Dict[str, List[StockInfo]]] = None
    stock_info: Optional[Dict[str, Any]] = None
    graph: Optional[Dict[str, Any]] = None
    news_results: Optional[List[Dict[str, Any]]] = None
    people_also_search_for: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None

class CachedSearch:
    """Cache for search results.
    
    This class stores the formatted response (raw JSON dict, readable text, or clean JSON dict)
    along with the query and timestamp. The cache key includes both the search
    parameters and the requested output format to ensure that cached responses
    match the requested format.
    """
    def __init__(self, query: str, response: Union[Dict[str, Any], str]):
        self.query = query
        self.response = response
        self.timestamp = asyncio.get_event_loop().time()

class SerpApiGoogleFinanceServer:
    """Server for Google Finance search using SerpAPI."""
    
    def __init__(self, api_key: str):
        """Initialize the SerpAPI Google Finance server with an API key."""
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search"
        self.cache = {}  # Simple in-memory cache
        self.cache_ttl = 3600  # Cache TTL in seconds (1 hour)
        self.timeout = aiohttp.ClientTimeout(total=30)  # Add timeout parameter
        print(f"Initializing SerpAPI Google Finance server with API key: {api_key[:5]}...", file=sys.stderr)
        
    async def google_finance_search(self, args: GoogleFinanceSearchArgs) -> Union[Dict[str, Any], str]:
        """Perform a Google Finance search using SerpAPI."""
        # Build the cache key from the search parameters
        cache_key_parts = []
        cache_key_parts.append(f"q={args.q}")
        if args.hl:
            cache_key_parts.append(f"hl={args.hl}")
        if args.window:
            cache_key_parts.append(f"window={args.window}")
            
        # Include the output format in the cache key
        if args.raw_json:
            cache_key_parts.append("format=raw_json")
        elif args.readable_json:
            cache_key_parts.append("format=readable_json")
        else:
            cache_key_parts.append("format=clean_json")
        
        cache_key = "&".join(cache_key_parts)
        
        # Check cache first
        now = asyncio.get_event_loop().time()
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if now - cached.timestamp < self.cache_ttl:
                print(f"Cache hit for: {cache_key}", file=sys.stderr)
                return cached.response
        
        # Prepare the search parameters
        params = {
            "engine": "google_finance",
            "api_key": self.api_key,
            "q": args.q,
        }
        
        # Add optional parameters if provided
        if args.hl:
            params["hl"] = args.hl
        if args.window:
            params["window"] = args.window
        
        # Make the API request
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(self.base_url, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        error_message = f"SerpAPI returned status code {response.status}: {error_text}"
                        print(f"Error: {error_message}", file=sys.stderr)
                        
                        # Create a minimal response with the error
                        error_response = {
                            "search_metadata": {"status": "Error"},
                            "search_parameters": params,
                            "error": error_message
                        }
                        
                        # Format the error response based on the requested format
                        formatted_response = None
                        if args.raw_json:
                            formatted_response = error_response
                        elif args.readable_json:
                            error_model = GoogleFinanceResponseData(**error_response)
                            formatted_response = self.format_google_finance_results(error_model)
                        else:
                            # Return clean dict for error response
                            formatted_response = clean_json_dict(error_response)
                        
                        # Cache the formatted error response
                        self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                        return formatted_response
                    
                    # Get the raw JSON response
                    raw_data = await response.json()
                    
                    # Process the response based on the requested format
                    formatted_response = None
                    
                    # For raw_json, just return the raw data
                    if args.raw_json:
                        formatted_response = raw_data
                        self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                        return formatted_response
                    
                    # Format based on the requested format
                    if args.readable_json:
                        # Convert to model for readable format
                        finance_response = GoogleFinanceResponseData(**raw_data)
                        formatted_response = self.format_google_finance_results(finance_response)
                    else:
                        # Clean JSON mode (default) - return dict instead of model
                        formatted_response = clean_json_dict(raw_data)
                    
                    # Cache the formatted response
                    self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                    return formatted_response
                    
        except asyncio.TimeoutError:
            print("SerpAPI request timed out", file=sys.stderr)
            error_response = {
                "search_metadata": {"status": "Error"},
                "search_parameters": params,
                "error": "SerpAPI request timed out"
            }
            
            # Format the error response based on the requested format
            formatted_response = None
            if args.raw_json:
                formatted_response = error_response
            elif args.readable_json:
                error_model = GoogleFinanceResponseData(**error_response)
                formatted_response = self.format_google_finance_results(error_model)
            else:
                # Return clean dict for error response
                formatted_response = clean_json_dict(error_response)
            
            # Cache the formatted error response
            self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
            return formatted_response
        except Exception as e:
            print(f"Error in google_finance_search: {str(e)}", file=sys.stderr)
            # Create an error response
            error_response = {
                "search_metadata": {"status": "Error"},
                "search_parameters": params,
                "error": f"An error occurred: {str(e)}"
            }
            
            # Format the error response based on the requested format
            formatted_response = None
            if args.raw_json:
                formatted_response = error_response
            elif args.readable_json:
                error_model = GoogleFinanceResponseData(**error_response)
                formatted_response = self.format_google_finance_results(error_model)
            else:
                # Return clean dict for error response
                formatted_response = clean_json_dict(error_response)
            
            # Cache the formatted error response
            self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
            return formatted_response
    
    def format_google_finance_results(self, response: GoogleFinanceResponseData) -> str:
        """Format Google Finance search results in a human-readable format."""
        result_text = []
        
        # Add error message if present
        if response.error:
            result_text.append(f"# Error")
            result_text.append(response.error)
            result_text.append("")
            return "\n".join(result_text)
        
        # Add stock info if available
        if response.stock_info:
            stock = response.stock_info
            result_text.append(f"# {stock.get('title', 'Stock Information')}")
            result_text.append("")
            
            if "price" in stock:
                result_text.append(f"**Current Price:** {stock['price']}")
            
            if "price_movement" in stock:
                movement = stock["price_movement"]
                direction = "📈" if movement.get("movement") == "Up" else "📉"
                result_text.append(f"**Change:** {direction} {movement.get('value', '')} ({movement.get('percentage', '')}%)")
            
            if "exchange" in stock:
                result_text.append(f"**Exchange:** {stock['exchange']}")
            
            if "currency" in stock:
                result_text.append(f"**Currency:** {stock['currency']}")
                
            result_text.append("")
        
        # Add graph information if available
        if response.graph:
            result_text.append(f"# Graph Information")
            result_text.append("")
            
            graph = response.graph
            if "time_window" in graph:
                result_text.append(f"**Time Window:** {graph['time_window']}")
            
            if "time_window_buttons" in graph:
                buttons = graph["time_window_buttons"]
                result_text.append(f"**Available Time Windows:** {', '.join(buttons)}")
                
            result_text.append("")
        
        # Add market information if available
        if response.markets:
            for market_name, stocks in response.markets.items():
                result_text.append(f"# {market_name.capitalize()} Market")
                result_text.append("")
                
                for stock in stocks:
                    result_text.append(f"## {stock.name}")
                    
                    if stock.price is not None:
                        result_text.append(f"**Price:** {stock.price}")
                    
                    if stock.price_movement:
                        movement = stock.price_movement
                        direction = "📈" if movement.movement == "Up" else "📉"
                        result_text.append(f"**Change:** {direction} {movement.value} ({movement.percentage}%)")
                    
                    if stock.link:
                        result_text.append(f"**Link:** {stock.link}")
                        
                    result_text.append("")
        
        # Add news results if available
        if response.news_results:
            result_text.append(f"# News ({len(response.news_results)})")
            result_text.append("")
            
            for i, news in enumerate(response.news_results):
                if "title" in news:
                    result_text.append(f"## {i+1}. {news['title']}")
                else:
                    result_text.append(f"## {i+1}. [No title available]")
                
                if "date" in news:
                    result_text.append(f"**Date:** {news['date']}")
                
                if "source" in news:
                    result_text.append(f"**Source:** {news['source']}")
                
                if "snippet" in news:
                    result_text.append(f"\n{news['snippet']}")
                
                if "link" in news:
                    result_text.append(f"\n**Link:** {news['link']}")
                
                result_text.append("")
        
        # Add "People also search for" if available
        if response.people_also_search_for:
            result_text.append(f"# People Also Search For")
            result_text.append("")
            
            for i, item in enumerate(response.people_also_search_for):
                if "title" in item:
                    result_text.append(f"- {item['title']}")
                    if "link" in item:
                        result_text.append(f"  **Link:** {item['link']}")
                    result_text.append("")
        
        return "\n".join(result_text)

def clean_json_dict(d):
    """Remove null and empty values from a dictionary recursively."""
    if d is None:
        return None
    
    if isinstance(d, dict):
        return {k: clean_json_dict(v) for k, v in d.items() if v is not None and v != "" and v != [] and v != {}}
    elif isinstance(d, list):
        return [clean_json_dict(i) for i in d if i is not None]
    else:
        return d

async def serve(api_key: str) -> None:
    """Start the SerpAPI Google Finance MCP server."""
    server = Server("mcp-serpapi-google-finance")
    serpapi_google_finance_server = SerpApiGoogleFinanceServer(api_key)
    
    # Test API key validity with a simple search request
    try:
        print("Testing API key validity...", file=sys.stderr)
        # Use a minimal search to validate the API key
        test_args = GoogleFinanceSearchArgs(q="AAPL")
        await serpapi_google_finance_server.google_finance_search(test_args)
        print("SerpAPI key validated successfully", file=sys.stderr)
    except Exception as e:
        print(f"Error validating SerpAPI key: {str(e)}", file=sys.stderr)
        sys.exit(1)
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        print("list_tools called", file=sys.stderr)
        return [
            Tool(
                name="google_finance_search",
                description="""Our Google Finance API allows you to scrape results from the Google Finance page.
                
                The API allows you to search for financial information about stocks, indices, 
                mutual funds, currencies, or futures. Results include comprehensive data such as 
                current prices, price movements, market information, and related news.
                
                You can specify a time window for the graph data, ranging from 1 day to the maximum 
                available historical data.
                
                By default, returns cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON.""",
                inputSchema=GoogleFinanceSearchArgs.model_json_schema(),
            ),
        ]
    
    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        print("list_prompts called", file=sys.stderr)
        return [
            Prompt(
                name="google_finance_search_prompt",
                description="""Search for financial information using Google Finance via SerpAPI.
                
                By default, results are returned as cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON for easier reading.
                """,
                arguments=[
                    PromptArgument(
                        name="query",
                        description="Parameter defines the query you want to search. It can be a stock, index, mutual fund, currency or futures.",
                        required=True,
                    ),
                    PromptArgument(
                        name="hl",
                        description="Parameter defines the language to use for the Google Finance search. It's a two-letter language code. (e.g., `en` for English, `es` for Spanish, or `fr` for French). Head to the Google languages page for a full list of supported Google languages.",
                        required=False,
                    ),
                    PromptArgument(
                        name="window",
                        description="Parameter is used for setting time range for the graph. It can be set to: `1D` - 1 Day(default), `5D` - 5 Days, `1M` - 1 Month, `6M` - 6 Months, `YTD` - Year to Date, `1Y` - 1 Year, `5Y` - 5 Years, `MAX` - Maximum",
                        required=False,
                    ),
                    PromptArgument(
                        name="raw_json",
                        description="Return the complete raw JSON response directly from the SerpAPI server without any processing or validation. This bypasses all model validation and returns exactly what the API returns.",
                        required=False,
                    ),
                    PromptArgument(
                        name="readable_json",
                        description="Return results in markdown-formatted text instead of JSON. Creates a structured, human-readable document with headings, bold text, and organized sections for easy reading.",
                        required=False,
                    ),
                ],
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        print(f"call_tool called with name: {name}, arguments: {arguments}", file=sys.stderr)
        
        if name == "google_finance_search":
            args = GoogleFinanceSearchArgs(**arguments)
            
            # Call the API and get the response in the requested format
            response = await serpapi_google_finance_server.google_finance_search(args)
            
            # Process the response based on its type
            if isinstance(response, dict):
                # JSON response (raw or clean)
                return [TextContent(type="text", text=json.dumps(response, indent=2))]
            elif isinstance(response, str):
                # Formatted readable text
                return [TextContent(type="text", text=response)]
            else:
                # Fallback for unexpected response types
                return [TextContent(type="text", text=str(response))]
        else:
            raise McpError(ErrorData(
                code=METHOD_NOT_FOUND,
                message=f"Unknown tool: {name}",
            ))
    
    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict | None) -> GetPromptResult:
        print(f"get_prompt called with name: {name}, arguments: {arguments}", file=sys.stderr)
        
        if name == "google_finance_search_prompt":
            if arguments is None:
                arguments = {}
            
            query = arguments.get("query")
            hl = arguments.get("hl")
            window = arguments.get("window")
            raw_json = arguments.get("raw_json", False)
            readable_json = arguments.get("readable_json", False)
            
            messages = []
            
            # System message
            messages.append(PromptMessage(
                role="system",
                content="You are a helpful assistant that can search for financial information using Google Finance. "
                        "Provide informative and concise summaries of the search results."
            ))
            
            # User message
            user_message = "I want to search for financial information"
            if query:
                user_message += f" about '{query}'"
            if hl:
                user_message += f" in {hl} language"
            if window:
                user_message += f" with a time window of {window}"
            user_message += "."
            
            messages.append(PromptMessage(
                role="user",
                content=user_message
            ))
            
            # Prepare search arguments
            search_args = {}
            if query:
                search_args["q"] = query
            if hl:
                search_args["hl"] = hl
            if window:
                search_args["window"] = window
            
            search_args["raw_json"] = raw_json
            search_args["readable_json"] = readable_json
            
            tool_calls = [
                {
                    "id": "google_finance_search_1",
                    "type": "function",
                    "function": {
                        "name": "google_finance_search",
                        "arguments": json.dumps(search_args)
                    }
                }
            ]
            
            return GetPromptResult(
                messages=messages,
                tool_calls=tool_calls,
            )
        else:
            raise McpError(ErrorData(
                code=METHOD_NOT_FOUND,
                message=f"Unknown prompt: {name}",
            ))
    
    # Run the server
    print("Starting SerpAPI Google Finance MCP server...", file=sys.stderr)
    
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)

if __name__ == "__main__":
    # Load environment variables from .env file if it exists
    script_dir = pathlib.Path(__file__).parent.absolute()
    parent_dir = script_dir.parent
    env_path = parent_dir / '.env'
    
    if env_path.exists():
        print(f"Loading environment variables from {env_path}", file=sys.stderr)
        load_dotenv(dotenv_path=env_path)
    else:
        print(f"Warning: .env file not found at {env_path}", file=sys.stderr)
    
    # Get API key from environment variable - check both possible environment variable names
    api_key = os.environ.get("SERP_API_KEY") or os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("Error: Neither SERP_API_KEY nor SERPAPI_KEY environment variable is set", file=sys.stderr)
        print(f"Please create a .env file in {parent_dir} with SERPAPI_KEY=your_api_key", file=sys.stderr)
        sys.exit(1)
    
    # Start the server
    asyncio.run(serve(api_key)) 