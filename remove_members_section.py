#!/usr/bin/env python3
"""
Remove Members Section from Artist Cards

This script removes the "Members" section (including "Original Members" subsection)
and "members"/"original_members" frontmatter fields from all artist cards.

Usage:
    python remove_members_section.py [--dry-run] [--cards-dir PATH]
"""

import os
import re
import sys
import logging
import argparse
from pathlib import Path
from typing import Optional, Tuple

import yaml

# Default vault path
DEFAULT_CARDS_DIR = "/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists"


class MembersRemover:
    """Remove Members section from artist cards."""

    def __init__(self, cards_dir: str, dry_run: bool = False):
        self.cards_dir = Path(cards_dir)
        self.dry_run = dry_run

        if not self.cards_dir.exists():
            raise ValueError(f"Cards directory does not exist: {cards_dir}")

        # Statistics
        self.stats = {
            'total': 0,
            'processed': 0,
            'modified': 0,
            'skipped': 0,
            'errors': 0
        }

        # Setup logging
        self.setup_logging()

    def setup_logging(self):
        """Configure logging."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('remove_members_section.log')
            ]
        )
        self.logger = logging.getLogger(__name__)

    def get_all_artist_cards(self) -> list:
        """Get all artist card markdown files."""
        cards = list(self.cards_dir.glob("*.md"))
        # Filter out the connections file
        cards = [c for c in cards if c.name != "artist_connections.json"]
        self.logger.info(f"Found {len(cards)} artist cards in {self.cards_dir}")
        return sorted(cards)

    def parse_card(self, card_path: Path) -> Tuple[Optional[dict], str]:
        """
        Parse artist card and extract frontmatter and content.

        Returns: (frontmatter_dict, full_content)
        """
        try:
            with open(card_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.startswith('---'):
                self.logger.warning(f"No frontmatter found in {card_path.name}")
                return None, content

            # Find frontmatter boundaries
            frontmatter_end = content.find('---', 3)
            if frontmatter_end == -1:
                self.logger.warning(f"Malformed frontmatter in {card_path.name}")
                return None, content

            frontmatter_text = content[3:frontmatter_end]
            frontmatter = yaml.safe_load(frontmatter_text)

            return frontmatter, content

        except Exception as e:
            self.logger.error(f"Error parsing {card_path.name}: {e}")
            return None, ""

    def remove_members_from_frontmatter(self, frontmatter: dict) -> bool:
        """
        Remove 'members' and 'original_members' fields from frontmatter.

        Returns: True if any fields were removed, False otherwise
        """
        modified = False

        if 'members' in frontmatter:
            del frontmatter['members']
            modified = True
            self.logger.debug("Removed 'members' from frontmatter")

        if 'original_members' in frontmatter:
            del frontmatter['original_members']
            modified = True
            self.logger.debug("Removed 'original_members' from frontmatter")

        return modified

    def remove_members_section(self, content: str) -> Tuple[str, bool]:
        """
        Remove the Members section from markdown content.

        Returns: (updated_content, was_modified)
        """
        modified = False

        # Pattern to match the Members section (including Original Members subsection)
        # Matches from "## Members" until the next "## " heading or end of file
        pattern = r'\n## Members\n.*?(?=\n## |\Z)'

        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, '', content, flags=re.DOTALL)
            modified = True
            self.logger.debug("Removed Members section from markdown")

        return content, modified

    def process_card(self, card_path: Path) -> str:
        """
        Process a single artist card to remove Members section.

        Returns: Status message string
        """
        try:
            self.logger.info(f"Processing: {card_path.name}")

            # Parse card
            frontmatter, content = self.parse_card(card_path)
            if frontmatter is None:
                self.stats['errors'] += 1
                return "❌ Parse error"

            # Check if card has members data
            has_members_frontmatter = 'members' in frontmatter or 'original_members' in frontmatter
            has_members_section = '## Members' in content

            if not has_members_frontmatter and not has_members_section:
                self.stats['skipped'] += 1
                return "⏭️  No members data"

            # Remove from frontmatter
            frontmatter_modified = self.remove_members_from_frontmatter(frontmatter)

            # Parse content parts
            content_parts = content.split('---', 2)
            if len(content_parts) < 3:
                self.logger.error(f"Cannot parse content structure for {card_path.name}")
                self.stats['errors'] += 1
                return "❌ Parse error"

            markdown_content = content_parts[2]

            # Remove Members section from markdown
            markdown_content, markdown_modified = self.remove_members_section(markdown_content)

            # Check if anything was modified
            if not frontmatter_modified and not markdown_modified:
                self.stats['skipped'] += 1
                return "⏭️  No changes needed"

            # Rebuild the file
            frontmatter_text = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
            updated_content = f"---\n{frontmatter_text}---{markdown_content}"

            # Write updated card
            if not self.dry_run:
                with open(card_path, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                self.logger.info(f"Updated: {card_path.name}")
            else:
                self.logger.info(f"[DRY RUN] Would update: {card_path.name}")

            self.stats['modified'] += 1
            return "✅ Removed members data"

        except Exception as e:
            self.logger.error(f"Error processing {card_path.name}: {e}")
            self.stats['errors'] += 1
            return f"❌ Error: {str(e)[:30]}"

    def run(self):
        """Run the removal process."""
        cards = self.get_all_artist_cards()
        self.stats['total'] = len(cards)

        print(f"\n🧹 Remove Members Section Process")
        print(f"Cards directory: {self.cards_dir}")
        print(f"Total cards: {self.stats['total']}")
        if self.dry_run:
            print("🔍 DRY RUN MODE - No files will be modified")
        print()

        from tqdm import tqdm

        with tqdm(cards, desc="Processing cards", unit="card") as pbar:
            for card_path in pbar:
                pbar.set_description(f"Processing: {card_path.stem[:30]}")

                status = self.process_card(card_path)
                pbar.set_postfix_str(status)
                self.stats['processed'] += 1

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print processing summary."""
        print(f"\n📊 Removal Summary:")
        print(f"✅ Modified: {self.stats['modified']} cards")
        print(f"⏭️  Skipped (no members data): {self.stats['skipped']}")
        print(f"❌ Errors: {self.stats['errors']}")
        print(f"📁 Total processed: {self.stats['processed']}/{self.stats['total']}")

        if self.stats['processed'] > 0:
            modified_rate = (self.stats['modified'] / self.stats['processed'] * 100)
            print(f"\n🎯 Modification rate: {modified_rate:.1f}%")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Remove Members section from all artist cards"
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
        # Create remover and run
        remover = MembersRemover(
            cards_dir=args.cards_dir,
            dry_run=args.dry_run
        )

        remover.run()

        print("\n✅ Removal process completed successfully")

    except KeyboardInterrupt:
        print("\n\n⏹️  Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
