# SerpApi MCP Server

A collection of Model Context Protocol (MCP) servers that integrate with SerpAPI and YouTube to provide search capabilities and data retrieval for AI assistants.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

This project provides several MCP servers that enable AI assistants like Claude to perform various search operations and retrieve data from:

- Google Search
- Google News
- Google Scholar
- Google Trends
- YouTube Search
- YouTube Transcripts

Each server is designed to work with the Model Context Protocol (MCP), making it easy to integrate with AI assistants that support this protocol, such as Claude for Desktop or Grok.

## Features

### Google Search (`serpapi_google_search.py`)
### Google News (`serpapi_google_news.py`)
### Google Scholar (`serpapi_google_scholar.py`)
### Google Trends (`serpapi_google_trend.py`)
### YouTube Search (`serpapi_youtube_search.py`)
### YouTube Transcript (`youtube_transcript.py`)

## Installation

### Prerequisites

- Python 3.8 or higher
- A SerpAPI API key (get one at [serpapi.com](https://serpapi.com))

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/serpapi-mcp-server.git
cd serpapi-mcp-server
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install mcp serpapi python-dotenv youtube-transcript-api
```

3. Create a `.env` file in the project root based on the provided `.env.example`:
```bash
cp .env.example .env
```

4. Edit the `.env` file and add your SerpAPI API key:
```
SERPAPI_API_KEY=your_api_key_here
```

## Quick Start

1. Save the Server Code: Place the server code in a file, e.g., server.py.

2. Configure the API Key: Create a .env file in the same directory with your SerpApi API key:
```plaintext
SERPAPI_API_KEY=your_api_key_here
```

3. Run the Server: Start the server with:
```bash
python src/serpapi_google_search.py  # Or any other server file
```

4. Integrate with an MCP Client: Connect the server to an MCP client or host (e.g., Claude for Desktop).

## Usage with Claude for Desktop

1. Configure Claude for Desktop to use these MCP servers by adding them to your `claude_desktop_config.json` file:

```json
{
  "mcpServers": {
    "serpapi-google-search": {
      "type": "stdio",
      "command": "path/to/python",
      "args": [
        "path/to/serpapi-mcp-server/src/serpapi_google_search.py"
      ],
      "env": {
        "PYTHONPATH": "path/to/site-packages"
      }
    },
    "serpapi-youtube-search": {
      "type": "stdio",
      "command": "path/to/python",
      "args": [
        "path/to/serpapi-mcp-server/src/serpapi_youtube_search.py"
      ],
      "env": {
        "PYTHONPATH": "path/to/site-packages"
      }
    },
    "serpapi-google-news": {
      "type": "stdio",
      "command": "path/to/python",
      "args": [
        "path/to/serpapi-mcp-server/src/serpapi_google_news.py"
      ],
      "env": {
        "PYTHONPATH": "path/to/site-packages"
      }
    },
    "serpapi-google-trend": {
      "type": "stdio",
      "command": "path/to/python",
      "args": [
        "path/to/serpapi-mcp-server/src/serpapi_google_trend.py"
      ],
      "env": {
        "PYTHONPATH": "path/to/site-packages"
      }
    },
    "serpapi-google-scholar": {
      "type": "stdio",
      "command": "path/to/python",
      "args": [
        "path/to/serpapi-mcp-server/src/serpapi_google_scholar.py"
      ],
      "env": {
        "PYTHONPATH": "path/to/site-packages"
      }
    },
    "youtube-transcript": {
      "type": "stdio",
      "command": "path/to/python",
      "args": [
        "path/to/serpapi-mcp-server/src/youtube_transcript.py"
      ],
      "env": {
        "PYTHONPATH": "path/to/site-packages"
      }
    }
  }
}
```

2. Make sure your SerpAPI key is set in the `.env` file in the project root directory.

3. Restart Claude for Desktop to load the new configuration.

4. You can now use these search capabilities directly in your conversations with Claude.

## Example Queries

Here are some examples of how to use these servers with Claude:

### Google Search
```
Please search for "climate change solutions" and summarize the top results.
```

### Google News
```
Find the latest news about artificial intelligence.
```

### YouTube Search
```
Search for tutorial videos on Python programming.
```

### YouTube Transcript
```
Get the transcript of this YouTube video: https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

### Google Scholar
```
Find recent academic papers on quantum computing.
```

### Google Trends
```
What are the trending topics in technology right now?
```

## API Parameters

Each server supports various parameters for fine-tuning your searches. Here are some key parameters for each:

### Google Search
- `q`: Search query
- `num`: Number of results (1-100)
- `location`: Location to search from
- `time_period`: Filter by recency (e.g., 'd' for past day)
- `include_domains`/`exclude_domains`: Filter by domains
- `gl`: Country code for Google search (e.g., 'us', 'uk')
- `hl`: Language code (e.g., 'en', 'es')
- `safe`: Safe search setting ('active', 'off')

[Full Google Search API Parameters Documentation](https://serpapi.com/search-api)

### Google News
- `q`: Search query
- `publication_token`: Search within a specific publication
- `topic_token`: Search within a specific topic
- `story_token`: Get full coverage of a specific story
- `section_token`: Search within a specific section
- `gl`: Country code (e.g., 'us', 'uk')
- `hl`: Language code (e.g., 'en', 'es')

[Full Google News API Parameters Documentation](https://serpapi.com/google-news-api)

### Google Scholar
- `q`: Search query
- `hl`: Language code (e.g., 'en', 'es')
- `as_ylo`: Start year for time range
- `as_yhi`: End year for time range
- `scisbd`: Sort by date (0 for relevance, 1 for date)

[Full Google Scholar API Parameters Documentation](https://serpapi.com/google-scholar-api)

### Google Trends
- `q`: Search query (can be multiple queries separated by commas)
- `geo`: Geographic location (e.g., 'US', 'GB')
- `date`: Time range (e.g., 'now 1-d', 'now 7-d', 'today 12-m')
- `cat`: Category ID
- `gprop`: Property filter (e.g., 'web', 'news', 'images')

[Full Google Trends API Parameters Documentation](https://serpapi.com/google-trends-api)

### YouTube Search
- `search_query`: Search query
- `sp`: Filter parameters (e.g., 'CAISAhAB' for videos uploaded today)
- `gl`: Country code (e.g., 'us', 'uk')
- `hl`: Language code (e.g., 'en', 'es')

[Full YouTube Search API Parameters Documentation](https://serpapi.com/youtube-search-api)

### YouTube Transcript
- `video_url`: YouTube video URL or ID
- `with_timestamps`: Include timestamps in transcript
- `language`: Language code for transcript (default: 'en')
- `format`: Output format ('text', 'json')

For a complete list of parameters, refer to the source code documentation [YouTube Transcript API](https://github.com/jdepoix/youtube-transcript-api)
## Supported Engines

SerpAPI supports a wide range of search engines, including:

- Google
- Google Light
- Bing
- Walmart
- Yahoo
- eBay
- YouTube
- DuckDuckGo
- Yandex
- Baidu

## Development

### Running the Servers Individually

You can run each server individually for testing:

```bash
python src/serpapi_google_search.py
```

### Debugging with MCP Inspector

For development and debugging, you can use the MCP Inspector:

```bash
mcp dev src/serpapi_google_search.py
```

### Troubleshooting

#### Invalid API Key
- Verify API key configuration in `.env` file
- Confirm API key is active in SerpAPI dashboard
- Check for any quotation marks or whitespace in the API key

#### Request Failures
- Check network connectivity
- Verify API call quota hasn't been exceeded
- Validate request parameter format
- Check for rate limiting issues

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [SerpApi](https://serpapi.com) for providing the search API
- [YouTube Transcript API](https://github.com/jdepoix/youtube-transcript-api) for transcript retrieval
- The MCP protocol for enabling AI assistant integration

## Resources

- [SerpAPI Documentation](https://serpapi.com/docs)
- [MCP Protocol Documentation](https://github.com/modelcontextprotocol/mcp)
- [Claude for Desktop Documentation](https://claude.ai/docs) 