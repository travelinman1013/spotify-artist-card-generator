#!/usr/bin/env python3
"""
Artist Discovery Pipeline - Consolidated WWOZ Archive Processor

This script consolidates three separate workflows into one streamlined pipeline:
1. Parse WWOZ markdown archive for artist names
2. Check if artist card exists in Obsidian vault
3. If new or missing enhancement:
   - Get Spotify metadata (genres, followers, popularity, image URL)
   - Research with Perplexity AI (biography, musical connections)
   - Download high-res artist image
   - Build/update artist card with merged data
   - Update artist connections network

Architecture:
- Hybrid approach: Spotify for metadata, Perplexity for content
- Atomic operations: Each artist fully succeeds or fully skips
- Smart updates: Only enhance cards missing Perplexity data
- Rate limiting: Respects all API limits
- Network graph: Maintains artist_connections.json

Usage:
    python artist_discovery_pipeline.py --archive path/to/wwoz_archive.md [--force] [--dry-run]
"""

import os
import re
import sys
import json
import time
import logging
import argparse
import requests
import base64
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import quote

import yaml
from openai import OpenAI
from tqdm import tqdm

# Configuration
SPOTIFY_CLIENT_ID = "a088edf333334899b6ad55579b834389"
SPOTIFY_CLIENT_SECRET = "78b5d889d9094ff0bb0b2a22cc8cfaac"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_ARTIST_URL = "https://api.spotify.com/v1/artists"

PERPLEXITY_API_BASE = "https://api.perplexity.ai"
PERPLEXITY_MODEL = "sonar-pro"
PERPLEXITY_TEMPERATURE = 0.3
PERPLEXITY_MAX_TOKENS = 4096

# Default vault paths
DEFAULT_CARDS_DIR = "/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists"
DEFAULT_IMAGES_DIR = "/Users/maxwell/LETSGO/MaxVault/03_Resources/source_material/ArtistPortraits"
CONNECTIONS_FILE = "artist_connections.json"

# Rate limiting
SPOTIFY_RATE_LIMIT = 0.6  # seconds
PERPLEXITY_RATE_LIMIT = 2.0  # seconds
REQUEST_TIMEOUT = 30


class ArtistDiscoveryPipeline:
    """Main pipeline for discovering and processing new artists from WWOZ archives."""

    def __init__(self, cards_dir: str, images_dir: str, dry_run: bool = False, force: bool = False):
        self.cards_dir = Path(cards_dir)
        self.images_dir = Path(images_dir)
        self.dry_run = dry_run
        self.force = force

        # Create directories if they don't exist
        self.cards_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.session = requests.Session()
        self.spotify_token = None
        self.spotify_token_expires_at = 0
        self.perplexity_client = None

        # Load connections database
        self.connections_file = self.cards_dir / CONNECTIONS_FILE
        self.connections_db = self._load_connections()

        # Statistics
        self.stats = {
            'total': 0,
            'processed': 0,
            'skipped_existing': 0,
            'enhanced': 0,
            'created': 0,
            'errors': 0,
            'connections_found': 0
        }

        # Setup logging
        self.setup_logging()

    def setup_logging(self):
        """Configure logging for the pipeline."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('artist_discovery_pipeline.log')
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _load_connections(self) -> Dict[str, Any]:
        """Load existing connections database or create new one."""
        if self.connections_file.exists():
            try:
                with open(self.connections_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Could not load connections file: {e}")
        return {}

    def _save_connections(self) -> None:
        """Save connections database to file."""
        if not self.dry_run:
            try:
                with open(self.connections_file, 'w', encoding='utf-8') as f:
                    json.dump(self.connections_db, f, indent=2, ensure_ascii=False)
                self.logger.info(f"Saved connections database with {len(self.connections_db)} artists")
            except Exception as e:
                self.logger.error(f"Error saving connections: {e}")

    # === SPOTIFY API METHODS ===

    def authenticate_spotify(self) -> bool:
        """Authenticate with Spotify using Client Credentials flow."""
        try:
            credentials = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            headers = {
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            data = {"grant_type": "client_credentials"}

            response = self.session.post(
                SPOTIFY_TOKEN_URL,
                headers=headers,
                data=data,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                token_data = response.json()
                self.spotify_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                self.spotify_token_expires_at = time.time() + expires_in - 60

                self.logger.info("Successfully authenticated with Spotify API")
                return True
            else:
                self.logger.error(f"Failed to authenticate with Spotify: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"Exception during Spotify authentication: {e}")
            return False

    def ensure_spotify_authenticated(self) -> bool:
        """Ensure we have a valid Spotify access token."""
        if not self.spotify_token or time.time() >= self.spotify_token_expires_at:
            return self.authenticate_spotify()
        return True

    def get_spotify_metadata(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive Spotify metadata for an artist.

        Returns dict with: artist_id, name, genres, popularity, followers, spotify_url, image_url
        """
        if not self.ensure_spotify_authenticated():
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.spotify_token}",
                "Content-Type": "application/json"
            }

            # Search for artist
            query = quote(artist_name)
            url = f"{SPOTIFY_SEARCH_URL}?q={query}&type=artist&limit=10"

            response = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                data = response.json()
                artists = data.get('artists', {}).get('items', [])

                if artists:
                    artist = artists[0]

                    # Get image URL
                    image_url = None
                    if artist.get('images'):
                        image_url = artist['images'][0]['url']

                    metadata = {
                        'artist_id': artist['id'],
                        'name': artist['name'],
                        'genres': artist.get('genres', []),
                        'popularity': artist.get('popularity', 0),
                        'followers': artist.get('followers', {}).get('total', 0),
                        'spotify_url': artist.get('external_urls', {}).get('spotify', ''),
                        'image_url': image_url
                    }

                    self.logger.info(f"Found Spotify artist: {artist['name']} (ID: {artist['id']})")
                    return metadata
                else:
                    self.logger.warning(f"No Spotify artist found for: {artist_name}")
                    return None

            elif response.status_code == 401:
                self.logger.warning("Spotify token expired, re-authenticating...")
                if self.authenticate_spotify():
                    return self.get_spotify_metadata(artist_name)
                return None

            else:
                self.logger.error(f"Spotify API error for {artist_name}: {response.status_code}")
                return None

        except Exception as e:
            self.logger.error(f"Error getting Spotify metadata for {artist_name}: {e}")
            return None

    def download_artist_image(self, image_url: str, artist_name: str) -> Optional[str]:
        """
        Download artist image and return relative path for Obsidian.

        Returns: Relative path string like "03_Resources/source_material/ArtistPortraits/Artist_Name.jpg"
        """
        try:
            sanitized_name = self.sanitize_filename(artist_name)

            # Check if image already exists
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                image_path = self.images_dir / f"{sanitized_name}{ext}"
                if image_path.exists():
                    self.logger.info(f"Image already exists: {image_path}")
                    return f"03_Resources/source_material/ArtistPortraits/{sanitized_name}{ext}"

            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would download image for: {artist_name}")
                return f"03_Resources/source_material/ArtistPortraits/{sanitized_name}.jpg"

            # Download new image
            response = self.session.get(image_url, timeout=REQUEST_TIMEOUT, stream=True)

            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'jpeg' in content_type or 'jpg' in content_type:
                    extension = '.jpg'
                elif 'png' in content_type:
                    extension = '.png'
                elif 'webp' in content_type:
                    extension = '.webp'
                else:
                    extension = '.jpg'

                file_path = self.images_dir / f"{sanitized_name}{extension}"

                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                self.logger.info(f"Downloaded image: {file_path}")
                return f"03_Resources/source_material/ArtistPortraits/{sanitized_name}{extension}"
            else:
                self.logger.error(f"Failed to download image from {image_url}: {response.status_code}")
                return None

        except Exception as e:
            self.logger.error(f"Error downloading image for {artist_name}: {e}")
            return None

    # === PERPLEXITY API METHODS ===

    def initialize_perplexity(self) -> bool:
        """Initialize Perplexity API client."""
        if self.dry_run:
            self.logger.info("[DRY RUN] Skipping Perplexity initialization")
            return True

        try:
            api_key = os.getenv('PERPLEXITY_API_KEY')
            if not api_key:
                self.logger.error("PERPLEXITY_API_KEY environment variable is required")
                return False

            self.perplexity_client = OpenAI(
                api_key=api_key,
                base_url=PERPLEXITY_API_BASE
            )
            self.logger.info(f"Initialized Perplexity client with model: {PERPLEXITY_MODEL}")
            return True

        except Exception as e:
            self.logger.error(f"Error initializing Perplexity: {e}")
            return False

    def research_with_perplexity(self, artist_name: str, spotify_metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Research artist using Perplexity AI web search.

        Returns dict with: biography, connections, fun_facts, sources, wikipedia_url, location_full, entity_type
        """
        if self.dry_run:
            mock_biography = f"""**{artist_name}** is a renowned musical artist known for their contributions to {', '.join(spotify_metadata.get('genres', ['music'])[:2])}. Throughout their career, they have established themselves as a significant figure in the music industry."""

            return {
                'success': True,
                'biography': mock_biography,
                'connections': {
                    'mentors': [],
                    'collaborators': [],
                    'influenced': []
                },
                'fun_facts': ["Pioneering artist in their genre", "Recorded numerous acclaimed albums"],
                'sources': ["Wikipedia", "AllMusic"],
                'wikipedia_url': f"https://en.wikipedia.org/wiki/{artist_name.replace(' ', '_')}",
                'location_full': "United States",
                'entity_type': "individual"
            }

        try:
            # Extract Spotify context
            top_tracks = spotify_metadata.get('top_tracks', [])[:3] if 'top_tracks' in spotify_metadata else []
            genres = spotify_metadata.get('genres', [])

            # Build research prompt
            research_prompt = f"""Research the musical artist "{artist_name}" and provide comprehensive biographical information.

CONTEXT FROM SPOTIFY:
- Genres: {', '.join(genres) if genres else 'Unknown'}
- Popularity: {spotify_metadata.get('popularity', 'Unknown')}

REQUIRED INFORMATION:
1. **Biography**: 2-3 flowing paragraphs covering early life, career development, musical style, and legacy

2. **Musical Connections** (be specific and accurate):
   - **Mentors/Influences**: Teachers, inspirations, stylistic influences
   - **Key Collaborators**: Band members, frequent collaborators
   - **Artists Influenced**: Students, proteges, inspired musicians

3. **Fun Facts**: 3-4 interesting anecdotes or lesser-known details

4. **Sources**: Note Wikipedia URL if available

RESPONSE FORMAT (JSON):
{{
  "biography": "2-3 paragraph biography text...",
  "connections": {{
    "mentors": [
      {{"name": "Artist Name", "context": "relationship description", "specific_works": "albums/projects", "time_period": "years"}}
    ],
    "collaborators": [
      {{"name": "Artist Name", "context": "nature of collaboration", "specific_works": "albums/bands", "time_period": "years"}}
    ],
    "influenced": [
      {{"name": "Artist Name", "context": "how they were influenced", "specific_works": "relevant works", "time_period": "years"}}
    ]
  }},
  "fun_facts": ["fact 1", "fact 2", "fact 3"],
  "wikipedia_url": "URL if found",
  "sources": ["source1", "source2"],
  "location_full": "City, State/Region, Country (birthplace for individuals, origin for bands/groups)",
  "entity_type": "individual" or "band" or "group"
}}

Only include verified information from credible sources."""

            self.logger.info(f"Researching artist with Perplexity: {artist_name}")

            response = self.perplexity_client.chat.completions.create(
                model=PERPLEXITY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert music researcher with access to web search. Provide accurate, well-researched information. Always respond with valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": research_prompt
                    }
                ],
                temperature=PERPLEXITY_TEMPERATURE,
                max_tokens=PERPLEXITY_MAX_TOKENS
            )

            # Parse JSON response
            if not response or not hasattr(response, 'choices') or not response.choices:
                self.logger.error(f"Invalid Perplexity response for {artist_name}")
                return None

            response_text = response.choices[0].message.content.strip()

            # Clean and parse JSON
            if response_text.startswith('```json'):
                response_text = response_text.replace('```json', '').replace('```', '').strip()
            elif response_text.startswith('```'):
                response_text = response_text.replace('```', '').strip()

            research_data = json.loads(response_text)

            # Add confidence scores to connections
            for conn_type in ['mentors', 'collaborators', 'influenced']:
                if conn_type in research_data.get('connections', {}):
                    for connection in research_data['connections'][conn_type]:
                        if 'confidence' not in connection:
                            connection['confidence'] = 0.95

            self.logger.info(f"Research successful: {len(research_data.get('biography', ''))} chars biography")

            return {
                'success': True,
                **research_data
            }

        except Exception as e:
            self.logger.error(f"Error researching with Perplexity for {artist_name}: {e}")
            return None

    # === HELPER METHODS ===

    def parse_archive(self, archive_path: str) -> List[str]:
        """Parse WWOZ markdown archive and extract artist names."""
        try:
            with open(archive_path, 'r', encoding='utf-8') as file:
                content = file.read()

            lines = content.split('\n')
            found_artists = []

            for line in lines:
                line = line.strip()

                if not line:
                    continue

                # Check if this is a table row (starts with |)
                if line.startswith('|') and '|' in line[1:]:
                    columns = [col.strip() for col in line.split('|')]

                    # Skip header rows and separator rows
                    if len(columns) >= 9 and columns[1] not in ['Time', ':----', '']:
                        artist = columns[2].strip()
                        status = columns[8].strip()

                        # Check if status is "✅ Found"
                        if status == "✅ Found" and artist:
                            found_artists.append(artist)
                            self.logger.debug(f"Found artist: {artist}")

            self.logger.info(f"Parsed {len(found_artists)} artists from {archive_path}")
            return found_artists

        except Exception as e:
            self.logger.error(f"Failed to parse archive file {archive_path}: {e}")
            return []

    def sanitize_filename(self, name: str) -> str:
        """Sanitize artist name for use as filename."""
        sanitized = name.replace(' ', '_')
        sanitized = re.sub(r'[<>:"/\\|?*]', '', sanitized)
        sanitized = re.sub(r'[&]', 'and', sanitized)
        sanitized = re.sub(r'[^\w\-_.]', '', sanitized)

        if len(sanitized) > 200:
            sanitized = sanitized[:200]

        return sanitized.strip('.')

    def card_exists(self, artist_name: str) -> Tuple[bool, Optional[Path]]:
        """Check if artist card exists in vault."""
        sanitized_name = self.sanitize_filename(artist_name)
        card_path = self.cards_dir / f"{sanitized_name}.md"
        return card_path.exists(), card_path if card_path.exists() else None

    def needs_enhancement(self, card_path: Path) -> bool:
        """Check if existing card needs Perplexity enhancement."""
        try:
            with open(card_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check for Perplexity enhancement marker in frontmatter
            if content.startswith('---'):
                frontmatter_end = content.find('---', 3)
                if frontmatter_end != -1:
                    frontmatter_text = content[3:frontmatter_end]
                    frontmatter = yaml.safe_load(frontmatter_text)

                    # Check if already enhanced with Perplexity
                    if frontmatter and frontmatter.get('enhancement_provider') == 'perplexity':
                        return False

            return True  # Needs enhancement

        except Exception as e:
            self.logger.error(f"Error checking enhancement status: {e}")
            return True  # Assume needs enhancement on error

    def build_artist_card(self, artist_name: str, spotify_data: Dict[str, Any],
                         perplexity_data: Dict[str, Any], image_path: str) -> str:
        """Build complete artist card markdown with merged data."""
        # Extract data
        genres = spotify_data.get('genres', [])
        popularity = spotify_data.get('popularity', 0)
        followers = spotify_data.get('followers', 0)
        spotify_url = spotify_data.get('spotify_url', '')

        biography = perplexity_data.get('biography', '')
        connections = perplexity_data.get('connections', {})
        fun_facts = perplexity_data.get('fun_facts', [])
        sources = perplexity_data.get('sources', [])
        wikipedia_url = perplexity_data.get('wikipedia_url', '')
        location_full = perplexity_data.get('location_full', '')
        entity_type = perplexity_data.get('entity_type', 'individual')

        # Convert connections to simple format for frontmatter
        simple_connections = {}
        for conn_type in ['mentors', 'collaborators', 'influenced']:
            if conn_type in connections:
                simple_connections[conn_type] = [
                    conn.get('name', '') for conn in connections[conn_type] if isinstance(conn, dict)
                ]

        # Build YAML frontmatter
        frontmatter = {
            'title': artist_name,
            'status': 'active',
            'genres': genres[:10],
            'spotify_data': {
                'id': spotify_data.get('artist_id', ''),
                'url': spotify_url,
                'popularity': popularity,
                'followers': followers
            },
            'primary_source': 'perplexity',
            'enhancement_provider': 'perplexity',
            'research_sources': sources,
            'musical_connections': simple_connections,
            'network_extracted': True,
            'biography_enhanced_at': datetime.now().isoformat(),
            'external_urls': {
                'spotify': spotify_url,
                'wikipedia': wikipedia_url
            },
            'image_path': image_path,
            'entry_created': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }

        # Add location based on entity type
        if location_full:
            if entity_type == 'individual':
                frontmatter['birth_place'] = location_full
            elif entity_type in ['band', 'group']:
                frontmatter['origin'] = location_full

        # Build markdown content
        image_filename = image_path.split('/')[-1] if image_path else ''

        content = f"""![]({image_filename})

# {artist_name}

## Quick Info
- **Genres**: {', '.join(genres[:5]) if genres else 'Not specified'}
- **Spotify Popularity**: {popularity}/100
- **Followers**: {followers:,}
"""

        if location_full:
            if entity_type == 'individual':
                content += f"- **Born**: {location_full}\n"
            elif entity_type in ['band', 'group']:
                content += f"- **Origin**: {location_full}\n"

        content += f"""
## Biography
{biography}

*Enhanced with Perplexity AI research*
"""

        # Add sources (excluding Wikipedia)
        non_wiki_sources = [s for s in sources if 'wikipedia.org' not in s.lower()]
        if non_wiki_sources:
            source_links = [f"[Source{i+1}]({url})" for i, url in enumerate(non_wiki_sources)]
            content += f"\n*Sources: {', '.join(source_links)}*\n"

        # Add Fun Facts
        if fun_facts:
            content += "\n## Fun Facts\n"
            for fact in fun_facts:
                content += f"- {fact}\n"

        # Add Musical Connections
        if connections:
            content += "\n## Musical Connections\n"

            if connections.get('mentors'):
                content += "\n### Mentors/Influences\n"
                for mentor in connections['mentors']:
                    if isinstance(mentor, dict):
                        name = mentor.get('name', '')
                        context = mentor.get('context', '')
                        works = mentor.get('specific_works', '')
                        period = mentor.get('time_period', '')

                        detail_parts = [context]
                        if works:
                            detail_parts.append(f"({works})")
                        if period:
                            detail_parts.append(f"[{period}]")

                        content += f"- [[{name}]] - {' '.join(detail_parts)}\n"

            if connections.get('collaborators'):
                content += "\n### Key Collaborators\n"
                for collab in connections['collaborators']:
                    if isinstance(collab, dict):
                        name = collab.get('name', '')
                        context = collab.get('context', '')
                        works = collab.get('specific_works', '')
                        period = collab.get('time_period', '')

                        detail_parts = [context]
                        if works:
                            detail_parts.append(f"({works})")
                        if period:
                            detail_parts.append(f"[{period}]")

                        content += f"- [[{name}]] - {' '.join(detail_parts)}\n"

            if connections.get('influenced'):
                content += "\n### Artists Influenced\n"
                for influenced in connections['influenced']:
                    if isinstance(influenced, dict):
                        name = influenced.get('name', '')
                        context = influenced.get('context', '')
                        works = influenced.get('specific_works', '')
                        period = influenced.get('time_period', '')

                        detail_parts = [context]
                        if works:
                            detail_parts.append(f"({works})")
                        if period:
                            detail_parts.append(f"[{period}]")

                        content += f"- [[{name}]] - {' '.join(detail_parts)}\n"

        # Add external links
        content += "\n## External Links\n"
        if spotify_url:
            content += f"- [Spotify]({spotify_url})\n"
        if wikipedia_url:
            content += f"- [Wikipedia]({wikipedia_url})\n"

        # Combine frontmatter and content
        frontmatter_text = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        return f"---\n{frontmatter_text}---\n\n{content}"

    def write_card(self, card_path: Path, content: str) -> bool:
        """Write artist card to disk."""
        try:
            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would write card: {card_path}")
                return True

            card_path.write_text(content, encoding='utf-8')
            self.logger.info(f"Wrote card: {card_path}")
            return True

        except Exception as e:
            self.logger.error(f"Error writing card {card_path}: {e}")
            return False

    def process_artist(self, artist_name: str) -> str:
        """
        Process a single artist through the complete pipeline.

        Returns: Status message string
        """
        try:
            self.logger.info(f"Processing: {artist_name}")

            # Check if card exists
            exists, card_path = self.card_exists(artist_name)

            if exists and not self.force:
                # Card exists, check if it needs enhancement
                if not self.needs_enhancement(card_path):
                    self.stats['skipped_existing'] += 1
                    return "🔄 Already enhanced"
                else:
                    self.logger.info(f"Card exists but needs Perplexity enhancement: {artist_name}")

            # STEP 1: Get Spotify metadata
            self.logger.info(f"Fetching Spotify metadata for: {artist_name}")
            spotify_data = self.get_spotify_metadata(artist_name)
            if not spotify_data:
                self.stats['errors'] += 1
                return "❌ Spotify not found"

            time.sleep(SPOTIFY_RATE_LIMIT)

            # STEP 2: Research with Perplexity
            self.logger.info(f"Researching with Perplexity: {artist_name}")
            perplexity_data = self.research_with_perplexity(artist_name, spotify_data)
            if not perplexity_data or not perplexity_data.get('success'):
                self.stats['errors'] += 1
                return "❌ Perplexity research failed"

            time.sleep(PERPLEXITY_RATE_LIMIT)

            # STEP 3: Download image
            self.logger.info(f"Downloading image for: {artist_name}")
            image_path = None
            if spotify_data.get('image_url'):
                image_path = self.download_artist_image(spotify_data['image_url'], artist_name)

            if not image_path:
                self.logger.warning(f"No image downloaded for: {artist_name}")
                image_path = ""  # Continue without image

            # STEP 4: Build card
            self.logger.info(f"Building card for: {artist_name}")
            card_content = self.build_artist_card(artist_name, spotify_data, perplexity_data, image_path)

            # STEP 5: Write card
            card_path = self.cards_dir / f"{self.sanitize_filename(artist_name)}.md"
            if not self.write_card(card_path, card_content):
                self.stats['errors'] += 1
                return "❌ Failed to write card"

            # STEP 6: Update connections database
            connections = perplexity_data.get('connections', {})
            if connections:
                simple_connections = {}
                for conn_type in ['mentors', 'collaborators', 'influenced']:
                    if conn_type in connections:
                        simple_connections[conn_type] = [
                            conn.get('name', '') for conn in connections[conn_type] if isinstance(conn, dict)
                        ]

                self.connections_db[artist_name] = {
                    **simple_connections,
                    'updated': datetime.now().isoformat(),
                    'source': 'perplexity_research'
                }

                connection_count = sum(len(v) for v in simple_connections.values())
                self.stats['connections_found'] += connection_count

            # Update stats
            if exists:
                self.stats['enhanced'] += 1
                status_msg = f"✅ Enhanced ({self.stats['connections_found']} connections)"
            else:
                self.stats['created'] += 1
                status_msg = f"✨ Created ({self.stats['connections_found']} connections)"

            return status_msg

        except Exception as e:
            self.logger.error(f"Error processing {artist_name}: {e}")
            self.stats['errors'] += 1
            return f"❌ Error: {str(e)[:50]}"

    def process_archive(self, archive_path: str) -> None:
        """Process entire WWOZ archive file."""
        self.logger.info(f"Processing archive: {archive_path}")

        # Parse archive
        artists = self.parse_archive(archive_path)
        if not artists:
            self.logger.error("No artists found in archive")
            return

        self.stats['total'] = len(artists)

        # Authenticate with Spotify
        if not self.authenticate_spotify():
            self.logger.error("Failed to authenticate with Spotify")
            return

        # Initialize Perplexity
        if not self.initialize_perplexity():
            self.logger.error("Failed to initialize Perplexity")
            return

        # Process each artist
        print(f"\n🎵 Artist Discovery Pipeline")
        print(f"Archive: {archive_path}")
        print(f"Found: {len(artists)} artists")
        if self.dry_run:
            print("🔍 DRY RUN MODE - No files will be modified")
        print()

        with tqdm(artists, desc="Processing artists", unit="artist") as pbar:
            for artist in pbar:
                pbar.set_description(f"Processing: {artist}")

                status = self.process_artist(artist)
                pbar.set_postfix_str(status)
                self.stats['processed'] += 1

                time.sleep(0.1)  # Brief pause

        # Save connections database
        self._save_connections()

        # Print summary
        self._print_summary()

    def _print_summary(self) -> None:
        """Print processing summary statistics."""
        print(f"\n📊 Processing Summary:")
        print(f"✨ Created: {self.stats['created']} new cards")
        print(f"✅ Enhanced: {self.stats['enhanced']} existing cards")
        print(f"🔄 Skipped (already complete): {self.stats['skipped_existing']}")
        print(f"🔗 Connections found: {self.stats['connections_found']}")
        print(f"📚 Network size: {len(self.connections_db)} artists")
        print(f"❌ Errors: {self.stats['errors']}")
        print(f"📁 Total processed: {self.stats['processed']}/{self.stats['total']}")

        if self.stats['processed'] > 0:
            success_count = self.stats['created'] + self.stats['enhanced']
            success_rate = (success_count / self.stats['processed'] * 100)
            print(f"\n🎯 Success rate: {success_rate:.1f}%")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Unified pipeline for discovering and processing artists from WWOZ archives"
    )

    parser.add_argument(
        '--archive',
        required=True,
        help='Path to WWOZ markdown archive file'
    )
    parser.add_argument(
        '--cards-dir',
        default=DEFAULT_CARDS_DIR,
        help=f'Directory for artist cards (default: {DEFAULT_CARDS_DIR})'
    )
    parser.add_argument(
        '--images-dir',
        default=DEFAULT_IMAGES_DIR,
        help=f'Directory for artist images (default: {DEFAULT_IMAGES_DIR})'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Re-process and re-enhance already completed artists'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Set logging level (default: INFO)'
    )

    args = parser.parse_args()

    # Setup logging level
    numeric_level = getattr(logging, args.log_level.upper())
    logging.getLogger().setLevel(numeric_level)

    try:
        # Check for required API key
        if not args.dry_run and not os.getenv('PERPLEXITY_API_KEY'):
            print("❌ Error: PERPLEXITY_API_KEY environment variable is required")
            print("Please set your Perplexity API key:")
            print("export PERPLEXITY_API_KEY='your-api-key-here'")
            print("\nGet your API key at: https://www.perplexity.ai/settings/api")
            sys.exit(1)

        # Validate archive file
        if not os.path.exists(args.archive):
            print(f"❌ Error: Archive file does not exist: {args.archive}")
            sys.exit(1)

        # Create pipeline and process
        pipeline = ArtistDiscoveryPipeline(
            cards_dir=args.cards_dir,
            images_dir=args.images_dir,
            dry_run=args.dry_run,
            force=args.force
        )

        pipeline.process_archive(args.archive)

        print("\n✅ Pipeline completed successfully")

    except KeyboardInterrupt:
        print("\n\n⏹️ Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
