#!/usr/bin/env python3
"""
Spotify Artist Card Generator with Biography Integration

Generates comprehensive artist cards for Obsidian vault by combining:
- Spotify API metadata (albums, tracks, popularity)
- Wikipedia biographies (primary source)
- MusicBrainz data (fallback source)

Usage:
    python spotify_artist_card_generator.py --artist "Artist Name" --output-dir path/to/Artists
    python spotify_artist_card_generator.py --input-file daily_archive.md --output-dir path/to/Artists
"""

import os
import re
import sys
import time
import json
import logging
import argparse
import requests
import base64
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import quote, unquote
from bs4 import BeautifulSoup

# Spotify API Configuration (reuse from existing script)
SPOTIFY_CLIENT_ID = "a088edf333334899b6ad55579b834389"
SPOTIFY_CLIENT_SECRET = "78b5d889d9094ff0bb0b2a22cc8cfaac"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_ARTIST_URL = "https://api.spotify.com/v1/artists"

# Wikipedia API Configuration
WIKIPEDIA_API_BASE = "https://en.wikipedia.org/api/rest_v1"
WIKIMEDIA_CORE_API = "https://api.wikimedia.org/core/v1/wikipedia"

# Wikidata API Configuration
WIKIDATA_API_BASE = "https://www.wikidata.org/wiki/Special:EntityData"

# MusicBrainz API Configuration
MUSICBRAINZ_API_BASE = "https://musicbrainz.org/ws/2"

# Configuration
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
RATE_LIMIT_DELAY = 1.0  # Delay between API requests
USER_AGENT = "SpotifyArtistCardGenerator/1.0 (https://github.com/yourusername/project)"


class WikipediaAPI:
    """Handles Wikipedia API interactions for fetching artist biographies."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT
        })
        self.logger = logging.getLogger(__name__)

    def search_artist(self, artist_name: str) -> Optional[str]:
        """
        Search for artist Wikipedia page.

        Args:
            artist_name: Name of the artist to search for

        Returns:
            Wikipedia page title if found, None otherwise
        """
        try:
            # First try with REST API search
            search_url = f"{WIKIMEDIA_CORE_API}/en/search/page"
            params = {
                'q': artist_name,
                'limit': 3
            }

            response = self.session.get(
                search_url,
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                data = response.json()
                pages = data.get('pages', [])

                # Look for best match (case-insensitive)
                for page in pages:
                    title = page.get('title', '')
                    # Check if it's likely an artist page (not a disambiguation)
                    if artist_name.lower() in title.lower():
                        if 'disambiguation' not in title.lower():
                            self.logger.info(f"Found Wikipedia page: {title}")
                            return title

                # If no exact match, return first result if available
                if pages:
                    title = pages[0].get('title')
                    self.logger.info(f"Using Wikipedia page: {title}")
                    return title

            self.logger.warning(f"No Wikipedia page found for {artist_name}")
            return None

        except Exception as e:
            self.logger.error(f"Error searching Wikipedia for {artist_name}: {e}")
            return None

    def get_page_summary(self, page_title: str) -> Dict[str, Any]:
        """
        Get Wikipedia page summary and extract.

        Args:
            page_title: Wikipedia page title

        Returns:
            Dictionary with biography text and metadata
        """
        try:
            # URL encode the title
            encoded_title = quote(page_title.replace(' ', '_'))

            # Get page summary
            summary_url = f"{WIKIPEDIA_API_BASE}/page/summary/{encoded_title}"

            response = self.session.get(summary_url, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                data = response.json()

                result = {
                    'biography': data.get('extract', ''),
                    'description': data.get('description', ''),
                    'wikipedia_url': data.get('content_urls', {}).get('desktop', {}).get('page', ''),
                    'thumbnail': data.get('thumbnail', {}).get('source', ''),
                    'page_title': data.get('title', page_title)
                }

                # Try to get more detailed extract if needed
                if len(result['biography']) < 200:
                    result['biography'] = self._get_full_extract(encoded_title)

                return result

            return {'biography': '', 'wikipedia_url': ''}

        except Exception as e:
            self.logger.error(f"Error getting Wikipedia summary for {page_title}: {e}")
            return {'biography': '', 'wikipedia_url': ''}

    def _get_full_extract(self, page_title: str) -> str:
        """
        Get fuller extract from Wikipedia page.

        Args:
            page_title: URL-encoded page title

        Returns:
            Extended biography text
        """
        try:
            # Use action API for longer extracts
            api_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'format': 'json',
                'titles': unquote(page_title),
                'prop': 'extracts',
                'exintro': True,
                'explaintext': True,
                'exsectionformat': 'plain',
                'exchars': 2500
            }

            response = self.session.get(api_url, params=params, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                data = response.json()
                pages = data.get('query', {}).get('pages', {})

                for page_id, page_data in pages.items():
                    extract = page_data.get('extract', '')
                    if extract:
                        return extract

            return ''

        except Exception as e:
            self.logger.error(f"Error getting full extract: {e}")
            return ''

    def get_mobile_sections(self, page_title: str) -> Optional[Dict]:
        """
        Get mobile sections data which includes infobox HTML.

        Args:
            page_title: Wikipedia page title

        Returns:
            Dictionary with sections data or None
        """
        try:
            encoded_title = quote(page_title.replace(' ', '_'))
            mobile_url = f"{WIKIPEDIA_API_BASE}/page/mobile-sections/{encoded_title}"

            response = self.session.get(mobile_url, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                return response.json()

            self.logger.warning(f"Failed to get mobile sections for {page_title}: {response.status_code}")
            return None

        except Exception as e:
            self.logger.error(f"Error getting mobile sections for {page_title}: {e}")
            return None

    def extract_infobox_data(self, mobile_data: Dict) -> Dict[str, Any]:
        """
        Extract structured data from mobile sections HTML.

        Args:
            mobile_data: Mobile sections response data

        Returns:
            Dictionary with extracted structured data
        """
        extracted = {
            'birth_date': '',
            'death_date': '',
            'birth_place': '',
            'birth_name': '',
            'also_known_as': [],
            'occupation': [],
            'origin': '',
            'instruments': [],
            'years_active': '',
            'associated_acts': [],
            'record_labels': [],
            'spouse': []
        }

        try:
            # Get the lead section which contains infobox data
            lead = mobile_data.get('lead', {})
            sections = mobile_data.get('remaining', {}).get('sections', [])

            # Combine lead text and first few sections to find infobox
            html_content = lead.get('sections', [{}])[0].get('text', '') if lead.get('sections') else ''

            if html_content:
                soup = BeautifulSoup(html_content, 'html.parser')

                # Look for infobox table
                infobox = soup.find('table', class_=lambda x: x and 'infobox' in x.lower() if x else False)

                if infobox:
                    extracted.update(self._parse_infobox_table(infobox))
                else:
                    # Try to find individual data points in the HTML
                    extracted.update(self._parse_general_html(soup))

        except Exception as e:
            self.logger.error(f"Error extracting infobox data: {e}")

        return extracted

    def _parse_infobox_table(self, infobox) -> Dict[str, Any]:
        """Parse an infobox table for artist data."""
        data = {
            'birth_date': '',
            'death_date': '',
            'birth_place': '',
            'birth_name': '',
            'also_known_as': [],
            'occupation': [],
            'origin': '',
            'instruments': [],
            'years_active': '',
            'associated_acts': [],
            'record_labels': [],
            'spouse': []
        }

        try:
            rows = infobox.find_all('tr')

            for row in rows:
                th = row.find('th')
                td = row.find('td')

                if not th or not td:
                    continue

                label = th.get_text(strip=True).lower()
                value = td.get_text(strip=True)

                # Map common infobox labels to our fields
                if 'born' in label:
                    # Extract date and place
                    birth_info = self._parse_birth_info(value)
                    data['birth_date'] = birth_info.get('date', '')
                    data['birth_place'] = birth_info.get('place', '')
                elif 'died' in label:
                    data['death_date'] = self._extract_date(value)
                elif 'origin' in label or 'hometown' in label:
                    data['origin'] = value
                elif 'instrument' in label:
                    data['instruments'] = self._parse_list_field(value)
                elif 'years active' in label or 'active' in label:
                    data['years_active'] = value
                elif 'associated acts' in label or 'associated' in label:
                    data['associated_acts'] = self._parse_list_field(value)
                elif 'birth name' in label or 'real name' in label:
                    data['birth_name'] = value
                elif 'also known as' in label or 'aliases' in label or 'nickname' in label:
                    data['also_known_as'] = self._parse_list_field(value)
                elif 'occupation' in label or 'profession' in label or 'genre' in label:
                    data['occupation'] = self._parse_list_field(value)
                elif 'label' in label and 'record' in label or 'labels' in label:
                    data['record_labels'] = self._parse_list_field(value)
                elif 'spouse' in label or 'partner' in label or 'married' in label:
                    data['spouse'] = self._parse_list_field(value)

        except Exception as e:
            self.logger.error(f"Error parsing infobox table: {e}")

        return data

    def _parse_general_html(self, soup) -> Dict[str, Any]:
        """Parse general HTML for artist data when no infobox is found."""
        # This is a fallback method for pages without clear infoboxes
        return {
            'birth_date': '',
            'death_date': '',
            'birth_place': '',
            'birth_name': '',
            'also_known_as': [],
            'occupation': [],
            'origin': '',
            'instruments': [],
            'years_active': '',
            'associated_acts': [],
            'record_labels': [],
            'spouse': []
        }

    def _parse_birth_info(self, birth_text: str) -> Dict[str, str]:
        """Parse birth information to extract date and place."""
        import re

        # Common patterns for birth info
        # Example: "September 23, 1926, Hamlet, North Carolina, U.S."
        date_match = re.search(r'(\w+\s+\d{1,2},\s+\d{4})', birth_text)

        result = {'date': '', 'place': ''}

        if date_match:
            result['date'] = date_match.group(1)
            # Everything after the date is typically the place
            remaining = birth_text[date_match.end():].strip(' ,')
            if remaining:
                result['place'] = remaining

        return result

    def _extract_date(self, text: str) -> str:
        """Extract date from text."""
        import re
        date_match = re.search(r'(\w+\s+\d{1,2},\s+\d{4})', text)
        return date_match.group(1) if date_match else ''

    def _parse_list_field(self, text: str) -> List[str]:
        """Parse comma-separated or newline-separated list fields."""
        if not text:
            return []

        # Split by common separators and clean up
        items = re.split(r'[,\n]', text)
        return [item.strip() for item in items if item.strip()]

    def get_infobox_via_action_api(self, page_title: str) -> Dict[str, Any]:
        """
        Get infobox data using Wikipedia Action API.

        Args:
            page_title: Wikipedia page title

        Returns:
            Dictionary with extracted infobox data
        """
        extracted = {
            'birth_date': '',
            'death_date': '',
            'birth_place': '',
            'birth_name': '',
            'also_known_as': [],
            'occupation': [],
            'origin': '',
            'instruments': [],
            'years_active': '',
            'associated_acts': [],
            'record_labels': [],
            'spouse': []
        }

        try:
            # Use Wikipedia Action API to get page content
            action_api_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'prop': 'revisions',
                'titles': page_title,
                'rvprop': 'content',
                'format': 'json',
                'formatversion': '2',
                'rvslots': 'main'
            }

            response = self.session.get(action_api_url, params=params, timeout=REQUEST_TIMEOUT)

            self.logger.debug(f"Action API response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                pages = data.get('query', {}).get('pages', [])

                if pages and len(pages) > 0:
                    page = pages[0]
                    revisions = page.get('revisions', [])

                    if revisions and len(revisions) > 0:
                        content = revisions[0].get('slots', {}).get('main', {}).get('content', '')

                        if content:
                            # Parse the wikitext for infobox data
                            extracted.update(self._parse_wikitext_infobox(content))
                            self.logger.debug(f"Action API extracted data: {extracted}")
                else:
                    self.logger.warning("Action API returned 200 but no pages found")
            else:
                self.logger.warning(f"Action API failed with status {response.status_code}")

        except Exception as e:
            self.logger.error(f"Error getting infobox via Action API: {e}")

        return extracted

    def _parse_wikitext_infobox(self, wikitext: str) -> Dict[str, Any]:
        """
        Parse wikitext to extract infobox data.

        Args:
            wikitext: Raw wikitext content

        Returns:
            Dictionary with extracted data
        """
        import re

        data = {}

        # Extract years active - handle various formats
        years_pattern = r'\|\s*years[_\s]active\s*=\s*([^\|]*?)(?=\n|\|)'
        years_match = re.search(years_pattern, wikitext, re.IGNORECASE)
        if years_match:
            years_text = years_match.group(1).strip()
            # Clean up the text - remove references, links, etc.
            years_text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', years_text)  # Remove wiki links
            years_text = re.sub(r'<[^>]+>', '', years_text)  # Remove HTML tags
            years_text = re.sub(r'\{\{[^}]+\}\}', '', years_text)  # Remove templates
            years_text = re.sub(r'<ref[^>]*>.*?</ref>', '', years_text)  # Remove references
            years_text = years_text.strip()
            if years_text:
                data['years_active'] = years_text
                self.logger.debug(f"Extracted years_active from wikitext: {years_text}")

        # Extract other useful fields
        # Birth date
        birth_pattern = r'\|\s*birth[_\s]date\s*=\s*([^\|]*?)(?=\n|\|)'
        birth_match = re.search(birth_pattern, wikitext, re.IGNORECASE)
        if birth_match:
            birth_text = birth_match.group(1).strip()
            # Extract date from templates like {{birth date|1926|09|23}}
            date_template_match = re.search(r'\{\{[^|]+\|(\d{4})\|(\d{1,2})\|(\d{1,2})', birth_text)
            if date_template_match:
                year, month, day = date_template_match.groups()
                data['birth_date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # Death date
        death_pattern = r'\|\s*death[_\s]date\s*=\s*([^\|]*?)(?=\n|\|)'
        death_match = re.search(death_pattern, wikitext, re.IGNORECASE)
        if death_match:
            death_text = death_match.group(1).strip()
            # Extract date from templates
            date_template_match = re.search(r'\{\{[^|]+\|(\d{4})\|(\d{1,2})\|(\d{1,2})', death_text)
            if date_template_match:
                year, month, day = date_template_match.groups()
                data['death_date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # Instruments
        instruments_pattern = r'\|\s*instruments?\s*=\s*([^\|]*?)(?=\n|\|)'
        instruments_match = re.search(instruments_pattern, wikitext, re.IGNORECASE)
        if instruments_match:
            instruments_text = instruments_match.group(1).strip()
            # Clean up and split
            instruments_text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', instruments_text)
            instruments_text = re.sub(r'<[^>]+>', '', instruments_text)
            instruments = [i.strip() for i in re.split(r'[,\n•]', instruments_text) if i.strip()]
            if instruments:
                data['instruments'] = instruments

        return data

    def get_wikidata_entity(self, wikipedia_url: str) -> Optional[str]:
        """
        Extract Wikidata entity ID from Wikipedia page.

        Args:
            wikipedia_url: Wikipedia page URL

        Returns:
            Wikidata entity ID (e.g., 'Q7346') or None
        """
        try:
            # Use Wikipedia API to get Wikidata entity
            page_title = wikipedia_url.split('/')[-1]
            api_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'format': 'json',
                'titles': unquote(page_title),
                'prop': 'pageprops',
                'ppprop': 'wikibase_item'
            }

            response = self.session.get(api_url, params=params, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                data = response.json()
                pages = data.get('query', {}).get('pages', {})

                for page_data in pages.values():
                    wikibase_item = page_data.get('pageprops', {}).get('wikibase_item')
                    if wikibase_item:
                        return wikibase_item

            return None

        except Exception as e:
            self.logger.error(f"Error getting Wikidata entity: {e}")
            return None

    def get_wikidata_claims(self, entity_id: str) -> Dict[str, Any]:
        """
        Get structured data from Wikidata.

        Args:
            entity_id: Wikidata entity ID (e.g., 'Q7346')

        Returns:
            Dictionary with structured artist data
        """
        structured_data = {
            'birth_date': '',
            'death_date': '',
            'birth_place': '',
            'birth_name': '',
            'also_known_as': [],
            'occupation': [],
            'instruments': [],
            'years_active': '',
            'associated_acts': [],
            'record_labels': [],
            'spouse': []
        }

        try:
            # Get entity data from Wikidata
            wikidata_url = f"{WIKIDATA_API_BASE}/{entity_id}.json"

            response = self.session.get(wikidata_url, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                data = response.json()
                entity_data = data.get('entities', {}).get(entity_id, {})
                claims = entity_data.get('claims', {})

                # Extract relevant properties
                # P569: Date of birth
                if 'P569' in claims:
                    birth_date = self._extract_wikidata_date(claims['P569'])
                    if birth_date:
                        structured_data['birth_date'] = birth_date

                # P570: Date of death
                if 'P570' in claims:
                    death_date = self._extract_wikidata_date(claims['P570'])
                    if death_date:
                        structured_data['death_date'] = death_date

                # P19: Place of birth
                if 'P19' in claims:
                    birth_place = self._extract_wikidata_label(claims['P19'])
                    if birth_place:
                        structured_data['birth_place'] = birth_place

                # P1303: Instruments played
                if 'P1303' in claims:
                    instruments = self._extract_wikidata_labels(claims['P1303'])
                    structured_data['instruments'] = instruments

                # P1477: Birth name
                if 'P1477' in claims:
                    birth_name = self._extract_wikidata_text(claims['P1477'])
                    if birth_name:
                        structured_data['birth_name'] = birth_name

                # P742: Pseudonym (also known as)
                if 'P742' in claims:
                    aliases = self._extract_wikidata_text_list(claims['P742'])
                    self.logger.debug(f"Found P742 pseudonyms: {aliases}")
                    structured_data['also_known_as'].extend(aliases)
                else:
                    self.logger.debug("P742 (pseudonym) not found in claims")

                # P1449: Nickname (nicknames like "Trane")
                if 'P1449' in claims:
                    nicknames = self._extract_wikidata_text_list(claims['P1449'])
                    self.logger.debug(f"Found P1449 nicknames: {nicknames}")
                    structured_data['also_known_as'].extend(nicknames)
                else:
                    self.logger.debug("P1449 (nickname) not found in claims")

                # P106: Occupation
                if 'P106' in claims:
                    occupation = self._extract_wikidata_labels(claims['P106'])
                    structured_data['occupation'] = occupation

                # P264: Record label
                if 'P264' in claims:
                    record_labels = self._extract_wikidata_labels(claims['P264'])
                    structured_data['record_labels'] = record_labels

                # P26: Spouse
                if 'P26' in claims:
                    spouse = self._extract_wikidata_labels(claims['P26'])
                    structured_data['spouse'] = spouse

                # P527: Has part(s) - for band members / associated acts
                if 'P527' in claims:
                    associated_acts = self._extract_wikidata_labels(claims['P527'])
                    structured_data['associated_acts'].extend(associated_acts)

                # P361: Part of - for bands the artist was part of
                if 'P361' in claims:
                    part_of = self._extract_wikidata_labels(claims['P361'])
                    structured_data['associated_acts'].extend(part_of)

                # P2032: Work period start, P2034: Work period end
                start_year = ''
                end_year = ''
                if 'P2032' in claims:
                    start_year = self._extract_wikidata_year(claims['P2032'])
                    self.logger.debug(f"Extracted work period start: {start_year}")
                if 'P2034' in claims:
                    end_year = self._extract_wikidata_year(claims['P2034'])
                    self.logger.debug(f"Extracted work period end: {end_year}")

                if start_year:
                    if end_year:
                        structured_data['years_active'] = f"{start_year}-{end_year}"
                        self.logger.debug(f"Years active from work periods: {start_year}-{end_year}")
                    else:
                        # If no end year but we have death date, use death year
                        death_year = ''
                        if structured_data.get('death_date'):
                            death_year = structured_data['death_date'][:4]  # Extract year from YYYY-MM-DD

                        if death_year:
                            structured_data['years_active'] = f"{start_year}-{death_year}"
                            self.logger.debug(f"Years active using death date: {start_year}-{death_year}")
                        else:
                            structured_data['years_active'] = f"{start_year}-present"
                            self.logger.debug(f"Years active (ongoing): {start_year}-present")
                else:
                    # Fallback: try to estimate from biographical text or use birth/death years
                    if structured_data.get('birth_date') and structured_data.get('death_date'):
                        birth_year = structured_data['birth_date'][:4]
                        death_year = structured_data['death_date'][:4]
                        # Assume career started around age 20-25 for musicians
                        estimated_start = str(int(birth_year) + 20)
                        structured_data['years_active'] = f"{estimated_start}-{death_year}"
                        self.logger.debug(f"Years active estimated from birth/death: {estimated_start}-{death_year}")

        except Exception as e:
            self.logger.error(f"Error getting Wikidata claims for {entity_id}: {e}")

        # Log final alias collection
        final_aliases = structured_data.get('also_known_as', [])
        self.logger.debug(f"Final collected aliases: {final_aliases}")

        return structured_data

    def _extract_wikidata_date(self, claims: List) -> str:
        """Extract date from Wikidata claims."""
        try:
            if claims and len(claims) > 0:
                main_snak = claims[0].get('mainsnak', {})
                if main_snak.get('datatype') == 'time':
                    time_value = main_snak.get('datavalue', {}).get('value', {}).get('time', '')
                    # Parse Wikidata time format (+1926-09-23T00:00:00Z) to readable date
                    if time_value:
                        import re
                        date_match = re.search(r'\+(\d{4})-(\d{2})-(\d{2})', time_value)
                        if date_match:
                            year, month, day = date_match.groups()
                            return f"{year}-{month}-{day}"
        except Exception:
            pass
        return ''

    def _extract_wikidata_year(self, claims: List) -> str:
        """Extract year from Wikidata claims."""
        try:
            if claims and len(claims) > 0:
                main_snak = claims[0].get('mainsnak', {})
                if main_snak.get('datatype') == 'time':
                    time_value = main_snak.get('datavalue', {}).get('value', {}).get('time', '')
                    if time_value:
                        import re
                        year_match = re.search(r'\+(\d{4})', time_value)
                        if year_match:
                            return year_match.group(1)
        except Exception:
            pass
        return ''

    def _extract_wikidata_label(self, claims: List) -> str:
        """
        Extract single label from Wikidata claims.

        Args:
            claims: List of Wikidata claims for a property

        Returns:
            Human-readable label string or empty string if not found
        """
        if not claims:
            return ''

        try:
            # Get the first claim's entity ID
            first_claim = claims[0]
            if 'mainsnak' in first_claim and 'datavalue' in first_claim['mainsnak']:
                datavalue = first_claim['mainsnak']['datavalue']
                if datavalue.get('type') == 'wikibase-entityid':
                    entity_id = datavalue['value']['id']
                    return self._get_entity_label(entity_id)
        except Exception as e:
            self.logger.error(f"Error extracting Wikidata label: {e}")

        return ''

    def _extract_wikidata_labels(self, claims: List) -> List[str]:
        """
        Extract multiple labels from Wikidata claims.

        Args:
            claims: List of Wikidata claims for a property

        Returns:
            List of human-readable label strings
        """
        labels = []

        try:
            for claim in claims[:5]:  # Limit to first 5 to avoid too many API calls
                if 'mainsnak' in claim and 'datavalue' in claim['mainsnak']:
                    datavalue = claim['mainsnak']['datavalue']
                    if datavalue.get('type') == 'wikibase-entityid':
                        entity_id = datavalue['value']['id']
                        label = self._get_entity_label(entity_id)
                        if label:
                            labels.append(label)
        except Exception as e:
            self.logger.error(f"Error extracting Wikidata labels: {e}")

        return labels

    def _get_entity_label(self, entity_id: str) -> str:
        """
        Get human-readable label for a Wikidata entity ID.

        Args:
            entity_id: Wikidata entity ID (e.g., 'Q123456')

        Returns:
            Human-readable label or empty string if not found
        """
        try:
            # Use Wikidata Special:EntityData API to get entity information
            entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"

            response = self.session.get(entity_url, timeout=REQUEST_TIMEOUT)
            time.sleep(RATE_LIMIT_DELAY)  # Rate limiting

            if response.status_code == 200:
                data = response.json()
                entities = data.get('entities', {})

                if entity_id in entities:
                    entity = entities[entity_id]
                    labels = entity.get('labels', {})

                    # Try to get English label first
                    if 'en' in labels:
                        return labels['en']['value']

                    # Fallback to any available label
                    if labels:
                        first_label = next(iter(labels.values()))
                        return first_label['value']
            else:
                self.logger.warning(f"Failed to get entity data for {entity_id}: {response.status_code}")

        except Exception as e:
            self.logger.error(f"Error getting entity label for {entity_id}: {e}")

        return ''

    def _extract_wikidata_text(self, claims: List) -> str:
        """
        Extract text value from Wikidata claims.

        Args:
            claims: List of Wikidata claims for a text property

        Returns:
            Text string or empty string if not found
        """
        if not claims:
            return ''

        try:
            first_claim = claims[0]
            if 'mainsnak' in first_claim and 'datavalue' in first_claim['mainsnak']:
                datavalue = first_claim['mainsnak']['datavalue']
                if datavalue.get('type') == 'string':
                    return datavalue['value']
                elif datavalue.get('type') == 'monolingualtext':
                    return datavalue['value']['text']
        except Exception as e:
            self.logger.error(f"Error extracting Wikidata text: {e}")

        return ''

    def _extract_wikidata_text_list(self, claims: List) -> List[str]:
        """
        Extract multiple text values from Wikidata claims.

        Args:
            claims: List of Wikidata claims for text properties

        Returns:
            List of text strings
        """
        texts = []

        try:
            for claim in claims[:5]:  # Limit to first 5
                if 'mainsnak' in claim and 'datavalue' in claim['mainsnak']:
                    datavalue = claim['mainsnak']['datavalue']
                    text = ''
                    if datavalue.get('type') == 'string':
                        text = datavalue['value']
                    elif datavalue.get('type') == 'monolingualtext':
                        text = datavalue['value']['text']

                    if text:
                        texts.append(text)
        except Exception as e:
            self.logger.error(f"Error extracting Wikidata text list: {e}")

        return texts

    def get_artist_structured_data(self, artist_name: str) -> Dict[str, Any]:
        """
        Get comprehensive artist data from Wikipedia/Wikidata.

        Args:
            artist_name: Name of the artist

        Returns:
            Dictionary with comprehensive artist data
        """
        # Start with existing summary method
        page_title = self.search_artist(artist_name)
        if not page_title:
            return {'biography': '', 'wikipedia_url': ''}

        # Get basic summary data
        summary_data = self.get_page_summary(page_title)

        # Try to get structured data from mobile sections
        mobile_data = self.get_mobile_sections(page_title)
        structured_data = {}

        if mobile_data:
            structured_data = self.extract_infobox_data(mobile_data)
        else:
            # Mobile sections failed (403 error), try Action API
            self.logger.info(f"Mobile sections failed, trying Action API for {page_title}")
            action_api_data = self.get_infobox_via_action_api(page_title)
            self.logger.debug(f"Action API data received: {action_api_data}")
            if action_api_data:
                structured_data = action_api_data
                self.logger.debug(f"Using Action API data for structured_data: {structured_data.get('years_active', 'NOT FOUND')}")

        # Try to get Wikidata for more reliable structured data
        wikipedia_url = summary_data.get('wikipedia_url', '')
        if wikipedia_url:
            entity_id = self.get_wikidata_entity(wikipedia_url)
            if entity_id:
                wikidata_structured = self.get_wikidata_claims(entity_id)
                # Merge with preference for Wikidata (more reliable) but keep years_active from Wikipedia if present
                for key, value in wikidata_structured.items():
                    if value:  # Only override if Wikidata has a value
                        # Keep Wikipedia years_active if it exists and looks more complete
                        if key == 'years_active':
                            wiki_years = structured_data.get('years_active', '')
                            # Prefer Wikipedia if it has a range (e.g., "1945-1967" or "1945–1967") over estimated values
                            # Check for both regular hyphen and en-dash
                            if wiki_years and ('-' in wiki_years or '–' in wiki_years):
                                self.logger.debug(f"Keeping Wikipedia years_active: {wiki_years} over Wikidata: {value}")
                                continue
                        structured_data[key] = value

        # Combine all data
        result = summary_data.copy()
        result.update(structured_data)

        return result


class MusicBrainzAPI:
    """Handles MusicBrainz API interactions as fallback for artist data."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'application/json'
        })
        self.logger = logging.getLogger(__name__)

    def search_artist(self, artist_name: str) -> Optional[Dict]:
        """
        Search for artist on MusicBrainz.

        Args:
            artist_name: Name of the artist to search for

        Returns:
            Artist data if found, None otherwise
        """
        try:
            search_url = f"{MUSICBRAINZ_API_BASE}/artist/"
            params = {
                'query': f'name:"{artist_name}"',
                'fmt': 'json',
                'limit': 5
            }

            response = self.session.get(
                search_url,
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            # MusicBrainz rate limiting
            time.sleep(1.0)

            if response.status_code == 200:
                data = response.json()
                artists = data.get('artists', [])

                if artists:
                    # Return best match (highest score)
                    best_match = artists[0]
                    self.logger.info(f"Found MusicBrainz artist: {best_match.get('name')}")
                    return best_match

            self.logger.warning(f"No MusicBrainz artist found for {artist_name}")
            return None

        except Exception as e:
            self.logger.error(f"Error searching MusicBrainz for {artist_name}: {e}")
            return None

    def get_artist_details(self, artist_mbid: str) -> Dict[str, Any]:
        """
        Get detailed artist information from MusicBrainz.

        Args:
            artist_mbid: MusicBrainz artist ID

        Returns:
            Dictionary with artist details
        """
        try:
            details_url = f"{MUSICBRAINZ_API_BASE}/artist/{artist_mbid}"
            params = {
                'inc': 'aliases+annotation+tags+genres',
                'fmt': 'json'
            }

            response = self.session.get(
                details_url,
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            # MusicBrainz rate limiting
            time.sleep(1.0)

            if response.status_code == 200:
                data = response.json()

                result = {
                    'name': data.get('name', ''),
                    'aliases': [alias.get('name') for alias in data.get('aliases', [])],
                    'biography': data.get('annotation', ''),
                    'tags': [tag.get('name') for tag in data.get('tags', [])],
                    'genres': [genre.get('name') for genre in data.get('genres', [])],
                    'begin_date': data.get('life-span', {}).get('begin', ''),
                    'end_date': data.get('life-span', {}).get('end', ''),
                    'area': data.get('area', {}).get('name', ''),
                    'musicbrainz_url': f"https://musicbrainz.org/artist/{artist_mbid}"
                }

                return result

            return {}

        except Exception as e:
            self.logger.error(f"Error getting MusicBrainz details for {artist_mbid}: {e}")
            return {}


class SpotifyArtistCardGenerator:
    """Main class for generating artist cards with Spotify and biography data."""

    def __init__(self, output_dir: str, images_dir: Optional[str] = None):
        self.output_dir = Path(output_dir)
        self.images_dir = Path(images_dir) if images_dir else Path(output_dir).parent.parent.parent / "03_Resources/source_material/ArtistPortraits"

        # Create directories if they don't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

        # Initialize APIs
        self.wikipedia_api = WikipediaAPI()
        self.musicbrainz_api = MusicBrainzAPI()

        # Spotify authentication
        self.access_token = None
        self.token_expires_at = 0
        self.session = requests.Session()

        # Set up logging
        self.setup_logging()

    def setup_logging(self):
        """Configure logging for the application."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('artist_card_generator.log')
            ]
        )
        self.logger = logging.getLogger(__name__)

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
                self.access_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                self.token_expires_at = time.time() + expires_in - 60

                self.logger.info("Successfully authenticated with Spotify API")
                return True
            else:
                self.logger.error(f"Failed to authenticate with Spotify: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"Exception during Spotify authentication: {e}")
            return False

    def ensure_authenticated(self) -> bool:
        """Ensure we have a valid access token."""
        if not self.access_token or time.time() >= self.token_expires_at:
            return self.authenticate_spotify()
        return True

    def search_spotify_artist(self, artist_name: str) -> Optional[Dict]:
        """Search for an artist on Spotify."""
        if not self.ensure_authenticated():
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            query = quote(artist_name)
            url = f"{SPOTIFY_SEARCH_URL}?q={query}&type=artist&limit=10"

            response = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                data = response.json()
                artists = data.get('artists', {}).get('items', [])

                if artists:
                    best_match = artists[0]
                    self.logger.info(f"Found Spotify artist: {best_match['name']} (ID: {best_match['id']})")
                    return best_match

            elif response.status_code == 401:
                self.logger.warning("Access token expired, re-authenticating...")
                if self.authenticate_spotify():
                    return self.search_spotify_artist(artist_name)

            return None

        except Exception as e:
            self.logger.error(f"Error searching Spotify for {artist_name}: {e}")
            return None

    def get_artist_albums(self, artist_id: str) -> List[Dict]:
        """Get artist's albums from Spotify."""
        if not self.ensure_authenticated():
            return []

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            albums = []
            url = f"{SPOTIFY_ARTIST_URL}/{artist_id}/albums"
            params = {
                'include_groups': 'album,single',
                'limit': 50,
                'market': 'US'
            }

            while url:
                response = self.session.get(
                    url,
                    headers=headers,
                    params=params if not albums else {},
                    timeout=REQUEST_TIMEOUT
                )

                if response.status_code == 200:
                    data = response.json()
                    albums.extend(data.get('items', []))
                    url = data.get('next')
                    time.sleep(0.5)  # Rate limiting
                else:
                    break

            return albums

        except Exception as e:
            self.logger.error(f"Error getting albums for artist {artist_id}: {e}")
            return []

    def get_artist_top_tracks(self, artist_id: str) -> List[Dict]:
        """Get artist's top tracks from Spotify."""
        if not self.ensure_authenticated():
            return []

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            url = f"{SPOTIFY_ARTIST_URL}/{artist_id}/top-tracks"
            params = {'market': 'US'}

            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('tracks', [])

            return []

        except Exception as e:
            self.logger.error(f"Error getting top tracks for artist {artist_id}: {e}")
            return []

    def get_related_artists(self, artist_id: str) -> List[Dict]:
        """Get related artists from Spotify."""
        if not self.ensure_authenticated():
            return []

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            url = f"{SPOTIFY_ARTIST_URL}/{artist_id}/related-artists"

            response = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                data = response.json()
                return data.get('artists', [])[:10]  # Limit to 10 related artists

            return []

        except Exception as e:
            self.logger.error(f"Error getting related artists for {artist_id}: {e}")
            return []

    def download_artist_image(self, image_url: str, artist_name: str) -> str:
        """Download artist image and return the relative path."""
        try:
            sanitized_name = self.sanitize_filename(artist_name)

            # Check if image already exists
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                image_path = self.images_dir / f"{sanitized_name}{ext}"
                if image_path.exists():
                    self.logger.info(f"Image already exists: {image_path}")
                    return f"03_Resources/source_material/ArtistPortraits/{sanitized_name}{ext}"

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

        except Exception as e:
            self.logger.error(f"Error downloading image for {artist_name}: {e}")

        return ""

    def sanitize_filename(self, name: str) -> str:
        """Sanitize artist name for use as filename."""
        sanitized = name.replace(' ', '_')
        sanitized = re.sub(r'[<>:"/\\|?*]', '', sanitized)
        sanitized = re.sub(r'[&]', 'and', sanitized)
        sanitized = re.sub(r'[^\w\-_.]', '', sanitized)

        if len(sanitized) > 200:
            sanitized = sanitized[:200]

        return sanitized.strip('.')

    def generate_artist_card(self, artist_name: str) -> bool:
        """
        Generate a comprehensive artist card.

        Args:
            artist_name: Name of the artist

        Returns:
            True if card was successfully generated, False otherwise
        """
        self.logger.info(f"Generating artist card for: {artist_name}")

        # Check if card already exists
        sanitized_name = self.sanitize_filename(artist_name)
        card_path = self.output_dir / f"{sanitized_name}.md"

        if card_path.exists():
            self.logger.info(f"Artist card already exists: {card_path}")
            return True

        # Fetch Spotify data
        spotify_artist = self.search_spotify_artist(artist_name)
        if not spotify_artist:
            self.logger.error(f"Could not find {artist_name} on Spotify")
            return False

        artist_id = spotify_artist['id']

        # Gather all Spotify data
        albums = self.get_artist_albums(artist_id)
        top_tracks = self.get_artist_top_tracks(artist_id)
        related_artists = self.get_related_artists(artist_id)

        # Download artist image
        image_path = ""
        if spotify_artist.get('images'):
            image_url = spotify_artist['images'][0]['url']
            image_path = self.download_artist_image(image_url, spotify_artist['name'])

        # Fetch comprehensive Wikipedia data (biography + structured data)
        wikipedia_data = self.wikipedia_api.get_artist_structured_data(artist_name)
        biography = wikipedia_data.get('biography', '')
        biography_source = "wikipedia" if biography else "none"
        wikipedia_url = wikipedia_data.get('wikipedia_url', '')

        # Extract structured data
        birth_date = wikipedia_data.get('birth_date', '')
        death_date = wikipedia_data.get('death_date', '')
        birth_place = wikipedia_data.get('birth_place', '')
        birth_name = wikipedia_data.get('birth_name', '')
        also_known_as = wikipedia_data.get('also_known_as', [])
        occupation = wikipedia_data.get('occupation', [])
        origin = wikipedia_data.get('origin', '')
        instruments = wikipedia_data.get('instruments', [])
        years_active = wikipedia_data.get('years_active', '')
        associated_acts = wikipedia_data.get('associated_acts', [])
        record_labels = wikipedia_data.get('record_labels', [])
        spouse = wikipedia_data.get('spouse', [])

        # Try MusicBrainz as fallback
        musicbrainz_url = ""
        if not biography:
            mb_artist = self.musicbrainz_api.search_artist(artist_name)
            if mb_artist:
                mb_details = self.musicbrainz_api.get_artist_details(mb_artist['id'])
                if mb_details.get('biography'):
                    biography = mb_details['biography']
                    biography_source = "musicbrainz"
                    musicbrainz_url = mb_details.get('musicbrainz_url', '')

        # Build the artist card
        card_content = self.build_artist_card(
            spotify_artist=spotify_artist,
            albums=albums,
            top_tracks=top_tracks,
            related_artists=related_artists,
            biography=biography,
            biography_source=biography_source,
            wikipedia_url=wikipedia_url,
            musicbrainz_url=musicbrainz_url,
            image_path=image_path,
            birth_date=birth_date,
            death_date=death_date,
            birth_place=birth_place,
            birth_name=birth_name,
            also_known_as=also_known_as,
            occupation=occupation,
            origin=origin,
            instruments=instruments,
            years_active=years_active,
            associated_acts=associated_acts,
            record_labels=record_labels,
            spouse=spouse
        )

        # Save the card
        with open(card_path, 'w', encoding='utf-8') as f:
            f.write(card_content)

        self.logger.info(f"Successfully generated artist card: {card_path}")
        return True

    def build_artist_card(self, **kwargs) -> str:
        """Build the markdown content for the artist card."""
        artist = kwargs['spotify_artist']
        albums = kwargs['albums']
        top_tracks = kwargs['top_tracks']
        related_artists = kwargs['related_artists']
        biography = kwargs['biography']
        biography_source = kwargs['biography_source']
        wikipedia_url = kwargs['wikipedia_url']
        musicbrainz_url = kwargs['musicbrainz_url']
        image_path = kwargs['image_path']

        # New structured data fields
        birth_date = kwargs.get('birth_date', '')
        death_date = kwargs.get('death_date', '')
        birth_place = kwargs.get('birth_place', '')
        birth_name = kwargs.get('birth_name', '')
        also_known_as = kwargs.get('also_known_as', [])
        occupation = kwargs.get('occupation', [])
        origin = kwargs.get('origin', '')
        instruments = kwargs.get('instruments', [])
        years_active = kwargs.get('years_active', '')
        associated_acts = kwargs.get('associated_acts', [])
        record_labels = kwargs.get('record_labels', [])
        spouse = kwargs.get('spouse', [])

        # Prepare data for template
        name = artist['name']
        genres = artist.get('genres', [])
        popularity = artist.get('popularity', 0)
        followers = artist.get('followers', {}).get('total', 0)
        spotify_url = artist.get('external_urls', {}).get('spotify', '')

        # Separate albums and singles
        album_list = [a for a in albums if a.get('album_type') == 'album']
        single_list = [a for a in albums if a.get('album_type') == 'single']

        # Format top tracks
        top_track_names = []
        for track in top_tracks[:10]:
            track_name = track.get('name', '')
            album_name = track.get('album', {}).get('name', '')
            top_track_names.append(f"{track_name} ({album_name})")

        # Format related artists
        related_artist_names = [a.get('name', '') for a in related_artists[:10]]

        # Determine status based on whether artist is deceased
        status = "deceased" if death_date else "active"

        # Build YAML frontmatter
        frontmatter = f"""---
title: {name}
aliases: {json.dumps(also_known_as) if also_known_as else '[]'}
status: {status}
genres: {json.dumps(genres[:10]) if genres else '[]'}
spotify_data:
  id: {artist['id']}
  url: {spotify_url}
  popularity: {popularity}
  followers: {followers}
  verified: false
albums_count: {len(album_list)}
singles_count: {len(single_list)}
top_tracks: {json.dumps(top_track_names[:5]) if top_track_names else '[]'}
related_artists: {json.dumps(related_artist_names[:5]) if related_artist_names else '[]'}
biography_source: {biography_source}"""

        # Add structured data fields if available
        if birth_date:
            frontmatter += f"\nbirth_date: \"{birth_date}\""
        if death_date:
            frontmatter += f"\ndeath_date: \"{death_date}\""
        if birth_place:
            frontmatter += f"\nbirth_place: \"{birth_place}\""
        if birth_name:
            frontmatter += f"\nbirth_name: \"{birth_name}\""
        if also_known_as:
            frontmatter += f"\nalso_known_as: {json.dumps(also_known_as[:5])}"
        if occupation:
            frontmatter += f"\noccupation: {json.dumps(occupation[:5])}"
        if origin:
            frontmatter += f"\norigin: \"{origin}\""
        if instruments:
            frontmatter += f"\ninstruments: {json.dumps(instruments)}"
        if years_active:
            frontmatter += f"\nyears_active: \"{years_active}\""
        if associated_acts:
            frontmatter += f"\nassociated_acts: {json.dumps(associated_acts[:10])}"
        if record_labels:
            frontmatter += f"\nrecord_labels: {json.dumps(record_labels[:10])}"
        if spouse:
            frontmatter += f"\nspouse: {json.dumps(spouse[:5])}"

        frontmatter += f"""
external_urls:
  spotify: {spotify_url}
  wikipedia: {wikipedia_url}
  musicbrainz: {musicbrainz_url}
image_path: {image_path}
entry_created: {datetime.now().isoformat()}
last_updated: {datetime.now().isoformat()}
---

"""

        # Build markdown content
        content = f"""![]({image_path.split('/')[-1] if image_path else ''})

# {name}

## Quick Info
- **Genres**: {', '.join(genres[:5]) if genres else 'Not specified'}"""

        # Add structured data to Quick Info if available
        if birth_name:
            content += f"\n- **Birth Name**: {birth_name}"
        if also_known_as:
            content += f"\n- **Also Known As**: {', '.join(also_known_as[:3])}"
        if birth_date:
            content += f"\n- **Born**: {birth_date}"
            if birth_place:
                content += f" in {birth_place}"
        if death_date:
            content += f"\n- **Died**: {death_date}"
        if origin and origin != birth_place:
            content += f"\n- **Origin**: {origin}"
        if occupation:
            content += f"\n- **Occupation**: {', '.join(occupation[:3])}"
        if instruments:
            content += f"\n- **Instruments**: {', '.join(instruments[:5])}"
        if years_active:
            content += f"\n- **Years Active**: {years_active}"
        if record_labels:
            content += f"\n- **Record Labels**: {', '.join(record_labels[:5])}"
        if spouse:
            content += f"\n- **Spouse**: {', '.join(spouse[:2])}"
        if associated_acts:
            content += f"\n- **Associated Acts**: {', '.join(associated_acts[:5])}"

        content += f"""
- **Spotify Popularity**: {popularity}/100
- **Followers**: {followers:,}

## Biography
{biography if biography else 'No biography available.'}

"""

        if biography_source == 'wikipedia' and wikipedia_url:
            content += f"*Source: [Wikipedia]({wikipedia_url})*\n\n"
        elif biography_source == 'musicbrainz' and musicbrainz_url:
            content += f"*Source: [MusicBrainz]({musicbrainz_url})*\n\n"

        # Add discography
        if album_list or single_list:
            content += "## Discography\n\n"

            if album_list:
                content += "### Albums\n"
                content += "| Title | Release Date | Type |\n"
                content += "|-------|--------------|------|\n"

                for album in album_list[:20]:  # Limit to 20 albums
                    title = album.get('name', 'Unknown')
                    date = album.get('release_date', 'Unknown')
                    album_type = album.get('album_type', 'album').title()
                    content += f"| {title} | {date} | {album_type} |\n"

                content += "\n"

        # Add top tracks
        if top_tracks:
            content += "### Top Tracks\n"
            for i, track in enumerate(top_tracks[:10], 1):
                track_name = track.get('name', '')
                album_name = track.get('album', {}).get('name', '')
                content += f"{i}. {track_name} ({album_name})\n"
            content += "\n"

        # Add related artists
        if related_artists:
            content += "## Related Artists\n"
            for artist in related_artists[:10]:
                artist_name = artist.get('name', '')
                content += f"- [[{artist_name}]]\n"
            content += "\n"

        # Add external links
        content += "## External Links\n"
        if spotify_url:
            content += f"- [Spotify]({spotify_url})\n"
        if wikipedia_url:
            content += f"- [Wikipedia]({wikipedia_url})\n"
        if musicbrainz_url:
            content += f"- [MusicBrainz]({musicbrainz_url})\n"

        return frontmatter + content

    def process_daily_archive(self, input_file: str) -> Dict[str, int]:
        """Process a daily archive file and generate artist cards."""
        self.logger.info(f"Processing daily archive: {input_file}")

        # Parse the markdown file to get artists
        artists = self.parse_daily_archive(input_file)
        if not artists:
            self.logger.error("No artists found in the daily archive file")
            return {"total": 0, "success": 0, "failed": 0}

        # Authenticate with Spotify
        if not self.authenticate_spotify():
            self.logger.error("Failed to authenticate with Spotify")
            return {"total": len(artists), "success": 0, "failed": len(artists)}

        # Generate cards for each artist
        stats = {"total": len(artists), "success": 0, "failed": 0}

        for i, artist in enumerate(artists, 1):
            self.logger.info(f"Processing artist {i}/{len(artists)}: {artist}")

            success = self.generate_artist_card(artist)
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1

            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)

        self.logger.info(f"Processing complete. Total: {stats['total']}, "
                        f"Success: {stats['success']}, Failed: {stats['failed']}")

        return stats

    def parse_daily_archive(self, file_path: str) -> List[str]:
        """Parse the Obsidian daily archive markdown file and extract artists."""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            lines = content.split('\n')
            found_artists = []

            for line in lines:
                line = line.strip()

                if not line:
                    continue

                if line.startswith('|') and '|' in line[1:]:
                    columns = [col.strip() for col in line.split('|')]

                    if len(columns) >= 9 and columns[1] not in ['Time', ':----', '']:
                        artist = columns[2].strip()
                        status = columns[8].strip()

                        if status == "✅ Found" and artist:
                            found_artists.append(artist)
                            self.logger.debug(f"Found artist: {artist}")

            self.logger.info(f"Parsed {len(found_artists)} artists from {file_path}")
            return found_artists

        except Exception as e:
            self.logger.error(f"Failed to parse daily archive file {file_path}: {e}")
            return []


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Generate comprehensive artist cards for Obsidian vault"
    )

    # Mutually exclusive group for input mode
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--artist",
        help="Single artist name to generate card for"
    )
    input_group.add_argument(
        "--input-file",
        help="Path to daily archive markdown file with multiple artists"
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to save generated artist cards"
    )
    parser.add_argument(
        "--images-dir",
        help="Directory to save artist images (default: relative to output-dir)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )

    args = parser.parse_args()

    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Create generator
    generator = SpotifyArtistCardGenerator(args.output_dir, args.images_dir)

    # Process based on input mode
    if args.artist:
        # Single artist mode
        success = generator.generate_artist_card(args.artist)
        if success:
            print(f"✅ Successfully generated artist card for: {args.artist}")
        else:
            print(f"❌ Failed to generate artist card for: {args.artist}")
            sys.exit(1)

    else:
        # Batch mode from file
        if not os.path.exists(args.input_file):
            print(f"Error: Input file does not exist: {args.input_file}")
            sys.exit(1)

        stats = generator.process_daily_archive(args.input_file)

        print(f"\nProcessing Summary:")
        print(f"Total artists: {stats['total']}")
        print(f"Successfully generated: {stats['success']}")
        print(f"Failed: {stats['failed']}")


if __name__ == "__main__":
    main()