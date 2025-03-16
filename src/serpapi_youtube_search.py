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

class YouTubeSearchArgs(BaseModel):
    """Arguments for YouTube search using SerpAPI."""
    search_query: Annotated[
        str, 
        Field(
            description="YouTube search query. You can use anything that you would use in a regular YouTube search."
        )
    ]
    gl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Country code for YouTube search results (e.g., 'us' for United States, 'uk' for United Kingdom, 'fr' for France). Determines the country-specific version of YouTube to use.",
        ),
    ] = None
    hl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Language code for YouTube search results (e.g., 'en' for English, 'es' for Spanish, 'fr' for French). Determines the language of the YouTube interface and results.",
        ),
    ] = None
    sp: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Special parameter for filtering results or pagination. Can be used to filter by upload date, quality (4K), etc. Also used for pagination with tokens from previous responses.",
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

class YouTubeVideoArgs(BaseModel):
    """Arguments for YouTube video details using SerpAPI."""
    v: Annotated[
        str, 
        Field(
            description="YouTube video ID. This is the unique identifier for the video you want to get details about."
        )
    ]
    gl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Country code for YouTube video results (e.g., 'us' for United States, 'uk' for United Kingdom, 'fr' for France). Determines the country-specific version of YouTube to use.",
        ),
    ] = None
    hl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Language code for YouTube video results (e.g., 'en' for English, 'es' for Spanish, 'fr' for French). Determines the language of the YouTube interface and results.",
        ),
    ] = None
    next_page_token: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Token for retrieving next page of related videos, comments or replies. Should be one of related_videos_next_page_token, comments_next_page_token, comments_sorting_token.token, or replies_next_page_token from previous responses.",
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

class YouTubeVideoResult(BaseModel):
    """Single video result from YouTube search."""
    position: Optional[int] = None
    title: str
    link: str
    thumbnail: Optional[Union[str, Dict[str, str]]] = None
    channel: Optional[Dict[str, Any]] = None
    published_date: Optional[str] = None
    views: Optional[int] = None
    length: Optional[str] = None
    description: Optional[str] = None
    extensions: Optional[List[str]] = None
    video_id: Optional[str] = None

class YouTubeSearchResponseData(BaseModel):
    """The data field of the SerpAPI YouTube search response."""
    search_metadata: Dict[str, Any]
    search_parameters: Dict[str, Any]
    search_information: Optional[Dict[str, Any]] = None
    video_results: Optional[List[YouTubeVideoResult]] = None
    channel_results: Optional[List[Dict[str, Any]]] = None
    playlist_results: Optional[List[Dict[str, Any]]] = None
    shorts_results: Optional[List[Dict[str, Any]]] = None
    related_searches: Optional[List[Dict[str, Any]]] = None
    pagination: Optional[Dict[str, Any]] = None
    serpapi_pagination: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class YouTubeVideoResponseData(BaseModel):
    """The data field of the SerpAPI YouTube video response."""
    search_metadata: Dict[str, Any]
    search_parameters: Dict[str, Any]
    video_information: Optional[Dict[str, Any]] = None
    video_details: Optional[Dict[str, Any]] = None
    related_videos: Optional[List[Dict[str, Any]]] = None
    comments: Optional[List[Dict[str, Any]]] = None
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

class SerpApiYouTubeServer:
    """Server for SerpAPI YouTube search."""
    
    def __init__(self, api_key: str):
        """Initialize the SerpAPI server with an API key."""
        self.api_key = api_key
        self.base_url = "https://serpapi.com"
        self.endpoints = {
            "SEARCH": "/search",
        }
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour in seconds
        print(f"Initializing SerpAPI YouTube server with API key: {api_key[:5]}...", file=sys.stderr)

    async def youtube_search(self, args: YouTubeSearchArgs) -> Union[Dict[str, Any], str]:
        """Search YouTube using SerpAPI."""
        # Build the cache key from the search parameters
        cache_key_parts = []
        cache_key_parts.append(f"search_query={args.search_query}")
        if args.gl:
            cache_key_parts.append(f"gl={args.gl}")
        if args.hl:
            cache_key_parts.append(f"hl={args.hl}")
        if args.sp:
            cache_key_parts.append(f"sp={args.sp}")
        
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

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # Prepare request parameters
            params = {
                "engine": "youtube",
                "search_query": args.search_query,
                "api_key": self.api_key,
            }
            
            # Add optional parameters if provided
            if args.gl:
                params["gl"] = args.gl
            if args.hl:
                params["hl"] = args.hl
            if args.sp:
                params["sp"] = args.sp
            
            try:
                print(f"Making SerpAPI YouTube search request for query: {args.search_query}", file=sys.stderr)
                async with session.get(
                    f"{self.base_url}{self.endpoints['SEARCH']}",
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
                            error_model = YouTubeSearchResponseData(**error_response)
                            formatted_response = self.format_youtube_search_results(error_model)
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
                        search_response = YouTubeSearchResponseData(**raw_data)
                        formatted_response = self.format_youtube_search_results(search_response)
                    else:
                        # Clean JSON mode (default) - return dict instead of model
                        formatted_response = clean_json_dict(raw_data)
                    
                    # Cache the formatted response
                    self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                    return formatted_response
                    
            except Exception as e:
                print(f"Error in youtube_search: {str(e)}", file=sys.stderr)
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
                    error_model = YouTubeSearchResponseData(**error_response)
                    formatted_response = self.format_youtube_search_results(error_model)
                else:
                    # Return clean dict for error response
                    formatted_response = clean_json_dict(error_response)
                
                # Cache the formatted error response
                self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                return formatted_response

    async def youtube_video(self, args: YouTubeVideoArgs) -> Union[Dict[str, Any], str]:
        """Get YouTube video details using SerpAPI."""
        # Build the cache key from the search parameters
        cache_key_parts = []
        cache_key_parts.append(f"v={args.v}")
        if args.gl:
            cache_key_parts.append(f"gl={args.gl}")
        if args.hl:
            cache_key_parts.append(f"hl={args.hl}")
        if args.next_page_token:
            cache_key_parts.append(f"next_page_token={args.next_page_token}")
        
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

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # Prepare request parameters
            params = {
                "engine": "youtube_video",
                "v": args.v,
                "api_key": self.api_key,
            }
            
            # Add optional parameters if provided
            if args.gl:
                params["gl"] = args.gl
            if args.hl:
                params["hl"] = args.hl
            if args.next_page_token:
                params["next_page_token"] = args.next_page_token
            
            try:
                print(f"Making SerpAPI YouTube video request for video ID: {args.v}", file=sys.stderr)
                async with session.get(
                    f"{self.base_url}{self.endpoints['SEARCH']}",
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
                            error_model = YouTubeVideoResponseData(**error_response)
                            formatted_response = self.format_youtube_video_results(error_model)
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
                        video_response = YouTubeVideoResponseData(**raw_data)
                        formatted_response = self.format_youtube_video_results(video_response)
                    else:
                        # Clean JSON mode (default) - return dict instead of model
                        formatted_response = clean_json_dict(raw_data)
                    
                    # Cache the formatted response
                    self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                    return formatted_response
                    
            except Exception as e:
                print(f"Error in youtube_video: {str(e)}", file=sys.stderr)
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
                    error_model = YouTubeVideoResponseData(**error_response)
                    formatted_response = self.format_youtube_video_results(error_model)
                else:
                    # Return clean dict for error response
                    formatted_response = clean_json_dict(error_response)
                
                # Cache the formatted error response
                self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                return formatted_response

    def format_youtube_search_results(self, response: YouTubeSearchResponseData) -> str:
        """Format YouTube search results as human-readable text."""
        result = []
        
        # Add search information
        if response.search_information:
            result.append(f"Search Information:")
            if "total_results" in response.search_information:
                result.append(f"  Total Results: {response.search_information['total_results']}")
            result.append("")
        
        # Add video results
        if response.video_results:
            result.append(f"Video Results ({len(response.video_results)}):")
            for i, video in enumerate(response.video_results):
                result.append(f"  {i+1}. {video.title}")
                result.append(f"     Link: {video.link}")
                if video.channel and "name" in video.channel:
                    result.append(f"     Channel: {video.channel['name']}")
                if video.published_date:
                    result.append(f"     Published: {video.published_date}")
                if video.views:
                    result.append(f"     Views: {video.views}")
                if video.length:
                    result.append(f"     Length: {video.length}")
                # Handle thumbnail format
                if video.thumbnail:
                    thumbnail_url = video.thumbnail
                    if isinstance(thumbnail_url, dict) and 'static' in thumbnail_url:
                        thumbnail_url = thumbnail_url['static']
                    result.append(f"     Thumbnail: {thumbnail_url}")
                if video.description:
                    result.append(f"     Description: {video.description}")
                result.append("")
        
        # Add channel results
        if response.channel_results:
            result.append(f"Channel Results ({len(response.channel_results)}):")
            for i, channel in enumerate(response.channel_results):
                result.append(f"  {i+1}. {channel.get('name', 'Unknown Channel')}")
                if "link" in channel:
                    result.append(f"     Link: {channel['link']}")
                if "subscribers" in channel:
                    result.append(f"     Subscribers: {channel['subscribers']}")
                result.append("")
        
        # Add playlist results
        if response.playlist_results:
            result.append(f"Playlist Results ({len(response.playlist_results)}):")
            for i, playlist in enumerate(response.playlist_results):
                result.append(f"  {i+1}. {playlist.get('title', 'Unknown Playlist')}")
                if "link" in playlist:
                    result.append(f"     Link: {playlist['link']}")
                if "video_count" in playlist:
                    result.append(f"     Videos: {playlist['video_count']}")
                result.append("")
        
        # Add shorts results
        if response.shorts_results:
            result.append(f"Shorts Results ({len(response.shorts_results)}):")
            for i, short in enumerate(response.shorts_results):
                result.append(f"  {i+1}. {short.get('title', 'Unknown Short')}")
                if "link" in short:
                    result.append(f"     Link: {short['link']}")
                if "views" in short:
                    result.append(f"     Views: {short['views']}")
                result.append("")
        
        # Add related searches
        if response.related_searches:
            result.append(f"Related Searches:")
            for i, related in enumerate(response.related_searches):
                result.append(f"  {i+1}. {related.get('query', 'Unknown Query')}")
            result.append("")
        
        return "\n".join(result)

    def format_youtube_video_results(self, response: YouTubeVideoResponseData) -> str:
        """Format YouTube video details as human-readable text."""
        result = []
        
        # Add video information
        if response.video_information:
            result.append(f"Video Information:")
            if "title" in response.video_information:
                result.append(f"  Title: {response.video_information['title']}")
            if "channel" in response.video_information and "name" in response.video_information["channel"]:
                result.append(f"  Channel: {response.video_information['channel']['name']}")
            if "views" in response.video_information:
                result.append(f"  Views: {response.video_information['views']}")
            if "upload_date" in response.video_information:
                result.append(f"  Upload Date: {response.video_information['upload_date']}")
            if "length" in response.video_information:
                result.append(f"  Length: {response.video_information['length']}")
            result.append("")
        
        # Add video details
        if response.video_details:
            result.append(f"Video Details:")
            if "description" in response.video_details:
                result.append(f"  Description: {response.video_details['description']}")
            if "likes" in response.video_details:
                result.append(f"  Likes: {response.video_details['likes']}")
            if "category" in response.video_details:
                result.append(f"  Category: {response.video_details['category']}")
            result.append("")
        
        # Add related videos
        if response.related_videos:
            result.append(f"Related Videos ({len(response.related_videos)}):")
            for i, video in enumerate(response.related_videos):
                result.append(f"  {i+1}. {video.get('title', 'Unknown Video')}")
                if "link" in video:
                    result.append(f"     Link: {video['link']}")
                if "channel" in video and "name" in video["channel"]:
                    result.append(f"     Channel: {video['channel']['name']}")
                if "views" in video:
                    result.append(f"     Views: {video['views']}")
                if "length" in video:
                    result.append(f"     Length: {video['length']}")
                # Handle thumbnail format
                if "thumbnail" in video:
                    thumbnail_url = video["thumbnail"]
                    if isinstance(thumbnail_url, dict) and 'static' in thumbnail_url:
                        thumbnail_url = thumbnail_url['static']
                    result.append(f"     Thumbnail: {thumbnail_url}")
                result.append("")
        
        # Add comments
        if response.comments:
            result.append(f"Comments ({len(response.comments)}):")
            for i, comment in enumerate(response.comments):
                result.append(f"  {i+1}. {comment.get('author', {}).get('name', 'Unknown User')}:")
                if "text" in comment:
                    result.append(f"     {comment['text']}")
                if "likes" in comment:
                    result.append(f"     Likes: {comment['likes']}")
                if "published_date" in comment:
                    result.append(f"     Published: {comment['published_date']}")
                result.append("")
        
        return "\n".join(result)

def clean_json_dict(data):
    """Remove null, empty lists, and empty dicts from a dict, recursively."""
    if isinstance(data, dict):
        return {
            k: clean_json_dict(v)
            for k, v in data.items()
            if v is not None and v != [] and v != {} and v != ""
        }
    elif isinstance(data, list):
        return [clean_json_dict(v) for v in data if v is not None and v != [] and v != {} and v != ""]
    else:
        return data

async def serve(api_key: str) -> None:
    """Start the SerpAPI YouTube MCP server."""
    server = Server("mcp-serpapi-youtube-search")
    serpapi_youtube_server = SerpApiYouTubeServer(api_key)
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        print("list_tools called", file=sys.stderr)
        return [
            Tool(
                name="youtube_search",
                description="""Search YouTube and get video, channel, playlist, and shorts results.
                
                Provides comprehensive search results from YouTube, including videos, channels, 
                playlists, shorts, and related searches. Supports various parameters to customize 
                your search experience.
                
                You can specify country (gl) and language (hl) settings. Additionally, you can use the sp parameter
                for filtering results or pagination.
                
                Set readable_json=True to get markdown-formatted text instead of JSON.
                
                This tool is ideal for finding videos, channels, and content on YouTube.""",
                inputSchema=YouTubeSearchArgs.model_json_schema(),
            ),
            Tool(
                name="youtube_video",
                description="""Get detailed information about a specific YouTube video.
                
                Returns comprehensive details about a YouTube video, including title, channel, 
                views, upload date, description, likes, category, related videos, and comments.
                
                You can specify country (gl) and language (hl) settings. Additionally, you can use the 
                next_page_token parameter for pagination of related videos, comments, or replies.
                
                Set readable_json=True to get markdown-formatted text instead of JSON.
                
                This tool is ideal for getting detailed information about a specific YouTube video.""",
                inputSchema=YouTubeVideoArgs.model_json_schema(),
            ),
        ]
    
    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        print("list_prompts called", file=sys.stderr)
        return [
            Prompt(
                name="youtube_search_prompt",
                description="""Search YouTube and get video, channel, playlist, and shorts results.
                
                By default, results are returned as cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON for easier reading.
                """,
                arguments=[
                    PromptArgument(
                        name="search_query",
                        description="YouTube search query. You can use anything that you would use in a regular YouTube search.",
                        required=True,
                    ),
                    PromptArgument(
                        name="gl",
                        description="Country code for YouTube search results (e.g., 'us' for United States, 'uk' for United Kingdom, 'fr' for France).",
                        required=False,
                    ),
                    PromptArgument(
                        name="hl",
                        description="Language code for YouTube search results (e.g., 'en' for English, 'es' for Spanish, 'fr' for French).",
                        required=False,
                    ),
                    PromptArgument(
                        name="sp",
                        description="Special parameter for filtering results or pagination. Can be used to filter by upload date, quality (4K), etc.",
                        required=False,
                    ),
                    PromptArgument(
                        name="raw_json",
                        description="Return the complete raw JSON response directly from the SerpAPI server without any processing or validation.",
                        required=False,
                    ),
                    PromptArgument(
                        name="readable_json",
                        description="Return results in markdown-formatted text instead of JSON.",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="youtube_video_prompt",
                description="""Get detailed information about a specific YouTube video.
                
                By default, results are returned as cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON for easier reading.
                """,
                arguments=[
                    PromptArgument(
                        name="v",
                        description="YouTube video ID. This is the unique identifier for the video you want to get details about.",
                        required=True,
                    ),
                    PromptArgument(
                        name="gl",
                        description="Country code for YouTube video results (e.g., 'us' for United States, 'uk' for United Kingdom, 'fr' for France).",
                        required=False,
                    ),
                    PromptArgument(
                        name="hl",
                        description="Language code for YouTube video results (e.g., 'en' for English, 'es' for Spanish, 'fr' for French).",
                        required=False,
                    ),
                    PromptArgument(
                        name="next_page_token",
                        description="Token for retrieving next page of related videos, comments or replies.",
                        required=False,
                    ),
                    PromptArgument(
                        name="raw_json",
                        description="Return the complete raw JSON response directly from the SerpAPI server without any processing or validation.",
                        required=False,
                    ),
                    PromptArgument(
                        name="readable_json",
                        description="Return results in markdown-formatted text instead of JSON.",
                        required=False,
                    ),
                ],
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        print(f"call_tool called with name: {name}, arguments: {arguments}", file=sys.stderr)
        
        if name == "youtube_search":
            args = YouTubeSearchArgs(**arguments)
            response = await serpapi_youtube_server.youtube_search(args)
            
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
        
        elif name == "youtube_video":
            args = YouTubeVideoArgs(**arguments)
            response = await serpapi_youtube_server.youtube_video(args)
            
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
        
        if name == "youtube_search_prompt":
            if arguments is None:
                arguments = {}
            
            search_query = arguments.get("search_query")
            gl = arguments.get("gl")
            hl = arguments.get("hl")
            sp = arguments.get("sp")
            raw_json = arguments.get("raw_json", False)
            readable_json = arguments.get("readable_json", False)
            
            messages = []
            
            # System message
            messages.append(PromptMessage(
                role="system",
                content="You are a helpful assistant that can search for videos, channels, and playlists on YouTube. "
                        "Provide informative and concise summaries of the search results."
            ))
            
            # User message
            user_message = "I want to search for videos on YouTube"
            if search_query:
                user_message += f" about {search_query}"
            if gl:
                user_message += f" in {gl}"
            if hl:
                user_message += f" in language {hl}"
            if sp:
                user_message += f" with special filtering"
            user_message += "."
            
            messages.append(PromptMessage(
                role="user",
                content=user_message
            ))
            
            # Assistant message
            search_args = {}
            if search_query:
                search_args["search_query"] = search_query
            if gl:
                search_args["gl"] = gl
            if hl:
                search_args["hl"] = hl
            if sp:
                search_args["sp"] = sp
            
            search_args["raw_json"] = raw_json
            search_args["readable_json"] = readable_json
            
            tool_calls = [
                {
                    "id": "youtube_search_1",
                    "type": "function",
                    "function": {
                        "name": "youtube_search",
                        "arguments": json.dumps(search_args)
                    }
                }
            ]
            
            return GetPromptResult(
                messages=messages,
                tool_calls=tool_calls,
            )
        
        elif name == "youtube_video_prompt":
            if arguments is None:
                arguments = {}
            
            v = arguments.get("v")
            gl = arguments.get("gl")
            hl = arguments.get("hl")
            next_page_token = arguments.get("next_page_token")
            raw_json = arguments.get("raw_json", False)
            readable_json = arguments.get("readable_json", False)
            
            messages = []
            
            # System message
            messages.append(PromptMessage(
                role="system",
                content="You are a helpful assistant that can get detailed information about YouTube videos. "
                        "Provide informative and concise summaries of the video details."
            ))
            
            # User message
            user_message = "I want to get information about a YouTube video"
            if v:
                user_message += f" with ID {v}"
            if gl:
                user_message += f" in {gl}"
            if hl:
                user_message += f" in language {hl}"
            if next_page_token:
                user_message += f" with pagination"
            user_message += "."
            
            messages.append(PromptMessage(
                role="user",
                content=user_message
            ))
            
            # Assistant message
            video_args = {}
            if v:
                video_args["v"] = v
            if gl:
                video_args["gl"] = gl
            if hl:
                video_args["hl"] = hl
            if next_page_token:
                video_args["next_page_token"] = next_page_token
            
            video_args["raw_json"] = raw_json
            video_args["readable_json"] = readable_json
            
            tool_calls = [
                {
                    "id": "youtube_video_1",
                    "type": "function",
                    "function": {
                        "name": "youtube_video",
                        "arguments": json.dumps(video_args)
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
    
    print("Starting SerpAPI YouTube MCP server...", file=sys.stderr)
    
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)

if __name__ == "__main__":
    load_dotenv()
    api_key = os.environ.get("SERPAPI_KEY")
    
    if not api_key:
        print("Error: SERPAPI_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)
    
    asyncio.run(serve(api_key)) 