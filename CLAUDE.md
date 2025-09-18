# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python scripts for generating comprehensive Spotify artist cards for an Obsidian vault:

1. **spotify_image_downloader.py**: Downloads Spotify artist cover images from daily archive markdown files
2. **spotify_artist_card_generator.py**: Generates artist cards combining Spotify, Wikipedia, and MusicBrainz data
3. **enhance_biographies.py**: AI-powered post-processor that enhances artist biographies with comprehensive content and artist network analysis
4. **spotify_ui.py**: Streamlit web interface for running the core scripts

## Quick Start

```bash
# Setup environment
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Launch web UI
streamlit run spotify_ui.py
```

## Core Features

### Streamlit Web Interface ✅ COMPLETE (September 18, 2025)
- **File Browser**: Modal-style archive file selection with validation
- **Dual Modes**: Image downloader + Artist card generator tabs
- **Real-time Progress**: Live log output and progress tracking
- **Persistent Settings**: Saves directories and recent files to JSON
- **Session State Management**: Fixed conflicts for stable operation

### Artist Card Generation ✅ COMPLETE
- **Multi-API Integration**: Spotify + Wikipedia/Wikidata + MusicBrainz
- **Rich Metadata**: Birth/death dates, genres, albums, top tracks, biography
- **YAML Frontmatter**: Structured data for Obsidian compatibility
- **Image Downloads**: High-resolution artist portraits with sanitized filenames

### Wikipedia/Wikidata Integration ✅ COMPLETE (September 2025)
- **Structured Data**: Birth/death dates, places, instruments via Wikidata API
- **Biography Text**: Wikipedia REST API for comprehensive artist biographies
- **Fallback Strategy**: MusicBrainz when Wikipedia unavailable
- **HTML Parsing**: BeautifulSoup4 for mobile sections infobox data

### AI Biography Enhancement ✅ COMPLETE (September 18, 2025)
- **Intelligent Assessment**: Gemini AI evaluates if enhancement adds substantial value
- **Comprehensive Biographies**: Multi-paragraph, well-structured artist life stories
- **Artist Network Extraction**: Identifies mentors, collaborators, influenced artists
- **Jazz Encyclopedia**: Builds connected network of artist relationships
- **Smart Skipping**: Only enhances when significant new content is available

## Command Line Usage

```bash
# Single artist mode
python spotify_artist_card_generator.py --artist "John Coltrane" --output-dir "/path/to/Artists"

# Batch processing
python spotify_artist_card_generator.py --input-file "daily_archive.md" --output-dir "/path/to/Artists" --images-dir "/path/to/Images"

# Image downloader
python spotify_image_downloader.py --input "/path/to/archive.md" --output "/path/to/images"

# Biography enhancement (requires GOOGLE_API_KEY)
export GOOGLE_API_KEY='your-gemini-api-key'
python enhance_biographies.py --dry-run  # Preview mode
python enhance_biographies.py            # Full enhancement
```

## Configuration

### Spotify API Credentials (Hardcoded)
- Client ID: `a088edf333334899b6ad55579b834389`
- Client Secret: `78b5d889d9094ff0bb0b2a22cc8cfaac`
- Redirect URI: `http://127.0.0.1:8888/callback`

### Default Paths
- Artist Cards: `/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists`
- Artist Images: `/Users/maxwell/LETSGO/MaxVault/03_Resources/source_material/ArtistPortraits`
- Archive Search: `/Users/maxwell/LETSGO/MaxVault`

### API Keys & Rate Limiting
- **Spotify**: Hardcoded credentials, 100 requests/minute (0.6s delay)
- **Wikipedia**: 1 second delay between requests
- **MusicBrainz**: 1 second delay (required by API)
- **Gemini AI**: Requires GOOGLE_API_KEY environment variable, 2 second delays

## Input Format

Expects Obsidian daily archive markdown files with pipe-separated tables:
- Column 2: Artist name
- Column 8: Status ("✅ Found" indicates Spotify match)

Example:
```
| 06:07 | John Coltrane | Welcome | Album | jazz, bebop | Show | DJ | ✅ Found | 100.0% | [Link] |
```

## Output Format

### Artist Cards (`Artist_Name.md`)
```yaml
---
title: Artist Name
birth_date: "1926-09-23"
death_date: "1967-07-17"
genres: ["jazz", "bebop"]
spotify_data:
  id: spotify_id
  popularity: 66
  followers: 1000000
albums_count: 50
biography_source: wikipedia
---

# Artist Name

## Quick Info
- **Born**: 1926-09-23
- **Died**: 1967-07-17
- **Genres**: jazz, bebop

## Biography
[Wikipedia biography text]

## Discography
[Albums and singles tables]
```

### Artist Images (`Artist_Name.jpg`)
- Sanitized filenames (spaces → underscores)
- High resolution from Spotify
- Automatic duplicate detection

## File Structure

```
image_agent_v5/
├── spotify_image_downloader.py     # Image downloader
├── spotify_artist_card_generator.py # Artist card generator
├── enhance_biographies.py          # AI biography enhancer
├── spotify_ui.py                   # Streamlit web UI
├── requirements.txt                # Dependencies
├── spotify_ui_config.json          # UI settings (auto-generated)
├── artist_connections.json         # Network database (auto-generated)
├── venv/                           # Virtual environment
└── *.log                           # Log files
```

## Dependencies

- Python 3.7+
- Core: requests, pillow, beautifulsoup4, streamlit
- AI Enhancement: google-generativeai, pyyaml, tqdm
- Standard library: json, pathlib, datetime, logging

## AI Biography Enhancement

### Setup
```bash
# Get Gemini API key from https://makersuite.google.com/app/apikey
export GOOGLE_API_KEY='your-api-key-here'

# Install additional dependencies
pip install google-generativeai pyyaml tqdm
```

### Usage
```bash
# Dry-run mode (preview without changes)
python enhance_biographies.py --dry-run

# Full enhancement (modifies files)
python enhance_biographies.py

# Custom directory
python enhance_biographies.py --cards-dir "/path/to/artists"
```

### Features
- **Intelligent Assessment**: Only enhances when substantial new content is available
- **Artist Network**: Extracts mentors, collaborators, influenced artists
- **Enhanced Frontmatter**: Adds `musical_connections` and `biography_enhanced_at`
- **Progress Tracking**: Real-time progress bar with connection counts
- **Network Database**: Maintains `artist_connections.json` for visualization

### Example Output
```yaml
---
biography_enhanced_at: "2025-09-18T14:30:00Z"
musical_connections:
  mentors: ["Miles Davis", "Charlie Parker"]
  collaborators: ["McCoy Tyner", "Elvin Jones"]
  influenced: ["Pharoah Sanders", "David Murray"]
  bands: ["John Coltrane Quartet"]
network_extracted: true
---

## Biography
[Comprehensive AI-enhanced biography with **bolded artist names**]

## Musical Connections
### Mentors/Influences
- **[[Miles Davis]]** - Provided crucial early career opportunities

### Key Collaborators
- **[[McCoy Tyner]]** - Pianist in the classic quartet
```

## Current Status (September 18, 2025)

✅ **ALL MAJOR FEATURES COMPLETE + AI ENHANCEMENT**

### Recently Added (September 18, 2025)
- **enhance_biographies.py**: Complete AI-powered biography enhancement system
- **Artist Network Analysis**: Extracts and structures musical relationships
- **Intelligent Content Assessment**: Gemini AI evaluates enhancement value
- **Jazz Encyclopedia Foundation**: Connected network of artist relationships
- **Full Testing**: Dry-run mode and real API integration verified

### Recently Fixed
- **Streamlit File Browser**: Fixed session state conflicts and widget key issues
- **Modal Pattern**: Implemented proper Browse → Select → Confirm workflow
- **File Validation**: Added comprehensive file existence and format validation
- **End-to-End Testing**: All functionality verified working

### Known Minor Issues
- Years active calculation needs refinement
- Wikidata label extraction could be enhanced for birth places/instruments
- Mobile sections API occasionally returns 403 errors

### Next Priorities
1. Integrate biography enhancement into Streamlit UI
2. Add network visualization tools
3. Improve Wikidata label extraction for places and instruments
4. Add caching for API responses to reduce costs

The project is feature-complete with AI-enhanced biographies and artist network analysis, forming the foundation of a comprehensive jazz encyclopedia.