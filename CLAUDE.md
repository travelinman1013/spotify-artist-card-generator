# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Spotify Artist Tools is a Python-based system for building a personal artist knowledge base integrated with Obsidian. It combines data from Spotify API, Wikipedia, and Wikidata to create comprehensive artist profiles with images, biographies, and structured metadata.

## Core Architecture

### Three-Tier System

1. **Image Downloader** (`spotify_image_downloader.py`)
   - Parses markdown table archives to extract artist names
   - Downloads highest-resolution artist images from Spotify
   - Handles duplicate detection and sanitized filename generation
   - Uses rate limiting (0.6s delay) to respect Spotify API limits

2. **Artist Card Generator** (`spotify_artist_card_generator.py`)
   - Multi-API data aggregation from Spotify, Wikipedia, and Wikidata
   - Creates Obsidian-compatible markdown files with YAML frontmatter
   - Handles complex data extraction from Wikipedia infoboxes and Wikidata entities
   - Fallback hierarchy: Wikipedia → Wikidata → MusicBrainz
   - Special handling for `years_active` field: prefers Wikipedia wikitext parsing over Wikidata estimates

3. **Biography Enhancement** (`enhance_biographies.py` / `enhance_biographies_perplexity.py`)
   - AI-powered biography enrichment using Google Gemini or Perplexity AI
   - **Gemini Version**: Original implementation using Google Gemini API
   - **Perplexity Version** (NEW): Enhanced research using Perplexity's web search capabilities
   - Extracts artist connections and relationships from Wikipedia content
   - Builds network graph of related artists for encyclopedia purposes
   - Requires `GOOGLE_API_KEY` (Gemini) or `PERPLEXITY_API_KEY` (Perplexity) environment variable

### Web Interface (`spotify_ui.py`)

Streamlit-based UI with three main tabs:
- **Image Downloader**: File upload with batch processing
- **Artist Card Generator**: Single artist or batch mode
- **Biography Enhancement**: AI-powered biography expansion with network analysis
- **Settings**: Configuration persistence via `spotify_ui_config.json`

Session state management for uploaded files uses temporary file handling with cleanup on session end.

## Common Commands

### Setup and Installation
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Running the Application

```bash
# Start the web UI (primary interface)
streamlit run spotify_ui.py
```

### Command-Line Tools

```bash
# Download artist images from archive file
python spotify_image_downloader.py \
  --input "/path/to/daily_archive.md" \
  --output "/path/to/images/" \
  --skip-existing

# Generate single artist card
python spotify_artist_card_generator.py \
  --artist "Artist Name" \
  --output-dir "/path/to/cards/" \
  --images-dir "/path/to/images/"

# Batch generate from archive file
python spotify_artist_card_generator.py \
  --input-file "/path/to/daily_archive.md" \
  --output-dir "/path/to/cards/" \
  --images-dir "/path/to/images/" \
  --log-level INFO

# Enhance biographies with AI (Gemini)
export GOOGLE_API_KEY="your-api-key"
python enhance_biographies.py \
  --cards-dir "/path/to/cards/" \
  --dry-run  # Preview changes without modifying files
  --force    # Re-enhance already processed files

# Enhance biographies with AI (Perplexity - recommended)
export PERPLEXITY_API_KEY="your-api-key"
python enhance_biographies_perplexity.py \
  --cards-dir "/path/to/cards/" \
  --dry-run  # Preview changes without modifying files
  --force    # Re-enhance already processed files
```

## Data Flow and API Integration

### Archive File Format

Input files are markdown tables with this structure:
```markdown
| Time  | Artist | Song | Album | Genres | Show | Location | Status    | Match | Link |
| 06:07 | Name   | Song | Album | jazz   | Show | Studio   | ✅ Found | 100%  | URL  |
```

Only rows with `Status = "✅ Found"` are processed.

### Spotify API Authentication

Uses Client Credentials flow with hardcoded credentials (read-only access). Token auto-refresh implemented with 60-second buffer before expiration.

### Wikipedia Data Extraction Strategy

1. **Search**: REST API with multiple search strategies (artist name, "artist band", "artist musician")
2. **Summary**: Get basic biography via `/page/summary/` endpoint
3. **Structured Data**:
   - Primary: Mobile sections API (`/page/mobile-sections/`)
   - Fallback: Action API wikitext parsing when mobile API returns 403
   - Wikitext parsing handles `years_active`, `birth_date`, `death_date`, `instruments` fields
4. **Wikidata**: Entity lookup via Wikipedia pageprops, then structured claims extraction

### Wikidata Properties Used

- P569: Date of birth
- P570: Date of death
- P19: Place of birth
- P1303: Instruments played
- P1477: Birth name
- P742: Pseudonym (also known as)
- P1449: Nickname
- P106: Occupation
- P264: Record label
- P26: Spouse
- P2032/P2034: Work period start/end

### Perplexity API Integration (NEW)

The `enhance_biographies_perplexity.py` script uses Perplexity AI for improved biography enhancement:

**Key Features:**
- Real-time web search for up-to-date artist information beyond Wikipedia
- Native citation support for better source verification
- Structured JSON output mode for cleaner artist connection extraction
- OpenAI-compatible API using the `openai` Python client

**Configuration:**
- API Base URL: `https://api.perplexity.ai`
- Model: `sonar-pro` (recommended for high-quality research)
- Temperature: 0.3 (balanced creativity and accuracy)
- Max Tokens: 2048 (standard), 4096 (biography generation)

**Advantages over Gemini:**
- Better at finding and verifying artist connections from multiple sources
- Real-time web search can discover recent information not in Wikipedia
- More accurate at extracting structured relationship data
- Built-in citation tracking improves source verification

**Setup:**
1. Get API key from https://www.perplexity.ai/settings/api
2. Set environment variable: `export PERPLEXITY_API_KEY='your-key'`
3. Run with same CLI interface as Gemini version

**Frontmatter Tracking:**
Enhanced files include `enhancement_provider: 'perplexity'` to distinguish from Gemini-enhanced biographies.

## File Structure and Naming

### Generated Files

**Artist Cards**: `{Artist_Name}.md` in output directory
- Spaces → underscores
- Special characters removed
- Ampersands → "and"
- Max 200 characters

**Artist Images**: `{Artist_Name}.jpg` in images directory
- Same sanitization rules
- Extensions: .jpg (default), .png, .webp

**Configuration**: `spotify_ui_config.json` (auto-generated)
- Stores default directories
- Maintains recent files list (max 10)
- Session-specific settings for web UI

### Obsidian Integration

Generated markdown files include:
- YAML frontmatter with structured metadata
- Wikilinks to related artists: `[[Artist Name]]`
- Relative image paths: `![]({filename})`
- External links to Spotify, Wikipedia, MusicBrainz

## Important Implementation Details

### Years Active Field Priority

The `years_active` field uses Wikipedia wikitext parsing over Wikidata estimates because:
1. Wikipedia often has manually curated ranges (e.g., "1945-1967")
2. Wikidata may only have start year, requiring estimation
3. Code at `spotify_artist_card_generator.py:1034-1039` preserves Wikipedia data when it contains a range

### Rate Limiting

- **Spotify**: 100 req/min (0.6s delay)
- **Wikipedia**: 1s delay between requests
- **Wikidata**: 1s delay (required by ToS)
- **MusicBrainz**: 1s delay (strictly enforced)

### Error Handling Patterns

- Spotify 401 responses trigger automatic re-authentication
- Wikipedia mobile API 403 errors fallback to Action API
- Empty biographies trigger MusicBrainz fallback
- Wikidata label extraction requires separate API calls per entity

### Session State Management (Streamlit)

Key session state variables:
- `running`: Process execution flag
- `log_output`: Real-time command output buffer
- `uploaded_file_{downloader|generator}`: Uploaded file references
- `temp_file_path_{downloader|generator}`: Temporary file paths requiring cleanup

## Development Notes

### Adding New Data Fields

1. Extract data in `WikipediaAPI.get_artist_structured_data()`
2. Update `build_artist_card()` to include in frontmatter
3. Add to markdown content in Quick Info section
4. Update `_parse_wikitext_infobox()` or `get_wikidata_claims()` for source

### Debugging Wikipedia Extraction

Enable DEBUG logging to see:
- Search queries and results
- Mobile sections vs Action API fallback decisions
- Wikitext parsing results
- Wikidata entity lookups

### Testing Individual Artists

Use single artist mode to test data extraction without batch overhead:
```bash
python spotify_artist_card_generator.py \
  --artist "John Coltrane" \
  --output-dir "./test_output" \
  --log-level DEBUG
```

## Known Issues

- Years active calculation occasionally shows incorrect start dates when using Wikidata estimation
- Wikidata label extraction requires additional API calls (rate limiting concern)
- Wikipedia mobile sections API intermittently returns 403 (fallback to Action API mitigates)
- English Wikipedia only (no multi-language support)

## API Credentials

Spotify API credentials are embedded in source code for read-only operations. No user authentication required.

For biography enhancement, obtain Google Gemini API key from https://makersuite.google.com/app/apikey and set as environment variable.