# SerpApi MCP Server - Python

A collection of Model Context Protocol (MCP) servers that integrate with SerpAPI and YouTube to provide search capabilities and data retrieval for AI assistants.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

This project provides several MCP servers that enable AI assistants like Claude to perform various search operations and retrieve data from:

- Google Search
- Google News
- Google Scholar
- Google Trends
- Google Finance
- Google Maps
- Google Images
- YouTube Search
- YouTube Transcripts

Each server is designed to work with the Model Context Protocol (MCP), making it easy to integrate with AI assistants that support this protocol, such as Claude for Desktop or Grok.

## Features

 - Google Search (`serpapi_google_search.py`)
 - Google News (`serpapi_google_news.py`)
 - Google Scholar (`serpapi_google_scholar.py`)
 - Google Trends (`serpapi_google_trend.py`)
 - Google Finance (`serpapi_google_finance.py`)
 - Google Maps (`serpapi_google_maps.py`)
 - Google Images (`serpapi_google_images.py`)
 - YouTube Search (`serpapi_youtube_search.py`)
 - YouTube Transcript (`youtube_transcript.py`)

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
pip install -r requirements.txt
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
    "serpapi-google-finance": {
      "type": "stdio",
      "command": "path/to/python",
      "args": [
        "path/to/serpapi-mcp-server/src/serpapi_google_finance.py"
      ],
      "env": {
        "PYTHONPATH": "path/to/site-packages"
      }
    },
    "serpapi-google-maps": {
      "type": "stdio",
      "command": "path/to/python",
      "args": [
        "path/to/serpapi-mcp-server/src/serpapi_google_maps.py"
      ],
      "env": {
        "PYTHONPATH": "path/to/site-packages"
      }
    },
    "serpapi-google-images": {
      "type": "stdio",
      "command": "path/to/python",
      "args": [
        "path/to/serpapi-mcp-server/src/serpapi_google_images.py"
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

Here are some examples of how to use these servers with Claude Desktop:

### Google Search
```
Please search for "climate change solutions" and summarize the top results.
```

### Google News
```
Find the latest news about artificial intelligence.
```

### Google Scholar
```
Find recent academic papers on quantum computing.
```

### Google Trends
```
What are the trending topics in technology right now?
```

### Google Finance
```
Look up the current stock price and financial information for Apple (AAPL).
```

### Google Maps
```
Find coffee shops near Central Park, New York.
```

### Google Images
```
Search for images of "northern lights" and describe what you see.
```

### YouTube Search
```
Search for tutorial videos on Python programming.
```

### YouTube Transcript
```
Get the transcript of this YouTube video: https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

## API Parameters

Each server supports various parameters for fine-tuning your searches. Here are all the parameters for each:

### Google Search
- `q`: Search query
- `num`: Number of results (1-100)
- `start`: Result offset for pagination (1-based indexing)
- `location`: Location to search from
- `gl`: Country code for Google search (e.g., 'us', 'uk')
- `hl`: Language code (e.g., 'en', 'es')
- `device`: Device type ('desktop', 'mobile', 'tablet')
- `safe`: Safe search setting ('active', 'off')
- `filter`: Filter duplicate content ('0' for off, '1' for on)
- `time_period`: Filter by recency (e.g., 'd' for past day)
- `exactTerms`: Words or phrases that should appear exactly
- `include_domains`: List of domains to include in search results
- `exclude_domains`: List of domains to exclude from search results
- `raw_json`: Return complete raw JSON response (boolean)
- `readable_json`: Return results in markdown-formatted text (boolean)

[Full Google Search API Parameters Documentation](https://serpapi.com/search-api)

### Google News
- `q`: Search query
- `gl`: Country code (e.g., 'us', 'uk')
- `hl`: Language code (e.g., 'en', 'es')
- `publication_token`: Search within a specific publication
- `topic_token`: Search within a specific topic
- `story_token`: Get full coverage of a specific story
- `section_token`: Search within a specific section
- `so`: Sorting method ('0' for relevance, '1' for date)
- `raw_json`: Return complete raw JSON response (boolean)
- `readable_json`: Return results in markdown-formatted text (boolean)

[Full Google News API Parameters Documentation](https://serpapi.com/google-news-api)

### Google Scholar
- `q`: Search query
- `hl`: Language code (e.g., 'en', 'es')
- `lr`: Language restriction (e.g., 'lang_fr|lang_de')
- `start`: Result offset for pagination
- `num`: Number of results (1-20)
- `cites`: ID for cited by searches
- `as_ylo`: Start year for time range
- `as_yhi`: End year for time range
- `scisbd`: Sort by date (0 for relevance, 1 for abstracts, 2 for everything)
- `cluster`: ID for all versions searches
- `as_sdt`: Search type or filter
- `safe`: Safe search setting ('active', 'off')
- `filter`: Filter for similar/omitted results ('0' for off, '1' for on)
- `as_vis`: Include citations ('0' to include, '1' to exclude)
- `as_rr`: Show only review articles ('0' for all, '1' for reviews only)
- `raw_json`: Return complete raw JSON response (boolean)
- `readable_json`: Return results in markdown-formatted text (boolean)

[Full Google Scholar API Parameters Documentation](https://serpapi.com/google-scholar-api)

### Google Trends
- `q`: Search query (can be multiple queries separated by commas)
- `geo`: Geographic location (e.g., 'US', 'GB')
- `date`: Time range (e.g., 'now 1-d', 'now 7-d', 'today 12-m')
- `tz`: Time zone offset in minutes
- `data_type`: Type of search (e.g., 'TIMESERIES', 'GEO_MAP')
- `cat`: Category ID
- `gprop`: Property filter (e.g., 'web', 'news', 'images')
- `raw_json`: Return complete raw JSON response (boolean)
- `readable_json`: Return results in markdown-formatted text (boolean)

[Full Google Trends API Parameters Documentation](https://serpapi.com/google-trends-api)

### Google Finance
- `q`: Search query for a stock, index, mutual fund, currency or futures
- `hl`: Language code (e.g., 'en', 'es')
- `window`: Time range for the graph (e.g., '1D', '5D', '1M', '6M', 'YTD', '1Y', '5Y', 'MAX')
- `raw_json`: Return complete raw JSON response (boolean)
- `readable_json`: Return results in markdown-formatted text (boolean)

[Full Google Finance API Parameters Documentation](https://serpapi.com/google-finance-api)

### Google Maps
- `q`: Search query
- `type`: Type of search ('search' or 'place')
- `place_id`: Unique reference to a place on Google Maps
- `data`: Filter search results or search for a specific place
- `ll`: GPS coordinates in format '@latitude,longitude,zoom'
- `google_domain`: Google domain to use (defaults to google.com)
- `hl`: Language code (e.g., 'en', 'es')
- `gl`: Country code (e.g., 'us', 'uk')
- `start`: Result offset for pagination (integer)
- `raw_json`: Return complete raw JSON response (boolean)
- `readable_json`: Return results in markdown-formatted text (boolean)

[Full Google Maps API Parameters Documentation](https://serpapi.com/google-maps-api)

### Google Images
- `q`: Search query
- `location`: Location to search from
- `uule`: Google encoded location (cannot be used with location)
- `google_domain`: Google domain to use (defaults to google.com)
- `hl`: Language code (e.g., 'en', 'es')
- `gl`: Country code (e.g., 'us', 'uk')
- `cr`: Country restriction (e.g., 'countryUS')
- `device`: Device type ('desktop', 'tablet', 'mobile')
- `ijn`: Page number (zero-based index)
- `chips`: Filter string provided by Google as suggested search
- `tbs`: Advanced search parameters
- `imgar`: Aspect ratio of images ('s' - Square, 't' - Tall, 'w' - Wide, 'xw' - Panoramic)
- `imgsz`: Size of images ('l' - Large, 'm' - Medium, 'i' - Icon, etc.)
- `image_color`: Color of images ('red', 'blue', 'green', 'black', 'white', etc.)
- `image_type`: Type of images ('face', 'photo', 'clipart', 'lineart', 'animated')
- `licenses`: Scope of licenses ('f' - Free to use, 'fc' - Free commercial use, etc.)
- `safe`: Safe search setting ('active', 'off')
- `nfpr`: Exclude auto-corrected results ('1' to exclude, '0' to include)
- `filter`: Enable/disable 'Similar Results' and 'Omitted Results' filters
- `time_period`: Filter by recency (e.g., 'd' for past day)
- `raw_json`: Return complete raw JSON response (boolean)
- `readable_json`: Return results in markdown-formatted text (boolean)

[Full Google Images API Parameters Documentation](https://serpapi.com/google-images-api)

### YouTube Search
- `search_query`: Search query
- `gl`: Country code (e.g., 'us', 'uk')
- `hl`: Language code (e.g., 'en', 'es')
- `sp`: Filter parameters (e.g., 'CAISAhAB' for videos uploaded today)
- `raw_json`: Return complete raw JSON response (boolean)
- `readable_json`: Return results in markdown-formatted text (boolean)

[Full YouTube Search API Parameters Documentation](https://serpapi.com/youtube-search-api)

### YouTube Video
- `v`: YouTube video ID
- `gl`: Country code (e.g., 'us', 'uk')
- `hl`: Language code (e.g., 'en', 'es')
- `next_page_token`: Token for retrieving next page of related videos, comments or replies
- `raw_json`: Return complete raw JSON response (boolean)
- `readable_json`: Return results in markdown-formatted text (boolean)

### YouTube Transcript
- `video_url`: YouTube video URL or ID
- `with_timestamps`: Include timestamps in transcript (boolean)
- `language`: Language code for transcript (default: 'en')
- `preserve_formatting`: Preserve HTML formatting elements (boolean)
- `cookies_path`: Path to cookies.txt file for age-restricted videos
- `proxy`: HTTPS proxy to use for the request
- `raw_json`: Return complete raw JSON response (boolean)
- `readable_json`: Return human-readable formatted text (boolean)
- `text_transcript`: Return transcript as a single text string (boolean)

[YouTube Transcript API Documentation](https://github.com/jdepoix/youtube-transcript-api)

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

<meta name="google-site-verification" content="7IUYOCgEkfkiWIEriwc2wXkKfrWOHg2SzPp8BKGEh7g" />
