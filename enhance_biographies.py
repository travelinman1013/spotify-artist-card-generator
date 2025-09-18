#!/usr/bin/env python3
"""
Jazz Encyclopedia Biography Enhancer

Enhances existing artist markdown cards by:
1. Extracting full Wikipedia content from existing wikipedia_url
2. Using Google Gemini AI to assess content value and extract artist connections
3. Generating comprehensive biographies with highlighted artist relationships
4. Building a connected network of jazz artists for encyclopedia purposes

Usage:
    python enhance_biographies.py [--dry-run] [--force] [--show-network]
"""

import os
import re
import sys
import json
import time
import logging
import argparse
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import quote, unquote

import yaml
import google.generativeai as genai
from bs4 import BeautifulSoup
from tqdm import tqdm

# Configuration
DEFAULT_CARDS_DIR = "/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists"
CONNECTIONS_FILE = "artist_connections.json"
USER_AGENT = "JazzEncyclopediaBiographyEnhancer/1.0 (https://github.com/yourusername/project)"
REQUEST_TIMEOUT = 30
RATE_LIMIT_DELAY = 2.0  # Delay between API requests
MAX_RETRIES = 3

# Gemini Configuration
GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_TEMPERATURE = 0.3
GEMINI_MAX_TOKENS = 2048


class WikipediaExtractor:
    """Handles extraction of full Wikipedia content from URLs."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT
        })
        self.logger = logging.getLogger(__name__)

    def extract_full_content(self, wikipedia_url: str) -> Optional[str]:
        """
        Extract full article content from Wikipedia URL.

        Args:
            wikipedia_url: Full Wikipedia URL

        Returns:
            Clean article text or None if extraction fails
        """
        try:
            self.logger.info(f"Fetching Wikipedia content from: {wikipedia_url}")

            response = self.session.get(
                wikipedia_url,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find main content area
            content_div = soup.find('div', {'class': 'mw-parser-output'})
            if not content_div:
                self.logger.warning("Could not find main content div")
                return None

            # Extract all paragraphs
            paragraphs = content_div.find_all('p')

            # Clean and combine text
            article_text = []
            for para in paragraphs:
                # Remove citations and reference links
                for cite in para.find_all(['sup', 'span'], class_=['reference', 'mw-ref']):
                    cite.decompose()

                text = para.get_text().strip()
                if text and len(text) > 50:  # Skip very short paragraphs
                    article_text.append(text)

            full_text = '\n\n'.join(article_text)

            if len(full_text) < 500:
                self.logger.warning("Extracted text seems too short")
                return None

            self.logger.info(f"Extracted {len(full_text)} characters of content")
            return full_text

        except Exception as e:
            self.logger.error(f"Error extracting Wikipedia content: {e}")
            return None


class GeminiAnalyzer:
    """Handles Gemini AI integration for content assessment and enhancement."""

    def __init__(self, dry_run: bool = False):
        self.logger = logging.getLogger(__name__)
        self.dry_run = dry_run
        self.wikipedia_extractor = None  # Will be set by processor

        # Initialize Gemini only if not in dry-run mode
        if not dry_run:
            api_key = os.getenv('GOOGLE_API_KEY')
            if not api_key:
                raise ValueError("GOOGLE_API_KEY environment variable is required")

            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(GEMINI_MODEL)
            self.logger.info(f"Initialized Gemini model: {GEMINI_MODEL}")
        else:
            self.model = None
            self.logger.info("Dry-run mode: Gemini initialization skipped")

    def assess_content_value(self, existing_bio: str, wikipedia_content: str) -> Dict[str, Any]:
        """
        Assess if Wikipedia content adds substantial value beyond existing biography.

        Args:
            existing_bio: Current biography text
            wikipedia_content: Full Wikipedia article text

        Returns:
            Dictionary with assessment results and extracted data
        """
        if self.dry_run:
            # Return mock assessment for dry-run mode
            return {
                "should_enhance": "yes",
                "reason": "[DRY RUN] Mock assessment - substantial content found",
                "mentioned_artists": ["Miles Davis", "Charlie Parker", "McCoy Tyner"],
                "key_collaborations": ["John Coltrane Quartet", "Miles Davis Quintet"],
                "additional_content_areas": ["early life", "musical style", "legacy"]
            }

        try:
            assessment_prompt = f"""Analyze if this Wikipedia article contains substantially more biographical content than the existing summary, AND identify ONLY the musical artists/collaborators EXPLICITLY mentioned in the Wikipedia source.

EXISTING SUMMARY:
{existing_bio}

FULL WIKIPEDIA ARTICLE:
{wikipedia_content}

Respond in this JSON format:
{{
  "should_enhance": "yes" or "no",
  "reason": "explanation of decision",
  "mentioned_artists": ["Artist Name 1", "Artist Name 2"],
  "key_collaborations": ["specific collaboration details"],
  "additional_content_areas": ["early life", "musical style", "legacy"]
}}

CRITICAL REQUIREMENTS:
- ONLY include artists/collaborators EXPLICITLY mentioned in the Wikipedia article
- DO NOT infer, assume, or create any connections not directly stated in the source
- VERIFY each artist name appears in the Wikipedia text before including it
- Focus on factual accuracy over creative interpretation

Criteria for "yes": Significant biographical details missing from summary (early life, career development, personal relationships, musical evolution, collaborations, legacy)
Criteria for "no": Existing summary captures most key biographical information"""

            self.logger.info("Sending content assessment request to Gemini")

            response = self.model.generate_content(
                assessment_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=GEMINI_TEMPERATURE,
                    max_output_tokens=GEMINI_MAX_TOKENS
                )
            )

            # Parse JSON response
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            assessment = json.loads(response_text)

            self.logger.info(f"Assessment result: {assessment.get('should_enhance', 'unknown')}")
            return assessment

        except Exception as e:
            self.logger.error(f"Error in content assessment: {e}")
            return {
                "should_enhance": "no",
                "reason": f"Assessment failed: {e}",
                "mentioned_artists": [],
                "key_collaborations": [],
                "additional_content_areas": []
            }


    def _extract_connections_from_markdown(self, biography_text: str) -> Dict[str, Any]:
        """
        Extract artist connections from markdown-formatted Musical Connections section.

        Args:
            biography_text: Biography text with markdown connections

        Returns:
            Dictionary with extracted connections
        """
        import re

        connections = {
            "mentors": [],
            "collaborators": [],
            "influenced": [],
            "bands": []
        }

        # Find Musical Connections section
        connections_match = re.search(r'## Musical Connections\s*\n(.*?)(?=\n##|\Z)', biography_text, re.DOTALL)
        if not connections_match:
            return connections

        connections_text = connections_match.group(1)

        # Extract mentors/influences - look for simple format "- Artist Name - description"
        mentors_match = re.search(r'### Mentors/Influences\s*\n(.*?)(?=\n###|\Z)', connections_text, re.DOTALL)
        if mentors_match:
            mentor_lines = mentors_match.group(1).strip().split('\n')
            for line in mentor_lines:
                if line.strip().startswith('- '):
                    # Extract artist name before the first dash
                    line_content = line.strip()[2:]  # Remove "- "
                    if ' - ' in line_content:
                        artist_name = line_content.split(' - ')[0].strip()
                        if artist_name:
                            connections["mentors"].append(artist_name)

        # Extract collaborators
        collab_match = re.search(r'### Key Collaborators\s*\n(.*?)(?=\n###|\Z)', connections_text, re.DOTALL)
        if collab_match:
            collab_lines = collab_match.group(1).strip().split('\n')
            for line in collab_lines:
                if line.strip().startswith('- '):
                    line_content = line.strip()[2:]  # Remove "- "
                    if ' - ' in line_content:
                        artist_name = line_content.split(' - ')[0].strip()
                        if artist_name:
                            connections["collaborators"].append(artist_name)

        # Extract influenced artists
        influenced_match = re.search(r'### Artists Influenced\s*\n(.*?)(?=\n###|\Z)', connections_text, re.DOTALL)
        if influenced_match:
            influenced_lines = influenced_match.group(1).strip().split('\n')
            for line in influenced_lines:
                if line.strip().startswith('- '):
                    line_content = line.strip()[2:]  # Remove "- "
                    if ' - ' in line_content:
                        artist_name = line_content.split(' - ')[0].strip()
                        if artist_name:
                            connections["influenced"].append(artist_name)

        self.logger.info(f"Extracted connections: {len(connections['mentors'])} mentors, {len(connections['collaborators'])} collaborators, {len(connections['influenced'])} influenced")

        return connections

    def _verify_connections_in_source(self, connections: Dict[str, Any], wikipedia_content: str) -> Dict[str, Any]:
        """
        Verify that extracted connections are mentioned in the Wikipedia source.

        Args:
            connections: Extracted artist connections
            wikipedia_content: Wikipedia source text

        Returns:
            Dictionary with verified connections and confidence scores
        """
        if not connections or not wikipedia_content:
            return {}

        verified_connections = {}
        verification_log = []

        for category, artists in connections.items():
            if not isinstance(artists, list):
                continue

            verified_artists = []
            for artist in artists:
                # Check if artist name appears in Wikipedia content
                if artist.lower() in wikipedia_content.lower():
                    verified_artists.append(artist)
                    verification_log.append(f"✓ {artist} found in source")
                else:
                    verification_log.append(f"✗ {artist} NOT found in source")
                    self.logger.warning(f"Artist '{artist}' in {category} not found in Wikipedia source")

            if verified_artists:
                verified_connections[category] = verified_artists

        # Log verification results
        verified_count = sum(len(v) if isinstance(v, list) else 0 for v in verified_connections.values())
        total_count = sum(len(v) if isinstance(v, list) else 0 for v in connections.values())

        if verified_count < total_count:
            self.logger.warning(f"Source verification: {verified_count}/{total_count} connections verified")
        else:
            self.logger.info(f"Source verification: All {verified_count} connections verified")

        return verified_connections

    def enhance_biography(self, wikipedia_content: str, artist_name: str) -> Dict[str, Any]:
        """
        Generate enhanced biography with artist connections.

        Args:
            wikipedia_content: Full Wikipedia article text
            artist_name: Name of the artist

        Returns:
            Dictionary with enhanced biography and extracted connections
        """
        if self.dry_run:
            # Return mock enhancement for dry-run mode
            mock_biography = f"""## Early Life & Musical Beginnings

[DRY RUN] **{artist_name}** was born into a musical family and showed early talent for jazz music. Influenced by **Charlie Parker** and **Dizzy Gillespie**, they began developing their unique style during their formative years.

## Career Development

During the 1950s, {artist_name} joined **Miles Davis**'s quintet, where they collaborated with **Red Garland**, **Paul Chambers**, and **Philly Joe Jones**. This period marked significant growth in their musical sophistication.

## Major Works & Collaborations

Key collaborations include work with **[[McCoy Tyner]]**, **[[Elvin Jones]]**, and **[[Jimmy Garrison]]** in the classic quartet formation. Notable albums from this period revolutionized jazz music.

## Musical Style & Influence

{artist_name}'s approach influenced countless musicians including **[[Pharoah Sanders]]** and **[[Archie Shepp]]**. Their spiritual approach to jazz opened new pathways for future generations.

## Musical Connections

### Mentors/Influences
- **[[Miles Davis]]** - Provided crucial early career opportunities
- **[[Charlie Parker]]** - Major bebop influence on style development

### Collaborators
- **[[McCoy Tyner]]** - Primary pianist in classic quartet
- **[[Elvin Jones]]** - Revolutionary drummer partnership

### Artists Influenced
- **[[Pharoah Sanders]]** - Spiritual jazz pioneer following similar path
- **[[David Murray]]** - Contemporary saxophonist inspired by legacy"""

            mock_connections = {
                "mentors": ["Miles Davis", "Charlie Parker"],
                "collaborators": ["McCoy Tyner", "Elvin Jones", "Jimmy Garrison"],
                "influenced": ["Pharoah Sanders", "David Murray"],
                "bands": ["Miles Davis Quintet", f"{artist_name} Quartet"]
            }

            return {
                "biography": mock_biography,
                "connections": mock_connections
            }

        try:
            enhancement_prompt = f"""Create a comprehensive biography for {artist_name} using the Wikipedia source provided.

FORMAT REQUIREMENTS:
- Write 2-3 flowing biographical paragraphs with clear paragraph breaks
- Focus on: early life, career highlights, key collaborations, musical style, and legacy
- Follow with a "## Fun Facts" section containing 3-4 interesting trivia points
- Then create a "## Musical Connections" section listing artist relationships

CRITICAL ACCURACY REQUIREMENTS:
- ONLY include information EXPLICITLY mentioned in the Wikipedia source
- DO NOT infer, assume, or create any information not directly stated
- VERIFY each fact against the source material before including it
- Be factual and encyclopedic in tone

CONTENT STRUCTURE:
Paragraph 1: Early life, musical beginnings, key influences and teachers

Paragraph 2: Career development, major collaborations, band memberships, significant recordings

Paragraph 3: Musical style, innovations, legacy, and ongoing influence (if applicable)

## Fun Facts
- Interesting anecdote or lesser-known fact
- Notable achievement or unusual detail
- Personal characteristic or unique aspect
- Historical context or cultural impact

## Musical Connections
### Mentors/Influences
- Artist Name - Brief description of relationship

### Key Collaborators
- Artist Name - Brief description of collaboration

### Artists Influenced
- Artist Name - Brief description of influence

FORMATTING RULES:
- Use natural language without special formatting for artist names
- Ensure clear paragraph breaks between biographical sections
- Keep tone encyclopedic but engaging
- Only include connections explicitly stated in Wikipedia source

Wikipedia source:
{wikipedia_content}"""

            self.logger.info(f"Generating enhanced biography for {artist_name}")

            response = self.model.generate_content(
                enhancement_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=GEMINI_TEMPERATURE,
                    max_output_tokens=GEMINI_MAX_TOKENS * 2  # Longer for full biography
                )
            )

            response_text = response.text.strip()

            # Extract connections from markdown format
            connections = self._extract_connections_from_markdown(response_text)

            # Verify connections against source material
            verified_connections = self._verify_connections_in_source(connections, wikipedia_content)

            self.logger.info(f"Generated enhanced biography ({len(response_text)} characters)")

            return {
                "biography": response_text,
                "connections": verified_connections,
                "original_connections": connections,  # Keep original for comparison
                "source_verified": len(verified_connections) > 0
            }

        except Exception as e:
            self.logger.error(f"Error generating enhanced biography: {e}")
            return {
                "biography": "",
                "connections": {}
            }

    def verify_biography_accuracy(self, artist_name: str, biography_text: str,
                                 frontmatter: Dict[str, Any], wikipedia_url: str) -> Dict[str, Any]:
        """
        Verify that the biography accurately describes the artist.

        Args:
            artist_name: Name of the artist
            biography_text: Current biography text
            frontmatter: Artist card frontmatter with Spotify data
            wikipedia_url: URL of Wikipedia page used

        Returns:
            Dictionary with verification results
        """
        if self.dry_run:
            return {
                "is_accurate": True,
                "confidence": 0.95,
                "reason": "[DRY RUN] Mock verification passed",
                "issues": []
            }

        try:
            # Extract key data for verification
            spotify_genres = frontmatter.get('genres', [])
            spotify_popularity = frontmatter.get('spotify_data', {}).get('popularity', 0)
            top_tracks = frontmatter.get('top_tracks', [])

            verification_prompt = f"""Verify if this biography accurately describes the artist "{artist_name}".

ARTIST INFORMATION:
- Name: {artist_name}
- Spotify Genres: {', '.join(spotify_genres) if spotify_genres else 'Unknown'}
- Top Tracks: {', '.join(top_tracks[:3]) if top_tracks else 'Unknown'}
- Wikipedia URL: {wikipedia_url}

CURRENT BIOGRAPHY:
{biography_text}

VERIFICATION TASKS:
1. Check if the biography is about a musical artist/band (not an album or song)
2. Verify the artist name appears prominently in the biography
3. Check if genres mentioned align with Spotify genres: {spotify_genres}
4. Identify any clear mismatches (e.g., biography about an album instead of artist)
5. Check if the Wikipedia URL seems correct (e.g., not "Soul_Rebels" album for "The Soul Rebels" band)

Respond in JSON:
{{
  "is_accurate": true/false,
  "confidence": 0.0-1.0,
  "entity_type": "artist" or "album" or "song" or "other",
  "reason": "explanation",
  "issues": ["list of specific issues found"],
  "suggested_search": "alternative search term if inaccurate"
}}"""

            self.logger.info(f"Verifying biography accuracy for {artist_name}")

            response = self.model.generate_content(
                verification_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # Low temperature for accuracy
                    max_output_tokens=512
                )
            )

            # Parse response
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            verification = json.loads(response_text)

            self.logger.info(f"Verification result for {artist_name}: {verification.get('is_accurate')} "
                           f"(confidence: {verification.get('confidence', 0):.2f})")

            return verification

        except Exception as e:
            self.logger.error(f"Error verifying biography: {e}")
            return {
                "is_accurate": True,  # Default to true to avoid false positives
                "confidence": 0.5,
                "reason": f"Verification failed: {e}",
                "issues": []
            }


class ArtistCardProcessor:
    """Main processor for enhancing artist cards and managing connections."""

    def __init__(self, cards_dir: str, dry_run: bool = False, force: bool = False):
        self.cards_dir = Path(cards_dir)
        self.dry_run = dry_run
        self.force = force
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.wikipedia_extractor = WikipediaExtractor()
        self.gemini_analyzer = GeminiAnalyzer(dry_run)
        # Link the extractor to analyzer for re-fetching
        self.gemini_analyzer.wikipedia_extractor = self.wikipedia_extractor

        # Load or initialize connections database
        self.connections_file = self.cards_dir / CONNECTIONS_FILE
        self.connections_db = self._load_connections()

        # Statistics
        self.stats = {
            'processed': 0,
            'enhanced': 0,
            'skipped_content': 0,
            'skipped_already_enhanced': 0,
            'skipped_no_wikipedia': 0,
            'errors': 0,
            'connections_found': 0
        }

    def _load_connections(self) -> Dict[str, Any]:
        """Load existing connections database or create new one."""
        if self.connections_file.exists():
            try:
                with open(self.connections_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Could not load connections file: {e}")

        return {}

    def _attempt_correct_wikipedia_fetch(self, artist_name: str, suggested_search: str = None) -> Optional[str]:
        """
        Attempt to fetch correct Wikipedia content using alternative search.

        Args:
            artist_name: Artist name
            suggested_search: Alternative search term suggested by verification

        Returns:
            Wikipedia content or None if failed
        """
        try:
            # Try different search strategies
            search_terms = []
            if suggested_search:
                search_terms.append(suggested_search)

            # Add common disambiguators for musical artists
            search_terms.extend([
                f"{artist_name} band",
                f"{artist_name} musician",
                f"{artist_name} music group",
                f"{artist_name} American band",  # Try with nationality
                f"{artist_name} musical group"
            ])

            for search_term in search_terms:
                self.logger.info(f"Attempting Wikipedia search with: {search_term}")

                # Use Wikipedia search API
                search_url = "https://en.wikipedia.org/w/api.php"
                params = {
                    'action': 'opensearch',
                    'search': search_term,
                    'limit': 5,
                    'format': 'json'
                }

                response = requests.get(search_url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    if len(data) >= 4:
                        titles = data[1]  # List of page titles
                        descriptions = data[2]  # List of descriptions
                        urls = data[3]  # List of URLs

                        # Find best match
                        for i, (title, desc, url) in enumerate(zip(titles, descriptions, urls)):
                            # Check if it's likely an artist page
                            if any(term in desc.lower() for term in ['band', 'musician', 'group', 'singer', 'artist']):
                                if 'album' not in title.lower() and 'song' not in title.lower():
                                    self.logger.info(f"Found likely correct page: {title} - {desc}")
                                    # Extract content from this URL
                                    content = self.wikipedia_extractor.extract_full_content(url)
                                    if content:
                                        return content

                # Brief delay between attempts
                time.sleep(1)

        except Exception as e:
            self.logger.error(f"Error in alternative Wikipedia fetch: {e}")

        return None

    def _save_connections(self) -> None:
        """Save connections database to file."""
        if not self.dry_run:
            try:
                with open(self.connections_file, 'w', encoding='utf-8') as f:
                    json.dump(self.connections_db, f, indent=2, ensure_ascii=False)
                self.logger.info(f"Saved connections database with {len(self.connections_db)} artists")
            except Exception as e:
                self.logger.error(f"Error saving connections: {e}")

    def find_artist_cards(self) -> List[Path]:
        """Find all artist markdown files in the directory."""
        if not self.cards_dir.exists():
            raise FileNotFoundError(f"Cards directory not found: {self.cards_dir}")

        md_files = list(self.cards_dir.glob("*.md"))
        self.logger.info(f"Found {len(md_files)} markdown files in {self.cards_dir}")
        return md_files

    def parse_frontmatter(self, file_path: Path) -> Tuple[Dict[str, Any], str]:
        """
        Parse YAML frontmatter and content from markdown file.

        Args:
            file_path: Path to markdown file

        Returns:
            Tuple of (frontmatter_dict, content_text)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.startswith('---'):
                return {}, content

            # Find end of frontmatter
            frontmatter_end = content.find('---', 3)
            if frontmatter_end == -1:
                return {}, content

            frontmatter_text = content[3:frontmatter_end].strip()
            content_text = content[frontmatter_end + 3:].strip()

            frontmatter = yaml.safe_load(frontmatter_text)
            return frontmatter or {}, content_text

        except Exception as e:
            self.logger.error(f"Error parsing frontmatter from {file_path}: {e}")
            return {}, ""

    def should_process_file(self, frontmatter: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if file should be processed for enhancement.

        Args:
            frontmatter: Parsed YAML frontmatter

        Returns:
            Tuple of (should_process, reason)
        """
        # Check if already enhanced (unless force mode)
        if frontmatter.get('biography_enhanced_at') and not self.force:
            return False, "already_enhanced"

        # Check if Wikipedia URL exists
        wikipedia_url = frontmatter.get('external_urls', {}).get('wikipedia')
        if not wikipedia_url:
            return False, "no_wikipedia_url"

        return True, "ready_for_processing"

    def _clean_biography_content(self, biography_text: str) -> str:
        """
        Clean biography content to remove duplicate headers and formatting issues.

        Args:
            biography_text: Raw biography text from AI

        Returns:
            Cleaned biography text
        """
        import re

        # Remove any artist-specific Biography headers (e.g., "## Jimmie Lunceford: A Biography")
        biography_text = re.sub(r'^##\s+[^:]+:\s*A\s+Biography\s*\n', '', biography_text, flags=re.MULTILINE)

        # Remove any standalone "## Biography" headers
        biography_text = re.sub(r'^##\s+Biography\s*\n', '', biography_text, flags=re.MULTILINE)

        # Clean up any extra whitespace at the beginning
        biography_text = biography_text.lstrip()

        # Ensure there's proper spacing between sections
        biography_text = re.sub(r'\n{3,}', '\n\n', biography_text)

        return biography_text

    def extract_current_biography(self, content: str) -> str:
        """Extract current biography section from markdown content."""
        try:
            # Find biography section
            bio_match = re.search(r'## Biography\s*\n(.*?)(?=\n##|\n\*Source:|\Z)', content, re.DOTALL)
            if bio_match:
                return bio_match.group(1).strip()
            return ""
        except Exception as e:
            self.logger.error(f"Error extracting biography: {e}")
            return ""

    def update_artist_card(self, file_path: Path, frontmatter: Dict[str, Any],
                          content: str, enhanced_bio: str, connections: Dict[str, Any]) -> bool:
        """
        Update artist card with enhanced biography and connections.

        Args:
            file_path: Path to artist card file
            frontmatter: Current frontmatter data
            content: Current file content
            enhanced_bio: New enhanced biography
            connections: Extracted artist connections

        Returns:
            True if update successful, False otherwise
        """
        try:
            # Update frontmatter
            frontmatter['biography_enhanced_at'] = datetime.now().isoformat()
            if connections:
                frontmatter['musical_connections'] = connections
                frontmatter['network_extracted'] = True
                frontmatter['source_verified'] = True  # Mark as source-verified

            # Clean up enhanced biography to remove duplicate headers
            cleaned_bio = self._clean_biography_content(enhanced_bio)

            # Replace biography section in content
            bio_pattern = r'(## Biography\s*\n).*?(?=\n##|\n\*Source:|\Z)'
            replacement = f'\\1{cleaned_bio}\n\n*Enhanced with AI analysis*\n'

            if re.search(bio_pattern, content, re.DOTALL):
                new_content = re.sub(bio_pattern, replacement, content, flags=re.DOTALL)
            else:
                # Add biography section if not found
                new_content = content + f"\n\n## Biography\n{cleaned_bio}\n\n*Enhanced with AI analysis*\n"

            # Reconstruct full file
            frontmatter_text = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
            full_content = f"---\n{frontmatter_text}---\n\n{new_content}"

            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would update {file_path.name}")
                return True
            else:
                # Backup original file
                backup_path = file_path.with_suffix('.md.backup')
                if not backup_path.exists():
                    file_path.rename(backup_path)
                    file_path.write_text(full_content, encoding='utf-8')
                else:
                    file_path.write_text(full_content, encoding='utf-8')

                self.logger.info(f"Updated {file_path.name}")
                return True

        except Exception as e:
            self.logger.error(f"Error updating {file_path}: {e}")
            return False

    def process_single_file(self, file_path: Path) -> str:
        """
        Process a single artist card file.

        Args:
            file_path: Path to artist card file

        Returns:
            Status string indicating result
        """
        try:
            self.stats['processed'] += 1
            artist_name = file_path.stem.replace('_', ' ')

            # Parse file
            frontmatter, content = self.parse_frontmatter(file_path)

            # Check if should process
            should_process, reason = self.should_process_file(frontmatter)
            if not should_process:
                if reason == "already_enhanced":
                    self.stats['skipped_already_enhanced'] += 1
                    return "🔄 Already enhanced"
                elif reason == "no_wikipedia_url":
                    self.stats['skipped_no_wikipedia'] += 1
                    return "⚠️ No Wikipedia URL"

            # Extract Wikipedia URL and current biography
            wikipedia_url = frontmatter.get('external_urls', {}).get('wikipedia')
            current_bio = self.extract_current_biography(content)

            # First, verify the current biography accuracy
            verification = self.gemini_analyzer.verify_biography_accuracy(
                artist_name, current_bio, frontmatter, wikipedia_url
            )

            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)

            wikipedia_content = None

            # If biography is inaccurate, try to fetch correct Wikipedia page
            if not verification.get('is_accurate', True):
                self.logger.warning(f"Biography mismatch detected for {artist_name}: {verification.get('reason')}")
                self.logger.info(f"Issues found: {verification.get('issues', [])}")

                # Try to fetch correct Wikipedia content
                suggested_search = verification.get('suggested_search')
                correct_content = self._attempt_correct_wikipedia_fetch(artist_name, suggested_search)

                if correct_content:
                    wikipedia_content = correct_content
                    self.logger.info(f"Successfully fetched correct Wikipedia content for {artist_name}")
                    # Update the Wikipedia URL in frontmatter will be done during card update
                else:
                    self.logger.error(f"Could not find correct Wikipedia page for {artist_name}")
                    self.stats['errors'] += 1
                    return f"❌ Biography mismatch: {verification.get('reason', 'Unknown')}"
            else:
                # Biography is accurate, use existing Wikipedia URL
                wikipedia_content = self.wikipedia_extractor.extract_full_content(wikipedia_url)

            if not wikipedia_content:
                self.stats['errors'] += 1
                return "❌ Wikipedia extraction failed"

            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)

            # Assess content value
            assessment = self.gemini_analyzer.assess_content_value(current_bio, wikipedia_content)

            if assessment.get('should_enhance', 'no').lower() != 'yes':
                self.stats['skipped_content'] += 1
                return f"⏭️ Skipped: {assessment.get('reason', 'Minimal new content')}"

            # Rate limiting before enhancement
            time.sleep(RATE_LIMIT_DELAY)

            # Generate enhanced biography
            enhancement_result = self.gemini_analyzer.enhance_biography(wikipedia_content, artist_name)
            enhanced_bio = enhancement_result.get('biography', '')
            connections = enhancement_result.get('connections', {})
            source_verified = enhancement_result.get('source_verified', False)
            original_connections = enhancement_result.get('original_connections', {})

            if not enhanced_bio:
                self.stats['errors'] += 1
                return "❌ Biography generation failed"

            # Update file
            if self.update_artist_card(file_path, frontmatter, content, enhanced_bio, connections):
                # Update connections database
                if connections:
                    self.connections_db[artist_name] = {
                        **connections,
                        'updated': datetime.now().isoformat()
                    }
                    self.stats['connections_found'] += len(connections.get('mentors', [])) + \
                                                     len(connections.get('collaborators', [])) + \
                                                     len(connections.get('influenced', []))

                self.stats['enhanced'] += 1
                connection_count = sum(len(v) if isinstance(v, list) else 0 for v in connections.values())
                original_count = sum(len(v) if isinstance(v, list) else 0 for v in original_connections.values())

                if original_count > connection_count:
                    return f"✅ Enhanced ({connection_count}/{original_count} verified connections)"
                else:
                    return f"✅ Enhanced ({connection_count} connections)"
            else:
                self.stats['errors'] += 1
                return "❌ File update failed"

        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Error processing {file_path}: {e}")
            return f"❌ Error: {str(e)[:50]}"

    def process_all_files(self) -> None:
        """Process all artist card files with progress tracking."""
        files = self.find_artist_cards()

        if not files:
            self.logger.warning("No artist card files found")
            return

        print(f"\n🎵 Jazz Encyclopedia Enhancement Tool")
        print(f"Scanning: {self.cards_dir}")
        print(f"Found: {len(files)} artist cards")
        if self.dry_run:
            print("🔍 DRY RUN MODE - No files will be modified")
        print()

        # Process files with progress bar
        with tqdm(files, desc="Processing artists", unit="artist") as pbar:
            for file_path in pbar:
                artist_name = file_path.stem.replace('_', ' ')
                pbar.set_description(f"Processing: {artist_name}")

                status = self.process_single_file(file_path)
                pbar.set_postfix_str(status)

                # Brief pause for readability
                time.sleep(0.1)

        # Save connections database
        self._save_connections()

        # Print summary
        self._print_summary()

    def _print_summary(self) -> None:
        """Print processing summary statistics."""
        print(f"\n📊 Processing Summary:")
        print(f"✅ Enhanced: {self.stats['enhanced']} artists")
        print(f"🔗 Connections found: {self.stats['connections_found']}")
        print(f"📚 Network nodes: {len(self.connections_db)} artists")
        print(f"⏭️ Skipped (minimal content): {self.stats['skipped_content']}")
        print(f"🔄 Skipped (already enhanced): {self.stats['skipped_already_enhanced']}")
        print(f"⚠️ Skipped (no Wikipedia): {self.stats['skipped_no_wikipedia']}")
        print(f"❌ Errors: {self.stats['errors']}")
        print(f"📁 Total processed: {self.stats['processed']}")

        if self.stats['enhanced'] > 0:
            print(f"\n🎯 Success rate: {(self.stats['enhanced'] / self.stats['processed'] * 100):.1f}%")


def setup_logging(log_level: str) -> None:
    """Setup logging configuration."""
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('biography_enhancer.log'),
            logging.StreamHandler()
        ]
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enhance jazz artist biographies with AI-generated content and network analysis"
    )
    parser.add_argument(
        '--cards-dir',
        default=DEFAULT_CARDS_DIR,
        help=f'Directory containing artist cards (default: {DEFAULT_CARDS_DIR})'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Re-enhance already processed files'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Set logging level (default: INFO)'
    )
    parser.add_argument(
        '--show-network',
        action='store_true',
        help='Display network statistics after processing'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        # Verify API key (unless in dry-run mode)
        if not args.dry_run and not os.getenv('GOOGLE_API_KEY'):
            print("❌ Error: GOOGLE_API_KEY environment variable is required")
            print("Please set your Google Gemini API key:")
            print("export GOOGLE_API_KEY='your-api-key-here'")
            sys.exit(1)

        # Process files
        processor = ArtistCardProcessor(args.cards_dir, args.dry_run, args.force)
        processor.process_all_files()

        # Show network statistics if requested
        if args.show_network:
            print(f"\n🕸️ Network Analysis:")
            print(f"Total artists in network: {len(processor.connections_db)}")
            # Add more network analysis here if needed

        logger.info("Biography enhancement completed successfully")

    except KeyboardInterrupt:
        print("\n\n⏹️ Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()