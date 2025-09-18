# 🎵 Spotify Artist Tools

A comprehensive Python toolkit for building a personal artist knowledge base using Spotify API data, Wikipedia biographies, and Obsidian integration. Generate rich artist cards with biographical data, download cover images, and manage everything through a user-friendly web interface.

## ✨ Features

### 🖼️ Image Downloader
- **Automatic Discovery**: Scans Obsidian daily archive files for artist mentions
- **High-Quality Downloads**: Retrieves highest resolution artist images from Spotify
- **Smart Management**: Duplicate detection and organized file naming
- **Batch Processing**: Process entire archive files with progress tracking

### 📇 Artist Card Generator
- **Rich Metadata**: Combines Spotify, Wikipedia, and Wikidata sources
- **Biographical Data**: Birth/death dates, career periods, instruments, genres
- **Comprehensive Discography**: Albums, singles, top tracks, related artists
- **Obsidian Integration**: YAML frontmatter compatible with Obsidian databases
- **Structured Output**: Cross-linked markdown files for your knowledge vault

### 🌐 Web Interface (NEW!)
- **User-Friendly UI**: Streamlit-based web interface for all operations
- **File Browser**: Automatically discovers archive files in your vault
- **Real-Time Progress**: Live progress bars and log output
- **Persistent Settings**: Saves default directories and recent files
- **Dual Mode**: Single artist or batch processing

## 🚀 Quick Start

### Installation

```bash
# Clone or download the project
cd image_agent_v5

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Launch Web Interface

```bash
# Activate virtual environment
source venv/bin/activate

# Start the web UI
streamlit run spotify_ui.py
```

The interface will open at `http://localhost:8501` with three tabs:
- **🖼️ Image Downloader**: Download artist images from archives
- **📇 Artist Card Generator**: Create comprehensive artist profiles
- **⚙️ Settings**: Configure directories and manage files

### Command Line Usage

If you prefer command-line operation:

```bash
# Download images from daily archive
python spotify_image_downloader.py \
  --input "/path/to/daily_archive.md" \
  --output "/path/to/images/"

# Generate single artist card
python spotify_artist_card_generator.py \
  --artist "John Coltrane" \
  --output-dir "/path/to/artist_cards/"

# Batch generate from archive
python spotify_artist_card_generator.py \
  --input-file "/path/to/daily_archive.md" \
  --output-dir "/path/to/artist_cards/" \
  --images-dir "/path/to/images/"
```

## 📊 Output Examples

### Artist Card Structure
```yaml
---
title: John Coltrane
genres: ["jazz", "hard bop", "bebop", "free jazz"]
birth_date: "1926-09-23"
death_date: "1967-07-17"
biography_source: wikipedia
spotify_data:
  id: spotify_artist_id
  popularity: 78
  followers: 1234567
albums_count: 25
top_tracks: ["Giant Steps", "A Love Supreme", "My Favorite Things"]
related_artists: ["Miles Davis", "Thelonious Monk", "Bill Evans"]
wikipedia_url: "https://en.wikipedia.org/wiki/John_Coltrane"
image_path: "../../03_Resources/source_material/ArtistPortraits/John_Coltrane.jpg"
entry_created: "2025-09-18T12:34:56Z"
---

# John Coltrane

## Quick Info
- **Born**: 1926-09-23
- **Died**: 1967-07-17
- **Genres**: jazz, hard bop, bebop, free jazz
- **Popularity**: 78/100
- **Followers**: 1.2M

## Biography
[Rich biographical content from Wikipedia...]

## Discography
[Albums and singles tables...]

## Top Tracks
1. Giant Steps
2. A Love Supreme
3. My Favorite Things

## Related Artists
- [[Miles Davis]]
- [[Thelonious Monk]]
- [[Bill Evans]]

## External Links
- [Spotify](https://open.spotify.com/artist/...)
- [Wikipedia](https://en.wikipedia.org/wiki/John_Coltrane)
```

### Archive File Format
Expected input format for daily archive files:
```markdown
| Time  | Artist        | Song     | Album        | Genres    | Show | Location | Status    | Match | Link |
|-------|---------------|----------|--------------|-----------|------|----------|-----------|-------|------|
| 06:07 | John Coltrane | Welcome  | Giant Steps  | jazz      | Morning | Studio | ✅ Found | 100%  | [Link] |
```

## 🔧 Configuration

### Spotify API
The scripts use pre-configured Spotify credentials for read-only access. No setup required.

### Default Paths
The web UI is pre-configured for this Obsidian vault structure:
- **Artist Cards**: `/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists`
- **Artist Images**: `/Users/maxwell/LETSGO/MaxVault/03_Resources/source_material/ArtistPortraits`
- **Archive Search**: `/Users/maxwell/LETSGO/MaxVault`

Paths can be customized in the Settings tab.

### File Naming
- **Images**: `Artist_Name.jpg` (spaces→underscores, special chars removed)
- **Cards**: `Artist_Name.md` (same sanitization)
- **Config**: `spotify_ui_config.json` (auto-generated)

## 🛠️ Architecture

### Core Components

1. **SpotifyImageDownloader**: Handles artist image discovery and download
   - Spotify API authentication and search
   - Archive file parsing for artist extraction
   - High-resolution image retrieval and storage

2. **SpotifyArtistCardGenerator**: Creates comprehensive artist profiles
   - Multi-API integration (Spotify + Wikipedia + Wikidata)
   - Structured data extraction and formatting
   - Obsidian-compatible markdown generation

3. **Web UI (spotify_ui.py)**: User-friendly interface
   - Streamlit-based tabbed interface
   - File browser integration with vault scanning
   - Real-time progress tracking and log display
   - Persistent configuration management

### Data Sources

- **Spotify API**: Discography, popularity, genres, related artists
- **Wikipedia**: Biographical narratives and career information
- **Wikidata**: Structured biographical data (birth/death dates, instruments)

### APIs Used

- **Spotify Web API**: Artist search, albums, tracks, images
- **Wikipedia REST API**: Page summaries and mobile sections
- **Wikidata API**: Structured claims and entity data
- **Wikipedia Action API**: Entity ID lookup for Wikidata integration

## 📁 Project Structure

```
image_agent_v5/
├── spotify_image_downloader.py     # Image download functionality
├── spotify_artist_card_generator.py # Artist card generation
├── spotify_ui.py                   # Web interface (NEW!)
├── requirements.txt                # Python dependencies
├── spotify_ui_config.json          # UI settings (auto-generated)
├── CLAUDE.md                       # Developer documentation
├── README.md                       # This file
├── venv/                           # Python virtual environment
└── *.log                           # Log files (gitignored)
```

## 🔍 Logging & Debugging

### Log Levels
- **DEBUG**: Detailed API calls and processing steps
- **INFO**: General operation progress and results
- **WARNING**: Non-critical issues and fallbacks
- **ERROR**: Failed operations and critical errors

### Log Files
- `spotify_downloader.log`: Image download operations
- `artist_card_generator.log`: Card generation operations
- Web UI logs can be exported from the Settings tab

### Rate Limiting
- **Spotify**: 100 requests/minute (0.6s delay between calls)
- **Wikipedia**: 1 second delay between requests
- **Wikidata**: 1 second delay (required by terms of service)

## ⚡ Performance

### Processing Speed
- **Single Artist**: ~3-5 seconds (including API calls)
- **Batch Processing**: ~5-10 artists per minute
- **Image Downloads**: ~2-3 seconds per image

### Resource Usage
- **Memory**: ~50-100MB during operation
- **Storage**: Images ~100-500KB each, cards ~10-50KB each
- **Network**: Conservative rate limiting prevents API throttling

## 🚧 Known Issues & Limitations

### Minor Issues
- Years active calculation occasionally shows incorrect start dates
- Wikidata label extraction for instruments/birthplace needs refinement
- Wikipedia mobile sections API may return 403 errors occasionally

### Limitations
- Requires internet connection for all operations
- Limited to publicly available Spotify content
- Wikipedia/Wikidata data quality varies by artist
- English Wikipedia only (could be extended to other languages)

## 🛣️ Future Enhancements

### Planned Features
- **Multi-language Support**: Wikipedia sources in multiple languages
- **Lyrics Integration**: Genius API integration for song lyrics
- **Album Artwork**: Download and organize album cover images
- **Graph Visualization**: Artist relationship networks for Obsidian
- **Playlist Generation**: Create playlists based on artist relationships

### Technical Improvements
- **Caching System**: Local caching for API responses
- **User-Agent Rotation**: Avoid Wikipedia API blocks
- **Batch Updates**: Update existing cards with new data
- **Performance Optimization**: Concurrent API calls and faster processing

## 📜 License

This project is for personal use. Spotify API usage follows their developer terms of service.

## 🙏 Acknowledgments

- **Spotify Web API**: Artist data and high-quality images
- **Wikipedia/Wikimedia**: Comprehensive biographical information
- **Wikidata**: Structured knowledge base
- **Streamlit**: Excellent framework for rapid UI development
- **BeautifulSoup**: HTML parsing for Wikipedia mobile sections

---

*Last updated: September 18, 2025*
*Version: 1.0 - Full web interface with session state fixes*