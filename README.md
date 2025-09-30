# 🎵 Spotify Artist Tools

Python toolkit for building a personal artist knowledge base using Spotify, Wikipedia, and AI-powered biography enhancement. Generate artist cards with rich metadata, download images, and extract musical connections.

## ✨ Features

- **Artist Card Generator**: Combines Spotify, Wikipedia, and Wikidata into comprehensive markdown profiles
- **Image Downloader**: Retrieves high-resolution artist images from Spotify
- **AI Biography Enhancement**: Perplexity-first web search for rich biographies with musical connections
- **Web Interface**: Streamlit UI for batch processing and single-artist operations
- **Obsidian Integration**: YAML frontmatter and wikilinks for knowledge vault organization

## 🚀 Quick Start

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Launch web interface
streamlit run spotify_ui.py

# Or use command line
python spotify_artist_card_generator.py --artist "John Coltrane" --output-dir "./cards/"

# Enhance with AI (Perplexity recommended)
export PERPLEXITY_API_KEY='your-key'
python enhance_biographies_perplexity.py --cards-dir "./cards/" --force
```

## 🤖 AI Enhancement (Perplexity-First Architecture)

The biography enhancer uses **Perplexity AI as the primary data source** via web search:

**Key Features:**
- Comprehensive web research (not limited to Wikipedia)
- Rich musical connections: mentors, collaborators, influenced artists
- Detailed context: specific albums, bands, time periods, confidence scores
- Multi-source citations: Wikipedia, AllMusic, JazzTimes, etc.
- Works for artists without Wikipedia pages

**Output Example:**
```yaml
primary_source: perplexity
research_sources: ["Wikipedia", "AllMusic", "JazzTimes"]
musical_connections:
  mentors: ["Miles Davis", "Charlie Parker"]
  collaborators: ["McCoy Tyner", "Elvin Jones"]
  influenced: ["Pharoah Sanders", "Archie Shepp"]
```

**Connections include:**
- Artist name
- Relationship context
- Specific works (albums/projects)
- Time periods
- Confidence scores (0-1)

**Alternative:** Use Google Gemini with `enhance_biographies.py` and `GOOGLE_API_KEY`

## 📊 Output Structure

Generated artist cards include:
- **Frontmatter**: Genres, dates, Spotify stats, URLs, connections
- **Biography**: AI-enhanced with musical relationships
- **Quick Info**: Birth/death dates, popularity, followers
- **Discography**: Albums and singles tables
- **Top Tracks**: Ordered list with Spotify data
- **Related Artists**: Wikilinks for Obsidian navigation
- **External Links**: Spotify, Wikipedia, MusicBrainz

**File naming:** `Artist_Name.md` (spaces→underscores, special chars removed)

## 📁 Project Structure

```
image_agent_v5/
├── spotify_artist_card_generator.py     # Main card generator
├── spotify_image_downloader.py          # Image downloader
├── enhance_biographies_perplexity.py    # AI enhancement (Perplexity)
├── enhance_biographies.py               # AI enhancement (Gemini)
├── spotify_ui.py                        # Web interface
├── requirements.txt                     # Dependencies
├── CLAUDE.md                            # Developer docs
└── README.md                            # This file
```

## 🔧 Configuration

**Spotify API**: Pre-configured credentials included (read-only)

**Perplexity AI**: Get key at https://www.perplexity.ai/settings/api
```bash
export PERPLEXITY_API_KEY='your-key'
```

**Google Gemini** (alternative): Get key at https://makersuite.google.com/app/apikey
```bash
export GOOGLE_API_KEY='your-key'
```

**Default Paths** (customize in Settings tab):
- Artist Cards: `/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists`
- Images: `/Users/maxwell/LETSGO/MaxVault/03_Resources/source_material/ArtistPortraits`

## 🛠️ Key Scripts

**Generate artist cards:**
```bash
# Single artist
python spotify_artist_card_generator.py --artist "Miles Davis" --output-dir "./cards/"

# Batch from archive
python spotify_artist_card_generator.py --input-file "archive.md" --output-dir "./cards/"
```

**Download images:**
```bash
python spotify_image_downloader.py --input "archive.md" --output "./images/"
```

**Enhance biographies:**
```bash
# Perplexity (recommended)
python enhance_biographies_perplexity.py --cards-dir "./cards/" --force --log-level INFO

# Gemini (alternative)
python enhance_biographies.py --cards-dir "./cards/" --force
```

**Archive file format:**
```markdown
| Time  | Artist | Song | Album | Genres | Show | Location | Status   | Match | Link |
| 06:07 | Name   | Song | Album | jazz   | Show | Studio   | ✅ Found | 100% | URL  |
```

## ⚡ Performance

- **Card generation**: ~3-5 seconds per artist (with API calls)
- **Batch processing**: ~5-10 artists per minute
- **AI enhancement**: ~20-30 seconds per artist (Perplexity web search)

**Rate limiting:**
- Spotify: 100 req/min (0.6s delay)
- Wikipedia: 1s delay
- Wikidata: 1s delay
- Perplexity: 2s delay (configurable)

## 🔍 Logging

Set log level with `--log-level [DEBUG|INFO|WARNING|ERROR]`

**Log files:**
- `artist_card_generator.log` - Card generation
- `spotify_downloader.log` - Image downloads
- `biography_enhancer_perplexity.log` - AI enhancement

## 📜 License

Personal use project. Follows Spotify API developer terms of service.

---

*Version 1.2 - Perplexity-first architecture with rich musical connections*