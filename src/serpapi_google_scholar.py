#!/usr/bin/env python3
"""
SerpAPI Google Scholar MCP Server

This module provides a server for accessing Google Scholar search results via SerpAPI.
"""

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
API_ERROR = "api_error"
INVALID_ARGUMENTS = INVALID_PARAMS

class GoogleScholarArgs(BaseModel):
    """Arguments for Google Scholar search using SerpAPI."""
    q: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the query you want to search. You can also use helpers in your query such as: 'author:', or 'source:'. Usage of 'cites' parameter makes 'q' optional. Usage of 'cites' together with 'q' triggers search within citing articles. Usage of 'cluster' together with 'q' and 'cites' parameters is prohibited. Use 'cluster' parameter only.",
        ),
    ] = None
    hl: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the language to use for the Google Scholar search. It's a two-letter language code. (e.g., 'en' for English, 'es' for Spanish, or 'fr' for French). Head to the Google languages page for a full list of supported Google languages.",
        ),
    ] = None
    lr: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines one or multiple languages to limit the search to. It uses 'lang_{two-letter language code}' to specify languages and '|' as a delimiter. (e.g., 'lang_fr|lang_de' will only search French and German pages). Head to the Google lr languages for a full list of supported languages.",
        ),
    ] = None
    start: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Parameter defines the result offset. It skips the given number of results. It's used for pagination. (e.g., '0' (default) is the first page of results, '10' is the 2nd page of results, '20' is the 3rd page of results, etc.).",
            ge=0,
        ),
    ] = None
    num: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Parameter defines the maximum number of results to return, ranging from '1' to '20', with a default of '10'.",
            ge=1,
            le=20,
        ),
    ] = None
    cites: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines unique ID for an article to trigger Cited By searches. Usage of 'cites' will bring up a list of citing documents in Google Scholar. Example value: 'cites=1275980731835430123'. Usage of 'cites' and 'q' parameters triggers search within citing articles.",
        ),
    ] = None
    as_ylo: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Parameter defines the year from which you want the results to be included. (e.g. if you set as_ylo parameter to the year '2018', the results before that year will be omitted.). This parameter can be combined with the as_yhi parameter.",
            ge=1000,
        ),
    ] = None
    as_yhi: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Parameter defines the year until which you want the results to be included. (e.g. if you set as_yhi parameter to the year '2018', the results after that year will be omitted.). This parameter can be combined with the as_ylo parameter.",
            ge=1000,
        ),
    ] = None
    scisbd: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Parameter defines articles added in the last year, sorted by date. It can be set to '1' to include only abstracts, or '2' to include everything. The default value is '0' which means that the articles are sorted by relevance.",
            ge=0,
            le=2,
        ),
    ] = None
    cluster: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines unique ID for an article to trigger All Versions searches. Example value: 'cluster=1275980731835430123'. Usage of 'cluster' together with 'q' and 'cites' parameters is prohibited. Use 'cluster' parameter only.",
        ),
    ] = None
    as_sdt: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter can be used either as a search type or a filter. As a Filter (only works when searching articles): '0' - exclude patents (default). '7' - include patents. As a Search Type: '4' - Select case law (US courts only). This will select all the State and Federal courts. e.g. 'as_sdt=4' - Selects case law (all courts). To select specific courts, see the full list of supported Google Scholar courts. e.g. 'as_sdt=4,33,192' - '4' is the required value and should always be in the first position, '33' selects all New York courts and '192' selects Tax Court. Values have to be separated by comma (',')",
        ),
    ] = None
    safe: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines the level of filtering for adult content. It can be set to 'active' or 'off', by default Google will blur explicit content.",
        ),
    ] = None
    filter: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines if the filters for 'Similar Results' and 'Omitted Results' are on or off. It can be set to '1' (default) to enable these filters, or '0' to disable these filters.",
        ),
    ] = None
    as_vis: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines whether you would like to include citations or not. It can be set to '1' to exclude these results, or '0' (default) to include them.",
        ),
    ] = None
    as_rr: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Parameter defines whether you would like to show only review articles or not (these articles consist of topic reviews, or discuss the works or authors you have searched for). It can be set to '1' to enable this filter, or '0' (default) to show all results.",
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

    @field_validator('q', 'cites', 'cluster')
    @classmethod
    def validate_search_parameters(cls, v, info):
        """Validate that the search parameters are used correctly."""
        field_name = info.field_name
        values = info.data
        
        # Check if cluster is used with q or cites
        if field_name == 'cluster' and v is not None and (values.get('q') or values.get('cites')):
            raise ValueError("When using 'cluster' parameter, 'q' and 'cites' parameters should not be used.")
        
        # Only check for required parameters when validating 'q'
        if field_name == 'q' and v is None:
            # If q is None, check if cites or cluster is provided
            if not values.get('cites') and not values.get('cluster'):
                raise ValueError("At least one of 'q', 'cites', or 'cluster' parameters must be provided.")
        
        return v

class GoogleScholarAuthor(BaseModel):
    """Author information for a Google Scholar result."""
    name: Optional[str] = None
    link: Optional[str] = None
    serpapi_link: Optional[str] = None

class GoogleScholarResult(BaseModel):
    """Single result from Google Scholar."""
    position: Optional[int] = None
    title: str
    result_id: Optional[str] = None
    link: Optional[str] = None
    snippet: Optional[str] = None
    publication_info: Optional[Dict[str, Any]] = None
    resources: Optional[List[Dict[str, Any]]] = None
    inline_links: Optional[Dict[str, Any]] = None
    cited_by: Optional[Dict[str, Any]] = None
    authors: Optional[List[GoogleScholarAuthor]] = None
    year: Optional[str] = None
    journal: Optional[str] = None

class GoogleScholarResponseData(BaseModel):
    """The data field of the SerpAPI Google Scholar search response."""
    search_metadata: Dict[str, Any]
    search_parameters: Dict[str, Any]
    search_information: Optional[Dict[str, Any]] = None
    organic_results: Optional[List[GoogleScholarResult]] = None
    pagination: Optional[Dict[str, Any]] = None
    serpapi_pagination: Optional[Dict[str, Any]] = None
    related_searches: Optional[List[Dict[str, Any]]] = None
    filters: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class CachedSearch:
    """Cache for storing search results to avoid redundant API calls."""
    
    def __init__(self, query: str, response: Union[Dict[str, Any], str]):
        """Initialize a cached search with a query and response."""
        self.query = query
        self.response = response

class SerpApiGoogleScholarServer:
    """Server for handling Google Scholar searches via SerpAPI."""
    
    def __init__(self, api_key: str):
        """Initialize the server with a SerpAPI key."""
        self.api_key = api_key
        self.cache = {}  # Simple in-memory cache
        self.base_url = "https://serpapi.com/search"
    
    async def google_scholar_search(self, args: GoogleScholarArgs) -> Union[Dict[str, Any], str]:
        """Perform a Google Scholar search using SerpAPI."""
        
        # Build the query parameters
        params = {
            "engine": "google_scholar",
            "api_key": self.api_key,
        }
        
        # Add optional parameters if they are provided
        if args.q is not None:
            params["q"] = args.q
        if args.hl is not None:
            params["hl"] = args.hl
        if args.lr is not None:
            params["lr"] = args.lr
        if args.start is not None:
            params["start"] = args.start
        if args.num is not None:
            params["num"] = args.num
        if args.cites is not None:
            params["cites"] = args.cites
        if args.as_ylo is not None:
            params["as_ylo"] = args.as_ylo
        if args.as_yhi is not None:
            params["as_yhi"] = args.as_yhi
        if args.scisbd is not None:
            params["scisbd"] = args.scisbd
        if args.cluster is not None:
            params["cluster"] = args.cluster
        if args.as_sdt is not None:
            params["as_sdt"] = args.as_sdt
        if args.safe is not None:
            params["safe"] = args.safe
        if args.filter is not None:
            params["filter"] = args.filter
        if args.as_vis is not None:
            params["as_vis"] = args.as_vis
        if args.as_rr is not None:
            params["as_rr"] = args.as_rr
        
        # Create a cache key from the parameters
        cache_key = json.dumps(params, sort_keys=True)
        
        # Check if we have a cached response
        if cache_key in self.cache:
            print(f"Using cached response for {cache_key}", file=sys.stderr)
            cached_response = self.cache[cache_key].response
            
            # Return the appropriate format based on the args
            if args.raw_json:
                if isinstance(cached_response, dict):
                    return cached_response
                elif isinstance(cached_response, GoogleScholarResponseData):
                    return cached_response.model_dump()
                else:
                    return cached_response
            elif args.readable_json:
                if isinstance(cached_response, str):
                    return cached_response
                elif isinstance(cached_response, dict):
                    return self.format_google_scholar_results(GoogleScholarResponseData(**cached_response))
                else:
                    return self.format_google_scholar_results(cached_response)
            else:
                if isinstance(cached_response, GoogleScholarResponseData):
                    return clean_json_dict(cached_response.model_dump())
                elif isinstance(cached_response, dict):
                    return clean_json_dict(cached_response)
                else:
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
                    
                    # Cache the response
                    if args.raw_json:
                        self.cache[cache_key] = CachedSearch(cache_key, json_response)
                        return json_response
                    elif args.readable_json:
                        # Parse the response into our model first for validation
                        response_data = GoogleScholarResponseData(**json_response)
                        formatted_response = self.format_google_scholar_results(response_data)
                        self.cache[cache_key] = CachedSearch(cache_key, formatted_response)
                        return formatted_response
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
    
    def format_google_scholar_results(self, response: GoogleScholarResponseData) -> str:
        """
        Format the Google Scholar search results as a readable markdown string.
        
        Args:
            response: The search response data.
            
        Returns:
            A markdown-formatted string representation of the search results.
        """
        result_parts = []
        
        # Add header with search information
        result_parts.append("# Google Scholar Search Results\n")
        
        # Add search metadata
        if response.search_information:
            total_results = response.search_information.get("total_results")
            if total_results:
                result_parts.append(f"**Total Results:** {total_results}\n")
            
            time_taken = response.search_information.get("time_taken_displayed")
            if time_taken:
                result_parts.append(f"**Time Taken:** {time_taken}\n")
        
        # Add search parameters
        result_parts.append("\n## Search Parameters\n")
        for key, value in response.search_parameters.items():
            if key != "engine" and key != "api_key":
                result_parts.append(f"**{key}:** {value}\n")
        
        # Add organic results
        if response.organic_results:
            result_parts.append("\n## Results\n")
            
            for i, result in enumerate(response.organic_results):
                result_parts.append(f"### {i+1}. {result.title}\n")
                
                if result.snippet:
                    result_parts.append(f"{result.snippet}\n")
                
                if result.publication_info:
                    pub_info = []
                    if "summary" in result.publication_info:
                        pub_info.append(f"**Publication:** {result.publication_info['summary']}")
                    if "authors" in result.publication_info:
                        authors = ", ".join([a.get("name", "") for a in result.publication_info["authors"]])
                        pub_info.append(f"**Authors:** {authors}")
                    result_parts.append(" | ".join(pub_info) + "\n")
                
                if result.authors:
                    authors = ", ".join([a.name for a in result.authors if a.name])
                    if authors:
                        result_parts.append(f"**Authors:** {authors}\n")
                
                if result.year:
                    result_parts.append(f"**Year:** {result.year}\n")
                
                if result.journal:
                    result_parts.append(f"**Journal:** {result.journal}\n")
                
                if result.cited_by:
                    cited_by = result.cited_by.get("value", "")
                    cited_by_link = result.cited_by.get("link", "")
                    if cited_by:
                        result_parts.append(f"**Cited by:** [{cited_by}]({cited_by_link})\n")
                
                if result.link:
                    result_parts.append(f"**Link:** [{result.link}]({result.link})\n")
                
                if result.resources:
                    result_parts.append("**Resources:**\n")
                    for resource in result.resources:
                        title = resource.get("title", "")
                        link = resource.get("link", "")
                        if title and link:
                            result_parts.append(f"- [{title}]({link})\n")
                
                result_parts.append("\n---\n")
        
        # Add related searches
        if response.related_searches:
            result_parts.append("\n## Related Searches\n")
            for search in response.related_searches:
                query = search.get("query", "")
                link = search.get("link", "")
                if query:
                    if link:
                        result_parts.append(f"- [{query}]({link})\n")
                    else:
                        result_parts.append(f"- {query}\n")
        
        # Add pagination information
        if response.pagination:
            result_parts.append("\n## Pagination\n")
            current = response.pagination.get("current", "")
            next_page = response.pagination.get("next", "")
            other_pages = response.pagination.get("other_pages", {})
            
            if current:
                result_parts.append(f"**Current Page:** {current}\n")
            
            if next_page:
                result_parts.append(f"**Next Page:** {next_page}\n")
            
            if other_pages:
                result_parts.append("**Other Pages:**\n")
                for page_num, page_link in other_pages.items():
                    result_parts.append(f"- Page {page_num}: {page_link}\n")
        
        return "".join(result_parts)

def clean_json_dict(data):
    """
    Recursively clean a dictionary by removing None values and empty collections.
    
    Args:
        data: The data to clean, can be a dict, list, or scalar value.
        
    Returns:
        The cleaned data.
    """
    if isinstance(data, dict):
        return {k: clean_json_dict(v) for k, v in data.items() 
                if v is not None and (not isinstance(v, (dict, list)) or v)}
    elif isinstance(data, list):
        return [clean_json_dict(item) for item in data 
                if item is not None and (not isinstance(item, (dict, list)) or item)]
    else:
        return data

async def serve(api_key: str) -> None:
    """
    Start the MCP server for Google Scholar search.
    
    Args:
        api_key: The SerpAPI API key.
    """
    server = Server("mcp-serpapi-google-scholar")
    scholar_server = SerpApiGoogleScholarServer(api_key)
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        print("list_tools called", file=sys.stderr)
        return [
            Tool(
                name="google_scholar_search",
                description="""Search Google Scholar for academic papers, articles, and citations.
                
                This tool allows you to search for scholarly literature across various disciplines and sources, 
                including articles, theses, books, abstracts, and court opinions from academic publishers, 
                professional societies, online repositories, universities, and other web sites.
                
                You can search by keyword, author, publication, or use advanced features like citation search 
                and date range filtering. Results include publication details, author information, citations, 
                and links to the papers.
                
                By default, returns cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON.
                
                This tool is ideal for academic research, literature reviews, and finding scholarly sources.""",
                inputSchema=GoogleScholarArgs.model_json_schema(),
            ),
        ]
    
    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        print("list_prompts called", file=sys.stderr)
        return [
            Prompt(
                name="google_scholar_prompt",
                description="""Search Google Scholar for academic papers, articles, and citations.
                
                By default, results are returned as cleaned JSON without null/empty values.
                Set raw_json=True to get the complete raw JSON response with all fields.
                Set readable_json=True to get markdown-formatted text instead of JSON for easier reading.
                """,
                arguments=[
                    PromptArgument(
                        name="q",
                        description="Parameter defines the query you want to search. You can also use helpers in your query such as: 'author:', or 'source:'. Usage of 'cites' parameter makes 'q' optional. Usage of 'cites' together with 'q' triggers search within citing articles. Usage of 'cluster' together with 'q' and 'cites' parameters is prohibited. Use 'cluster' parameter only.",
                        required=False,
                    ),
                    PromptArgument(
                        name="hl",
                        description="Parameter defines the language to use for the Google Scholar search. It's a two-letter language code. (e.g., 'en' for English, 'es' for Spanish, or 'fr' for French). Head to the Google languages page for a full list of supported Google languages.",
                        required=False,
                    ),
                    PromptArgument(
                        name="lr",
                        description="Parameter defines one or multiple languages to limit the search to. It uses 'lang_{two-letter language code}' to specify languages and '|' as a delimiter. (e.g., 'lang_fr|lang_de' will only search French and German pages). Head to the Google lr languages for a full list of supported languages.",
                        required=False,
                    ),
                    PromptArgument(
                        name="start",
                        description="Parameter defines the result offset. It skips the given number of results. It's used for pagination. (e.g., '0' (default) is the first page of results, '10' is the 2nd page of results, '20' is the 3rd page of results, etc.).",
                        required=False,
                    ),
                    PromptArgument(
                        name="num",
                        description="Parameter defines the maximum number of results to return, ranging from '1' to '20', with a default of '10'.",
                        required=False,
                    ),
                    PromptArgument(
                        name="cites",
                        description="Parameter defines unique ID for an article to trigger Cited By searches. Usage of 'cites' will bring up a list of citing documents in Google Scholar. Example value: 'cites=1275980731835430123'. Usage of 'cites' and 'q' parameters triggers search within citing articles.",
                        required=False,
                    ),
                    PromptArgument(
                        name="as_ylo",
                        description="Parameter defines the year from which you want the results to be included. (e.g. if you set as_ylo parameter to the year '2018', the results before that year will be omitted.). This parameter can be combined with the as_yhi parameter.",
                        required=False,
                    ),
                    PromptArgument(
                        name="as_yhi",
                        description="Parameter defines the year until which you want the results to be included. (e.g. if you set as_yhi parameter to the year '2018', the results after that year will be omitted.). This parameter can be combined with the as_ylo parameter.",
                        required=False,
                    ),
                    PromptArgument(
                        name="scisbd",
                        description="Parameter defines articles added in the last year, sorted by date. It can be set to '1' to include only abstracts, or '2' to include everything. The default value is '0' which means that the articles are sorted by relevance.",
                        required=False,
                    ),
                    PromptArgument(
                        name="cluster",
                        description="Parameter defines unique ID for an article to trigger All Versions searches. Example value: 'cluster=1275980731835430123'. Usage of 'cluster' together with 'q' and 'cites' parameters is prohibited. Use 'cluster' parameter only.",
                        required=False,
                    ),
                    PromptArgument(
                        name="as_sdt",
                        description="Parameter can be used either as a search type or a filter. As a Filter (only works when searching articles): '0' - exclude patents (default). '7' - include patents. As a Search Type: '4' - Select case law (US courts only). This will select all the State and Federal courts. e.g. 'as_sdt=4' - Selects case law (all courts). To select specific courts, see the full list of supported Google Scholar courts. e.g. 'as_sdt=4,33,192' - '4' is the required value and should always be in the first position, '33' selects all New York courts and '192' selects Tax Court. Values have to be separated by comma (',')",
                        required=False,
                    ),
                    PromptArgument(
                        name="safe",
                        description="Parameter defines the level of filtering for adult content. It can be set to 'active' or 'off', by default Google will blur explicit content.",
                        required=False,
                    ),
                    PromptArgument(
                        name="filter",
                        description="Parameter defines if the filters for 'Similar Results' and 'Omitted Results' are on or off. It can be set to '1' (default) to enable these filters, or '0' to disable these filters.",
                        required=False,
                    ),
                    PromptArgument(
                        name="as_vis",
                        description="Parameter defines whether you would like to include citations or not. It can be set to '1' to exclude these results, or '0' (default) to include them.",
                        required=False,
                    ),
                    PromptArgument(
                        name="as_rr",
                        description="Parameter defines whether you would like to show only review articles or not (these articles consist of topic reviews, or discuss the works or authors you have searched for). It can be set to '1' to enable this filter, or '0' (default) to show all results.",
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
        print(f"call_tool called with name={name}, arguments={arguments}", file=sys.stderr)
        try:
            if name == "google_scholar_search":
                # Parse and validate the arguments
                try:
                    args = GoogleScholarArgs(**arguments)
                except Exception as e:
                    print(f"Error parsing arguments: {str(e)}", file=sys.stderr)
                    raise McpError(ErrorData(
                        code=INVALID_PARAMS,
                        message=f"Invalid arguments: {str(e)}"
                    ))
                
                # Perform the search
                response = await scholar_server.google_scholar_search(args)
                
                # Return the response in the appropriate format
                if args.readable_json:
                    if isinstance(response, str):
                        return [TextContent(type="text", text=response)]
                    else:
                        # This should not happen, but just in case
                        if isinstance(response, GoogleScholarResponseData):
                            formatted = scholar_server.format_google_scholar_results(response)
                        else:
                            formatted = scholar_server.format_google_scholar_results(GoogleScholarResponseData(**response))
                        return [TextContent(type="text", text=formatted)]
                else:
                    if isinstance(response, dict):
                        return [TextContent(type="text", text=json.dumps(response, indent=2))]
                    else:
                        # This should not happen with the updated implementation
                        return [TextContent(type="text", text=str(response))]
            else:
                raise McpError(ErrorData(
                    code=METHOD_NOT_FOUND,
                    message=f"Unknown tool: {name}"
                ))
        except McpError:
            raise
        except Exception as e:
            print(f"Error in call_tool: {str(e)}", file=sys.stderr)
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"Error executing tool: {str(e)}"
            ))
    
    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict | None) -> GetPromptResult:
        print(f"get_prompt called with name={name}", file=sys.stderr)
        try:
            if arguments is None:
                arguments = {}
            
            if name == "google_scholar_prompt":
                # Extract parameters from arguments
                q = arguments.get("q")
                hl = arguments.get("hl")
                lr = arguments.get("lr")
                start = arguments.get("start")
                num = arguments.get("num")
                cites = arguments.get("cites")
                as_ylo = arguments.get("as_ylo")
                as_yhi = arguments.get("as_yhi")
                scisbd = arguments.get("scisbd")
                cluster = arguments.get("cluster")
                as_sdt = arguments.get("as_sdt")
                safe = arguments.get("safe")
                filter_param = arguments.get("filter")
                as_vis = arguments.get("as_vis")
                as_rr = arguments.get("as_rr")
                raw_json = arguments.get("raw_json", False)
                readable_json = arguments.get("readable_json", False)
                
                messages = []
                
                # System message
                messages.append(PromptMessage(
                    role="system",
                    content="You are a helpful assistant that can search Google Scholar for academic papers, articles, and citations. You can provide information about scholarly literature across various disciplines and sources."
                ))
                
                # User message
                user_message = "I want to search Google Scholar"
                if q:
                    user_message += f" for '{q}'"
                if cites:
                    user_message += f" for papers citing the article with ID '{cites}'"
                if cluster:
                    user_message += f" for all versions of the article with ID '{cluster}'"
                if as_ylo and as_yhi:
                    user_message += f" published between {as_ylo} and {as_yhi}"
                elif as_ylo:
                    user_message += f" published since {as_ylo}"
                elif as_yhi:
                    user_message += f" published before {as_yhi}"
                if scisbd:
                    user_message += " sorted by date"
                if as_sdt:
                    user_message += f" with search type '{as_sdt}'"
                if safe:
                    user_message += f" with safe search {safe}"
                if filter_param:
                    if filter_param == "0":
                        user_message += " with filters disabled"
                    else:
                        user_message += " with filters enabled"
                if as_vis:
                    if as_vis == "1":
                        user_message += " excluding citations"
                    else:
                        user_message += " including citations"
                if as_rr:
                    if as_rr == "1":
                        user_message += " showing only review articles"
                    else:
                        user_message += " showing all article types"
                if hl:
                    user_message += f" with interface language set to '{hl}'"
                if lr:
                    user_message += f" limited to languages: {lr}"
                
                user_message += "."
                
                messages.append(PromptMessage(
                    role="user",
                    content=user_message
                ))
                
                # Create the tool call
                tool_call = {
                    "name": "google_scholar_search",
                    "arguments": {}
                }
                
                # Add parameters to the tool call
                if q is not None:
                    tool_call["arguments"]["q"] = q
                if hl is not None:
                    tool_call["arguments"]["hl"] = hl
                if lr is not None:
                    tool_call["arguments"]["lr"] = lr
                if start is not None:
                    tool_call["arguments"]["start"] = start
                if num is not None:
                    tool_call["arguments"]["num"] = num
                if cites is not None:
                    tool_call["arguments"]["cites"] = cites
                if as_ylo is not None:
                    tool_call["arguments"]["as_ylo"] = as_ylo
                if as_yhi is not None:
                    tool_call["arguments"]["as_yhi"] = as_yhi
                if scisbd is not None:
                    tool_call["arguments"]["scisbd"] = scisbd
                if cluster is not None:
                    tool_call["arguments"]["cluster"] = cluster
                if as_sdt is not None:
                    tool_call["arguments"]["as_sdt"] = as_sdt
                if safe is not None:
                    tool_call["arguments"]["safe"] = safe
                if filter_param is not None:
                    tool_call["arguments"]["filter"] = filter_param
                if as_vis is not None:
                    tool_call["arguments"]["as_vis"] = as_vis
                if as_rr is not None:
                    tool_call["arguments"]["as_rr"] = as_rr
                if raw_json:
                    tool_call["arguments"]["raw_json"] = raw_json
                if readable_json:
                    tool_call["arguments"]["readable_json"] = readable_json
                
                return GetPromptResult(
                    messages=messages,
                    tool_calls=[tool_call]
                )
            else:
                raise McpError(ErrorData(
                    code=METHOD_NOT_FOUND,
                    message=f"Unknown prompt: {name}"
                ))
        except Exception as e:
            print(f"Error in get_prompt for {name}: {str(e)}", file=sys.stderr)
            if isinstance(e, McpError):
                raise
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"Error getting prompt {name}: {str(e)}"
            ))
    
    # Start the server
    print("Starting SerpAPI Google Scholar MCP server...", file=sys.stderr)
    
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)

if __name__ == "__main__":
    # Get the directory containing this script
    script_dir = pathlib.Path(__file__).parent.absolute()
    parent_dir = script_dir.parent
    
    # Load environment variables from .env file if it exists
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