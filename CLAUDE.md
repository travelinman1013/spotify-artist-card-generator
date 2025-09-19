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

## Core Features ✅ COMPLETE (September 18, 2025)

### Streamlit Web Interface
- **File Browser**: Modal-style archive file selection with validation
- **Triple Modes**: Image downloader + Artist card generator + Biography enhancement tabs
- **Real-time Progress**: Live log output and progress tracking
- **API Key Management**: Secure Google Gemini API key handling for AI features

### Artist Card Generation
- **Multi-API Integration**: Spotify + Wikipedia/Wikidata + MusicBrainz
- **Rich Metadata**: Birth/death dates, genres, albums, top tracks, biography
- **YAML Frontmatter**: Structured data for Obsidian compatibility
- **Image Downloads**: High-resolution artist portraits with sanitized filenames

### AI Biography Enhancement
- **Intelligent Assessment**: Gemini AI evaluates if enhancement adds substantial value
- **Artist Network Extraction**: Identifies mentors, collaborators, influenced artists
- **Biography Accuracy Verification**: Detects and corrects artist/album/song mismatches
- **Automatic Re-fetching**: Finds correct Wikipedia pages when mismatches detected

## Command Line Usage

```bash
# Single artist mode
python spotify_artist_card_generator.py --artist "John Coltrane" --output-dir "/path/to/Artists"

# Batch processing
python spotify_artist_card_generator.py --input-file "daily_archive.md" --output-dir "/path/to/Artists" --images-dir "/path/to/Images"

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
musical_connections:
  mentors: ["Miles Davis", "Charlie Parker"]
  collaborators: ["McCoy Tyner", "Elvin Jones"]
  influenced: ["Pharoah Sanders", "David Murray"]
  bands: ["John Coltrane Quartet"]
---

# Artist Name
## Biography
[Comprehensive AI-enhanced biography with **bolded artist names**]
## Musical Connections
- **[[Miles Davis]]** - Provided crucial early career opportunities
- **[[McCoy Tyner]]** - Pianist in the classic quartet
## Discography
[Albums and singles tables]
```

## Dependencies & Setup

- Python 3.7+, requests, pillow, beautifulsoup4, streamlit, google-generativeai, pyyaml, tqdm

```bash
# Get Gemini API key from https://makersuite.google.com/app/apikey
export GOOGLE_API_KEY='your-api-key-here'
```

## Current Status (September 18, 2025)

✅ **ALL MAJOR FEATURES COMPLETE + AI ENHANCEMENT + ACCURACY VERIFICATION**

### Recently Fixed
- **KeyError 'show_warning'**: Fixed inconsistent log_filters initialization between spotify_ui.py and enhanced_logging.py
- **Biography Accuracy Verification**: AI-powered detection of artist/album/song mismatches
- **Wikipedia Search Accuracy**: Better disambiguation between artists and albums/songs
- **Streamlit File Browser**: Fixed session state conflicts and widget key issues

The project is **fully feature-complete** with AI-enhanced biographies, artist network analysis, automatic accuracy verification, and a comprehensive Streamlit web interface, forming a robust foundation for a comprehensive jazz encyclopedia.