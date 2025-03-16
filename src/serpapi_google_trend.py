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

class GoogleTrendsArgs(BaseModel):
    """Arguments for Google Trends search using SerpAPI."""
    q: Annotated[
        str, 
        Field(
            description="Parameter defines the query or queries you want to search. You can use anything that you would use in a regular Google Trends search. The maximum number of queries per search is 5 (this only applies to 'Interest over time' and 'Compared breakdown by region' data_type, other types of data will only accept 1 query per search). When passing multiple queries, separate them with commas (e.g., 'coffee,pizza,dark chocolate'). Query can be a 'Search term' (e.g., 'World Cup', 'iPhone') or a 'Topic' (e.g., '/m/0663v'). Maximum length for each query is 100 characters.",
        )
    ]
    geo: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the location from where you want the search to originate. It defaults to Worldwide (activated when the value of geo parameter is not set or empty). Examples include 'US' for United States, 'GB' for United Kingdom, 'FR' for France. See Google Trends Locations for a full list of supported locations.",
        ),
    ] = None
    date: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter is used to define a date range. Available options: 'now 1-H' (past hour), 'now 4-H' (past 4 hours), 'now 1-d' (past day), 'now 7-d' (past 7 days), 'today 1-m' (past 30 days), 'today 3-m' (past 90 days), 'today 12-m' (past 12 months), 'today 5-y' (past 5 years), 'all' (2004-present). You can also pass custom date ranges: 'yyyy-mm-dd yyyy-mm-dd' (e.g., '2021-10-15 2022-05-25') or dates with hours within a week range: 'yyyy-mm-ddThh yyyy-mm-ddThh' (e.g., '2022-05-19T10 2022-05-24T22').",
        ),
    ] = None
    tz: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Parameter is used to define a time zone offset in minutes. The default value is 420 (Pacific Day Time: -07:00). Values can range from -1439 to 1439. Examples: 420 (PDT), 600 (Pacific/Tahiti), -540 (Asia/Tokyo), -480 (Canada/Pacific). The tz parameter is calculated using the time difference between UTC +0 and desired timezone.",
        ),
    ] = None
    data_type: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the type of search you want to do. Available options: 'TIMESERIES' or 'TIMESERIES_GRAPH_0' (Interest over time, default) - accepts both single and multiple queries per search, 'GEO_MAP' (Compared breakdown by region) - accepts only multiple queries per search, 'GEO_MAP_0' (Interest by region) - accepts only single query per search, 'RELATED_TOPICS' (Related topics) - accepts only single query per search, 'RELATED_QUERIES' (Related queries) - accepts only single query per search.",
        ),
    ] = None
    cat: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Parameter is used to define a search category. The default value is 0 ('All categories'). Examples include: 0 (All categories), 5 (Entertainment), 18 (Finance), etc. See Google Trends Categories for a full list of supported categories.",
        ),
    ] = None
    gprop: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter is used for sorting results by property. The default property is Web Search (activated when the value of gprop parameter is not set or empty). Other available options: 'images' (Image Search), 'news' (News Search), 'youtube' (YouTube Search), 'froogle' (Google Shopping).",
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

class GoogleTrendsResponseData(BaseModel):
    """The data field of the SerpAPI Google Trends response."""
    search_metadata: Dict[str, Any]
    search_parameters: Dict[str, Any]
    interest_over_time: Optional[Dict[str, Any]] = None
    interest_by_region: Optional[Dict[str, Any]] = None
    related_topics: Optional[Dict[str, Any]] = None
    related_queries: Optional[Dict[str, Any]] = None
    trending_searches: Optional[Dict[str, Any]] = None
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

class SerpApiGoogleTrendsServer:
    """Server for SerpAPI Google Trends search."""
    
    def __init__(self, api_key: str):
        """Initialize the SerpAPI server with an API key."""
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search"
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour in seconds
        print(f"Initializing SerpAPI Google Trends server with API key: {api_key[:5]}...", file=sys.stderr)

    async def google_trends_search(self, args: GoogleTrendsArgs) -> Union[Dict[str, Any], str]:
        """Search Google Trends using SerpAPI."""
        # Build the cache key from the search parameters
        cache_key_parts = []
        cache_key_parts.append(f"q={args.q}")
        if args.geo:
            cache_key_parts.append(f"geo={args.geo}")
        if args.date:
            cache_key_parts.append(f"date={args.date}")
        if args.tz:
            cache_key_parts.append(f"tz={args.tz}")
        if args.data_type:
            cache_key_parts.append(f"data_type={args.data_type}")
        if args.cat:
            cache_key_parts.append(f"cat={args.cat}")
        if args.gprop:
            cache_key_parts.append(f"gprop={args.gprop}")
            
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
            "engine": "google_trends",
            "api_key": self.api_key,
            "q": args.q,
        }
        
        # Add optional parameters if provided
        if args.geo:
            params["geo"] = args.geo
        if args.date:
            params["date"] = args.date
        if args.tz:
            params["tz"] = args.tz
        if args.data_type:
            params["data_type"] = args.data_type
        if args.cat:
            params["cat"] = args.cat
        if args.gprop:
            params["gprop"] = args.gprop
        
        # Make the API request
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                print(f"Making SerpAPI Google Trends request for query: {args.q}", file=sys.stderr)
                async with session.get(
                    self.base_url,
                    params=params
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"SerpAPI error response: {error_text}", file=sys.stderr)
                        try:
                            # Try to parse error as JSON
                            error_json = json.loads(error_text)
                            error_message = error_json.get("error", error_text)
                        except:
                            error_message = error_text
                        
                        # Create a minimal response with the error
                        error_response = {
                            "search_metadata": {"status": "Error"},
                            "search_parameters": params,
                            "error": f"SerpAPI error: {error_message}"
                        }
                        
                        # Format the error response based on the requested format
                        formatted_response = None
                        if args.raw_json:
                            formatted_response = error_response
                        elif args.readable_json:
                            error_model = GoogleTrendsResponseData(**error_response)
                            formatted_response = self.format_google_trends_results(error_model)
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
                    
                    # Check if the response contains an error field
                    if "error" in raw_data:
                        print(f"SerpAPI returned error: {raw_data['error']}", file=sys.stderr)
                        error_response = {
                            "search_metadata": {"status": "Error"},
                            "search_parameters": params,
                            "error": f"SerpAPI error: {raw_data['error']}"
                        }
                        
                        # Format the error response based on the requested format
                        if args.readable_json:
                            error_model = GoogleTrendsResponseData(**error_response)
                            formatted_response = self.format_google_trends_results(error_model)
                        else:
                            # Return clean dict for error response
                            formatted_response = clean_json_dict(error_response)
                        
                        # Cache the formatted error response
                        self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                        return formatted_response
                    
                    # Format based on the requested format
                    if args.readable_json:
                        # Convert to model for readable format
                        trends_response = GoogleTrendsResponseData(**raw_data)
                        formatted_response = self.format_google_trends_results(trends_response)
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
                    error_model = GoogleTrendsResponseData(**error_response)
                    formatted_response = self.format_google_trends_results(error_model)
                else:
                    # Return clean dict for error response
                    formatted_response = clean_json_dict(error_response)
                
                # Cache the formatted error response
                self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                return formatted_response
                
            except Exception as e:
                print(f"SerpAPI search error: {str(e)}", file=sys.stderr)
                error_response = {
                    "search_metadata": {"status": "Error"},
                    "search_parameters": params,
                    "error": f"SerpAPI error: {str(e)}"
                }
                
                # Format the error response based on the requested format
                formatted_response = None
                if args.raw_json:
                    formatted_response = error_response
                elif args.readable_json:
                    error_model = GoogleTrendsResponseData(**error_response)
                    formatted_response = self.format_google_trends_results(error_model)
                else:
                    # Return clean dict for error response
                    formatted_response = clean_json_dict(error_response)
                
                # Cache the formatted error response
                self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                return formatted_response

    def format_google_trends_results(self, response: GoogleTrendsResponseData) -> str:
        """Format Google Trends results as human-readable text."""
        result = []
        
        # Add search information
        result.append(f"# Google Trends Results")
        
        # Add error message if present
        if response.error:
            result.append(f"## Error")
            result.append(response.error)
            result.append("")
            return "\n".join(result)
        
        # Add search parameters
        if response.search_parameters:
            result.append(f"## Search Parameters")
            for key, value in response.search_parameters.items():
                if key != "api_key":  # Don't show API key
                    result.append(f"- **{key}**: {value}")
            result.append("")
        
        # Add interest over time data
        if response.interest_over_time:
            result.append(f"## Interest Over Time")
            if "timeline_data" in response.interest_over_time:
                result.append("### Timeline Data")
                for item in response.interest_over_time["timeline_data"]:
                    if "date" in item:
                        result.append(f"**{item['date']}**")
                    if "values" in item:
                        for value in item["values"]:
                            if "query" in value and "value" in value:
                                result.append(f"- {value['query']}: {value['value']}")
                    result.append("")
            result.append("")
        
        # Add interest by region data
        if response.interest_by_region:
            result.append(f"## Interest by Region")
            if "region_data" in response.interest_by_region:
                for item in response.interest_by_region["region_data"]:
                    if "region_name" in item and "values" in item:
                        result.append(f"**{item['region_name']}**")
                        for value in item["values"]:
                            if "query" in value and "value" in value:
                                result.append(f"- {value['query']}: {value['value']}")
                        result.append("")
            result.append("")
        
        # Add related topics data
        if response.related_topics:
            result.append(f"## Related Topics")
            if "rising" in response.related_topics:
                result.append("### Rising Topics")
                for topic in response.related_topics["rising"]:
                    if "topic_title" in topic and "value" in topic:
                        result.append(f"- **{topic['topic_title']}**: {topic['value']}")
                result.append("")
            if "top" in response.related_topics:
                result.append("### Top Topics")
                for topic in response.related_topics["top"]:
                    if "topic_title" in topic and "value" in topic:
                        result.append(f"- **{topic['topic_title']}**: {topic['value']}")
                result.append("")
            result.append("")
        
        # Add related queries data
        if response.related_queries:
            result.append(f"## Related Queries")
            if "rising" in response.related_queries:
                result.append("### Rising Queries")
                for query in response.related_queries["rising"]:
                    if "query" in query and "value" in query:
                        result.append(f"- **{query['query']}**: {query['value']}")
                result.append("")
            if "top" in response.related_queries:
                result.append("### Top Queries")
                for query in response.related_queries["top"]:
                    if "query" in query and "value" in query:
                        result.append(f"- **{query['query']}**: {query['value']}")
                result.append("")
            result.append("")
        
        # Add trending searches data
        if response.trending_searches:
            result.append(f"## Trending Searches")
            if "trending_searches" in response.trending_searches:
                for search in response.trending_searches["trending_searches"]:
                    if "title" in search:
                        result.append(f"- {search['title']}")
                    if "articles" in search:
                        for article in search["articles"]:
                            if "title" in article and "link" in article:
                                result.append(f"  - [{article['title']}]({article['link']})")
                    result.append("")
            result.append("")
        
        return "\n".join(result)

def clean_json_dict(data):
    """Remove null, empty lists, empty dicts, and empty strings from a dict, recursively."""
    if isinstance(data, dict):
        return {
            k: clean_json_dict(v)
            for k, v in data.items()
            if v is not None and v != [] and v != {} and v != ""
        }
    elif isinstance(data, list):
        cleaned_list = [clean_json_dict(v) for v in data if v is not None and v != [] and v != {} and v != ""]
        return cleaned_list if cleaned_list else None
    else:
        return data

async def serve(api_key: str) -> None:
    """Start the SerpAPI Google Trends MCP server."""
    server = Server("mcp-serpapi-google-trends")
    serpapi_server = SerpApiGoogleTrendsServer(api_key)
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        print("list_tools called", file=sys.stderr)
        return [
            Tool(
                name="google_trends_search",
                description="""Search Google Trends and get interest over time, interest by region, related topics, and related queries. The Google Trends API allows you to scrape results from the Google Trends search page. You can analyze search interest over time, geographic distribution of interest, related topics, and related search queries.
                You can specify location, time range, and data type to customize your trend analysis.

                Numbers represent search interest relative to the highest point on the chart for the given region and time. A value of 100 is the peak popularity for the term. A value of 50 means that the term is half as popular. A score of 0 means there was not enough data for this term.

                Output formats:
                - By default, returns cleaned JSON without null/empty values.
                - Set raw_json=True to get the complete raw JSON response with all fields.
                - Set readable_json=True to get markdown-formatted text instead of JSON.
                
                This tool is ideal for market research, content planning, understanding search trends over time, competitive analysis, and identifying regional interest patterns.""",
                inputSchema=GoogleTrendsArgs.model_json_schema(),
            ),
        ]
    
    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        print("list_prompts called", file=sys.stderr)
        return [
            Prompt(
                name="google_trends_prompt",
                description="""Search Google Trends and get interest over time, interest by region, related topics, and related queries. The Google Trends API allows you to analyze search trends data from Google Trends via SerpAPI. You can discover how search interest for terms changes over time, varies by region, and what related topics and queries are trending.

                Numbers represent search interest relative to the highest point on the chart for the given region and time. A value of 100 is the peak popularity for the term. A value of 50 means that the term is half as popular. A score of 0 means there was not enough data for this term.
                
                By default, results are returned as cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON for easier reading.
                """,
                arguments=[
                    PromptArgument(
                        name="q",
                        description="Parameter defines the query or queries you want to search. You can use anything that you would use in a regular Google Trends search. The maximum number of queries per search is 5 (this only applies to 'Interest over time' and 'Compared breakdown by region' data_type, other types of data will only accept 1 query per search). When passing multiple queries, separate them with commas (e.g., 'coffee,pizza,dark chocolate'). Query can be a 'Search term' (e.g., 'World Cup', 'iPhone') or a 'Topic' (e.g., '/m/0663v'). Maximum length for each query is 100 characters.",
                        required=True,
                    ),
                    PromptArgument(
                        name="geo",
                        description="Parameter defines the location from where you want the search to originate. It defaults to Worldwide (activated when the value of geo parameter is not set or empty). Examples include 'US' for United States, 'GB' for United Kingdom, 'FR' for France. See Google Trends Locations for a full list of supported locations.",
                        required=False,
                    ),
                    PromptArgument(
                        name="date",
                        description="Parameter is used to define a date range. Available options: 'now 1-H' (past hour), 'now 4-H' (past 4 hours), 'now 1-d' (past day), 'now 7-d' (past 7 days), 'today 1-m' (past 30 days), 'today 3-m' (past 90 days), 'today 12-m' (past 12 months), 'today 5-y' (past 5 years), 'all' (2004-present). You can also pass custom date ranges: 'yyyy-mm-dd yyyy-mm-dd' (e.g., '2021-10-15 2022-05-25') or dates with hours within a week range: 'yyyy-mm-ddThh yyyy-mm-ddThh' (e.g., '2022-05-19T10 2022-05-24T22').",
                        required=False,
                    ),
                    PromptArgument(
                        name="tz",
                        description="Parameter is used to define a time zone offset in minutes. The default value is 420 (Pacific Day Time: -07:00). Values can range from -1439 to 1439. Examples: 420 (PDT), 600 (Pacific/Tahiti), -540 (Asia/Tokyo), -480 (Canada/Pacific). The tz parameter is calculated using the time difference between UTC +0 and desired timezone.",
                        required=False,
                    ),
                    PromptArgument(
                        name="data_type",
                        description="Parameter defines the type of search you want to do. Available options: 'TIMESERIES' or 'TIMESERIES_GRAPH_0' (Interest over time, default) - accepts both single and multiple queries per search, 'GEO_MAP' (Compared breakdown by region) - accepts only multiple queries per search, 'GEO_MAP_0' (Interest by region) - accepts only single query per search, 'RELATED_TOPICS' (Related topics) - accepts only single query per search, 'RELATED_QUERIES' (Related queries) - accepts only single query per search.",
                        required=False,
                    ),
                    PromptArgument(
                        name="cat",
                        description="Parameter is used to define a search category. The default value is 0 ('All categories'). Examples include: 0 (All categories), 5 (Entertainment), 18 (Finance), etc. See Google Trends Categories for a full list of supported categories.",
                        required=False,
                    ),
                    PromptArgument(
                        name="gprop",
                        description="Parameter is used for sorting results by property. The default property is Web Search (activated when the value of gprop parameter is not set or empty). Other available options: 'images' (Image Search), 'news' (News Search), 'youtube' (YouTube Search), 'froogle' (Google Shopping).",
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
        
        if name == "google_trends_search":
            args = GoogleTrendsArgs(**arguments)
            
            # Call the API and get the response in the requested format
            response = await serpapi_server.google_trends_search(args)
            
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
        print(f"get_prompt called with name={name}", file=sys.stderr)
        try:
            if arguments is None:
                arguments = {}
            
            if name == "google_trends_prompt":
                # Extract parameters from arguments
                q = arguments.get("q")
                geo = arguments.get("geo")
                date = arguments.get("date")
                tz = arguments.get("tz")
                data_type = arguments.get("data_type")
                cat = arguments.get("cat")
                gprop = arguments.get("gprop")
                raw_json = arguments.get("raw_json", False)
                readable_json = arguments.get("readable_json", False)
                
                messages = []
                
                # System message
                messages.append(PromptMessage(
                    role="system",
                    content="You are a helpful assistant that can analyze Google Trends data and provide insights about search interest over time, regional interest, related topics, and related queries."
                ))
                
                # User message
                user_message = "I want to analyze Google Trends data"
                if q:
                    user_message += f" for '{q}'"
                if geo:
                    user_message += f" in {geo}"
                if date:
                    user_message += f" over the time period {date}"
                if data_type:
                    data_type_desc = {
                        "TIMESERIES_GRAPH_0": "interest over time",
                        "GEO_MAP_0": "interest by region",
                        "RELATED_TOPICS": "related topics",
                        "RELATED_QUERIES": "related queries"
                    }.get(data_type, data_type)
                    user_message += f" focusing on {data_type_desc}"
                if cat:
                    user_message += f" in category {cat}"
                if gprop:
                    user_message += f" for {gprop or 'web search'}"
                user_message += "."
                
                messages.append(PromptMessage(
                    role="user",
                    content=user_message
                ))
                
                # Prepare search arguments
                search_args = {}
                if q:
                    search_args["q"] = q
                if geo:
                    search_args["geo"] = geo
                if date:
                    search_args["date"] = date
                if tz:
                    search_args["tz"] = tz
                if data_type:
                    search_args["data_type"] = data_type
                if cat:
                    search_args["cat"] = cat
                if gprop:
                    search_args["gprop"] = gprop
                
                search_args["raw_json"] = raw_json
                search_args["readable_json"] = readable_json
                
                tool_calls = [
                    {
                        "id": "google_trends_search_1",
                        "type": "function",
                        "function": {
                            "name": "google_trends_search",
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
        except Exception as e:
            print(f"Error in get_prompt for {name}: {str(e)}", file=sys.stderr)
            if isinstance(e, McpError):
                raise
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"Error executing prompt {name}: {str(e)}"
            ))
    
    print("Starting SerpAPI Google Trends MCP server...", file=sys.stderr)
    
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)
        
if __name__ == "__main__":
    # Load environment variables from .env file in the parent directory of this script
    script_dir = pathlib.Path(__file__).parent.absolute()
    parent_dir = script_dir.parent
    env_path = parent_dir / '.env'
    
    if env_path.exists():
        print(f"Loading environment variables from {env_path}", file=sys.stderr)
        load_dotenv(dotenv_path=env_path)
    else:
        print(f"Warning: .env file not found at {env_path}", file=sys.stderr)
    
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        print("Error: SERPAPI_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)
    
    asyncio.run(serve(api_key)) 