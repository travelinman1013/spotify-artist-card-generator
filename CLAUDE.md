# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project contains Python scripts for working with Spotify artist data and generating comprehensive artist information cards for an Obsidian vault:

1. **spotify_image_downloader.py**: Downloads Spotify artist cover images based on data from Obsidian daily archive markdown files tracking radio station songs.

2. **spotify_artist_card_generator.py**: Generates comprehensive artist cards combining:
   - Spotify API metadata (albums, tracks, popularity, followers, genres)
   - Wikipedia biographies (primary source)
   - MusicBrainz data (fallback source)
   - Creates Obsidian-compatible markdown files with YAML frontmatter

## Core Architecture

### 1. SpotifyImageDownloader Class (spotify_image_downloader.py)
- **Authentication**: Manages Spotify API client credentials flow with automatic token refresh
- **Markdown Parser**: Extracts artist names from pipe-separated tables in Obsidian daily archive files
- **Spotify Integration**: Searches for artists and retrieves highest resolution cover images
- **File Management**: Downloads images with sanitized filenames and duplicate detection
- **Error Handling**: Comprehensive logging and retry logic for API and file operations

### 2. SpotifyArtistCardGenerator Class (spotify_artist_card_generator.py)
- **Multi-API Integration**: Combines data from Spotify, Wikipedia, and MusicBrainz
- **WikipediaAPI Class**: Fetches artist biographies using Wikimedia REST API
- **MusicBrainzAPI Class**: Fallback source for artist metadata and annotations
- **Comprehensive Metadata**: Albums, singles, top tracks, related artists, genres, popularity
- **Obsidian Integration**: Generates markdown with YAML frontmatter compatible with Obsidian Bases

## Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
# OR manually install: pip install requests pillow beautifulsoup4 streamlit
```

## ✨ NEW: Web UI Interface

**spotify_ui.py**: A user-friendly Streamlit web interface for running both scripts without command-line arguments.

### Quick Start with UI
```bash
# Activate virtual environment
source venv/bin/activate

# Launch the web interface
streamlit run spotify_ui.py
```

The UI will open in your browser at `http://localhost:8501` and provides:

- **🖼️ Image Downloader Tab**: Select archive files, configure output directories, run downloads with progress tracking
- **📇 Artist Card Generator Tab**: Single artist or batch mode, real-time log output, progress monitoring
- **⚙️ Settings Tab**: Save default directories, manage recent files, export logs

### UI Features
- **File Browser**: Automatically scans for daily archive files in your vault
- **Recent Files**: Quick access to previously used archive files
- **Default Paths**: Pre-configured with your Obsidian vault directories
- **Progress Tracking**: Real-time progress bars and live log output
- **Configuration**: Persistent settings saved to `spotify_ui_config.json`
- **Log Export**: Download execution logs for debugging

## Running the Scripts

### Image Downloader
```bash
# Activate virtual environment
source venv/bin/activate

# Basic usage
python spotify_image_downloader.py \
  --input "/path/to/daily_archive.md" \
  --output "/path/to/output_directory"

# With options
python spotify_image_downloader.py \
  --input "/path/to/daily_archive.md" \
  --output "/path/to/output_directory" \
  --skip-existing \
  --log-level INFO
```

### Artist Card Generator
```bash
# Single artist mode
python spotify_artist_card_generator.py \
  --artist "Artist Name" \
  --output-dir "/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists"

# Batch processing from daily archive
python spotify_artist_card_generator.py \
  --input-file "daily_archive.md" \
  --output-dir "/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists" \
  --images-dir "/Users/maxwell/LETSGO/MaxVault/03_Resources/source_material/ArtistPortraits"

# With custom log level
python spotify_artist_card_generator.py \
  --artist "John Coltrane" \
  --output-dir "/path/to/Artists" \
  --log-level DEBUG
```

## Configuration

### Spotify API Credentials
The scripts use hardcoded Spotify app credentials:
- Client ID: `a088edf333334899b6ad55579b834389`
- Client Secret: `78b5d889d9094ff0bb0b2a22cc8cfaac`
- Redirect URI: `http://127.0.0.1:8888/callback`

### API Rate Limiting
- Spotify: 100 requests per minute (0.6 second delay between requests)
- Wikipedia: 1 second delay between requests
- MusicBrainz: 1 second delay between requests (required by their terms)
- Automatic retry logic with exponential backoff
- Token refresh handling for expired authentication

## Input File Format

The scripts expect Obsidian daily archive markdown files with pipe-separated tables containing:
- Column 2: Artist name
- Column 8: Status ("✅ Found" indicates Spotify match)

Example table row:
```
| 06:07 | John Coltrane | Welcome | The Gentle Side of John Coltrane | jazz, hard bop, free jazz | The Morning Set | Breaux Bridges | ✅ Found | 100.0% | [Open](https://open.spotify.com/track/...) |
```

## Output Format

### Artist Images
- Images saved with sanitized artist names (spaces → underscores, special characters removed)
- Format: `Artist_Name.jpg` (preserves original image format from Spotify)
- Location: `/Users/maxwell/LETSGO/MaxVault/03_Resources/source_material/ArtistPortraits/`
- Automatic duplicate detection and skipping

### Artist Cards
- Markdown files with YAML frontmatter
- Location: `/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists/`
- Format: `Artist_Name.md`
- Includes comprehensive metadata, biography, discography, and cross-links to related artists

## Artist Card Structure

```yaml
---
title: Artist Name
genres: ["genre1", "genre2"]
spotify_data:
  id: spotify_artist_id
  url: spotify_url
  popularity: 0-100
  followers: number
albums_count: number
singles_count: number
top_tracks: ["track1", "track2"]
related_artists: ["artist1", "artist2"]
biography_source: wikipedia/musicbrainz/none
external_urls:
  spotify: url
  wikipedia: url
  musicbrainz: url
image_path: relative/path/to/image
entry_created: ISO timestamp
---

# Artist Name

## Quick Info
[Artist metadata summary]

## Biography
[Wikipedia/MusicBrainz biography text]

## Discography
[Albums and singles tables]

## Top Tracks
[Numbered list of popular songs]

## Related Artists
[Cross-linked artist names]

## External Links
[Links to Spotify, Wikipedia, MusicBrainz]
```

## Logging

- Logs to both console and log files (`spotify_downloader.log`, `artist_card_generator.log`)
- Configurable log levels: DEBUG, INFO, WARNING, ERROR
- Tracks processing progress, API calls, success/failure
- Final summary with statistics (total, success, failed, skipped)

## ✅ COMPLETED: Enhanced Wikipedia/Wikidata API Integration

### Recently Implemented (September 2025)
**COMPLETED**: Successfully implemented comprehensive Wikipedia/Wikidata API integration for structured artist data extraction:

#### **1. Wikidata API Integration** ✅
- **Primary source**: Wikidata REST API for structured data
- **Entity lookup**: Wikipedia Action API to get Wikidata entity IDs
- **Extracted data**: Birth/death dates, places, instruments, career periods
- **Reliability**: Wikidata provides authoritative, structured information

#### **2. Mobile Sections API** ✅
- **Secondary source**: Wikipedia REST API mobile sections for infobox HTML
- **HTML parsing**: BeautifulSoup4 integration for extracting structured data
- **Fallback**: Graceful handling when mobile API returns 403 errors

#### **3. Enhanced Artist Cards** ✅
- **YAML frontmatter**: Now includes structured fields (birth_date, death_date, etc.)
- **Quick Info section**: Displays birth/death dates, instruments, years active
- **Comprehensive data**: Combines Spotify + Wikipedia + Wikidata information

#### **4. Successful Test Results** ✅
Example output for John Coltrane:
```yaml
birth_date: "1926-09-23"
death_date: "1967-07-17"
biography_source: wikipedia
wikipedia_url: "https://en.wikipedia.org/wiki/John_Coltrane"
```

Quick Info display:
```markdown
- **Born**: 1926-09-23
- **Died**: 1967-07-17
- **Genres**: jazz, hard bop, bebop, free jazz, cool jazz
```

### **Architecture: Single API Family Approach** ✅
- **Wikimedia REST API**: Page summaries and mobile sections
- **Wikipedia Action API**: Wikidata entity lookup
- **Wikidata API**: Structured claims extraction
- **No additional APIs needed**: MediaWiki Action API not required

### **Dependencies Added**
- `beautifulsoup4`: For HTML parsing (mobile sections)

## TODO / Future Enhancements

### Current Status: Enhanced Wikipedia Integration COMPLETE

### Next Priority Enhancements

1. **Improve Wikidata Label Extraction**:
   - Complete implementation of `_extract_wikidata_label()` and `_extract_wikidata_labels()`
   - Add birth place and instruments extraction from Wikidata
   - Implement additional API calls to resolve Wikidata entity labels

2. **Fine-tune Years Active Calculation**:
   - Improve logic for extracting accurate career start dates
   - Add fallback to biographical text parsing when Wikidata work periods are incomplete
   - Handle edge cases for living vs. deceased artists

3. **Enhanced HTML Parsing**:
   - Add User-Agent rotation to avoid 403 errors on mobile sections API
   - Implement more robust infobox parsing patterns
   - Add support for different Wikipedia infobox templates

### Additional Enhancements
- Add support for batch updating existing artist cards with new structured data
- Implement caching for API responses to reduce rate limiting
- Add support for multiple language Wikipedia sources
- Create a web interface for browsing/searching artist cards
- Add support for album artwork downloads
- Generate artist relationship graphs for Obsidian's graph view
- Add lyrics integration from Genius API
- Create playlists based on artist relationships

## Dependencies

- Python 3.7+
- requests (for API calls)
- pillow (for image processing)
- beautifulsoup4 (for HTML parsing - added September 2025)
- streamlit (for web UI - added September 2025)
- Standard library: json, base64, pathlib, datetime, urllib, logging

## File Structure

```
image_agent_v5/
├── spotify_image_downloader.py     # Original image downloader
├── spotify_artist_card_generator.py # New artist card generator
├── spotify_ui.py                   # NEW: Streamlit web UI (September 2025)
├── requirements.txt                # Python dependencies
├── spotify_ui_config.json          # UI settings (auto-generated)
├── CLAUDE.md                        # This file
├── venv/                           # Python virtual environment
└── *.log                           # Log files (gitignored)
```

## Notes for Future Sessions

### Current Implementation Status (September 2025)
- ✅ **Wikipedia/Wikidata Integration**: COMPLETE - Successfully extracting structured data (birth/death dates, biography)
- ✅ **Enhanced Artist Cards**: COMPLETE - Rich YAML frontmatter with biographical data
- ✅ **Single API Strategy**: COMPLETE - Using only Wikimedia/Wikipedia/Wikidata APIs
- ✅ **Streamlit Web UI**: COMPLETE - Full-featured web interface with file browsers and progress tracking
- ✅ **Session State Fix**: COMPLETE - Fixed Streamlit session state conflicts for stable operation

### ✨ Latest Addition: Streamlit Web UI (September 18, 2025)
**COMPLETED**: Successfully implemented and debugged a comprehensive web interface:

#### **UI Features** ✅
- **Dual-mode operation**: Image downloader and Artist card generator tabs
- **File browser integration**: Automatically scans vault for daily archive files
- **Recent files management**: Quick access to previously used archive files
- **Real-time progress tracking**: Live progress bars and log output during execution
- **Persistent configuration**: Saves default directories and settings
- **Error handling**: Proper Streamlit session state management

#### **Technical Implementation** ✅
- **Session state management**: Fixed conflicts between widget keys and programmatic updates
- **File discovery**: Smart scanning for archive files with date/archive patterns
- **Command execution**: Subprocess integration with real-time output capture
- **Configuration persistence**: JSON-based settings storage

#### **Debugging Completed** ✅
- **Problem**: `StreamlitAPIException` when trying to modify widget-bound session state
- **Solution**: Implemented separate state variables with `st.rerun()` for file browser functionality
- **Result**: Stable UI operation without session state conflicts

### Implementation Details
- **WikipediaAPI.get_artist_structured_data()**: Main method combining all data sources
- **Wikidata Claims Extraction**: Working for dates (P569/P570), needs label extraction completion
- **Mobile Sections Fallback**: Implemented but may encounter 403 errors
- **Rate Limiting**: Conservative (1 second delays) - can be optimized if needed
- **UI Architecture**: Streamlit-based with tabbed interface and persistent configuration

### Minor Issues to Address
- Years active calculation needs refinement (currently getting incorrect start dates)
- Wikidata label extraction methods need completion for birth place and instruments
- Mobile sections API may need User-Agent rotation to avoid blocks

The project now has a complete end-to-end solution: rich biographical data extraction + user-friendly web interface.