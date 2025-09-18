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
            assessment_prompt = f"""Analyze if this Wikipedia article contains substantially more biographical content than the existing summary, AND identify all mentioned musical artists/collaborators.

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
            enhancement_prompt = f"""Create a comprehensive biography for {artist_name} that emphasizes artist relationships and collaborations. Structure with these sections:

1. **Early Life & Musical Beginnings** - mentioning early influences and teachers
2. **Career Development** - highlighting key collaborations and band memberships
3. **Major Works & Collaborations** - emphasizing partnerships with other artists
4. **Musical Style & Influence** - noting artists influenced by and who influenced them
5. **Legacy & Connections** - showing ongoing influence on other musicians

SPECIAL REQUIREMENTS:
- **Bold** all artist names when first mentioned: **Miles Davis**, **John Coltrane**
- Create a "## Musical Connections" section listing:
  - **Mentors/Influences**: Artists who influenced them
  - **Collaborators**: Key musical partners
  - **Mentees/Influenced**: Artists they influenced
- Use markdown linking syntax for potential wiki links: [[Artist Name]]
- Focus on biographical narrative, not just facts
- Keep encyclopedic but engaging tone

Also provide a separate JSON structure with extracted connections:
{{
  "mentors": ["Artist Name 1", "Artist Name 2"],
  "collaborators": ["Artist Name 3", "Artist Name 4"],
  "influenced": ["Artist Name 5", "Artist Name 6"],
  "bands": ["Band Name 1", "Band Name 2"]
}}

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

            # Try to extract JSON connections if present
            connections = {}
            if '```json' in response_text:
                try:
                    json_start = response_text.find('```json') + 7
                    json_end = response_text.find('```', json_start)
                    if json_end > json_start:
                        json_text = response_text[json_start:json_end].strip()
                        connections = json.loads(json_text)
                        # Remove JSON from main text
                        response_text = response_text[:response_text.find('```json')].strip()
                except Exception as e:
                    self.logger.warning(f"Could not parse connections JSON: {e}")

            self.logger.info(f"Generated enhanced biography ({len(response_text)} characters)")

            return {
                "biography": response_text,
                "connections": connections
            }

        except Exception as e:
            self.logger.error(f"Error generating enhanced biography: {e}")
            return {
                "biography": "",
                "connections": {}
            }


class ArtistCardProcessor:
    """Main processor for enhancing artist cards and managing connections."""

    def __init__(self, cards_dir: str, dry_run: bool = False):
        self.cards_dir = Path(cards_dir)
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.wikipedia_extractor = WikipediaExtractor()
        self.gemini_analyzer = GeminiAnalyzer(dry_run)

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
        # Check if already enhanced
        if frontmatter.get('biography_enhanced_at'):
            return False, "already_enhanced"

        # Check if Wikipedia URL exists
        wikipedia_url = frontmatter.get('external_urls', {}).get('wikipedia')
        if not wikipedia_url:
            return False, "no_wikipedia_url"

        return True, "ready_for_processing"

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

            # Replace biography section in content
            bio_pattern = r'(## Biography\s*\n).*?(?=\n##|\n\*Source:|\Z)'
            replacement = f'\\1{enhanced_bio}\n\n*Enhanced with AI analysis*\n'

            if re.search(bio_pattern, content, re.DOTALL):
                new_content = re.sub(bio_pattern, replacement, content, flags=re.DOTALL)
            else:
                # Add biography section if not found
                new_content = content + f"\n\n## Biography\n{enhanced_bio}\n\n*Enhanced with AI analysis*\n"

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

            # Extract Wikipedia content
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
        processor = ArtistCardProcessor(args.cards_dir, args.dry_run)
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