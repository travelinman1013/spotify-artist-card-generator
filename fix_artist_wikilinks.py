#!/usr/bin/env python3
"""
Fix Artist Card Wikilinks

This script fixes broken Obsidian wikilinks in artist cards by converting:
- [[Artist Name]] → [[Artist_Name|Artist Name]]

The proper format tells Obsidian: "Link to Artist_Name.md but display as 'Artist Name'"

Usage:
    python fix_artist_wikilinks.py --cards-dir /path/to/artists [--dry-run] [--backup]
"""

import os
import re
import sys
import logging
import argparse
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Set

from tqdm import tqdm


class WikilinkFixer:
    """Fixes broken Obsidian wikilinks in artist card markdown files."""

    def __init__(self, cards_dir: str, dry_run: bool = False, backup: bool = False, log_level: str = "INFO"):
        self.cards_dir = Path(cards_dir)
        self.dry_run = dry_run
        self.backup = backup

        # Statistics
        self.stats = {
            'cards_scanned': 0,
            'cards_with_wikilinks': 0,
            'cards_modified': 0,
            'links_found': 0,
            'links_fixed': 0,
            'links_broken_unfixable': 0,
            'errors': 0
        }

        # Setup logging
        self.setup_logging(log_level)

        # Cache of existing artist files (for fast lookup)
        self.artist_files: Set[str] = set()
        self._build_artist_cache()

    def setup_logging(self, log_level: str):
        """Configure logging for the script."""
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)

        logging.basicConfig(
            level=numeric_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('fix_wikilinks.log')
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _build_artist_cache(self):
        """Build cache of all existing artist card filenames."""
        if not self.cards_dir.exists():
            self.logger.error(f"Cards directory does not exist: {self.cards_dir}")
            sys.exit(1)

        # Get all .md files in the directory (without extension)
        for file_path in self.cards_dir.glob("*.md"):
            # Store just the stem (filename without .md extension)
            self.artist_files.add(file_path.stem)

        self.logger.info(f"Found {len(self.artist_files)} artist cards in vault")

    def extract_artist_name(self, link_text: str) -> str:
        """
        Extract artist name from wikilink text.

        Handles both simple names and path-based links:
        - "Allen Toussaint" → "Allen Toussaint"
        - "01_Projects/PersonalArtistWiki/Artists/Allen_Toussaint" → "Allen Toussaint"
        """
        # Check if this is a path-based link
        if '/' in link_text:
            # Extract just the last component (the artist name)
            artist_name = link_text.split('/')[-1]
            # Convert underscores back to spaces for display
            artist_name = artist_name.replace('_', ' ')
            return artist_name

        return link_text

    def sanitize_filename(self, name: str) -> str:
        """
        Sanitize artist name for use as filename.

        This matches the logic from artist_discovery_pipeline.py to ensure consistency.
        """
        sanitized = name.replace(' ', '_')
        sanitized = re.sub(r'[<>:"/\\|?*]', '', sanitized)
        sanitized = re.sub(r'[&]', 'and', sanitized)
        sanitized = re.sub(r'[^\w\-_.]', '', sanitized)

        if len(sanitized) > 200:
            sanitized = sanitized[:200]

        return sanitized.strip('.')

    def find_wikilinks(self, content: str) -> List[Tuple[str, int, int]]:
        """
        Find all wikilinks in content.

        Returns: List of (link_text, start_pos, end_pos) tuples
        """
        wikilink_pattern = r'\[\[([^\]]+?)\]\]'
        matches = []

        for match in re.finditer(wikilink_pattern, content):
            link_text = match.group(1)
            # Skip links that already have the pipe format (already fixed)
            if '|' not in link_text:
                matches.append((link_text, match.start(), match.end()))

        return matches

    def is_in_musical_connections(self, content: str, link_pos: int) -> bool:
        """
        Check if a wikilink position is within a Musical Connections section.

        We want to focus on links in the Musical Connections sections to avoid
        accidentally modifying other parts of the document.
        """
        # Find the Musical Connections header
        connections_match = re.search(r'^## Musical Connections', content, re.MULTILINE)

        if not connections_match:
            return False

        # Find the next section header after Musical Connections
        next_section = re.search(r'^## ', content[connections_match.end():], re.MULTILINE)

        connections_start = connections_match.start()
        connections_end = connections_match.end() + next_section.start() if next_section else len(content)

        return connections_start <= link_pos < connections_end

    def fix_wikilink(self, link_text: str) -> Tuple[str, bool]:
        """
        Fix a single wikilink.

        Returns: (fixed_link, was_fixed) tuple
        """
        # Extract artist name from path-based links
        artist_name = self.extract_artist_name(link_text)

        # Sanitize the artist name to get the filename
        sanitized = self.sanitize_filename(artist_name)

        # Check if a file exists with the sanitized filename
        if sanitized in self.artist_files:
            # Check if this link needs fixing
            # Path-based links always need fixing
            # Regular links need fixing if they contain spaces or special chars
            if '/' in link_text or sanitized != artist_name:
                # Fix the link: [[Artist_Name|Artist Name]]
                fixed_link = f"[[{sanitized}|{artist_name}]]"
                self.logger.debug(f"Fixed: [[{link_text}]] → {fixed_link}")
                return fixed_link, True
        else:
            # The target file doesn't exist, so we can't fix this link
            self.logger.warning(f"Cannot fix [[{link_text}]]: target file {sanitized}.md not found")
            self.stats['links_broken_unfixable'] += 1

        # Link is already in correct format or doesn't need fixing
        return f"[[{link_text}]]", False

    def process_card(self, card_path: Path) -> bool:
        """
        Process a single artist card file.

        Returns: True if card was modified, False otherwise
        """
        try:
            self.stats['cards_scanned'] += 1

            # Read the file
            with open(card_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Find all wikilinks
            wikilinks = self.find_wikilinks(content)

            if not wikilinks:
                return False

            self.stats['cards_with_wikilinks'] += 1
            self.stats['links_found'] += len(wikilinks)

            # Filter to only Musical Connections wikilinks
            relevant_links = [
                (text, start, end) for text, start, end in wikilinks
                if self.is_in_musical_connections(content, start)
            ]

            if not relevant_links:
                return False

            # Fix the wikilinks (process in reverse order to preserve positions)
            modified = False
            new_content = content

            for link_text, start, end in reversed(relevant_links):
                fixed_link, was_fixed = self.fix_wikilink(link_text)

                if was_fixed:
                    # Replace the wikilink in the content
                    new_content = new_content[:start] + fixed_link + new_content[end:]
                    modified = True
                    self.stats['links_fixed'] += 1

            # Write back if modified
            if modified:
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would fix {len([w for w in relevant_links if self.fix_wikilink(w[0])[1]])} links in: {card_path.name}")
                else:
                    # Create backup if requested
                    if self.backup:
                        self._create_backup(card_path)

                    # Write the fixed content
                    with open(card_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)

                    self.logger.info(f"Fixed {len([w for w in relevant_links if self.fix_wikilink(w[0])[1]])} links in: {card_path.name}")

                self.stats['cards_modified'] += 1
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error processing {card_path}: {e}")
            self.stats['errors'] += 1
            return False

    def _create_backup(self, file_path: Path):
        """Create a timestamped backup of a file."""
        backup_dir = self.cards_dir / "backups"
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{file_path.stem}_{timestamp}.md"

        shutil.copy2(file_path, backup_path)
        self.logger.debug(f"Created backup: {backup_path}")

    def process_all_cards(self):
        """Process all artist cards in the vault directory."""
        self.logger.info(f"Processing cards in: {self.cards_dir}")

        if self.dry_run:
            print("🔍 DRY RUN MODE - No files will be modified\n")

        # Get all .md files
        card_files = list(self.cards_dir.glob("*.md"))

        if not card_files:
            self.logger.warning("No artist cards found")
            return

        print(f"🔍 Scanning {len(card_files)} artist cards...\n")

        # Process each card
        with tqdm(card_files, desc="Processing cards", unit="card") as pbar:
            for card_path in pbar:
                pbar.set_description(f"Processing: {card_path.stem[:30]}")

                was_modified = self.process_card(card_path)

                if was_modified:
                    pbar.set_postfix_str("✓ Fixed")
                else:
                    pbar.set_postfix_str("")

        # Print summary
        self._print_summary()

    def _print_summary(self):
        """Print processing summary statistics."""
        print(f"\n📊 Summary:")
        print(f"Cards scanned: {self.stats['cards_scanned']}")
        print(f"Cards with wikilinks: {self.stats['cards_with_wikilinks']}")
        print(f"Cards modified: {self.stats['cards_modified']}")
        print(f"Links found: {self.stats['links_found']}")
        print(f"Links fixed: {self.stats['links_fixed']}")

        if self.stats['links_broken_unfixable'] > 0:
            print(f"⚠️  Links broken (target not found): {self.stats['links_broken_unfixable']}")

        if self.stats['errors'] > 0:
            print(f"❌ Errors: {self.stats['errors']}")

        if self.stats['cards_modified'] > 0:
            success_rate = (self.stats['links_fixed'] / self.stats['links_found'] * 100) if self.stats['links_found'] > 0 else 0
            print(f"\n🎯 Fix rate: {success_rate:.1f}%")

        if not self.dry_run and self.backup and self.stats['cards_modified'] > 0:
            print(f"\n💾 Backups saved to: {self.cards_dir / 'backups'}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fix broken Obsidian wikilinks in artist cards"
    )

    parser.add_argument(
        '--cards-dir',
        required=True,
        help='Directory containing artist card markdown files'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--backup',
        action='store_true',
        help='Create timestamped backups before modifying files'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Set logging level (default: INFO)'
    )

    args = parser.parse_args()

    try:
        # Create fixer and process
        fixer = WikilinkFixer(
            cards_dir=args.cards_dir,
            dry_run=args.dry_run,
            backup=args.backup,
            log_level=args.log_level
        )

        fixer.process_all_cards()

        print("\n✅ Processing completed successfully")

    except KeyboardInterrupt:
        print("\n\n⏹️ Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
