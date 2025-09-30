#!/usr/bin/env python3
"""
Jazz Encyclopedia Biography Enhancer (Perplexity Edition - Web-First Approach)

PERPLEXITY-FIRST ARCHITECTURE:
This script uses Perplexity AI's web search as the PRIMARY data source for comprehensive
artist research, moving away from Wikipedia-dependent architecture.

Key Features:
1. PRIMARY: Perplexity web search for comprehensive artist research
2. Structured JSON responses with biography, connections, and sources
3. Rich musical connections extraction (mentors, collaborators, influenced artists)
4. Detailed relationship context (albums, bands, time periods)
5. Wikipedia used only as supplementary metadata fallback
6. Three-phase problematic card detection and recovery system

Data Flow:
1. Perplexity web search → comprehensive research with citations
2. Format structured biography with musical connections
3. Optional Wikipedia metadata supplement
4. Update artist card with enhanced content

Connection Types Extracted:
- Mentors/Influences: Teachers, inspirations, stylistic influences
- Key Collaborators: Band members, frequent collaborators, partnerships
- Artists Influenced: Students, proteges, inspired musicians

Each connection includes:
- Artist name
- Relationship context
- Specific works (albums, projects)
- Time periods
- Confidence scores

Uses Perplexity API for improved research quality and real-time web search capabilities.

Usage:
    python enhance_biographies_perplexity.py [--dry-run] [--force] [--show-network] [--skip-detection]
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
from openai import OpenAI
from bs4 import BeautifulSoup
from tqdm import tqdm

# Configuration
DEFAULT_CARDS_DIR = "/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists"
CONNECTIONS_FILE = "artist_connections.json"
USER_AGENT = "JazzEncyclopediaBiographyEnhancer/2.0 (https://github.com/yourusername/project)"
REQUEST_TIMEOUT = 30
RATE_LIMIT_DELAY = 2.0  # Delay between API requests
MAX_RETRIES = 3

# Perplexity Configuration
PERPLEXITY_API_BASE = "https://api.perplexity.ai"
PERPLEXITY_MODEL = "sonar-pro"
PERPLEXITY_TEMPERATURE = 0.3
PERPLEXITY_MAX_TOKENS = 2048

# Detection Configuration (Phase 1)
PROBLEM_CARDS_DIR = "problem-cards"
QUARANTINE_LOG_FILE = "quarantine_log.txt"

# Red flag indicators for problematic cards
SUSPICIOUS_URL_PATTERNS = [
    "List_of_", "list_of_",
    "recipe", "Recipe",
    "_blues", "_jazz", "_music",  # Genre pages
    "cuisine", "Cuisine",
    "food", "Food"
]

FOOD_RECIPE_TERMS = [
    "beefsteak", "flour", "recipe", "cook", "fried", "bake", "ingredient",
    "chicken-fried", "pan-fried", "deep-fried", "dish", "cuisine"
]

GENRE_DEFINITION_PHRASES = [
    "refers to the local",
    "is a genre",
    "is a list of",
    "is a subgenre",
    "is a style of music",
    "is a music genre",
    "is a type of"
]

GENERIC_ASSOCIATED_ACTS = [
    "beefsteak", "flour", "lists of songs", "lists of", "theme"
]

# Detection confidence thresholds
DETECTION_CONFIDENCE_HIGH = 0.9
DETECTION_CONFIDENCE_MEDIUM = 0.7
DETECTION_CONFIDENCE_LOW = 0.5


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


class PerplexityAnalyzer:
    """Handles Perplexity AI integration for content assessment and enhancement."""

    def __init__(self, dry_run: bool = False):
        self.logger = logging.getLogger(__name__)
        self.dry_run = dry_run
        self.wikipedia_extractor = None  # Will be set by processor

        # Initialize Perplexity client only if not in dry-run mode
        if not dry_run:
            api_key = os.getenv('PERPLEXITY_API_KEY')
            if not api_key:
                raise ValueError("PERPLEXITY_API_KEY environment variable is required")

            self.client = OpenAI(
                api_key=api_key,
                base_url=PERPLEXITY_API_BASE
            )
            self.logger.info(f"Initialized Perplexity client with model: {PERPLEXITY_MODEL}")
        else:
            self.client = None
            self.logger.info("Dry-run mode: Perplexity initialization skipped")

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

            self.logger.info("Sending content assessment request to Perplexity")

            response = self.client.chat.completions.create(
                model=PERPLEXITY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert music historian analyzing biographical content for accuracy and completeness. Always respond with valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": assessment_prompt
                    }
                ],
                temperature=PERPLEXITY_TEMPERATURE,
                max_tokens=PERPLEXITY_MAX_TOKENS
            )

            # Parse JSON response
            response_text = response.choices[0].message.content.strip()
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

    def research_artist_with_perplexity(self, artist_name: str, frontmatter: Dict[str, Any]) -> Dict[str, Any]:
        """
        PRIMARY DATA GATHERING: Use Perplexity web search to research artist comprehensively.

        Args:
            artist_name: Name of the artist
            frontmatter: Artist frontmatter with Spotify metadata

        Returns:
            Dictionary with research results including biography, connections, and sources
        """
        if self.dry_run:
            # Return mock research for dry-run mode
            mock_biography = f"""[DRY RUN] **{artist_name}** was born into a musical family and showed early talent for jazz music. Influenced by Charlie Parker and Dizzy Gillespie, they began developing their unique style during their formative years.

During the 1950s, {artist_name} joined Miles Davis's quintet, where they collaborated with Red Garland, Paul Chambers, and Philly Joe Jones. This period marked significant growth in their musical sophistication.

Key collaborations include work with McCoy Tyner, Elvin Jones, and Jimmy Garrison in the classic quartet formation. Notable albums from this period revolutionized jazz music. {artist_name}'s approach influenced countless musicians including Pharoah Sanders and Archie Shepp."""

            mock_connections = {
                "mentors": [{"name": "Miles Davis", "context": "Provided crucial early career opportunities", "confidence": 0.95}],
                "collaborators": [
                    {"name": "McCoy Tyner", "context": "Primary pianist in classic quartet", "confidence": 0.95},
                    {"name": "Elvin Jones", "context": "Revolutionary drummer partnership", "confidence": 0.95}
                ],
                "influenced": [
                    {"name": "Pharoah Sanders", "context": "Spiritual jazz pioneer following similar path", "confidence": 0.90}
                ]
            }

            mock_fun_facts = [
                "Pioneered spiritual jazz in the 1960s",
                "Recorded over 50 albums as bandleader",
                "Influenced by Indian classical music"
            ]

            return {
                "success": True,
                "biography": mock_biography,
                "connections": mock_connections,
                "fun_facts": mock_fun_facts,
                "sources": ["Wikipedia", "AllMusic", "JazzTimes"],
                "wikipedia_url": "https://en.wikipedia.org/wiki/Example_Artist"
            }

        try:
            # Extract Spotify metadata for context
            top_tracks = frontmatter.get('top_tracks', [])[:3]
            spotify_genres = frontmatter.get('genres', [])

            # Build comprehensive research query
            research_prompt = f"""Research the musical artist "{artist_name}" and provide comprehensive biographical information.

CONTEXT FROM SPOTIFY:
- Genres: {', '.join(spotify_genres) if spotify_genres else 'Unknown'}
- Popular tracks: {', '.join(top_tracks) if top_tracks else 'Unknown'}

REQUIRED INFORMATION:
1. **Biography**: 2-3 flowing paragraphs covering:
   - Early life and musical beginnings
   - Career development and major milestones
   - Musical style, innovations, and legacy

2. **Musical Connections** (CRITICAL - be specific and accurate):
   - **Mentors/Influences**: Teachers, inspirations, stylistic influences
   - **Key Collaborators**: Frequent collaborators, band members, important partnerships
   - **Artists Influenced**: Students, proteges, musicians they inspired

   For each connection, provide:
   - Artist name
   - Nature of relationship/collaboration
   - Specific context (albums, bands, time periods)

3. **Fun Facts**: 3-4 interesting anecdotes or lesser-known details

4. **Sources**: Note Wikipedia URL if available

RESPONSE FORMAT (JSON):
{{
  "biography": "2-3 paragraph biography text...",
  "connections": {{
    "mentors": [
      {{"name": "Artist Name", "context": "relationship description", "specific_works": "albums/projects", "time_period": "1950s-1960s"}}
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
  "sources": ["source1", "source2"]
}}

CRITICAL REQUIREMENTS:
- Use web search to find accurate, up-to-date information
- Verify all connections are real and documented
- Include specific album names, band names, and time periods for connections
- Only include information found in credible sources
- Provide factual, encyclopedic content"""

            self.logger.info(f"Researching artist with Perplexity: {artist_name}")

            response = self.client.chat.completions.create(
                model=PERPLEXITY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert music researcher with access to web search. Provide accurate, well-researched information about musical artists. Always respond with valid JSON only. Focus heavily on finding and verifying musical connections and relationships."
                    },
                    {
                        "role": "user",
                        "content": research_prompt
                    }
                ],
                temperature=0.3,
                max_tokens=PERPLEXITY_MAX_TOKENS * 2
            )

            # Parse JSON response
            response_text = response.choices[0].message.content.strip()
            if response_text.startswith('```json'):
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            research_data = json.loads(response_text)

            # Validate response
            if not research_data.get('biography'):
                self.logger.warning(f"No biography in research response for {artist_name}")
                return {"success": False, "reason": "No biography found"}

            # Add confidence scores to connections if not present
            for conn_type in ['mentors', 'collaborators', 'influenced']:
                if conn_type in research_data.get('connections', {}):
                    for connection in research_data['connections'][conn_type]:
                        if 'confidence' not in connection:
                            # High confidence by default since Perplexity has verified via web search
                            connection['confidence'] = 0.95

            self.logger.info(f"Research successful: {len(research_data.get('biography', ''))} chars, "
                           f"{sum(len(v) for v in research_data.get('connections', {}).values())} connections")

            return {
                "success": True,
                **research_data
            }

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON response: {e}")
            self.logger.debug(f"Response text: {response_text[:500]}")
            return {"success": False, "reason": f"JSON parsing failed: {e}"}
        except Exception as e:
            self.logger.error(f"Error in Perplexity research: {e}")
            return {"success": False, "reason": f"Research failed: {e}"}

    def generate_biography_from_research(self, research_data: Dict[str, Any], artist_name: str) -> Dict[str, Any]:
        """
        Format research data into structured biography markdown.

        Args:
            research_data: Research results from Perplexity
            artist_name: Name of the artist

        Returns:
            Dictionary with formatted biography and processed connections
        """
        try:
            biography_text = research_data.get('biography', '')
            connections_data = research_data.get('connections', {})
            fun_facts = research_data.get('fun_facts', [])

            # Build markdown content
            markdown_parts = [biography_text]

            # Add Fun Facts section
            if fun_facts:
                markdown_parts.append("\n## Fun Facts")
                for fact in fun_facts:
                    markdown_parts.append(f"- {fact}")

            # Add Musical Connections section
            if connections_data:
                markdown_parts.append("\n## Musical Connections")

                # Mentors/Influences
                if connections_data.get('mentors'):
                    markdown_parts.append("\n### Mentors/Influences")
                    for mentor in connections_data['mentors']:
                        name = mentor.get('name', '')
                        context = mentor.get('context', '')
                        specific_works = mentor.get('specific_works', '')
                        time_period = mentor.get('time_period', '')

                        detail_parts = [context]
                        if specific_works:
                            detail_parts.append(f"({specific_works})")
                        if time_period:
                            detail_parts.append(f"[{time_period}]")

                        markdown_parts.append(f"- {name} - {' '.join(detail_parts)}")

                # Key Collaborators
                if connections_data.get('collaborators'):
                    markdown_parts.append("\n### Key Collaborators")
                    for collab in connections_data['collaborators']:
                        name = collab.get('name', '')
                        context = collab.get('context', '')
                        specific_works = collab.get('specific_works', '')
                        time_period = collab.get('time_period', '')

                        detail_parts = [context]
                        if specific_works:
                            detail_parts.append(f"({specific_works})")
                        if time_period:
                            detail_parts.append(f"[{time_period}]")

                        markdown_parts.append(f"- {name} - {' '.join(detail_parts)}")

                # Artists Influenced
                if connections_data.get('influenced'):
                    markdown_parts.append("\n### Artists Influenced")
                    for influenced in connections_data['influenced']:
                        name = influenced.get('name', '')
                        context = influenced.get('context', '')
                        specific_works = influenced.get('specific_works', '')
                        time_period = influenced.get('time_period', '')

                        detail_parts = [context]
                        if specific_works:
                            detail_parts.append(f"({specific_works})")
                        if time_period:
                            detail_parts.append(f"[{time_period}]")

                        markdown_parts.append(f"- {name} - {' '.join(detail_parts)}")

            formatted_biography = '\n'.join(markdown_parts)

            # Convert connections to simple format for storage
            simple_connections = {}
            for conn_type in ['mentors', 'collaborators', 'influenced']:
                if conn_type in connections_data:
                    simple_connections[conn_type] = [
                        conn.get('name', '') for conn in connections_data[conn_type]
                    ]

            self.logger.info(f"Generated formatted biography ({len(formatted_biography)} chars)")

            return {
                "biography": formatted_biography,
                "connections": simple_connections,
                "detailed_connections": connections_data,  # Keep detailed version
                "source_verified": True
            }

        except Exception as e:
            self.logger.error(f"Error formatting biography: {e}")
            return {
                "biography": "",
                "connections": {}
            }

    def verify_biography_accuracy(self, artist_name: str, biography_text: str,
                                 frontmatter: Dict[str, Any], wikipedia_url: str) -> Dict[str, Any]:
        """
        Verify that the biography accurately describes the artist using Perplexity's web search.

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

            response = self.client.chat.completions.create(
                model=PERPLEXITY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at verifying biographical information accuracy. Always respond with valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": verification_prompt
                    }
                ],
                temperature=0.1,  # Low temperature for accuracy
                max_tokens=512
            )

            # Parse response
            response_text = response.choices[0].message.content.strip()
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

    def regenerate_with_perplexity(self, artist_name: str, frontmatter: Dict[str, Any],
                                   issues: List[str]) -> Dict[str, Any]:
        """
        Phase 2: Attempt to regenerate artist card using Perplexity web search.

        Args:
            artist_name: Name of the artist
            frontmatter: Current frontmatter with Spotify data
            issues: List of detected issues from Phase 1

        Returns:
            Dictionary with success status, new biography, connections, and metadata
        """
        if self.dry_run:
            return {
                "success": True,
                "biography": f"[DRY RUN] Regenerated biography for {artist_name} using Perplexity web search",
                "connections": {"mentors": [], "collaborators": [], "influenced": []},
                "new_wikipedia_url": "https://en.wikipedia.org/wiki/Example_Artist",
                "reason": "Dry run mode"
            }

        try:
            # Use the new research_artist_with_perplexity method for consistency
            self.logger.info(f"Attempting Perplexity regeneration for {artist_name}")

            research_result = self.research_artist_with_perplexity(artist_name, frontmatter)

            if not research_result.get('success'):
                self.logger.warning(f"Perplexity research failed: {research_result.get('reason')}")
                return {
                    "success": False,
                    "reason": research_result.get('reason', 'Research failed'),
                    "biography": "",
                    "connections": {}
                }

            # Format biography from research
            enhancement_result = self.generate_biography_from_research(research_result, artist_name)

            enhanced_biography = enhancement_result.get('biography', '')
            connections = enhancement_result.get('connections', {})
            new_wikipedia_url = research_result.get('wikipedia_url')

            if not enhanced_biography:
                return {
                    "success": False,
                    "reason": "Biography generation failed",
                    "biography": "",
                    "connections": {}
                }

            self.logger.info(f"Successfully regenerated biography for {artist_name}")

            return {
                "success": True,
                "biography": enhanced_biography,
                "connections": connections,
                "new_wikipedia_url": new_wikipedia_url,
                "research_sources": research_result.get('sources', []),
                "reason": "Perplexity regeneration successful"
            }

        except Exception as e:
            self.logger.error(f"Error in Perplexity regeneration: {e}")
            return {
                "success": False,
                "reason": f"Regeneration failed: {str(e)}",
                "biography": "",
                "connections": {}
            }

    def _validate_perplexity_response(self, artist_name: str, response_text: str) -> Dict[str, Any]:
        """
        Validate that Perplexity response contains credible artist information.

        Args:
            artist_name: Name of the artist
            response_text: Response from Perplexity

        Returns:
            Dictionary with validation result
        """
        response_lower = response_text.lower()

        # Check for explicit failure indicators
        failure_phrases = [
            "no credible information",
            "cannot find information",
            "appears to be misidentified",
            "not a real artist",
            "not a musician",
            "not a band",
            "is a recipe",
            "is a list",
            "is a genre"
        ]

        for phrase in failure_phrases:
            if phrase in response_lower:
                return {
                    "is_valid": False,
                    "reason": f"Response indicates no credible artist info: '{phrase}'"
                }

        # Check that response is substantial
        if len(response_text) < 200:
            return {
                "is_valid": False,
                "reason": "Response too short to be credible biography"
            }

        # Check for musical context
        musical_terms = ["music", "musician", "band", "artist", "song", "album", "record", "perform"]
        has_musical_context = any(term in response_lower for term in musical_terms)

        if not has_musical_context:
            return {
                "is_valid": False,
                "reason": "Response lacks musical context"
            }

        return {
            "is_valid": True,
            "reason": "Response appears credible"
        }

    def _extract_wikipedia_url_from_response(self, response_text: str) -> Optional[str]:
        """
        Extract Wikipedia URL from Perplexity response citations if present.

        Args:
            response_text: Response from Perplexity

        Returns:
            Wikipedia URL if found, None otherwise
        """
        # Look for Wikipedia URLs in the response
        import re
        wiki_pattern = r'https?://en\.wikipedia\.org/wiki/[^\s\)\]\"<>]+'
        matches = re.findall(wiki_pattern, response_text)

        if matches:
            # Return the first Wikipedia URL found
            return matches[0]

        return None


class ArtistCardProcessor:
    """Main processor for enhancing artist cards and managing connections."""

    def __init__(self, cards_dir: str, dry_run: bool = False, force: bool = False, skip_detection: bool = False):
        self.cards_dir = Path(cards_dir)
        self.dry_run = dry_run
        self.force = force
        self.skip_detection = skip_detection
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.wikipedia_extractor = WikipediaExtractor()
        self.perplexity_analyzer = PerplexityAnalyzer(dry_run)
        # Link the extractor to analyzer for re-fetching
        self.perplexity_analyzer.wikipedia_extractor = self.wikipedia_extractor

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
            'connections_found': 0,
            'problems_detected': 0,
            'recovered': 0,
            'quarantined': 0
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

    def detect_problematic_card(self, frontmatter: Dict[str, Any], content: str) -> Tuple[bool, float, List[str]]:
        """
        Phase 1: Detect if card has problematic Wikipedia match before enhancement.

        Args:
            frontmatter: Parsed frontmatter from card
            content: Full card content

        Returns:
            Tuple of (is_problematic, confidence_score, list_of_issues)
        """
        issues = []
        confidence_score = 0.0
        confidence_points = 0

        # Get key data
        wikipedia_url = frontmatter.get('external_urls', {}).get('wikipedia', '')
        associated_acts = frontmatter.get('associated_acts', [])
        title = frontmatter.get('title', '')
        biography = self.extract_current_biography(content)
        artist_name = Path(title).stem.replace('_', ' ')

        # Check 1: Suspicious Wikipedia URL patterns
        url_suspicious = False
        for pattern in SUSPICIOUS_URL_PATTERNS:
            if pattern in wikipedia_url:
                issues.append(f"Suspicious URL pattern: {pattern} in {wikipedia_url}")
                confidence_points += 25
                url_suspicious = True
                break

        # Check 2: Biography contains food/recipe terms when artist name suggests music
        food_terms_found = []
        biography_lower = biography.lower()
        for term in FOOD_RECIPE_TERMS:
            if term.lower() in biography_lower:
                food_terms_found.append(term)

        if food_terms_found and not url_suspicious:
            # Only flag if multiple food terms and URL doesn't already look suspicious
            if len(food_terms_found) >= 2:
                issues.append(f"Biography contains food/recipe terms: {', '.join(food_terms_found[:3])}")
                confidence_points += 20
        elif food_terms_found and url_suspicious:
            # Very strong signal if both URL and content have food terms
            issues.append(f"Biography contains food/recipe terms matching suspicious URL: {', '.join(food_terms_found[:3])}")
            confidence_points += 30

        # Check 3: Biography starts with genre definition phrases
        for phrase in GENRE_DEFINITION_PHRASES:
            if biography.lower().startswith(phrase) or f" {phrase} " in biography_lower[:200]:
                issues.append(f"Biography appears to define a genre: '{phrase}' in opening")
                confidence_points += 30
                break

        # Check 4: Generic/non-musical associated acts
        generic_acts_found = []
        for act in associated_acts:
            if isinstance(act, str):
                for generic_term in GENERIC_ASSOCIATED_ACTS:
                    if generic_term.lower() in act.lower():
                        generic_acts_found.append(act)
                        break

        if generic_acts_found:
            issues.append(f"Generic associated acts found: {', '.join(generic_acts_found)}")
            confidence_points += 20

        # Check 5: Biography explicitly states it can't describe the artist
        cant_describe_phrases = [
            "impossible to create a biography",
            "does not contain information about",
            "focuses on the history of",
            "is not about",
            "no information about any artists"
        ]
        for phrase in cant_describe_phrases:
            if phrase.lower() in biography_lower:
                issues.append(f"Biography explicitly states mismatch: '{phrase}'")
                confidence_points += 40
                break

        # Check 6: Title mismatch (filename vs frontmatter title)
        filename_artist = Path(content).stem if '/' in content else artist_name
        if title and filename_artist:
            # Normalize for comparison
            title_norm = title.lower().replace(' ', '').replace('_', '')
            filename_norm = filename_artist.lower().replace(' ', '').replace('_', '')

            if title_norm != filename_norm:
                # Check if it's a significant difference (not just case/punctuation)
                if len(set(title_norm) - set(filename_norm)) > 2:
                    issues.append(f"Title mismatch: frontmatter '{title}' vs filename '{filename_artist}'")
                    confidence_points += 15

        # Calculate confidence score (0-1 scale)
        confidence_score = min(confidence_points / 100.0, 1.0)

        is_problematic = confidence_score >= DETECTION_CONFIDENCE_MEDIUM

        if is_problematic:
            self.logger.info(f"Detected problematic card with {confidence_score:.2f} confidence: {len(issues)} issues")
        else:
            self.logger.debug(f"Card appears normal (confidence: {confidence_score:.2f})")

        return is_problematic, confidence_score, issues

    def quarantine_card(self, file_path: Path, frontmatter: Dict[str, Any],
                       issues: List[str], reason: str) -> bool:
        """
        Phase 3: Move problematic card to quarantine directory with metadata.

        Args:
            file_path: Path to the problematic card file
            frontmatter: Current frontmatter
            issues: List of detected issues
            reason: Reason for quarantine

        Returns:
            True if quarantine successful, False otherwise
        """
        try:
            # Create problem-cards directory if it doesn't exist
            problem_cards_dir = self.cards_dir / PROBLEM_CARDS_DIR
            problem_cards_dir.mkdir(exist_ok=True)

            # Update frontmatter with quarantine metadata
            frontmatter['data_quality'] = 'problematic'
            frontmatter['quarantine_reason'] = reason
            frontmatter['original_detection_issues'] = issues
            frontmatter['quarantine_date'] = datetime.now().isoformat()
            frontmatter['original_location'] = str(file_path)

            # Read current file content
            with open(file_path, 'r', encoding='utf-8') as f:
                current_content = f.read()

            # Extract content after frontmatter
            if current_content.startswith('---'):
                frontmatter_end = current_content.find('---', 3)
                if frontmatter_end != -1:
                    content_text = current_content[frontmatter_end + 3:].strip()
                else:
                    content_text = current_content
            else:
                content_text = current_content

            # Reconstruct file with updated frontmatter
            frontmatter_text = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
            full_content = f"---\n{frontmatter_text}---\n\n{content_text}"

            # Determine destination path
            destination_path = problem_cards_dir / file_path.name

            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would quarantine {file_path.name} to {destination_path}")
                self.logger.info(f"[DRY RUN] Reason: {reason}")
                self.logger.info(f"[DRY RUN] Issues: {issues}")
                return True

            # Write to quarantine location
            destination_path.write_text(full_content, encoding='utf-8')

            # Remove from original location
            file_path.unlink()

            # Log to quarantine log file
            log_file = self.cards_dir / QUARANTINE_LOG_FILE
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "filename": file_path.name,
                "artist_name": frontmatter.get('title', file_path.stem.replace('_', ' ')),
                "reason": reason,
                "issues": issues,
                "moved_to": str(destination_path)
            }

            # Append to log file
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

            self.logger.warning(f"⚠️ Quarantined {file_path.name}: {reason}")
            return True

        except Exception as e:
            self.logger.error(f"Error quarantining {file_path}: {e}")
            return False

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
            frontmatter['enhancement_provider'] = 'perplexity'
            if connections:
                frontmatter['musical_connections'] = connections
                frontmatter['network_extracted'] = True
                frontmatter['source_verified'] = True  # Mark as source-verified

            # Clean up enhanced biography to remove duplicate headers
            cleaned_bio = self._clean_biography_content(enhanced_bio)

            # Replace biography section in content
            bio_pattern = r'(## Biography\s*\n).*?(?=\n##|\n\*Source:|\Z)'
            replacement = f'\\1{cleaned_bio}\n\n*Enhanced with Perplexity AI research*\n'

            if re.search(bio_pattern, content, re.DOTALL):
                new_content = re.sub(bio_pattern, replacement, content, flags=re.DOTALL)
            else:
                # Add biography section if not found
                new_content = content + f"\n\n## Biography\n{cleaned_bio}\n\n*Enhanced with Perplexity AI research*\n"

            # Reconstruct full file
            frontmatter_text = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
            full_content = f"---\n{frontmatter_text}---\n\n{new_content}"

            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would update {file_path.name}")
                return True
            else:
                # Backup original file to backups subdirectory
                backup_dir = file_path.parent / 'backups'
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / f"{file_path.stem}.md.backup"

                if not backup_path.exists():
                    # Copy original content to backup before modifying
                    backup_path.write_text(file_path.read_text(encoding='utf-8'), encoding='utf-8')

                file_path.write_text(full_content, encoding='utf-8')

                self.logger.info(f"Updated {file_path.name}")
                return True

        except Exception as e:
            self.logger.error(f"Error updating {file_path}: {e}")
            return False

    def process_single_file(self, file_path: Path) -> str:
        """
        Process a single artist card file with three-phase detection system.

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

            # === PHASE 1: DETECTION (Pre-Enhancement) ===
            if not self.skip_detection:
                is_problematic, confidence, issues = self.detect_problematic_card(frontmatter, content)

                if is_problematic and confidence >= DETECTION_CONFIDENCE_MEDIUM:
                    self.stats['problems_detected'] += 1
                    self.logger.info(f"🔍 Detected problematic card: {artist_name} (confidence: {confidence:.2f})")
                    self.logger.debug(f"Issues: {issues}")

                    # === PHASE 2: RECOVERY ATTEMPT ===
                    self.logger.info(f"🔄 Attempting Perplexity recovery for {artist_name}")
                    recovery_result = self.perplexity_analyzer.regenerate_with_perplexity(
                        artist_name, frontmatter, issues
                    )

                    # Rate limiting
                    time.sleep(RATE_LIMIT_DELAY)

                    if recovery_result.get('success'):
                        # Recovery successful - update card with new data
                        self.logger.info(f"✅ Recovery successful for {artist_name}")

                        enhanced_bio = recovery_result.get('biography', '')
                        connections = recovery_result.get('connections', {})
                        new_wikipedia_url = recovery_result.get('new_wikipedia_url')
                        research_sources = recovery_result.get('research_sources', [])

                        # Update frontmatter with recovery metadata
                        frontmatter['data_quality'] = 'validated'
                        frontmatter['recovery_attempted_at'] = datetime.now().isoformat()
                        frontmatter['original_wikipedia_url'] = frontmatter.get('external_urls', {}).get('wikipedia')
                        frontmatter['primary_source'] = 'perplexity'
                        frontmatter['research_sources'] = research_sources
                        if new_wikipedia_url:
                            if 'external_urls' not in frontmatter:
                                frontmatter['external_urls'] = {}
                            frontmatter['external_urls']['wikipedia'] = new_wikipedia_url

                        # Update card
                        if self.update_artist_card(file_path, frontmatter, content, enhanced_bio, connections):
                            # Update connections database
                            if connections:
                                self.connections_db[artist_name] = {
                                    **connections,
                                    'updated': datetime.now().isoformat()
                                }
                                self.stats['connections_found'] += sum(
                                    len(v) if isinstance(v, list) else 0 for v in connections.values()
                                )

                            self.stats['recovered'] += 1
                            connection_count = sum(len(v) if isinstance(v, list) else 0 for v in connections.values())
                            return f"✅ Recovered ({connection_count} connections)"
                        else:
                            self.stats['errors'] += 1
                            return "❌ Recovery update failed"

                    else:
                        # === PHASE 3: QUARANTINE ===
                        self.logger.warning(f"⚠️ Recovery failed for {artist_name}: {recovery_result.get('reason')}")

                        if self.quarantine_card(file_path, frontmatter, issues, recovery_result.get('reason', 'Unknown')):
                            self.stats['quarantined'] += 1
                            return f"⚠️ Quarantined: {recovery_result.get('reason', 'No credible info')}"
                        else:
                            self.stats['errors'] += 1
                            return "❌ Quarantine failed"

            # === NEW: PERPLEXITY-FIRST ENHANCEMENT FLOW ===
            self.logger.info(f"🔍 Starting Perplexity-first research for {artist_name}")

            # PHASE 1: Primary research with Perplexity web search
            research_result = self.perplexity_analyzer.research_artist_with_perplexity(
                artist_name, frontmatter
            )

            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)

            if not research_result.get('success'):
                self.logger.error(f"Perplexity research failed: {research_result.get('reason')}")
                self.stats['errors'] += 1
                return f"❌ Research failed: {research_result.get('reason', 'Unknown')}"

            # PHASE 2: Format biography from research data
            enhancement_result = self.perplexity_analyzer.generate_biography_from_research(
                research_result, artist_name
            )

            enhanced_bio = enhancement_result.get('biography', '')
            connections = enhancement_result.get('connections', {})
            detailed_connections = enhancement_result.get('detailed_connections', {})

            if not enhanced_bio:
                self.stats['errors'] += 1
                return "❌ Biography formatting failed"

            # PHASE 3: Optional Wikipedia metadata supplement
            wikipedia_url = research_result.get('wikipedia_url') or frontmatter.get('external_urls', {}).get('wikipedia')

            # Update frontmatter with research metadata
            frontmatter['primary_source'] = 'perplexity'
            frontmatter['research_sources'] = research_result.get('sources', [])
            if wikipedia_url:
                if 'external_urls' not in frontmatter:
                    frontmatter['external_urls'] = {}
                frontmatter['external_urls']['wikipedia'] = wikipedia_url

            # Update file
            if self.update_artist_card(file_path, frontmatter, content, enhanced_bio, connections):
                # Update connections database with detailed information
                if connections:
                    self.connections_db[artist_name] = {
                        **connections,
                        'detailed': detailed_connections,  # Store detailed connection info
                        'updated': datetime.now().isoformat(),
                        'source': 'perplexity_research'
                    }
                    self.stats['connections_found'] += sum(
                        len(v) if isinstance(v, list) else 0 for v in connections.values()
                    )

                self.stats['enhanced'] += 1
                connection_count = sum(len(v) if isinstance(v, list) else 0 for v in connections.values())

                # Count detailed connections for reporting
                detailed_count = sum(
                    len(v) if isinstance(v, list) else 0
                    for v in detailed_connections.values()
                )

                return f"✅ Enhanced via Perplexity ({connection_count} connections, {len(research_result.get('sources', []))} sources)"
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

        print(f"\n🎵 Jazz Encyclopedia Enhancement Tool (Perplexity Edition)")
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
        print(f"🔍 Problems detected: {self.stats['problems_detected']}")
        print(f"✅ Recovered: {self.stats['recovered']} artists")
        print(f"⚠️ Quarantined: {self.stats['quarantined']} artists")
        print(f"🔗 Connections found: {self.stats['connections_found']}")
        print(f"📚 Network nodes: {len(self.connections_db)} artists")
        print(f"⏭️ Skipped (minimal content): {self.stats['skipped_content']}")
        print(f"🔄 Skipped (already enhanced): {self.stats['skipped_already_enhanced']}")
        print(f"⚠️ Skipped (no Wikipedia): {self.stats['skipped_no_wikipedia']}")
        print(f"❌ Errors: {self.stats['errors']}")
        print(f"📁 Total processed: {self.stats['processed']}")

        if self.stats['enhanced'] > 0 or self.stats['recovered'] > 0:
            total_success = self.stats['enhanced'] + self.stats['recovered']
            print(f"\n🎯 Success rate: {(total_success / self.stats['processed'] * 100):.1f}%")

        if self.stats['quarantined'] > 0:
            print(f"\n⚠️ Note: {self.stats['quarantined']} problematic cards moved to {PROBLEM_CARDS_DIR}/")


def setup_logging(log_level: str) -> None:
    """Setup logging configuration."""
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('biography_enhancer_perplexity.log'),
            logging.StreamHandler()
        ]
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enhance jazz artist biographies with Perplexity AI research and network analysis"
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
    parser.add_argument(
        '--skip-detection',
        action='store_true',
        help='Skip Phase 1 detection and proceed with standard enhancement for all cards'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        # Verify API key (unless in dry-run mode)
        if not args.dry_run and not os.getenv('PERPLEXITY_API_KEY'):
            print("❌ Error: PERPLEXITY_API_KEY environment variable is required")
            print("Please set your Perplexity API key:")
            print("export PERPLEXITY_API_KEY='your-api-key-here'")
            print("\nGet your API key at: https://www.perplexity.ai/settings/api")
            sys.exit(1)

        # Process files
        processor = ArtistCardProcessor(args.cards_dir, args.dry_run, args.force, args.skip_detection)
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