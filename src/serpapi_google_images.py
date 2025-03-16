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

class GoogleImagesArgs(BaseModel):
    """Arguments for Google Images search using SerpAPI."""
    q: Annotated[
        str, 
        Field(
            description="Parameter defines the query you want to search. You can use anything that you would use in a regular Google Images search. e.g. inurl:, site:, intitle:.",
        )
    ]
    location: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines from where you want the search to originate. If several locations match the location requested, we'll pick the most popular one. Head to the /locations.json API if you need more precise control. The location and uule parameters can't be used together. It is recommended to specify location at the city level in order to simulate a real user's search.",
        ),
    ] = None
    uule: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter is the Google encoded location you want to use for the search. uule and location parameters can't be used together.",
        ),
    ] = None
    google_domain: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the Google domain to use. It defaults to google.com. Head to the Google domains for a full list of supported Google domains.",
        ),
    ] = None
    gl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the country to use for the Google Images search. It's a two-letter country code. (e.g., us for the United States, uk for United Kingdom, or fr for France). Head to the Google countries for a full list of supported Google countries.",
        ),
    ] = None
    hl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the language to use for the Google Images search. It's a two-letter language code. (e.g., en for English, es for Spanish, or fr for French). Head to the Google languages for a full list of supported Google languages.",
        ),
    ] = None
    cr: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines one or multiple countries to limit the search to. It uses country{two-letter upper-case country code} to specify countries and | as a delimiter. (e.g., countryFR|countryDE will only search French and German pages). Head to the Google cr countries page for a full list of supported countries.",
        ),
    ] = None
    device: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the device to use to get the results. It can be set to desktop (default) to use a regular browser, tablet to use a tablet browser (currently using iPads), or mobile to use a mobile browser.",
        ),
    ] = None
    ijn: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Parameter defines the page number for Google Images. It's a zero-based index. (e.g., 0 for the first page, 1 for the second page, etc.).",
            ge=0,
        ),
    ] = None
    chips: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter enables to filter image search. It's a string provided by Google as suggested search, like: red apple. Chips are provided under the section: suggested_searches when ijn = 0. Both chips and serpapi_link values are provided for each suggested search.",
        ),
    ] = None
    tbs: Annotated[
        Optional[str],
        Field(
            default=None,
            description="(to be searched) parameter defines advanced search parameters that aren't possible in the regular query field.",
        ),
    ] = None
    imgar: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the set aspect ratio of images. Options: s - Square, t - Tall, w - Wide, xw - Panoramic.",
        ),
    ] = None
    imgsz: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the size of images. Options: l - Large, m - Medium, i - Icon, qsvga - Larger than 400×300, vga - Larger than 640×480, svga - Larger than 800×600, xga - Larger than 1024×768, 2mp - Larger than 2 MP, 4mp - Larger than 4 MP, 6mp - Larger than 6 MP, 8mp - Larger than 8 MP, 10mp - Larger than 10 MP, 12mp - Larger than 12 MP, 15mp - Larger than 15 MP, 20mp - Larger than 20 MP, 40mp - Larger than 40 MP, 70mp - Larger than 70 MP.",
        ),
    ] = None
    image_color: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the color of images. Options: bw - Black and white, trans - Transparent, red - Red, orange - Orange, yellow - Yellow, green - Green, teal - Teal, blue - Blue, purple - Purple, pink - Pink, white - White, gray - Gray, black - Black, brown - Brown. This parameter overrides ic and isc components of tbs parameter.",
        ),
    ] = None
    image_type: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the type of images. Options: face - Face, photo - Photo, clipart - Clip art, lineart - Line drawing, animated - Animated. This parameter overrides itp component of tbs parameter.",
        ),
    ] = None
    licenses: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the scope of licenses of images. Options: f - Free to use or share, fc - Free to use or share, even commercially, fm - Free to use, share or modify, fmc - Free to use, share or modify, even commercially, cl - Creative Commons licenses, ol - Commercial and other licenses. This parameter overrides sur component of tbs parameter.",
        ),
    ] = None
    safe: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the level of filtering for adult content. It can be set to active or off, by default Google will blur explicit content.",
        ),
    ] = None
    nfpr: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the exclusion of results from an auto-corrected query when the original query is spelled wrong. It can be set to 1 to exclude these results, or 0 to include them (default). Note that this parameter may not prevent Google from returning results for an auto-corrected query if no other results are available.",
        ),
    ] = None
    filter: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines if the filters for 'Similar Results' and 'Omitted Results' are on or off. It can be set to 1 (default) to enable these filters, or 0 to disable these filters.",
        ),
    ] = None
    time_period: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the time period for filtering results by recency. Supported values include: 'd' (past day), 'w' (past week), 'm' (past month), 'y' (past year). You can also specify a number with these letters, e.g., 'd3' for past 3 days.",
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

    @field_validator('location', 'uule')
    @classmethod
    def validate_location_parameters(cls, v, info):
        """Validate that location and uule are not used together."""
        model_data = info.data
        
        # If both location and uule are provided, raise an error
        if v is not None and model_data.get('location' if info.field_name == 'uule' else 'uule') is not None:
            raise ValueError("location and uule parameters can't be used together")
        
        return v

class GoogleImagesResult(BaseModel):
    """Single result from Google Images."""
    position: Optional[int] = None
    thumbnail: Optional[str] = None
    source: Optional[str] = None
    title: Optional[str] = None
    link: Optional[str] = None
    original: Optional[str] = None
    original_width: Optional[int] = None
    original_height: Optional[int] = None
    is_product: Optional[bool] = None
    in_stock: Optional[bool] = None
    source_logo: Optional[str] = None
    tag: Optional[str] = None
    license_details_url: Optional[str] = None
    related_content_id: Optional[str] = None
    serpapi_related_content_link: Optional[str] = None

class GoogleImagesSuggestedSearch(BaseModel):
    """Suggested search from Google Images."""
    name: Optional[str] = None
    link: Optional[str] = None
    chips: Optional[str] = None
    serpapi_link: Optional[str] = None
    thumbnail: Optional[str] = None

class GoogleImagesRelatedSearch(BaseModel):
    """Related search from Google Images."""
    query: Optional[str] = None
    link: Optional[str] = None
    serpapi_link: Optional[str] = None
    highlighted_words: Optional[List[str]] = None
    thumbnail: Optional[str] = None

class GoogleImagesResponseData(BaseModel):
    """The data field of the SerpAPI Google Images search response."""
    search_metadata: Dict[str, Any]
    search_parameters: Dict[str, Any]
    search_information: Optional[Dict[str, Any]] = None
    suggested_searches: Optional[List[GoogleImagesSuggestedSearch]] = None
    images_results: Optional[List[GoogleImagesResult]] = None
    related_searches: Optional[List[GoogleImagesRelatedSearch]] = None
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

class SerpApiGoogleImagesServer:
    """Server for Google Images search using SerpAPI."""
    
    def __init__(self, api_key: str):
        """Initialize the SerpAPI server with an API key."""
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search"
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour in seconds
        print(f"Initializing SerpAPI Google Images server with API key: {api_key[:5]}...", file=sys.stderr)

    async def google_images_search(self, args: GoogleImagesArgs) -> Union[Dict[str, Any], str]:
        """Search Google Images using SerpAPI."""
        # Build the cache key from the search parameters
        cache_key_parts = []
        cache_key_parts.append(f"q={args.q}")
        if args.location:
            cache_key_parts.append(f"location={args.location}")
        if args.uule:
            cache_key_parts.append(f"uule={args.uule}")
        if args.google_domain:
            cache_key_parts.append(f"google_domain={args.google_domain}")
        if args.gl:
            cache_key_parts.append(f"gl={args.gl}")
        if args.hl:
            cache_key_parts.append(f"hl={args.hl}")
        if args.cr:
            cache_key_parts.append(f"cr={args.cr}")
        if args.device:
            cache_key_parts.append(f"device={args.device}")
        if args.ijn is not None:
            cache_key_parts.append(f"ijn={args.ijn}")
        if args.chips:
            cache_key_parts.append(f"chips={args.chips}")
        if args.tbs:
            cache_key_parts.append(f"tbs={args.tbs}")
        if args.imgar:
            cache_key_parts.append(f"imgar={args.imgar}")
        if args.imgsz:
            cache_key_parts.append(f"imgsz={args.imgsz}")
        if args.image_color:
            cache_key_parts.append(f"image_color={args.image_color}")
        if args.image_type:
            cache_key_parts.append(f"image_type={args.image_type}")
        if args.licenses:
            cache_key_parts.append(f"licenses={args.licenses}")
        if args.safe:
            cache_key_parts.append(f"safe={args.safe}")
        if args.nfpr:
            cache_key_parts.append(f"nfpr={args.nfpr}")
        if args.filter:
            cache_key_parts.append(f"filter={args.filter}")
        if args.time_period:
            cache_key_parts.append(f"time_period={args.time_period}")
            
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
            "engine": "google_images",
            "api_key": self.api_key,
            "q": args.q,
        }
        
        # Add optional parameters if provided
        if args.location:
            params["location"] = args.location
        if args.uule:
            params["uule"] = args.uule
        if args.google_domain:
            params["google_domain"] = args.google_domain
        if args.gl:
            params["gl"] = args.gl
        if args.hl:
            params["hl"] = args.hl
        if args.cr:
            params["cr"] = args.cr
        if args.device:
            params["device"] = args.device
        if args.ijn is not None:
            params["ijn"] = args.ijn
        if args.chips:
            params["chips"] = args.chips
        if args.tbs:
            params["tbs"] = args.tbs
        if args.imgar:
            params["imgar"] = args.imgar
        if args.imgsz:
            params["imgsz"] = args.imgsz
        if args.image_color:
            params["image_color"] = args.image_color
        if args.image_type:
            params["image_type"] = args.image_type
        if args.licenses:
            params["licenses"] = args.licenses
        if args.safe:
            params["safe"] = args.safe
        if args.nfpr:
            params["nfpr"] = args.nfpr
        if args.filter:
            params["filter"] = args.filter
        if args.time_period:
            params["time_period"] = args.time_period
        
        # Make the API request
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                print(f"Making SerpAPI Google Images request for query: {args.q}", file=sys.stderr)
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
                            error_model = GoogleImagesResponseData(**error_response)
                            formatted_response = self.format_google_images_results(error_model)
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
                            error_model = GoogleImagesResponseData(**error_response)
                            formatted_response = self.format_google_images_results(error_model)
                        else:
                            # Return clean dict for error response
                            formatted_response = clean_json_dict(error_response)
                        
                        # Cache the formatted error response
                        self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                        return formatted_response
                    
                    # Format based on the requested format
                    if args.readable_json:
                        # Convert to model for readable format
                        images_response = GoogleImagesResponseData(**raw_data)
                        formatted_response = self.format_google_images_results(images_response)
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
                    error_model = GoogleImagesResponseData(**error_response)
                    formatted_response = self.format_google_images_results(error_model)
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
                    error_model = GoogleImagesResponseData(**error_response)
                    formatted_response = self.format_google_images_results(error_model)
                else:
                    # Return clean dict for error response
                    formatted_response = clean_json_dict(error_response)
                
                # Cache the formatted error response
                self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                return formatted_response 

    def format_google_images_results(self, response: GoogleImagesResponseData) -> str:
        """Format Google Images results as human-readable text."""
        result = []
        
        # Add search information
        result.append(f"# Google Images Results")
        
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
        
        # Add search information if available
        if response.search_information:
            result.append(f"## Search Information")
            for key, value in response.search_information.items():
                result.append(f"- **{key}**: {value}")
            result.append("")
        
        # Add suggested searches if available
        if response.suggested_searches:
            result.append(f"## Suggested Searches")
            for i, search in enumerate(response.suggested_searches):
                if search.name:
                    result.append(f"- **{search.name}**")
                    if search.link:
                        result.append(f"  - Link: {search.link}")
                    if search.chips:
                        result.append(f"  - Chips: {search.chips}")
            result.append("")
        
        # Add images results if available
        if response.images_results:
            result.append(f"## Images Results ({len(response.images_results)})")
            for i, image in enumerate(response.images_results):
                result.append(f"### Image {i+1}")
                if image.title:
                    result.append(f"- **Title**: {image.title}")
                if image.source:
                    result.append(f"- **Source**: {image.source}")
                if image.link:
                    result.append(f"- **Link**: {image.link}")
                if image.original:
                    result.append(f"- **Original Image**: {image.original}")
                if image.original_width and image.original_height:
                    result.append(f"- **Dimensions**: {image.original_width}x{image.original_height}")
                if image.is_product is not None:
                    result.append(f"- **Is Product**: {image.is_product}")
                if image.in_stock is not None:
                    result.append(f"- **In Stock**: {image.in_stock}")
                if image.tag:
                    result.append(f"- **Tag**: {image.tag}")
                result.append("")
        
        # Add related searches if available
        if response.related_searches:
            result.append(f"## Related Searches")
            for i, search in enumerate(response.related_searches):
                if search.query:
                    result.append(f"- **{search.query}**")
                    if search.highlighted_words:
                        result.append(f"  - Highlighted Words: {', '.join(search.highlighted_words)}")
                    if search.link:
                        result.append(f"  - Link: {search.link}")
            result.append("")
        
        # Add pagination information if available
        if response.serpapi_pagination:
            result.append(f"## Pagination")
            for key, value in response.serpapi_pagination.items():
                result.append(f"- **{key}**: {value}")
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
    """Start the SerpAPI Google Images MCP server."""
    server = Server("mcp-serpapi-google-images")
    serpapi_server = SerpApiGoogleImagesServer(api_key)
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        print("list_tools called", file=sys.stderr)
        return [
            Tool(
                name="google_images_search",
                description="""Search Google Images and get image results, suggested searches, and related searches. The Google Images API allows you to scrape results from the Google Images search page.
                
                You can search for images using any query you would use in a regular Google Images search, including operators like 'site:', 'inurl:', 'intitle:', etc.
                
                The API supports various filtering options such as image size, color, type, aspect ratio, and license. You can also filter by location, language, and device type.
                
                Output formats:
                - By default, returns cleaned JSON without null/empty values.
                - Set raw_json=True to get the complete raw JSON response with all fields.
                - Set readable_json=True to get markdown-formatted text instead of JSON.
                
                This tool is ideal for finding images for content creation, market research, competitive analysis, and more.""",
                inputSchema=GoogleImagesArgs.model_json_schema(),
            ),
        ]
    
    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        print("list_prompts called", file=sys.stderr)
        return [
            Prompt(
                name="google_images_prompt",
                description="""Search Google Images and get image results, suggested searches, and related searches. The Google Images API allows you to scrape results from the Google Images search page via SerpAPI.
                
                By default, results are returned as cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON for easier reading.
                """,
                arguments=[
                    PromptArgument(
                        name="q",
                        description="Parameter defines the query you want to search. You can use anything that you would use in a regular Google Images search. e.g. inurl:, site:, intitle:.",
                        required=True,
                    ),
                    PromptArgument(
                        name="location",
                        description="Parameter defines from where you want the search to originate. If several locations match the location requested, we'll pick the most popular one. The location and uule parameters can't be used together.",
                        required=False,
                    ),
                    PromptArgument(
                        name="gl",
                        description="Parameter defines the country to use for the Google Images search. It's a two-letter country code. (e.g., us for the United States, uk for United Kingdom, or fr for France).",
                        required=False,
                    ),
                    PromptArgument(
                        name="hl",
                        description="Parameter defines the language to use for the Google Images search. It's a two-letter language code. (e.g., en for English, es for Spanish, or fr for French).",
                        required=False,
                    ),
                    PromptArgument(
                        name="ijn",
                        description="Parameter defines the page number for Google Images. It's a zero-based index. (e.g., 0 for the first page, 1 for the second page, etc.).",
                        required=False,
                    ),
                    PromptArgument(
                        name="image_type",
                        description="Parameter defines the type of images. Options: face - Face, photo - Photo, clipart - Clip art, lineart - Line drawing, animated - Animated.",
                        required=False,
                    ),
                    PromptArgument(
                        name="image_color",
                        description="Parameter defines the color of images. Options: bw - Black and white, trans - Transparent, red - Red, orange - Orange, yellow - Yellow, green - Green, teal - Teal, blue - Blue, purple - Purple, pink - Pink, white - White, gray - Gray, black - Black, brown - Brown.",
                        required=False,
                    ),
                    PromptArgument(
                        name="imgsz",
                        description="Parameter defines the size of images. Options: l - Large, m - Medium, i - Icon, etc.",
                        required=False,
                    ),
                    PromptArgument(
                        name="imgar",
                        description="Parameter defines the set aspect ratio of images. Options: s - Square, t - Tall, w - Wide, xw - Panoramic.",
                        required=False,
                    ),
                    PromptArgument(
                        name="safe",
                        description="Parameter defines the level of filtering for adult content. It can be set to active or off, by default Google will blur explicit content.",
                        required=False,
                    ),
                    PromptArgument(
                        name="time_period",
                        description="Parameter defines the time period for filtering results by recency. Supported values include: 'd' (past day), 'w' (past week), 'm' (past month), 'y' (past year).",
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
        
        if name == "google_images_search":
            args = GoogleImagesArgs(**arguments)
            
            # Call the API and get the response in the requested format
            response = await serpapi_server.google_images_search(args)
            
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
            
            if name == "google_images_prompt":
                # Extract parameters from arguments
                q = arguments.get("q")
                location = arguments.get("location")
                gl = arguments.get("gl")
                hl = arguments.get("hl")
                ijn = arguments.get("ijn")
                image_type = arguments.get("image_type")
                image_color = arguments.get("image_color")
                imgsz = arguments.get("imgsz")
                imgar = arguments.get("imgar")
                safe = arguments.get("safe")
                time_period = arguments.get("time_period")
                raw_json = arguments.get("raw_json", False)
                readable_json = arguments.get("readable_json", False)
                
                messages = []
                
                # System message
                messages.append(PromptMessage(
                    role="system",
                    content="You are a helpful assistant that can search for images on Google Images and provide information about the search results."
                ))
                
                # User message
                user_message = "I want to search for images"
                if q:
                    user_message += f" of '{q}'"
                if location:
                    user_message += f" in {location}"
                if gl:
                    user_message += f" from {gl}"
                if hl:
                    user_message += f" in {hl} language"
                if ijn is not None:
                    user_message += f" on page {ijn + 1}"
                
                # Add filter information
                filters = []
                if image_type:
                    filters.append(f"type: {image_type}")
                if image_color:
                    filters.append(f"color: {image_color}")
                if imgsz:
                    filters.append(f"size: {imgsz}")
                if imgar:
                    filters.append(f"aspect ratio: {imgar}")
                if safe:
                    filters.append(f"safe search: {safe}")
                if time_period:
                    filters.append(f"time period: {time_period}")
                
                if filters:
                    user_message += f" with filters ({', '.join(filters)})"
                
                user_message += "."
                
                messages.append(PromptMessage(
                    role="user",
                    content=user_message
                ))
                
                # Prepare search arguments
                search_args = {}
                if q:
                    search_args["q"] = q
                if location:
                    search_args["location"] = location
                if gl:
                    search_args["gl"] = gl
                if hl:
                    search_args["hl"] = hl
                if ijn is not None:
                    search_args["ijn"] = ijn
                if image_type:
                    search_args["image_type"] = image_type
                if image_color:
                    search_args["image_color"] = image_color
                if imgsz:
                    search_args["imgsz"] = imgsz
                if imgar:
                    search_args["imgar"] = imgar
                if safe:
                    search_args["safe"] = safe
                if time_period:
                    search_args["time_period"] = time_period
                
                search_args["raw_json"] = raw_json
                search_args["readable_json"] = readable_json
                
                tool_calls = [
                    {
                        "id": "google_images_search_1",
                        "type": "function",
                        "function": {
                            "name": "google_images_search",
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
    
    print("Starting SerpAPI Google Images MCP server...", file=sys.stderr)
    
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