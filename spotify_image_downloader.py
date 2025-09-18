#!/usr/bin/env python3
"""
Spotify Artist Cover Image Downloader

Downloads artist cover images from Spotify based on data from an Obsidian vault
tracking radio station songs. Processes daily archive markdown files and downloads
images for artists marked as "✅ Found" in the Spotify status column.

Usage:
    python spotify_image_downloader.py --input path/to/daily_archive.md --output path/to/output_dir
"""

import os
import re
import sys
import time
import logging
import argparse
import requests
import base64
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote
import json

# Spotify API Configuration
SPOTIFY_CLIENT_ID = "a088edf333334899b6ad55579b834389"
SPOTIFY_CLIENT_SECRET = "78b5d889d9094ff0bb0b2a22cc8cfaac"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_ARTIST_URL = "https://api.spotify.com/v1/artists"

# Configuration
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
RATE_LIMIT_DELAY = 0.6  # 100 requests per minute = 0.6 seconds between requests


class SpotifyImageDownloader:
    """Main class for downloading Spotify artist cover images."""

    def __init__(self, output_dir: str, skip_existing: bool = True):
        self.output_dir = Path(output_dir)
        self.skip_existing = skip_existing
        self.access_token = None
        self.token_expires_at = 0
        self.session = requests.Session()

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Set up logging
        self.setup_logging()

    def setup_logging(self):
        """Configure logging for the application."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('spotify_downloader.log')
            ]
        )
        self.logger = logging.getLogger(__name__)

    def authenticate_spotify(self) -> bool:
        """
        Authenticate with Spotify using Client Credentials flow.

        Returns:
            bool: True if authentication successful, False otherwise
        """
        try:
            # Prepare credentials
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
                self.access_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                self.token_expires_at = time.time() + expires_in - 60  # Refresh 1 min early

                self.logger.info("Successfully authenticated with Spotify API")
                return True
            else:
                self.logger.error(f"Failed to authenticate with Spotify: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            self.logger.error(f"Exception during Spotify authentication: {e}")
            return False

    def ensure_authenticated(self) -> bool:
        """
        Ensure we have a valid access token, refreshing if necessary.

        Returns:
            bool: True if we have a valid token, False otherwise
        """
        if not self.access_token or time.time() >= self.token_expires_at:
            return self.authenticate_spotify()
        return True

    def parse_daily_archive(self, file_path: str) -> List[str]:
        """
        Parse the Obsidian daily archive markdown file and extract artists marked as "✅ Found".

        Args:
            file_path (str): Path to the markdown file

        Returns:
            List[str]: List of artist names that were found on Spotify
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            # Find the tracks table
            lines = content.split('\n')
            found_artists = []

            # Look for table content (starts after header row)
            in_table = False
            for line in lines:
                line = line.strip()

                # Skip empty lines
                if not line:
                    continue

                # Check if this is a table row (starts with |)
                if line.startswith('|') and '|' in line[1:]:
                    # Split by | and clean up
                    columns = [col.strip() for col in line.split('|')]

                    # Skip header rows and separator rows
                    if len(columns) >= 9 and columns[1] not in ['Time', ':----', '']:
                        # Extract artist (column 2) and status (column 8)
                        artist = columns[2].strip()
                        status = columns[8].strip()

                        # Check if status is "✅ Found"
                        if status == "✅ Found" and artist:
                            found_artists.append(artist)
                            self.logger.debug(f"Found artist: {artist}")

            self.logger.info(f"Parsed {len(found_artists)} artists marked as '✅ Found' from {file_path}")
            return found_artists

        except Exception as e:
            self.logger.error(f"Failed to parse daily archive file {file_path}: {e}")
            return []

    def sanitize_filename(self, artist_name: str) -> str:
        """
        Sanitize artist name for use as filename.

        Args:
            artist_name (str): Original artist name

        Returns:
            str: Sanitized filename
        """
        # Replace spaces with underscores
        sanitized = artist_name.replace(' ', '_')

        # Remove or replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '', sanitized)
        sanitized = re.sub(r'[&]', 'and', sanitized)
        sanitized = re.sub(r'[^\w\-_.]', '', sanitized)

        # Limit length to avoid filesystem issues
        if len(sanitized) > 200:
            sanitized = sanitized[:200]

        # Remove leading/trailing dots and spaces
        sanitized = sanitized.strip('.')

        return sanitized

    def check_duplicate(self, artist_name: str) -> bool:
        """
        Check if an image for this artist already exists.

        Args:
            artist_name (str): Name of the artist

        Returns:
            bool: True if image already exists, False otherwise
        """
        sanitized_name = self.sanitize_filename(artist_name)

        # Check for common image extensions
        extensions = ['.jpg', '.jpeg', '.png', '.webp']

        for ext in extensions:
            potential_file = self.output_dir / f"{sanitized_name}{ext}"
            if potential_file.exists():
                return True

        return False

    def search_spotify_artist(self, artist_name: str) -> Optional[Dict]:
        """
        Search for an artist on Spotify and return the best match.

        Args:
            artist_name (str): Name of the artist to search for

        Returns:
            Optional[Dict]: Artist data if found, None otherwise
        """
        if not self.ensure_authenticated():
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            # URL encode the search query
            query = quote(artist_name)
            url = f"{SPOTIFY_SEARCH_URL}?q={query}&type=artist&limit=10"

            response = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                data = response.json()
                artists = data.get('artists', {}).get('items', [])

                if artists:
                    # Return the first (most popular) result
                    best_match = artists[0]
                    self.logger.debug(f"Found artist: {best_match['name']} (ID: {best_match['id']})")
                    return best_match
                else:
                    self.logger.warning(f"No artists found for query: {artist_name}")
                    return None

            elif response.status_code == 401:
                self.logger.warning("Access token expired, re-authenticating...")
                if self.authenticate_spotify():
                    return self.search_spotify_artist(artist_name)  # Retry once
                return None
            else:
                self.logger.error(f"Failed to search for artist {artist_name}: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            self.logger.error(f"Exception while searching for artist {artist_name}: {e}")
            return None

    def get_artist_images(self, artist_id: str) -> List[Dict]:
        """
        Get artist images from Spotify API.

        Args:
            artist_id (str): Spotify artist ID

        Returns:
            List[Dict]: List of image dictionaries with url, height, width
        """
        if not self.ensure_authenticated():
            return []

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            url = f"{SPOTIFY_ARTIST_URL}/{artist_id}"
            response = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                data = response.json()
                images = data.get('images', [])
                return images
            else:
                self.logger.error(f"Failed to get artist images for ID {artist_id}: {response.status_code}")
                return []

        except Exception as e:
            self.logger.error(f"Exception while getting artist images for ID {artist_id}: {e}")
            return []

    def download_image(self, url: str, filename: str) -> bool:
        """
        Download an image from URL and save it to the output directory.

        Args:
            url (str): URL of the image to download
            filename (str): Filename to save the image as

        Returns:
            bool: True if download successful, False otherwise
        """
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT, stream=True)

            if response.status_code == 200:
                # Determine file extension from content type
                content_type = response.headers.get('content-type', '')
                if 'jpeg' in content_type or 'jpg' in content_type:
                    extension = '.jpg'
                elif 'png' in content_type:
                    extension = '.png'
                elif 'webp' in content_type:
                    extension = '.webp'
                else:
                    extension = '.jpg'  # Default to jpg

                file_path = self.output_dir / f"{filename}{extension}"

                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                self.logger.info(f"Downloaded image: {file_path}")
                return True
            else:
                self.logger.error(f"Failed to download image from {url}: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"Exception while downloading image from {url}: {e}")
            return False

    def download_artist_image(self, artist_name: str) -> bool:
        """
        Download the cover image for a given artist.

        Args:
            artist_name (str): Name of the artist

        Returns:
            bool: True if download successful, False otherwise
        """
        # Check for duplicates if skip_existing is enabled
        if self.skip_existing and self.check_duplicate(artist_name):
            self.logger.info(f"Skipping {artist_name} - image already exists")
            return True

        # Search for artist on Spotify
        artist_data = self.search_spotify_artist(artist_name)
        if not artist_data:
            return False

        # Get artist images
        images = artist_data.get('images', [])
        if not images:
            self.logger.warning(f"No images found for artist: {artist_name}")
            return False

        # Select the highest resolution image (first one is usually the largest)
        best_image = images[0]
        image_url = best_image['url']

        # Download the image
        sanitized_name = self.sanitize_filename(artist_name)
        success = self.download_image(image_url, sanitized_name)

        if success:
            self.logger.info(f"Successfully downloaded image for: {artist_name}")

        # Add delay to respect rate limits
        time.sleep(RATE_LIMIT_DELAY)

        return success

    def process_daily_archive(self, input_file: str) -> Dict[str, int]:
        """
        Process a daily archive file and download all artist images.

        Args:
            input_file (str): Path to the daily archive markdown file

        Returns:
            Dict[str, int]: Statistics about the processing
        """
        self.logger.info(f"Starting to process daily archive: {input_file}")

        # Parse the markdown file
        artists = self.parse_daily_archive(input_file)
        if not artists:
            self.logger.error("No artists found in the daily archive file")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

        # Authenticate with Spotify
        if not self.authenticate_spotify():
            self.logger.error("Failed to authenticate with Spotify")
            return {"total": len(artists), "success": 0, "failed": len(artists), "skipped": 0}

        # Download images for each artist
        stats = {"total": len(artists), "success": 0, "failed": 0, "skipped": 0}

        for i, artist in enumerate(artists, 1):
            self.logger.info(f"Processing artist {i}/{len(artists)}: {artist}")

            if self.skip_existing and self.check_duplicate(artist):
                stats["skipped"] += 1
                continue

            success = self.download_artist_image(artist)
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1

        # Log final statistics
        self.logger.info(f"Processing complete. Total: {stats['total']}, "
                        f"Success: {stats['success']}, Failed: {stats['failed']}, "
                        f"Skipped: {stats['skipped']}")

        return stats


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Download Spotify artist cover images from daily archive files")
    parser.add_argument("--input", required=True, help="Path to the daily archive markdown file")
    parser.add_argument("--output", required=True, help="Directory to save downloaded images")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                       help="Skip downloading if image already exists (default: True)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       default="INFO", help="Logging level")

    args = parser.parse_args()

    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Validate input file
    if not os.path.exists(args.input):
        print(f"Error: Input file does not exist: {args.input}")
        sys.exit(1)

    # Create downloader and process file
    downloader = SpotifyImageDownloader(args.output, args.skip_existing)
    stats = downloader.process_daily_archive(args.input)

    # Print final summary
    print(f"\nDownload Summary:")
    print(f"Total artists: {stats['total']}")
    print(f"Successfully downloaded: {stats['success']}")
    print(f"Failed: {stats['failed']}")
    print(f"Skipped (already exist): {stats['skipped']}")


if __name__ == "__main__":
    main()