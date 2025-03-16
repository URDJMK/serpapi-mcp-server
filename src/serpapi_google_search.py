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

class GoogleSearchArgs(BaseModel):
    """Arguments for Google search using SerpAPI."""
    q: Annotated[
        str, 
        Field(
            description="Search query for Google. You can use anything that you would use in a regular Google search, including operators like 'site:', 'inurl:', 'intitle:', etc. For more advanced filtering, you can use the include_domains and exclude_domains parameters."
        )
    ]
    num: Annotated[
        Optional[int],
        Field(
            default=10,
            description="Number of search results to return per page. The default is 10. Note that the Google Custom Search JSON API has a maximum value of 10 for this parameter, though SerpAPI may support up to 100. Also note that the API will never return more than 100 results total, so the sum of 'start + num' should not exceed 100. IMPORTANT: Due to Google's Knowledge Graph layout, Google may ignore the num parameter for the first page of results in searches related to celebrities, famous groups, and popular media. If you need num to work as expected, you can set start=1, but be aware that this approach will not return the first organic result and the Knowledge Graph.",
            gt=0,
            lt=100,
        ),
    ] = 10
    start: Annotated[
        Optional[int],
        Field(
            default=None,
            description="The index of the first result to return (1-based indexing). This is useful for pagination. For example, to get the second page of results with 10 results per page, set start=11. Note that the API will never return more than 100 results total, so the sum of 'start + num' should not exceed 100. IMPORTANT: Setting start=1 can be used as a workaround when Google ignores the num parameter due to Knowledge Graph results, but this will cause the first organic result and Knowledge Graph to be omitted from the results.",
            ge=1,
        ),
    ] = None
    location: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Location to search from (e.g., 'Austin, Texas, United States'). Determines the geographic context for search results. It is recommended to specify location at the city level to simulate a real user's search.",
        ),
    ] = None
    gl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Google country code (e.g., 'us' for United States, 'uk' for United Kingdom, 'fr' for France). Determines the country-specific version of Google to use.",
        ),
    ] = None
    hl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Google UI language code (e.g., 'en' for English, 'es' for Spanish, 'fr' for French). Determines the language of the Google interface and results.",
        ),
    ] = None
    device: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Device type to simulate for the search. Can be 'desktop' (default), 'mobile', or 'tablet'. Different devices may receive different search results and formats.",
        ),
    ] = None
    safe: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Safe search setting. Can be 'active' to filter explicit content or 'off' to disable filtering. If not specified, Google's default setting is used.",
        ),
    ] = None
    filter: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Controls whether to filter duplicate content. Can be set to '0' (off) or '1' (on). When turned on, duplicate content from the same site is filtered from the search results.",
        ),
    ] = None
    time_period: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Time period for filtering results by recency. Supported values include: 'd' (past day), 'w' (past week), 'm' (past month), 'y' (past year). You can also specify a number with these letters, e.g., 'd3' for past 3 days.",
        ),
    ] = None
    exactTerms: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Identifies a word or phrase that should appear exactly in the search results. This is useful for finding exact matches of specific terms.",
        ),
    ] = None
    include_domains: Annotated[
        Optional[List[str]],
        Field(
            default=[],
            description="List of domains to specifically include in search results. This is equivalent to using multiple 'site:' operators in the query. For example, ['example.com', 'sample.org'] will only return results from these domains.",
        ),
    ] = []
    exclude_domains: Annotated[
        Optional[List[str]],
        Field(
            default=[],
            description="List of domains to exclude from search results. This is equivalent to using multiple '-site:' operators in the query. For example, ['example.com', 'sample.org'] will exclude results from these domains.",
        ),
    ] = []
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

    @field_validator('include_domains', 'exclude_domains', mode='before')
    @classmethod
    def parse_domains_list(cls, v):
        """Parse domain lists from various input formats.
        
        Handles:
        - None -> []
        - String JSON arrays -> list
        - Comma-separated strings -> list
        - Single domain strings -> [string]
        - Lists -> unchanged
        """
        if v is None:
            return []
        
        # If it's already a list, return it
        if isinstance(v, list):
            return v
        
        # If it's a string, try to parse it
        if isinstance(v, str):
            # Try to parse as JSON
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except:
                pass
            
            # Try to parse as comma-separated list
            if ',' in v:
                return [domain.strip() for domain in v.split(',')]
            
            # Treat as single domain
            return [v]
        
        return v

    @field_validator('start')
    @classmethod
    def validate_start_and_num(cls, v, info):
        """Validate that start + num doesn't exceed 100."""
        if v is not None:
            num = info.data.get('num', 10)
            if v + num > 100:
                raise ValueError("The sum of 'start' and 'num' cannot exceed 100. The API will not return more than 100 results total.")
        return v

class GoogleSearchResult(BaseModel):
    """Single search result from Google."""
    position: int
    title: str
    link: str
    displayed_link: str
    snippet: Optional[str] = None
    snippet_highlighted_words: Optional[List[str]] = None
    date: Optional[str] = None
    favicon: Optional[str] = None
    source_icon: Optional[str] = None
    cached_page_link: Optional[str] = None
    related_pages_link: Optional[str] = None
    sitelinks: Optional[Dict[str, Any]] = None

class SearchResponseData(BaseModel):
    """The data field of the SerpAPI Google search response."""
    search_metadata: Dict[str, Any]
    search_parameters: Dict[str, Any]
    search_information: Optional[Dict[str, Any]] = None
    organic_results: List[GoogleSearchResult]
    related_searches: Optional[List[Dict[str, Any]]] = None
    pagination: Optional[Dict[str, Any]] = None
    serpapi_pagination: Optional[Dict[str, Any]] = None
    knowledge_graph: Optional[Dict[str, Any]] = None
    answer_box: Optional[Dict[str, Any]] = None
    related_questions: Optional[List[Dict[str, Any]]] = None
    shopping_results: Optional[List[Dict[str, Any]]] = None
    top_stories: Optional[List[Dict[str, Any]]] = None
    news_results: Optional[List[Dict[str, Any]]] = None
    local_results: Optional[Dict[str, Any]] = None
    local_map: Optional[Dict[str, Any]] = None
    images_results: Optional[List[Dict[str, Any]]] = None
    video_results: Optional[List[Dict[str, Any]]] = None
    twitter_results: Optional[List[Dict[str, Any]]] = None
    jobs_results: Optional[Dict[str, Any]] = None
    recipes_results: Optional[List[Dict[str, Any]]] = None
    ads: Optional[Dict[str, Any]] = None
    inline_videos: Optional[List[Dict[str, Any]]] = None
    inline_images: Optional[List[Dict[str, Any]]] = None
    inline_shopping: Optional[List[Dict[str, Any]]] = None
    inline_tweets: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None

class GoogleLocationsArgs(BaseModel):
    """Arguments for Google locations API."""
    q: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Query to search for locations",
        ),
    ] = None
    limit: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Limit the number of locations returned",
            gt=0,
        ),
    ] = None

class GoogleAccountArgs(BaseModel):
    """Arguments for Google account API."""
    pass

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

class SerpApiServer:
    """Server for SerpAPI Google search."""
    
    def __init__(self, api_key: str):
        """Initialize the SerpAPI server with an API key."""
        self.api_key = api_key
        self.base_url = "https://serpapi.com"
        self.endpoints = {
            "SEARCH": "/search",
            "LOCATIONS": "/locations.json",
            "ACCOUNT": "/account.json",
        }
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour in seconds
        print(f"Initializing SerpAPI server with API key: {api_key[:5]}...", file=sys.stderr)

    async def search(self, args: GoogleSearchArgs) -> Union[Dict[str, Any], str]:
        """Perform a Google search using SerpAPI."""
        # Build the query parameters
        params = {
            "engine": "google",
            "api_key": self.api_key,
            "q": args.q,
            "num": args.num,
        }
        
        # Add optional parameters if they are provided
        if args.start is not None:
            params["start"] = args.start
        if args.location is not None:
            params["location"] = args.location
        if args.gl is not None:
            params["gl"] = args.gl
        if args.hl is not None:
            params["hl"] = args.hl
        if args.device is not None:
            params["device"] = args.device
        if args.safe is not None:
            params["safe"] = args.safe
        if args.filter is not None:
            params["filter"] = args.filter
        if args.time_period is not None:
            params["tbs"] = f"qdr:{args.time_period}"
        if args.exactTerms is not None:
            params["exactTerms"] = args.exactTerms
        
        # Handle domain inclusion/exclusion
        if args.include_domains:
            # Convert the list to a query string with site: operators
            site_query = " OR ".join([f"site:{domain}" for domain in args.include_domains])
            # Append to the query
            params["q"] = f"({params['q']}) {site_query}"
        
        if args.exclude_domains:
            # Convert the list to a query string with -site: operators
            exclude_query = " ".join([f"-site:{domain}" for domain in args.exclude_domains])
            # Append to the query
            params["q"] = f"{params['q']} {exclude_query}"
        
        # Create a cache key from the parameters
        cache_key = json.dumps(params, sort_keys=True)
        
        # Add format to cache key
        if args.raw_json:
            cache_key += "_raw"
        elif args.readable_json:
            cache_key += "_readable"
        else:
            cache_key += "_clean"
        
        # Check if we have a cached response
        if cache_key in self.cache:
            print(f"Using cached response for {cache_key}", file=sys.stderr)
            cached_response = self.cache[cache_key].response
            return cached_response
        
        # Make the API request
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"Error from SerpAPI: {error_text}", file=sys.stderr)
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"SerpAPI returned an error: {response.status} - {error_text}"
                        ))
                    
                    # Parse the JSON response
                    json_response = await response.json()
                    
                    # Check for error in the response
                    if "error" in json_response:
                        print(f"Error in SerpAPI response: {json_response['error']}", file=sys.stderr)
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"SerpAPI returned an error: {json_response['error']}"
                        ))
                    
                    # Process the response based on the requested format
                    if args.raw_json:
                        # Return the raw JSON response
                        self.cache[cache_key] = CachedSearch(cache_key, json_response)
                        return json_response
                    elif args.readable_json:
                        # Parse the response into our model first for validation
                        try:
                            response_data = SearchResponseData(**json_response)
                            formatted_response = self.format_search_results(response_data)
                            self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                            return formatted_response
                        except Exception as e:
                            print(f"Error formatting search results: {str(e)}", file=sys.stderr)
                            # Fall back to raw JSON if formatting fails
                            self.cache[cache_key] = CachedSearch(cache_key, json_response)
                            return json_response
                    else:
                        # Return clean dict instead of model
                        clean_response = clean_json_dict(json_response)
                        self.cache[cache_key] = CachedSearch(cache_key, clean_response)
                        return clean_response
        
        except aiohttp.ClientError as e:
            print(f"HTTP error during SerpAPI request: {str(e)}", file=sys.stderr)
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"HTTP error during SerpAPI request: {str(e)}"
            ))
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from SerpAPI: {str(e)}", file=sys.stderr)
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"Error decoding JSON from SerpAPI: {str(e)}"
            ))
        except Exception as e:
            print(f"Unexpected error during SerpAPI request: {str(e)}", file=sys.stderr)
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"Unexpected error during SerpAPI request: {str(e)}"
            ))

    async def locations(self, args: GoogleLocationsArgs) -> Dict[str, Any]:
        """Get Google locations from SerpAPI."""
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            params = {"api_key": self.api_key}
            
            if args.q:
                params["q"] = args.q
            if args.limit:
                params["limit"] = args.limit
            
            try:
                print(f"Making SerpAPI locations request", file=sys.stderr)
                async with session.get(
                    f"{self.base_url}{self.endpoints['LOCATIONS']}",
                    params=params
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"SerpAPI locations error response: {error_text}", file=sys.stderr)
                        try:
                            # Try to parse error as JSON
                            error_json = json.loads(error_text)
                            error_message = error_json.get("error", error_text)
                        except:
                            error_message = error_text
                        
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"SerpAPI locations error: {error_message}"
                        ))
                    
                    data = await response.json()
                    
                    # Check if the response contains an error field
                    if isinstance(data, dict) and "error" in data:
                        print(f"SerpAPI locations returned error: {data['error']}", file=sys.stderr)
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"SerpAPI locations error: {data['error']}"
                        ))
                    
                    return data
            except asyncio.TimeoutError:
                print("SerpAPI locations request timed out", file=sys.stderr)
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message="SerpAPI locations request timed out"
                ))
            except Exception as e:
                if not isinstance(e, McpError):
                    print(f"SerpAPI locations error: {str(e)}", file=sys.stderr)
                    raise McpError(ErrorData(
                        code=INTERNAL_ERROR,
                        message=f"SerpAPI locations error: {str(e)}"
                    ))
                raise

    async def account(self, args: GoogleAccountArgs) -> Dict[str, Any]:
        """Get SerpAPI account information."""
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            params = {"api_key": self.api_key}
            
            try:
                print(f"Making SerpAPI account request to validate API key", file=sys.stderr)
                async with session.get(
                    f"{self.base_url}{self.endpoints['ACCOUNT']}",
                    params=params
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"SerpAPI account error response: {error_text}", file=sys.stderr)
                        try:
                            # Try to parse error as JSON
                            error_json = json.loads(error_text)
                            error_message = error_json.get("error", error_text)
                        except:
                            error_message = error_text
                        
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"SerpAPI account error: {error_message}"
                        ))
                    
                    data = await response.json()
                    
                    # Check if the response contains an error field
                    if "error" in data:
                        print(f"SerpAPI account returned error: {data['error']}", file=sys.stderr)
                        raise McpError(ErrorData(
                            code=INTERNAL_ERROR,
                            message=f"SerpAPI account error: {data['error']}"
                        ))
                    
                    return data
            except asyncio.TimeoutError:
                print("SerpAPI account request timed out", file=sys.stderr)
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message="SerpAPI account request timed out"
                ))
            except Exception as e:
                if not isinstance(e, McpError):
                    print(f"SerpAPI account error: {str(e)}", file=sys.stderr)
                    raise McpError(ErrorData(
                        code=INTERNAL_ERROR,
                        message=f"SerpAPI account error: {str(e)}"
                    ))
                raise

    def format_search_results(self, response: SearchResponseData) -> str:
        """Format search results as human-readable text."""
        result = []
        
        # Add search information
        if response.search_information:
            result.append(f"# Search Information")
            if "total_results" in response.search_information:
                result.append(f"Total Results: {response.search_information['total_results']}")
            if "time_taken_displayed" in response.search_information:
                result.append(f"Time Taken: {response.search_information['time_taken_displayed']}")
            result.append("")
        
        # Add error message if present
        if response.error:
            result.append(f"# Error")
            result.append(response.error)
            result.append("")
            return "\n".join(result)
        
        # Add organic results
        if response.organic_results:
            result.append(f"# Organic Results ({len(response.organic_results)})")
            for i, res in enumerate(response.organic_results):
                result.append(f"## {i+1}. {res.title}")
                result.append(f"Link: {res.link}")
                result.append(f"Displayed Link: {res.displayed_link}")
                if res.snippet:
                    result.append(f"\n{res.snippet}")
                if res.date:
                    result.append(f"\nDate: {res.date}")
                if res.sitelinks:
                    result.append("\nSitelinks:")
                    if "inline" in res.sitelinks:
                        for link in res.sitelinks["inline"]:
                            result.append(f"- [{link.get('title', 'Link')}]({link.get('link', '#')})")
                    if "expanded" in res.sitelinks:
                        for link in res.sitelinks["expanded"]:
                            result.append(f"- [{link.get('title', 'Link')}]({link.get('link', '#')})")
                            if "description" in link:
                                result.append(f"  {link['description']}")
                result.append("")
        
        # Add knowledge graph if present
        if response.knowledge_graph:
            result.append(f"# Knowledge Graph")
            if "title" in response.knowledge_graph:
                result.append(f"## {response.knowledge_graph['title']}")
            if "type" in response.knowledge_graph:
                result.append(f"Type: {response.knowledge_graph['type']}")
            if "description" in response.knowledge_graph:
                result.append(f"\n{response.knowledge_graph['description']}")
            
            # Add attributes
            if "attributes" in response.knowledge_graph:
                result.append("\n## Attributes")
                for key, value in response.knowledge_graph["attributes"].items():
                    result.append(f"- **{key}**: {value}")
            result.append("")
        
        # Add answer box if present
        if response.answer_box:
            result.append(f"# Answer Box")
            if "title" in response.answer_box:
                result.append(f"## {response.answer_box['title']}")
            if "answer" in response.answer_box:
                result.append(f"{response.answer_box['answer']}")
            elif "snippet" in response.answer_box:
                result.append(f"{response.answer_box['snippet']}")
            if "source" in response.answer_box:
                source = response.answer_box["source"]
                link = response.answer_box.get("link", "#")
                result.append(f"\nSource: [{source}]({link})")
            result.append("")
        
        # Add related questions if present
        if response.related_questions:
            result.append(f"# People Also Ask")
            for i, question in enumerate(response.related_questions):
                result.append(f"## {question.get('question', f'Question {i+1}')}")
                if "snippet" in question:
                    result.append(f"{question['snippet']}")
                if "source" in question:
                    source = question["source"]
                    link = question.get("link", "#")
                    result.append(f"\nSource: [{source}]({link})")
                result.append("")
        
        # Add top stories if present
        if response.top_stories:
            result.append(f"# Top Stories ({len(response.top_stories)})")
            for i, story in enumerate(response.top_stories):
                result.append(f"## {i+1}. {story.get('title', f'Story {i+1}')}")
                if "link" in story:
                    result.append(f"Link: {story['link']}")
                if "source" in story:
                    result.append(f"Source: {story['source']}")
                if "date" in story:
                    result.append(f"Date: {story['date']}")
                if "snippet" in story:
                    result.append(f"\n{story['snippet']}")
                result.append("")
        
        # Add related searches if present
        if response.related_searches:
            result.append(f"# Related Searches")
            for search in response.related_searches:
                query = search.get("query", "")
                link = search.get("link", "#")
                result.append(f"- [{query}]({link})")
            result.append("")
        
        # Add pagination information
        if response.pagination:
            result.append(f"# Pagination")
            if "current" in response.pagination:
                result.append(f"Current Page: {response.pagination['current']}")
            if "next" in response.pagination:
                result.append(f"Next Page: {response.pagination['next']}")
            if "other_pages" in response.pagination:
                result.append(f"Other Pages: {', '.join(str(p) for p in response.pagination['other_pages'])}")
            result.append("")
        
        return "\n".join(result)

    def format_locations_results(self, response: List[Dict[str, Any]]) -> str:
        """Format locations results for display."""
        result_text = ["Available Google Search Locations:"]
        
        for location in response:
            result_text.append(f"- {location.get('name', 'Unknown')} ({location.get('canonical_name', 'Unknown')})")
            if "country_code" in location:
                result_text.append(f"  Country Code: {location['country_code']}")
            if "target_type" in location:
                result_text.append(f"  Type: {location['target_type']}")
            result_text.append("")
        
        return "\n".join(result_text)

    def format_account_results(self, response: Dict[str, Any]) -> str:
        """Format account results for display."""
        result_text = ["SerpAPI Account Information:"]
        
        if "account_id" in response:
            result_text.append(f"Account ID: {response['account_id']}")
        if "api_key" in response:
            result_text.append(f"API Key: {response['api_key']}")
        if "account_email" in response:
            result_text.append(f"Email: {response['account_email']}")
        if "plan_name" in response:
            result_text.append(f"Plan: {response['plan_name']}")
        if "searches_per_month" in response:
            result_text.append(f"Searches Per Month: {response['searches_per_month']}")
        if "plan_searches_left" in response:
            result_text.append(f"Searches Left: {response['plan_searches_left']}")
        
        return "\n".join(result_text)

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
    """Start the SerpAPI MCP server."""
    server = Server("mcp-serpapi-google-search")
    serpapi_server = SerpApiServer(api_key)
    
    # Test API key validity with a simple account request
    try:
        print("Testing API key validity...", file=sys.stderr)
        await serpapi_server.account(GoogleAccountArgs())
        print("SerpAPI key validated successfully", file=sys.stderr)
    except Exception as e:
        print(f"Error validating SerpAPI key: {str(e)}", file=sys.stderr)
        sys.exit(1)
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        print("list_tools called", file=sys.stderr)
        return [
            Tool(
                name="google_search",
                description="""Search Google and get organic search results, knowledge graphs, and other SERP features.
                
                Provides comprehensive search results from Google, including organic listings, featured snippets, 
                knowledge graphs, related questions, top stories, and related searches. Supports various parameters 
                to customize your search experience.
                
                You can specify location, language (hl), country (gl), device type, and safety settings. 
                Additionally, you can include or exclude specific domains from your search results and 
                filter results by time period.
                
                By default, returns cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON.
                
                This tool is ideal for general web searches, research, and finding specific information online.""",
                inputSchema=GoogleSearchArgs.model_json_schema(),
            ),
            Tool(
                name="google_locations",
                description="""Get a list of supported Google locations for search.
                
                Returns a list of locations that can be used with the google_search tool to perform 
                location-specific searches. You can search for locations by name or browse the complete list.
                
                Each location includes details such as name, canonical name, country code, and target type.
                
                This is useful when you need to perform searches from specific geographic locations to get
                localized search results.""",
                inputSchema=GoogleLocationsArgs.model_json_schema(),
            ),
            Tool(
                name="serpapi_account",
                description="""Get SerpAPI account information.
                
                Returns detailed information about your SerpAPI account, including account ID, email,
                plan name, total searches per month, and remaining searches in your plan.
                
                This tool is useful for monitoring your API usage and understanding your account limits.""",
                inputSchema=GoogleAccountArgs.model_json_schema(),
            ),
        ]
    
    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        print("list_prompts called", file=sys.stderr)
        return [
            Prompt(
                name="google_search_prompt",
                description="""Search Google and get organic search results, knowledge graphs, and other SERP features.
                
                By default, results are returned as cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON for easier reading.
                """,
                arguments=[
                    PromptArgument(
                        name="q",
                        description="Search query for Google. You can use anything that you would use in a regular Google search, including operators like 'site:', 'inurl:', 'intitle:', etc.",
                        required=True,
                    ),
                    PromptArgument(
                        name="num",
                        description="Number of search results to return per page. The default is 10. Note that the Google Custom Search JSON API has a maximum value of 10 for this parameter, though SerpAPI may support up to 100. Also note that the API will never return more than 100 results total, so the sum of 'start + num' should not exceed 100. IMPORTANT: Due to Google's Knowledge Graph layout, Google may ignore the num parameter for the first page of results in searches related to celebrities, famous groups, and popular media. If you need num to work as expected, you can set start=1, but be aware that this approach will not return the first organic result and the Knowledge Graph.",
                        required=False,
                    ),
                    PromptArgument(
                        name="start",
                        description="The index of the first result to return (1-based indexing). This is useful for pagination. For example, to get the second page of results with 10 results per page, set start=11. Note that the API will never return more than 100 results total, so the sum of 'start + num' should not exceed 100. IMPORTANT: Setting start=1 can be used as a workaround when Google ignores the num parameter due to Knowledge Graph results, but this will cause the first organic result and Knowledge Graph to be omitted from the results.",
                        required=False,
                    ),
                    PromptArgument(
                        name="location",
                        description="Location to search from (e.g., 'Austin, Texas, United States'). Determines the geographic context for search results.",
                        required=False,
                    ),
                    PromptArgument(
                        name="gl",
                        description="Google country code (e.g., 'us' for United States, 'uk' for United Kingdom, 'fr' for France). Determines the country-specific version of Google to use.",
                        required=False,
                    ),
                    PromptArgument(
                        name="hl",
                        description="Google UI language code (e.g., 'en' for English, 'es' for Spanish, 'fr' for French). Determines the language of the Google interface and results.",
                        required=False,
                    ),
                    PromptArgument(
                        name="device",
                        description="Device type to simulate for the search. Can be 'desktop' (default), 'mobile', or 'tablet'. Different devices may receive different search results and formats.",
                        required=False,
                    ),
                    PromptArgument(
                        name="safe",
                        description="Safe search setting. Can be 'active' to filter explicit content or 'off' to disable filtering. If not specified, Google's default setting is used.",
                        required=False,
                    ),
                    PromptArgument(
                        name="filter",
                        description="Controls whether to filter duplicate content. Can be set to '0' (off) or '1' (on). When turned on, duplicate content from the same site is filtered from the search results.",
                        required=False,
                    ),
                    PromptArgument(
                        name="time_period",
                        description="Time period for filtering results by recency. Supported values include: 'd' (past day), 'w' (past week), 'm' (past month), 'y' (past year).",
                        required=False,
                    ),
                    PromptArgument(
                        name="exactTerms",
                        description="Identifies a word or phrase that should appear exactly in the search results. This is useful for finding exact matches of specific terms.",
                        required=False,
                    ),
                    PromptArgument(
                        name="include_domains",
                        description="List of domains to specifically include in search results. This is equivalent to using multiple 'site:' operators in the query.",
                        required=False,
                    ),
                    PromptArgument(
                        name="exclude_domains",
                        description="List of domains to exclude from search results. This is equivalent to using multiple '-site:' operators in the query.",
                        required=False,
                    ),
                    PromptArgument(
                        name="raw_json",
                        description="Return the complete raw JSON response directly from the SerpAPI server without any processing or validation.",
                        required=False,
                    ),
                    PromptArgument(
                        name="readable_json",
                        description="Return results in markdown-formatted text instead of JSON. Creates a structured, human-readable document with headings, bold text, and organized sections for easy reading.",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="google_locations_prompt",
                description="Get a list of supported Google locations for search.",
                arguments=[
                    PromptArgument(
                        name="q",
                        description="Query to search for locations. Use this to find specific cities, regions, or countries available for location-based searches.",
                        required=False,
                    ),
                    PromptArgument(
                        name="limit",
                        description="Limit the number of locations returned. Useful when you only need a few results or when searching for common location names.",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="serpapi_account_prompt",
                description="Get SerpAPI account information including usage statistics and plan details",
                arguments=[],
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        print(f"call_tool called with name: {name}, arguments: {arguments}", file=sys.stderr)
        
        if name == "google_search":
            args = GoogleSearchArgs(**arguments)
            
            # Call the API and get the response in the requested format
            response = await serpapi_server.search(args)
            
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
        
        elif name == "google_locations":
            args = GoogleLocationsArgs(**arguments)
            
            # Call the API
            response = await serpapi_server.locations(args)
            
            # Format the response
            if args.readable_json:
                formatted_response = serpapi_server.format_locations_results(response)
                return [TextContent(type="text", text=formatted_response)]
            else:
                return [TextContent(type="text", text=json.dumps(response, indent=2))]
        
        elif name == "google_account":
            args = GoogleAccountArgs(**arguments)
            
            # Call the API
            response = await serpapi_server.account(args)
            
            # Format the response
            if args.readable_json:
                formatted_response = serpapi_server.format_account_results(response)
                return [TextContent(type="text", text=formatted_response)]
            else:
                return [TextContent(type="text", text=json.dumps(response, indent=2))]
        
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
            
            if name == "google_search_prompt":
                # Extract parameters from arguments
                q = arguments.get("q")
                num = arguments.get("num", 10)
                start = arguments.get("start")
                location = arguments.get("location")
                gl = arguments.get("gl")
                hl = arguments.get("hl")
                device = arguments.get("device")
                safe = arguments.get("safe")
                filter = arguments.get("filter")
                time_period = arguments.get("time_period")
                exactTerms = arguments.get("exactTerms")
                include_domains = arguments.get("include_domains", [])
                exclude_domains = arguments.get("exclude_domains", [])
                raw_json = arguments.get("raw_json", False)
                readable_json = arguments.get("readable_json", False)
                
                messages = []
                
                # System message
                messages.append(PromptMessage(
                    role="system",
                    content="You are a helpful assistant that can search Google and provide comprehensive search results. "
                            "Provide informative and concise summaries of the search results."
                ))
                
                # User message
                user_message = "I want to search Google"
                if q:
                    user_message += f" for '{q}'"
                if location:
                    user_message += f" from {location}"
                if gl:
                    user_message += f" in {gl}"
                if hl:
                    user_message += f" in language {hl}"
                if device:
                    user_message += f" on {device}"
                if safe:
                    user_message += f" with safe search {safe}"
                if filter:
                    user_message += f" with duplicate filter {filter}"
                if time_period:
                    user_message += f" for the past {time_period}"
                if exactTerms:
                    user_message += f" with exact phrase '{exactTerms}'"
                if include_domains:
                    domains = include_domains if isinstance(include_domains, list) else [include_domains]
                    user_message += f" only on domains {', '.join(domains)}"
                if exclude_domains:
                    domains = exclude_domains if isinstance(exclude_domains, list) else [exclude_domains]
                    user_message += f" excluding domains {', '.join(domains)}"
                if start:
                    user_message += f" starting from result {start}"
                user_message += "."
                
                messages.append(PromptMessage(
                    role="user",
                    content=user_message
                ))
                
                # Prepare search arguments
                search_args = {}
                if q:
                    search_args["q"] = q
                if num:
                    search_args["num"] = num
                if start:
                    search_args["start"] = start
                if location:
                    search_args["location"] = location
                if gl:
                    search_args["gl"] = gl
                if hl:
                    search_args["hl"] = hl
                if device:
                    search_args["device"] = device
                if safe:
                    search_args["safe"] = safe
                if filter:
                    search_args["filter"] = filter
                if time_period:
                    search_args["time_period"] = time_period
                if exactTerms:
                    search_args["exactTerms"] = exactTerms
                if include_domains:
                    search_args["include_domains"] = include_domains
                if exclude_domains:
                    search_args["exclude_domains"] = exclude_domains
                
                search_args["raw_json"] = raw_json
                search_args["readable_json"] = readable_json
                
                tool_calls = [
                    {
                        "id": "google_search_1",
                        "type": "function",
                        "function": {
                            "name": "google_search",
                            "arguments": json.dumps(search_args)
                        }
                    }
                ]
                
                return GetPromptResult(
                    messages=messages,
                    tool_calls=tool_calls,
                )
            
            elif name == "google_locations_prompt":
                # Extract parameters from arguments
                q = arguments.get("q")
                limit = arguments.get("limit")
                
                messages = []
                
                # System message
                messages.append(PromptMessage(
                    role="system",
                    content="You are a helpful assistant that can provide information about Google search locations. "
                            "This helps users understand which locations are available for location-specific searches."
                ))
                
                # User message
                user_message = "I want to see available Google search locations"
                if q:
                    user_message += f" matching '{q}'"
                if limit:
                    user_message += f" limited to {limit} results"
                user_message += "."
                
                messages.append(PromptMessage(
                    role="user",
                    content=user_message
                ))
                
                # Prepare locations arguments
                locations_args = {}
                if q:
                    locations_args["q"] = q
                if limit:
                    locations_args["limit"] = limit
                
                tool_calls = [
                    {
                        "id": "google_locations_1",
                        "type": "function",
                        "function": {
                            "name": "google_locations",
                            "arguments": json.dumps(locations_args)
                        }
                    }
                ]
                
                return GetPromptResult(
                    messages=messages,
                    tool_calls=tool_calls,
                )
            
            elif name == "serpapi_account_prompt":
                messages = []
                
                # System message
                messages.append(PromptMessage(
                    role="system",
                    content="You are a helpful assistant that can provide information about SerpAPI account status. "
                            "This helps users understand their API usage and limits."
                ))
                
                # User message
                messages.append(PromptMessage(
                    role="user",
                    content="I want to see my SerpAPI account information."
                ))
                
                tool_calls = [
                    {
                        "id": "serpapi_account_1",
                        "type": "function",
                        "function": {
                            "name": "serpapi_account",
                            "arguments": "{}"
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
    
    print("Starting SerpAPI MCP server...", file=sys.stderr)
    
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
    
    # Get API key from environment variable - check both possible environment variable names
    api_key = os.environ.get("SERP_API_KEY") or os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("Error: Neither SERP_API_KEY nor SERPAPI_KEY environment variable is set", file=sys.stderr)
        print(f"Please create a .env file in {parent_dir} with SERPAPI_KEY=your_api_key", file=sys.stderr)
        sys.exit(1)
    
    # Start the server
    asyncio.run(serve(api_key))
