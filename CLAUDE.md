# CLAUDE.md

Developer documentation for Claude Code when working with this repository.

## Project Overview

Spotify Artist Tools: Python system for building a personal artist knowledge base integrated with Obsidian. Combines Spotify API, Wikipedia, Wikidata, and Perplexity AI to create comprehensive artist profiles.

## Core Architecture

### Three-Tier System

1. **Image Downloader** (`spotify_image_downloader.py`)
   - Parses markdown archives for artist names
   - Downloads high-res images from Spotify
   - Rate limiting: 0.6s delay

2. **Artist Card Generator** (`spotify_artist_card_generator.py`)
   - Multi-API: Spotify + Wikipedia + Wikidata
   - Creates Obsidian markdown with YAML frontmatter
   - Fallback hierarchy: Wikipedia → Wikidata → MusicBrainz

3. **Biography Enhancement** (`enhance_biographies_perplexity.py` / `enhance_biographies.py`)
   - **Perplexity Version** (RECOMMENDED): Web-first architecture using Perplexity AI
   - **Gemini Version**: Original Google Gemini implementation
   - Extracts musical connections and relationships
   - Builds artist network graph

### Web Interface (`spotify_ui.py`)

Streamlit UI with tabs:
- Image Downloader
- Artist Card Generator
- Biography Enhancement
- Settings (config persistence)

## Key Commands

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Web UI
streamlit run spotify_ui.py

# Generate cards
python spotify_artist_card_generator.py --artist "Artist Name" --output-dir "./cards/"

# Enhance with Perplexity (recommended)
export PERPLEXITY_API_KEY='your-key'
python enhance_biographies_perplexity.py --cards-dir "./cards/" --force

# Enhance with Gemini (alternative)
export GOOGLE_API_KEY='your-key'
python enhance_biographies.py --cards-dir "./cards/" --force
```

## Perplexity Integration (WEB-FIRST ARCHITECTURE)

**Core Architecture:**
1. **Primary Research**: Perplexity web search gathers comprehensive artist info
2. **Biography Generation**: Formats research into structured markdown
3. **Wikipedia Fallback**: Used only for supplementary metadata

**Key Methods:**
- `research_artist_with_perplexity()` - Primary web search (enhance_biographies_perplexity.py:374)
- `generate_biography_from_research()` - Formats research data (enhance_biographies_perplexity.py:531)
- `process_single_file()` - Main enhancement flow (enhance_biographies_perplexity.py:1331)

**Musical Connections Extracted:**
- Mentors/Influences: Teachers, stylistic inspirations
- Key Collaborators: Band members, frequent partners
- Artists Influenced: Students, proteges

**Frontmatter Added:**
- `primary_source: 'perplexity'`
- `research_sources: [...]`
- `musical_connections: {mentors, collaborators, influenced}`
- `enhancement_provider: 'perplexity'`

**Configuration:**
- Model: `sonar-pro`, Temp: 0.3, Max tokens: 4096

**Three-Phase Detection:**
Detection → Recovery (Perplexity) → Quarantine (problem-cards/)
Use `--skip-detection` to bypass.

## Data Flow

**Archive Input:**
```markdown
| Time  | Artist | Song | Album | Genres | Show | Location | Status   | Match | Link |
| 06:07 | Name   | Song | Album | jazz   | Show | Studio   | ✅ Found | 100% | URL  |
```

**Artist Card Flow:**
```
Spotify API → Wikipedia → Wikidata → MusicBrainz (fallback) → Markdown Card
```

**Perplexity Enhancement Flow:**
```
Spotify Metadata → Perplexity Research → Biography Generation → Optional Wikipedia → Card Update
```

## API Integration

**Rate Limits:**
- Spotify: 0.6s delay (hardcoded credentials, auto-refresh)
- Wikipedia: 1s delay (REST API + Mobile sections/Action API fallback)
- Wikidata: 1s delay (Properties: P569 birth, P570 death, P19 birthplace, P1303 instruments)
- Perplexity: 2s delay (OpenAI-compatible client, JSON mode)

## File Naming & Structure

**Generated Files:**
- Artist Cards: `{Artist_Name}.md`
- Images: `{Artist_Name}.jpg`
- Config: `spotify_ui_config.json`
- Connections DB: `artist_connections.json`

**Sanitization:**
- Spaces → underscores
- Special chars removed
- Ampersands → "and"
- Max 200 chars

**Obsidian Integration:**
- YAML frontmatter
- Wikilinks: `[[Artist Name]]`
- Relative image paths: `![]({filename})`

## Important Details

**Years Active:** Wikipedia wikitext preferred over Wikidata estimates (spotify_artist_card_generator.py:1034-1039)

**Error Handling:**
- Spotify 401 → auto re-auth
- Wikipedia 403 → Action API fallback
- Empty bio → MusicBrainz fallback
- Perplexity JSON error → logged with preview

## Development

**Testing:**
```bash
python spotify_artist_card_generator.py --artist "John Coltrane" --output-dir "./test/" --log-level DEBUG
```

**Adding Fields:**
1. Extract in `WikipediaAPI.get_artist_structured_data()`
2. Update `build_artist_card()` frontmatter
3. Add to Quick Info section

**Known Issues:**
- Years active estimation errors with Wikidata
- Wikipedia mobile API 403 errors (Action API fallback)
- English Wikipedia only

## API Credentials

- **Spotify**: Embedded credentials (read-only)
- **Perplexity**: Requires `PERPLEXITY_API_KEY` env var (https://www.perplexity.ai/settings/api)
- **Gemini**: Requires `GOOGLE_API_KEY` env var (https://makersuite.google.com/app/apikey)