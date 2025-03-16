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

class GoogleMapsSearchArgs(BaseModel):
    """Arguments for Google Maps search using SerpAPI."""
    q: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the query you want to search. You can use anything that you would use in a regular Google Maps search. The parameter is only required if type is set to 'search'.",
        ),
    ] = None
    type: Annotated[
        Optional[str],
        Field(
            default="search",
            description="Parameter defines the type of search you want to make. It can be set to: 'search' - returns a list of results for the set q parameter, 'place' - returns results for a specific place when data parameter is set. Parameter is not required when using place_id.",
        ),
    ] = "search"
    data: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter can be used to filter the search results. One of the uses of the parameter is to search for a specific place; therefore, it is required if the type is set to 'place'. Alternatively, place_id can be used. To use the data parameter to search for a specific place, it needs to be constructed in the following sequence: '!4m5!3m4!1s' + 'data_id' + '!8m2!3d' + 'latitude' + '!4d' + 'longitude'",
        ),
    ] = None
    place_id: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the unique reference to a place on a Google Map. Place IDs are available for most locations, including businesses, landmarks, parks, and intersections. You can find the place_id using our Google Maps API. place_id can be used without any other optional parameter.",
        ),
    ] = None
    ll: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the GPS coordinates of the location where you want the search to originate from. Its value must match the following format: '@' + 'latitude' + ',' + 'longitude' + ',' + 'zoom'. This will form a string that looks like this: e.g. '@40.7455096,-74.0083012,14z'. The 'zoom' attribute ranges from '3z', map completely zoomed out - to '21z', map completely zoomed in. The parameter should only be used when type is set to 'search'. Parameter is required when using pagination. Results are not guaranteed to be within the requested geographic location.",
        ),
    ] = None
    google_domain: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the Google domain to use. It defaults to 'google.com'. Head to the Google domains page for a full list of supported Google domains.",
        ),
    ] = None
    hl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the language to use for the Google Maps search. It's a two-letter language code. (e.g., 'en' for English, 'es' for Spanish, or 'fr' for French). Head to the Google Maps languages page for a full list of supported Google Maps languages.",
        ),
    ] = None
    gl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the country to use for the Google Maps search. It's a two-letter country code. (e.g., 'us' for the United States, 'uk' for United Kingdom, or 'fr' for France). Head to the Google countries page for a full list of supported Google countries. Parameter only affects Place Results API.",
        ),
    ] = None
    start: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Parameter defines the result offset. It skips the given number of results. It's used for pagination. (e.g., '0' (default) is the first page of results, '20' is the 2nd page of results, '40' is the 3rd page of results, etc.). We recommend starting with '0' and increasing by '20' for the next page.",
            ge=0,
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

    @field_validator('q')
    @classmethod
    def validate_search_parameters(cls, v, info):
        """Validate that search query is provided when type is 'search'."""
        model_data = info.data
        
        # If type is 'search', q is required
        if model_data.get('type') == 'search' and v is None:
            # Check if place_id is provided as an alternative
            if not model_data.get('place_id'):
                raise ValueError("Search query 'q' is required when type is 'search' and place_id is not provided")
        
        return v
    
    @field_validator('data')
    @classmethod
    def validate_place_parameters(cls, v, info):
        """Validate that data is provided when type is 'place'."""
        model_data = info.data
        
        # If type is 'place', data is required
        if model_data.get('type') == 'place' and v is None:
            # Check if place_id is provided as an alternative
            if not model_data.get('place_id'):
                raise ValueError("Parameter 'data' is required when type is 'place' and place_id is not provided")
        
        return v

class GoogleMapsLocation(BaseModel):
    """Location information for a Google Maps result."""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None

class GoogleMapsResult(BaseModel):
    """Single result from Google Maps."""
    position: Optional[int] = None
    title: Optional[str] = None
    place_id: Optional[str] = None
    data_id: Optional[str] = None
    link: Optional[str] = None
    type: Optional[str] = None
    rating: Optional[float] = None
    reviews: Optional[int] = None
    price_level: Optional[str] = None
    hours: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    thumbnail: Optional[str] = None
    gps_coordinates: Optional[GoogleMapsLocation] = None
    service_options: Optional[Dict[str, Any]] = None
    operating_hours: Optional[Dict[str, Any]] = None
    popular_times: Optional[Dict[str, Any]] = None
    photos: Optional[List[Dict[str, Any]]] = None
    reviews_data: Optional[List[Dict[str, Any]]] = None

class GoogleMapsResponseData(BaseModel):
    """The data field of the SerpAPI Google Maps search response."""
    search_metadata: Dict[str, Any]
    search_parameters: Dict[str, Any]
    local_results: Optional[List[GoogleMapsResult]] = None
    place_results: Optional[Dict[str, Any]] = None
    place_results_reviews: Optional[List[Dict[str, Any]]] = None
    pagination: Optional[Dict[str, Any]] = None
    serpapi_pagination: Optional[Dict[str, Any]] = None
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

class SerpApiGoogleMapsServer:
    """Server for Google Maps search using SerpAPI."""
    
    def __init__(self, api_key: str):
        """Initialize the SerpAPI Google Maps server with an API key."""
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search"
        self.cache = {}  # Simple in-memory cache
        self.cache_ttl = 3600  # Cache TTL in seconds (1 hour)
        self.timeout = aiohttp.ClientTimeout(total=30)  # Add timeout parameter
        print(f"Initializing SerpAPI Google Maps server with API key: {api_key[:5]}...", file=sys.stderr)
        
    async def google_maps_search(self, args: GoogleMapsSearchArgs) -> Union[Dict[str, Any], str]:
        """Perform a Google Maps search using SerpAPI."""
        # Build the cache key from the search parameters
        cache_key_parts = []
        if args.q:
            cache_key_parts.append(f"q={args.q}")
        if args.type:
            cache_key_parts.append(f"type={args.type}")
        if args.data:
            cache_key_parts.append(f"data={args.data}")
        if args.place_id:
            cache_key_parts.append(f"place_id={args.place_id}")
        if args.ll:
            cache_key_parts.append(f"ll={args.ll}")
        if args.google_domain:
            cache_key_parts.append(f"google_domain={args.google_domain}")
        if args.hl:
            cache_key_parts.append(f"hl={args.hl}")
        if args.gl:
            cache_key_parts.append(f"gl={args.gl}")
        if args.start is not None:
            cache_key_parts.append(f"start={args.start}")
            
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
            "engine": "google_maps",
            "api_key": self.api_key,
        }
        
        # Add optional parameters if provided
        if args.q:
            params["q"] = args.q
        if args.type:
            params["type"] = args.type
        if args.data:
            params["data"] = args.data
        if args.place_id:
            params["place_id"] = args.place_id
        if args.ll:
            params["ll"] = args.ll
        if args.google_domain:
            params["google_domain"] = args.google_domain
        if args.hl:
            params["hl"] = args.hl
        if args.gl:
            params["gl"] = args.gl
        if args.start is not None:
            params["start"] = args.start
        
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
                            error_model = GoogleMapsResponseData(**error_response)
                            formatted_response = self.format_google_maps_results(error_model)
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
                        maps_response = GoogleMapsResponseData(**raw_data)
                        formatted_response = self.format_google_maps_results(maps_response)
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
                error_model = GoogleMapsResponseData(**error_response)
                formatted_response = self.format_google_maps_results(error_model)
            else:
                # Return clean dict for error response
                formatted_response = clean_json_dict(error_response)
            
            # Cache the formatted error response
            self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
            return formatted_response
        except Exception as e:
            print(f"Error in google_maps_search: {str(e)}", file=sys.stderr)
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
                error_model = GoogleMapsResponseData(**error_response)
                formatted_response = self.format_google_maps_results(error_model)
            else:
                # Return clean dict for error response
                formatted_response = clean_json_dict(error_response)
            
            # Cache the formatted error response
            self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
            return formatted_response
    
    def format_google_maps_results(self, response: GoogleMapsResponseData) -> str:
        """Format Google Maps search results in a human-readable format."""
        result_text = []
        
        # Add error message if present
        if response.error:
            result_text.append(f"# Error")
            result_text.append(response.error)
            result_text.append("")
            return "\n".join(result_text)
        
        # Add local results if available
        if response.local_results:
            result_text.append(f"# Local Results ({len(response.local_results)})")
            result_text.append("")
            
            for i, result in enumerate(response.local_results):
                if result.title:
                    result_text.append(f"## {i+1}. {result.title}")
                else:
                    result_text.append(f"## {i+1}. [No title available]")
                
                if result.rating:
                    rating_text = f"Rating: {result.rating}"
                    if result.reviews:
                        rating_text += f" ({result.reviews} reviews)"
                    result_text.append(rating_text)
                
                if result.address:
                    result_text.append(f"Address: {result.address}")
                
                if result.phone:
                    result_text.append(f"Phone: {result.phone}")
                
                if result.hours:
                    result_text.append(f"Hours: {result.hours}")
                
                if result.price_level:
                    result_text.append(f"Price Level: {result.price_level}")
                
                if result.description:
                    result_text.append(f"\n{result.description}")
                
                if result.website:
                    result_text.append(f"\nWebsite: {result.website}")
                
                if result.link:
                    result_text.append(f"Google Maps Link: {result.link}")
                
                if result.place_id:
                    result_text.append(f"Place ID: {result.place_id}")
                
                result_text.append("")
        
        # Add place results if available
        if response.place_results:
            result_text.append(f"# Place Details")
            result_text.append("")
            
            place = response.place_results
            
            if "title" in place:
                result_text.append(f"## {place['title']}")
            
            if "rating" in place:
                rating_text = f"Rating: {place['rating']}"
                if "reviews" in place:
                    rating_text += f" ({place['reviews']} reviews)"
                result_text.append(rating_text)
            
            if "address" in place:
                result_text.append(f"Address: {place['address']}")
            
            if "phone" in place:
                result_text.append(f"Phone: {place['phone']}")
            
            if "website" in place:
                result_text.append(f"Website: {place['website']}")
            
            if "description" in place:
                result_text.append(f"\n{place['description']}")
            
            if "hours" in place:
                result_text.append("\n## Hours")
                for day, hours in place["hours"].items():
                    result_text.append(f"- {day}: {hours}")
            
            if "popular_times" in place:
                result_text.append("\n## Popular Times")
                for day, times in place["popular_times"].items():
                    result_text.append(f"- {day}: Busiest at {times.get('busiest_hours', 'N/A')}")
            
            result_text.append("")
        
        # Add reviews if available
        if response.place_results_reviews:
            result_text.append(f"# Reviews ({len(response.place_results_reviews)})")
            result_text.append("")
            
            for i, review in enumerate(response.place_results_reviews):
                if "user" in review:
                    result_text.append(f"## {i+1}. Review by {review['user']}")
                else:
                    result_text.append(f"## {i+1}. Anonymous Review")
                
                if "rating" in review:
                    result_text.append(f"Rating: {review['rating']}/5")
                
                if "date" in review:
                    result_text.append(f"Date: {review['date']}")
                
                if "text" in review:
                    result_text.append(f"\n{review['text']}")
                
                result_text.append("")
        
        # Add pagination information
        if response.pagination:
            result_text.append(f"# Pagination")
            if "current" in response.pagination:
                result_text.append(f"Current Page: {response.pagination['current']}")
            if "next" in response.pagination:
                result_text.append(f"Next Page: {response.pagination['next']}")
            if "other_pages" in response.pagination:
                result_text.append(f"Other Pages: {', '.join(str(p) for p in response.pagination['other_pages'])}")
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
    """Start the SerpAPI Google Maps MCP server."""
    server = Server("mcp-serpapi-google-maps")
    serpapi_google_maps_server = SerpApiGoogleMapsServer(api_key)
    
    # Test API key validity with a simple search request
    try:
        print("Testing API key validity...", file=sys.stderr)
        # Use a minimal search to validate the API key
        test_args = GoogleMapsSearchArgs(q="test")
        await serpapi_google_maps_server.google_maps_search(test_args)
        print("SerpAPI key validated successfully", file=sys.stderr)
    except Exception as e:
        print(f"Error validating SerpAPI key: {str(e)}", file=sys.stderr)
        sys.exit(1)
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        print("list_tools called", file=sys.stderr)
        return [
            Tool(
                name="google_maps_search",
                description="""Scrape Google Maps data with our Google Maps API.
                
                The API supports two main types of searches:
                - 'search' - returns a list of results for a given query
                - 'place' - returns detailed information about a specific place
                
                Results include comprehensive data from Google Maps such as business details, 
                ratings, reviews, contact information, hours, and more. You can search by query, 
                place ID, or specific coordinates.
                
                Note on Geographic Location and Search Queries:
                Results are not guaranteed to be within the geographic location provided in the ll parameter.
                When using the keywords 'near me' in a query, you will not always see results for the provided coordinates.
                City, state and zip code can be added to a query to refine the search.
                
                By default, returns cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON.""",
                inputSchema=GoogleMapsSearchArgs.model_json_schema(),
            ),
        ]
    
    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        print("list_prompts called", file=sys.stderr)
        return [
            Prompt(
                name="google_maps_search_prompt",
                description="""Search for places using Google Maps via SerpAPI.
                
                By default, results are returned as cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON for easier reading.
                """,
                arguments=[
                    PromptArgument(
                        name="query",
                        description="Parameter defines the query you want to search. You can use anything that you would use in a regular Google Maps search. The parameter is only required if type is set to 'search'.",
                        required=False,
                    ),
                    PromptArgument(
                        name="type",
                        description="Parameter defines the type of search you want to make. It can be set to: 'search' - returns a list of results for the set q parameter, 'place' - returns results for a specific place when data parameter is set. Parameter is not required when using place_id.",
                        required=False,
                    ),
                    PromptArgument(
                        name="data",
                        description="Parameter can be used to filter the search results. One of the uses of the parameter is to search for a specific place; therefore, it is required if the type is set to 'place'. Alternatively, place_id can be used.",
                        required=False,
                    ),
                    PromptArgument(
                        name="place_id",
                        description="Parameter defines the unique reference to a place on a Google Map. Place IDs are available for most locations, including businesses, landmarks, parks, and intersections. place_id can be used without any other optional parameter.",
                        required=False,
                    ),
                    PromptArgument(
                        name="ll",
                        description="Parameter defines the GPS coordinates of the location where you want the search to originate from. Format: '@latitude,longitude,zoom'. The parameter should only be used when type is set to 'search'. Parameter is required when using pagination.",
                        required=False,
                    ),
                    PromptArgument(
                        name="google_domain",
                        description="Parameter defines the Google domain to use. It defaults to 'google.com'.",
                        required=False,
                    ),
                    PromptArgument(
                        name="hl",
                        description="Parameter defines the language to use for the Google Maps search. It's a two-letter language code. (e.g., 'en' for English, 'es' for Spanish, or 'fr' for French).",
                        required=False,
                    ),
                    PromptArgument(
                        name="gl",
                        description="Parameter defines the country to use for the Google Maps search. It's a two-letter country code. (e.g., 'us' for the United States, 'uk' for United Kingdom, or 'fr' for France). Parameter only affects Place Results API.",
                        required=False,
                    ),
                    PromptArgument(
                        name="start",
                        description="Parameter defines the result offset for pagination. (e.g., '0' is the first page, '20' is the 2nd page, etc.)",
                        required=False,
                    ),
                    PromptArgument(
                        name="raw_json",
                        description="Return the complete raw JSON response directly from the SerpAPI server without any processing or validation.",
                        required=False,
                    ),
                    PromptArgument(
                        name="readable_json",
                        description="Return results in markdown-formatted text instead of JSON. Creates a structured, human-readable document.",
                        required=False,
                    ),
                ],
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        print(f"call_tool called with name: {name}, arguments: {arguments}", file=sys.stderr)
        
        if name == "google_maps_search":
            args = GoogleMapsSearchArgs(**arguments)
            
            # Call the API and get the response in the requested format
            response = await serpapi_google_maps_server.google_maps_search(args)
            
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
        
        if name == "google_maps_search_prompt":
            if arguments is None:
                arguments = {}
            
            query = arguments.get("query")
            search_type = arguments.get("type", "search")
            data = arguments.get("data")
            place_id = arguments.get("place_id")
            ll = arguments.get("ll")
            google_domain = arguments.get("google_domain")
            hl = arguments.get("hl")
            gl = arguments.get("gl")
            start = arguments.get("start")
            raw_json = arguments.get("raw_json", False)
            readable_json = arguments.get("readable_json", False)
            
            messages = []
            
            # System message
            messages.append(PromptMessage(
                role="system",
                content="You are a helpful assistant that can search for places using Google Maps. "
                        "Provide informative and concise summaries of the search results."
            ))
            
            # User message
            user_message = "I want to search for places"
            if query:
                user_message += f" matching '{query}'"
            if search_type == "place":
                user_message += f" and get detailed information about a specific place"
            if place_id:
                user_message += f" with place ID '{place_id}'"
            if ll:
                user_message += f" near the coordinates {ll}"
            if hl:
                user_message += f" in {hl} language"
            if gl:
                user_message += f" in {gl} country"
            user_message += "."
            
            messages.append(PromptMessage(
                role="user",
                content=user_message
            ))
            
            # Prepare search arguments
            search_args = {}
            if query:
                search_args["q"] = query
            if search_type:
                search_args["type"] = search_type
            if data:
                search_args["data"] = data
            if place_id:
                search_args["place_id"] = place_id
            if ll:
                search_args["ll"] = ll
            if google_domain:
                search_args["google_domain"] = google_domain
            if hl:
                search_args["hl"] = hl
            if gl:
                search_args["gl"] = gl
            if start is not None:
                search_args["start"] = start
            
            search_args["raw_json"] = raw_json
            search_args["readable_json"] = readable_json
            
            tool_calls = [
                {
                    "id": "google_maps_search_1",
                    "type": "function",
                    "function": {
                        "name": "google_maps_search",
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
    print("Starting SerpAPI Google Maps MCP server...", file=sys.stderr)
    
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
