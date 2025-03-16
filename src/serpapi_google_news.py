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
# not sure if this is correct(can find it in the url of the google news page for each topic)
# should add more topic-section tokens
TOPIC_TOKENS = {
    "Business": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB",
    "U.S.": "CAAqIggKIhxDQkFTRHdvSkwyMHZNRGxqTjNjd0VnSmxiaWdBUAE",
    "World": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB",
    "Technology": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB",
    "Entertainment": "CAAqJggKIiBDQkFTRWdvSUwyMHZNREpxYW5RU0FtVnVHZ0pWVXlnQVAB",
    "Sports": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp1ZEdvU0FtVnVHZ0pWVXlnQVAB",
    "Science": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp0Y1RjU0FtVnVHZ0pWVXlnQVAB",
    "Health": "CAAqIQgKIhtDQkFTRGdvSUwyMHZNR3QwTlRFU0FtVnVLQUFQAQ",
    "Headlines": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRFZxYUdjU0FtVnVHZ0pWVXlnQVAB"
}

class GoogleNewsSearchArgs(BaseModel):
    """Arguments for Google News search using SerpAPI."""
    q: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Search query for Google News. You can use anything that you would use in a regular Google News search, including operators like 'site:' and 'when:'. Cannot be used together with publication_token, story_token, or topic_token.",
        ),
    ] = None
    gl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Google country code (e.g., 'us' for United States, 'uk' for United Kingdom, 'fr' for France). Determines the country-specific version of Google News to use.",
        ),
    ] = None
    hl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Google UI language code (e.g., 'en' for English, 'es' for Spanish, 'fr' for French). Determines the language of the Google News interface and results.",
        ),
    ] = None
    publication_token: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Token used for retrieving news results from a specific publication (e.g., CNN, BBC). Found in Google News URLs after '/publications/'. Cannot be used together with q, story_token, or topic_token.",
        ),
    ] = None
    topic_token: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Token used for retrieving news results from a specific topic (e.g., World, Business, Technology). Found in Google News URLs after '/topics/'. Cannot be used together with q, story_token, or publication_token. Note that when using topic_token, the response format may differ from regular search results.",
        ),
    ] = None
    story_token: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Token used for retrieving news results with full coverage of a specific story. Found in Google News URLs after '/stories/'. Cannot be used together with q, topic_token, or publication_token.",
        ),
    ] = None
    section_token: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Token used for retrieving news results from a specific section (e.g., sub-section of a topic like 'Business -> Economy'). Found in Google News URLs after '/sections/'. Can only be used with topic_token or publication_token.",
        ),
    ] = None
    so: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Sorting method for results. Use '0' for sorting by relevance (default) or '1' for sorting by date. Can only be used with story_token parameter.",
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

    @field_validator('q', 'publication_token', 'topic_token', 'story_token', 'section_token')
    @classmethod
    def validate_search_parameters(cls, v, info):
        """Validate that at least one search parameter is provided."""
        field_name = info.field_name
        model_data = info.data
        
        # Check if q is provided when using tokens
        if field_name == 'q' and v is None:
            # If q is None, at least one token should be provided
            if not any([
                model_data.get('publication_token'),
                model_data.get('topic_token'),
                model_data.get('story_token'),
                model_data.get('section_token')
            ]):
                raise ValueError("Either 'q' or at least one token parameter must be provided")
        
        # Check token exclusivity
        if field_name in ['publication_token', 'topic_token', 'story_token', 'section_token'] and v is not None:
            # If a token is provided, q should not be provided
            if model_data.get('q') is not None and field_name in ['topic_token', 'story_token']:
                raise ValueError(f"'{field_name}' cannot be used together with 'q'")
        
        return v

class GoogleNewsSource(BaseModel):
    """Source information for a Google News result."""
    title: Optional[str] = None
    name: Optional[str] = None
    icon: Optional[str] = None
    authors: Optional[List[str]] = None

class GoogleNewsAuthor(BaseModel):
    """Author information for a Google News result."""
    thumbnail: Optional[str] = None
    name: Optional[str] = None
    handle: Optional[str] = None

class GoogleNewsResult(BaseModel):
    """Single news result from Google News."""
    position: Optional[int] = None
    title: Optional[str] = None
    link: Optional[str] = None
    snippet: Optional[str] = None
    source: Optional[GoogleNewsSource] = None
    author: Optional[GoogleNewsAuthor] = None
    thumbnail: Optional[str] = None
    thumbnail_small: Optional[str] = None
    type: Optional[str] = None
    video: Optional[bool] = None
    topic_token: Optional[str] = None
    story_token: Optional[str] = None
    serpapi_link: Optional[str] = None
    date: Optional[str] = None
    related_topics: Optional[List[Dict[str, Any]]] = None
    highlight: Optional[Dict[str, Any]] = None
    stories: Optional[List[Dict[str, Any]]] = None

class GoogleNewsResponseData(BaseModel):
    """The data field of the SerpAPI Google News search response."""
    search_metadata: Dict[str, Any]
    search_parameters: Dict[str, Any]
    title: Optional[str] = None
    news_results: Optional[List[GoogleNewsResult]] = None
    top_stories_link: Optional[Dict[str, Any]] = None
    menu_links: Optional[List[Dict[str, Any]]] = None
    sub_menu_links: Optional[List[Dict[str, Any]]] = None
    related_topics: Optional[List[Dict[str, Any]]] = None
    related_publications: Optional[List[Dict[str, Any]]] = None
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

class SerpApiGoogleNewsServer:
    """Server for Google News search using SerpAPI."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search"
        self.cache = {}  # Simple in-memory cache
        self.cache_ttl = 3600  # Cache TTL in seconds (1 hour)
        
    async def google_news_search(self, args: GoogleNewsSearchArgs) -> Union[Dict[str, Any], str]:
        """Perform a Google News search using SerpAPI."""
        # Build the cache key from the search parameters
        cache_key_parts = []
        if args.q:
            cache_key_parts.append(f"q={args.q}")
        if args.gl:
            cache_key_parts.append(f"gl={args.gl}")
        if args.hl:
            cache_key_parts.append(f"hl={args.hl}")
        if args.publication_token:
            cache_key_parts.append(f"publication_token={args.publication_token}")
        if args.topic_token:
            cache_key_parts.append(f"topic_token={args.topic_token}")
        if args.story_token:
            cache_key_parts.append(f"story_token={args.story_token}")
        if args.section_token:
            cache_key_parts.append(f"section_token={args.section_token}")
        if args.so:
            cache_key_parts.append(f"so={args.so}")
            
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
            "engine": "google_news",
            "api_key": self.api_key,
        }
        
        # Add optional parameters if provided
        if args.q:
            params["q"] = args.q
        if args.gl:
            params["gl"] = args.gl
        if args.hl:
            params["hl"] = args.hl
        if args.publication_token:
            params["publication_token"] = args.publication_token
        if args.topic_token:
            params["topic_token"] = args.topic_token
        if args.story_token:
            params["story_token"] = args.story_token
        if args.section_token:
            params["section_token"] = args.section_token
        if args.so:
            params["so"] = args.so
        
        # Make the API request
        try:
            async with aiohttp.ClientSession() as session:
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
                            error_model = GoogleNewsResponseData(**error_response)
                            formatted_response = self.format_google_news_results(error_model)
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
                    
                    # For other formats, preprocess the data
                    if 'news_results' in raw_data:
                        for result in raw_data['news_results']:
                            # Extract title and link from highlight if they're not directly available
                            if 'title' not in result and 'highlight' in result and result['highlight'] and 'title' in result['highlight']:
                                result['title'] = result['highlight']['title']
                            
                            if 'link' not in result and 'highlight' in result and result['highlight'] and 'link' in result['highlight']:
                                result['link'] = result['highlight']['link']
                    
                    # Format based on the requested format
                    if args.readable_json:
                        # Convert to model for readable format
                        news_response = GoogleNewsResponseData(**raw_data)
                        formatted_response = self.format_google_news_results(news_response)
                    else:
                        # Clean JSON mode (default) - return dict instead of model
                        formatted_response = clean_json_dict(raw_data)
                    
                    # Cache the formatted response
                    self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                    return formatted_response
                    
        except Exception as e:
            print(f"Error in google_news_search: {str(e)}", file=sys.stderr)
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
                error_model = GoogleNewsResponseData(**error_response)
                formatted_response = self.format_google_news_results(error_model)
            else:
                # Return clean dict for error response
                formatted_response = clean_json_dict(error_response)
            
            # Cache the formatted error response
            self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
            return formatted_response
    
    def format_google_news_results(self, response: GoogleNewsResponseData) -> str:
        """Format Google News search results in a human-readable format."""
        result_text = []
        
        # Add title if available
        if response.title:
            result_text.append(f"# {response.title}")
            result_text.append("")
        
        # Add news results
        if response.news_results:
            result_text.append("## News Results")
            result_text.append("")
            
            for i, result in enumerate(response.news_results):
                # Extract title from highlight if not directly available
                title = result.title
                if title is None and result.highlight and 'title' in result.highlight:
                    title = result.highlight['title']
                
                # Extract link from highlight if not directly available
                link = result.link
                if link is None and result.highlight and 'link' in result.highlight:
                    link = result.highlight['link']
                
                if title:
                    result_text.append(f"{i+1}. **{title}**")
                else:
                    result_text.append(f"{i+1}. **[No title available]**")
                
                if result.source and result.source.name:
                    source_text = f"Source: {result.source.name}"
                    if result.source.authors:
                        source_text += f" | Authors: {', '.join(result.source.authors)}"
                    result_text.append(source_text)
                if result.date:
                    result_text.append(f"Date: {result.date}")
                if result.snippet:
                    result_text.append(f"{result.snippet}")
                
                if link:
                    result_text.append(f"Link: {link}")
                result_text.append("")
        elif response.error:
            result_text.append("## Error")
            result_text.append(f"{response.error}")
            result_text.append("")
        else:
            result_text.append("## No News Results Found")
            result_text.append("")
        
        # Add related topics if available
        if response.related_topics:
            result_text.append("## Related Topics")
            result_text.append("")
            
            for topic in response.related_topics:
                if "title" in topic:
                    result_text.append(f"- {topic['title']}")
            
            result_text.append("")
        
        # Add related publications if available
        if response.related_publications:
            result_text.append("## Related Publications")
            result_text.append("")
            
            for pub in response.related_publications:
                if "title" in pub:
                    result_text.append(f"- {pub['title']}")
            
            result_text.append("")
        
        # Add pagination info if available
        if response.pagination:
            result_text.append("## Pagination")
            if "current" in response.pagination:
                result_text.append(f"Current Page: {response.pagination['current']}")
            if "next" in response.pagination:
                result_text.append(f"Next Page Available: Yes")
            
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
    """Start the SerpAPI Google News MCP server."""
    server = Server("mcp-serpapi-google-news")
    serpapi_google_news_server = SerpApiGoogleNewsServer(api_key)
    
    # Test API key validity with a simple search request
    try:
        print("Testing API key validity...", file=sys.stderr)
        # Use a minimal search to validate the API key
        test_args = GoogleNewsSearchArgs(q="test")
        await serpapi_google_news_server.google_news_search(test_args)
        print("SerpAPI key validated successfully", file=sys.stderr)
    except Exception as e:
        print(f"Error validating SerpAPI key: {str(e)}", file=sys.stderr)
        sys.exit(1)
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        print("list_tools called", file=sys.stderr)
        return [
            Tool(
                name="google_news_search",
                description="""Search for news articles using Google News via SerpAPI.
                
                Provides comprehensive news results from Google News, including articles, 
                sources, topics, and related publications. Supports various parameters to customize 
                your search experience.
                
                You can specify country (gl) and language (hl) settings, and use various tokens
                for specific publications, topics, stories, or sections.
                
                By default, returns cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON.
                
                This tool is ideal for finding recent news articles, tracking topics, and monitoring publications.""",
                inputSchema=GoogleNewsSearchArgs.model_json_schema(),
            ),
        ]
    
    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        print("list_prompts called", file=sys.stderr)
        return [
            Prompt(
                name="google_news_search_prompt",
                description="""Search for news articles using Google News via SerpAPI.
                
                By default, results are returned as cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON for easier reading.
                """,
                parameters=[
                    PromptArgument(
                        name="query",
                        description="Search query for Google News. You can use operators like 'site:' and 'when:'.",
                        type="string",
                        required=False,
                    ),
                    PromptArgument(
                        name="gl",
                        description="Country code (e.g., 'us' for United States, 'uk' for United Kingdom, 'fr' for France)",
                        type="string",
                        required=False,
                    ),
                    PromptArgument(
                        name="hl",
                        description="Language code (e.g., 'en' for English, 'es' for Spanish, 'fr' for French)",
                        type="string",
                        required=False,
                    ),
                    PromptArgument(
                        name="publication_token",
                        description="Token for a specific publication (e.g., CNN, BBC). Cannot be used with query.",
                        type="string",
                        required=False,
                    ),
                    PromptArgument(
                        name="topic_token",
                        description="Token for a specific topic (e.g., World, Business). Cannot be used with query. Note that responses may have a different structure when using this parameter.",
                        type="string",
                        required=False,
                    ),
                    PromptArgument(
                        name="story_token",
                        description="Token for full coverage of a specific story. Cannot be used with query.",
                        type="string",
                        required=False,
                    ),
                    PromptArgument(
                        name="section_token",
                        description="Token for a specific section. Use with topic_token or publication_token.",
                        type="string",
                        required=False,
                    ),
                    PromptArgument(
                        name="so",
                        description="Sorting method: '0' for relevance (default), '1' for date. Use with story_token.",
                        type="string",
                        required=False,
                    ),
                    PromptArgument(
                        name="raw_json",
                        description="Return the complete raw JSON response directly from the SerpAPI server without any processing or validation. This bypasses all model validation and returns exactly what the API returns.",
                        type="boolean",
                        required=False,
                    ),
                    PromptArgument(
                        name="readable_json",
                        description="Return results in markdown-formatted text instead of JSON. Creates a structured, human-readable document with headings, bold text, and organized sections for easy reading.",
                        type="boolean",
                        required=False,
                    ),
                ],
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        print(f"call_tool called with name: {name}, arguments: {arguments}", file=sys.stderr)
        
        if name == "google_news_search":
            args = GoogleNewsSearchArgs(**arguments)
            
            # Call the API and get the response in the requested format
            response = await serpapi_google_news_server.google_news_search(args)
            
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
        
        if name == "google_news_search_prompt":
            if arguments is None:
                arguments = {}
            
            query = arguments.get("query")
            gl = arguments.get("gl")
            hl = arguments.get("hl")
            publication_token = arguments.get("publication_token")
            topic_token = arguments.get("topic_token")
            story_token = arguments.get("story_token")
            section_token = arguments.get("section_token")
            so = arguments.get("so")
            raw_json = arguments.get("raw_json", False)
            readable_json = arguments.get("readable_json", False)
            
            messages = []
            
            # System message
            messages.append(PromptMessage(
                role="system",
                content="You are a helpful assistant that can search for news articles using Google News. "
                        "Provide informative and concise summaries of the news results."
            ))
            
            # User message
            user_message = "I want to search for news"
            if query:
                user_message += f" about {query}"
            if gl:
                user_message += f" in {gl}"
            if hl:
                user_message += f" in {hl}"
            if publication_token:
                user_message += f" from a specific publication"
            if topic_token:
                user_message += f" on a specific topic"
            if story_token:
                user_message += f" with full coverage of a specific story"
            if section_token:
                user_message += f" from a specific section"
            if so:
                sort_text = "sorted by date" if so == "1" else "sorted by relevance"
                user_message += f" {sort_text}"
            user_message += "."
            
            messages.append(PromptMessage(
                role="user",
                content=user_message
            ))
            
            # Assistant message
            search_args = {}
            if query:
                search_args["q"] = query
            if gl:
                search_args["gl"] = gl
            if hl:
                search_args["hl"] = hl
            if publication_token:
                search_args["publication_token"] = publication_token
            if topic_token:
                search_args["topic_token"] = topic_token
            if story_token:
                search_args["story_token"] = story_token
            if section_token:
                search_args["section_token"] = section_token
            if so:
                search_args["so"] = so
            
            search_args["raw_json"] = raw_json
            search_args["readable_json"] = readable_json
            
            tool_calls = [
                {
                    "id": "google_news_search_1",
                    "type": "function",
                    "function": {
                        "name": "google_news_search",
                        "arguments": json.dumps(search_args)
                    }
                }
            ]
            
            messages.append(PromptMessage(
                role="assistant",
                content="I'll search for news articles for you.",
                tool_calls=tool_calls
            ))
            
            # Tool response message
            try:
                args = GoogleNewsSearchArgs(**search_args)
                response = await serpapi_google_news_server.google_news_search(args)
                
                if isinstance(response, str):
                    tool_response = response
                else:
                    tool_response = serpapi_google_news_server.format_google_news_results(response)
                
                messages.append(PromptMessage(
                    role="tool",
                    content=tool_response,
                    tool_call_id="google_news_search_1"
                ))
                
                # Final assistant message
                messages.append(PromptMessage(
                    role="assistant",
                    content="Here are the news articles I found for you. Let me know if you need more information or have any questions about these results."
                ))
                
            except Exception as e:
                messages.append(PromptMessage(
                    role="tool",
                    content=f"Error searching for news: {str(e)}",
                    tool_call_id="google_news_search_1"
                ))
                
                messages.append(PromptMessage(
                    role="assistant",
                    content="I'm sorry, but I encountered an error while searching for news articles. Please try again with different search parameters."
                ))
            
            return GetPromptResult(messages=messages)
        else:
            raise McpError(ErrorData(
                code=METHOD_NOT_FOUND,
                message=f"Unknown prompt: {name}",
            ))
    
    # This is the missing part - actually run the server
    print("Starting SerpAPI Google News MCP server...", file=sys.stderr)
    
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)

if __name__ == "__main__":
    # Load environment variables from .env file if it exists
    dotenv_path = pathlib.Path(__file__).parent.parent / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path)
    
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("Error: SERPAPI_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)
    
    asyncio.run(serve(api_key)) 