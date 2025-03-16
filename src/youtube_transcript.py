import os
import json
import asyncio
import sys
from typing import List, Dict, Any, Union, Optional
from pydantic import BaseModel, Field, field_validator
from typing_extensions import Annotated
import pathlib
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable
from youtube_transcript_api._transcripts import Transcript

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

class YouTubeTranscriptArgs(BaseModel):
    """Arguments for fetching YouTube video transcripts."""
    video_url: Annotated[
        str,
        Field(
            description="YouTube video URL or video ID. Supports various YouTube URL formats including standard watch URLs, youtu.be short URLs, and YouTube Shorts."
        )
    ]
    with_timestamps: Annotated[
        Optional[bool],
        Field(
            default=False,
            description="Whether to include timestamps in the transcript. If True, each line will be prefixed with a timestamp in the format [MM:SS] or [HH:MM:SS] for longer videos."
        )
    ] = False
    language: Annotated[
        Optional[str],
        Field(
            default="en",
            description="Language code for the transcript. Defaults to 'en' for English. If the specified language is not available, the API will attempt to find any available transcript."
        )
    ] = "en"
    preserve_formatting: Annotated[
        Optional[bool],
        Field(
            default=False,
            description="Whether to preserve HTML formatting elements such as <i> (italics) and <b> (bold) in the transcript."
        )
    ] = False
    cookies_path: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Path to a cookies.txt file for accessing age-restricted videos. The file should be in Netscape format."
        )
    ] = None
    proxy: Annotated[
        Optional[str],
        Field(
            default=None,
            description="HTTPS proxy to use for the request, in the format 'https://user:pass@domain:port'."
        )
    ] = None
    raw_json: Annotated[
        Optional[bool],
        Field(
            default=False,
            description="Return the complete raw JSON response with the transcript data. This includes start times, durations, and other metadata for each segment."
        )
    ] = False
    readable_json: Annotated[
        Optional[bool],
        Field(
            default=False,
            description="Return a human-readable formatted text version of the transcript instead of JSON."
        )
    ] = False
    text_transcript: Annotated[
        Optional[bool],
        Field(
            default=False,
            description="Return the transcript as a single text string with all segments joined by spaces."
        )
    ] = False

    @field_validator('proxy')
    @classmethod
    def validate_proxy(cls, v):
        if v is not None:
            if not v.startswith('https://'):
                raise ValueError("Proxy must be an HTTPS proxy in the format 'https://user:pass@domain:port'")
        return v

class CachedTranscript:
    """Cache for transcript responses to avoid redundant API calls."""
    
    def __init__(self, video_id: str, language: str, response: Union[Dict[str, Any], str, List[Dict[str, Any]]]):
        self.video_id = video_id
        self.language = language
        self.response = response

class YouTubeTranscriptServer:
    """Server for handling YouTube transcript requests."""
    
    def __init__(self):
        """Initialize the YouTube transcript server with an empty cache."""
        self.cache = {}
        
    def extract_video_id(self, url: str) -> str:
        """Extract video ID from various forms of YouTube URLs."""
        # Check if the input is already a video ID (typically 11 characters)
        if len(url) <= 11 and "/" not in url and "." not in url:
            return url
            
        parsed = urlparse(url)
        if parsed.hostname in ('youtu.be', 'www.youtu.be'):
            return parsed.path[1:]
        if parsed.hostname in ('youtube.com', 'www.youtube.com'):
            if parsed.path == '/watch':
                return parse_qs(parsed.query)['v'][0]
            elif parsed.path.startswith('/v/'):
                return parsed.path[3:]
            elif parsed.path.startswith('/shorts/'):
                return parsed.path[8:]
            elif parsed.path.startswith('/embed/'):
                return parsed.path[7:]
        raise ValueError("Could not extract video ID from URL")
    
    async def get_transcript(self, args: YouTubeTranscriptArgs) -> Union[Dict[str, Any], str, List[Dict[str, Any]]]:
        """Get transcript for a YouTube video with specified options."""
        try:
            # Extract video ID from URL or use as is if it's already a video ID
            video_id = self.extract_video_id(args.video_url)
            
            # Create a cache key
            cache_key = f"{video_id}_{args.language}_{args.with_timestamps}_{args.preserve_formatting}_{args.raw_json}_{args.readable_json}_{args.text_transcript}"
            
            # Check if we have a cached response
            if cache_key in self.cache:
                print(f"Using cached transcript for {cache_key}", file=sys.stderr)
                return self.cache[cache_key].response
            
            # Prepare proxy dict if provided
            proxies = None
            if args.proxy:
                proxies = {"https": args.proxy}
            
            # Fetch the transcript
            available_transcripts = YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxies, cookies=args.cookies_path)
            transcript = None
            
            try:
                transcript = available_transcripts.find_transcript([args.language])
            except NoTranscriptFound:
                # If the specified language is not found, try to get any available transcript
                for t in available_transcripts:
                    transcript = t
                    break
                else:
                    return f"No transcript found for video {video_id}"
            
            # Fetch the transcript data
            transcript_data = transcript.fetch()
            
            # Return raw JSON if requested
            if args.raw_json:
                response = transcript_data
                self.cache[cache_key] = CachedTranscript(video_id, args.language, response)
                return response
            
            # Format the transcript with or without timestamps
            if args.readable_json:
                if args.with_timestamps:
                    formatted_transcript = self.format_transcript_with_timestamps(transcript_data)
                else:
                    formatted_transcript = self.format_transcript_without_timestamps(transcript_data)
                
                response = formatted_transcript
                self.cache[cache_key] = CachedTranscript(video_id, args.language, response)
                return response
            
            # Return the transcript as a single text string if requested
            if args.text_transcript:
                transcript_text = " ".join(entry['text'] for entry in transcript_data)
                response = transcript_text
                self.cache[cache_key] = CachedTranscript(video_id, args.language, response)
                return response
            
            # Return the transcript data as a cleaned dictionary
            response = clean_json_dict(transcript_data)
            self.cache[cache_key] = CachedTranscript(video_id, args.language, response)
            return response
            
        except ValueError as e:
            return f"Error: {str(e)}"
        except TranscriptsDisabled:
            return "Error: Transcripts are disabled for this video"
        except VideoUnavailable:
            return f"Error: Video {args.video_url} is unavailable"
        except NoTranscriptFound:
            return f"Error: No transcript found for video {args.video_url}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def format_transcript_with_timestamps(self, transcript_data: List[Dict[str, Any]]) -> str:
        """Format transcript with timestamps."""
        def format_timestamp(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            if hours > 0:
                return f"[{hours}:{minutes:02d}:{secs:02d}]"
            return f"[{minutes}:{secs:02d}]"
        
        return "\n".join(f"{format_timestamp(entry['start'])} {entry['text']}" for entry in transcript_data)
    
    def format_transcript_without_timestamps(self, transcript_data: List[Dict[str, Any]]) -> str:
        """Format transcript without timestamps."""
        return "\n".join(entry['text'] for entry in transcript_data)

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

async def serve() -> None:
    """Start the YouTube transcript MCP server."""
    server = Server("mcp-youtube-transcript")
    youtube_server = YouTubeTranscriptServer()
    
    @server.list_tools()
    async def list_tools() -> List[Tool]:
        print("list_tools called", file=sys.stderr)
        return [
            Tool(
                name="youtube_transcript",
                description="""Get transcript from YouTube videos.
                
                This tool extracts and returns the transcript (subtitles/closed captions) from YouTube videos.
                You can provide either a full YouTube URL or just the video ID.
                
                Supported URL formats:
                - Standard watch URLs: https://www.youtube.com/watch?v=VIDEO_ID
                - Short URLs: https://youtu.be/VIDEO_ID
                - YouTube Shorts: https://www.youtube.com/shorts/VIDEO_ID
                - Embedded videos: https://www.youtube.com/embed/VIDEO_ID
                
                You can specify the language for the transcript (defaults to English).
                If the requested language is not available, the tool will attempt to return any available transcript.
                
                Timestamps can be included to show when each line appears in the video.
                HTML formatting elements can be preserved if needed.
                
                For age-restricted videos, you can provide a path to a cookies.txt file.
                A proxy can be specified for making the request.
                
                By default, returns a JSON array with transcript segments.
                Set raw_json=True to get the complete transcript data with timing information.
                Set readable_json=True to get a human-readable formatted text version.
                Set text_transcript=True to get the transcript as a single text string with all segments joined by spaces.
                """,
                inputSchema=YouTubeTranscriptArgs.model_json_schema(),
            )
        ]
    
    @server.list_prompts()
    async def list_prompts() -> List[Prompt]:
        print("list_prompts called", file=sys.stderr)
        return [
            Prompt(
                name="youtube_transcript_prompt",
                description="""Get transcript from a YouTube video.
                
                This prompt helps you extract the transcript (subtitles/closed captions) from a YouTube video.
                You can provide either a full YouTube URL or just the video ID.
                
                The transcript will be returned as text, with optional timestamps showing when each line appears in the video.
                """,
                arguments=[
                    {
                        "name": "video_url",
                        "description": "YouTube video URL or video ID",
                        "required": True,
                    },
                    {
                        "name": "with_timestamps",
                        "description": "Whether to include timestamps in the transcript",
                        "required": False,
                    },
                    {
                        "name": "language",
                        "description": "Language code for the transcript (e.g., 'en' for English)",
                        "required": False,
                    },
                    {
                        "name": "preserve_formatting",
                        "description": "Whether to preserve HTML formatting elements in the transcript",
                        "required": False,
                    },
                    {
                        "name": "text_transcript",
                        "description": "Whether to return the transcript as a single text string with all segments joined by spaces",
                        "required": False,
                    }
                ],
            )
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        print(f"call_tool called with name={name}", file=sys.stderr)
        try:
            if name == "youtube_transcript":
                args = YouTubeTranscriptArgs(**arguments)
                response = await youtube_server.get_transcript(args)
                
                # Process the response based on its type
                if isinstance(response, (list, dict)):
                    # JSON response
                    return [TextContent(type="text", text=json.dumps(response, indent=2, ensure_ascii=False))]
                elif isinstance(response, str):
                    # Formatted text transcript or error message
                    return [TextContent(type="text", text=response)]
                else:
                    # Fallback for unexpected response types
                    return [TextContent(type="text", text=str(response))]
            else:
                raise McpError(ErrorData(
                    code=METHOD_NOT_FOUND,
                    message=f"Tool '{name}' not found",
                ))
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    @server.get_prompt()
    async def get_prompt(name: str, arguments: Dict[str, Any] | None) -> GetPromptResult:
        print(f"get_prompt called with name={name}", file=sys.stderr)
        try:
            if name == "youtube_transcript_prompt":
                if arguments is None:
                    arguments = {}
                
                video_url = arguments.get("video_url", "")
                with_timestamps = arguments.get("with_timestamps", False)
                language = arguments.get("language", "en")
                preserve_formatting = arguments.get("preserve_formatting", False)
                text_transcript = arguments.get("text_transcript", False)
                
                if not video_url:
                    return GetPromptResult(
                        content=[TextContent(type="text", text="Please provide a YouTube video URL or video ID.")],
                    )
                
                args = YouTubeTranscriptArgs(
                    video_url=video_url,
                    with_timestamps=with_timestamps,
                    language=language,
                    preserve_formatting=preserve_formatting,
                    text_transcript=text_transcript,
                    readable_json=True,
                )
                
                response = await youtube_server.get_transcript(args)
                
                return GetPromptResult(
                    content=[TextContent(type="text", text=response)],
                )
            else:
                raise McpError(ErrorData(
                    code=METHOD_NOT_FOUND,
                    message=f"Prompt '{name}' not found",
                ))
        except Exception as e:
            return GetPromptResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}")],
            )
    
    print("Starting YouTube Transcript MCP server...", file=sys.stderr)
    
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)

if __name__ == "__main__":
    # Load environment variables from .env file if it exists
    load_dotenv()
    
    # Start the server
    asyncio.run(serve()) 