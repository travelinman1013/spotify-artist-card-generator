# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python script that downloads Spotify artist cover images based on data from an Obsidian vault tracking radio station songs. The script processes daily archive markdown files and downloads images for artists marked as "✅ Found" in the Spotify status column.

## Core Architecture

### Main Component: `SpotifyImageDownloader` Class
- **Authentication**: Manages Spotify API client credentials flow with automatic token refresh
- **Markdown Parser**: Extracts artist names from pipe-separated tables in Obsidian daily archive files
- **Spotify Integration**: Searches for artists and retrieves highest resolution cover images
- **File Management**: Downloads images with sanitized filenames and duplicate detection
- **Error Handling**: Comprehensive logging and retry logic for API and file operations

### Key Processing Flow
1. Parse Obsidian markdown table to extract artists with "✅ Found" status
2. Authenticate with Spotify API using client credentials
3. For each artist: search Spotify → get artist images → download highest resolution image
4. Save images with sanitized filenames to specified output directory
5. Provide detailed statistics and logging

## Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install requests pillow
```

## Running the Script

```bash
# Activate virtual environment
source venv/bin/activate

# Basic usage
python spotify_image_downloader.py \
  --input "/path/to/daily_archive.md" \
  --output "/path/to/output_directory"

# With options
python spotify_image_downloader.py \
  --input "/path/to/daily_archive.md" \
  --output "/path/to/output_directory" \
  --skip-existing \
  --log-level INFO
```

## Configuration

### Spotify API Credentials
The script uses hardcoded Spotify app credentials:
- Client ID: `a088edf333334899b6ad55579b834389`
- Client Secret: `78b5d889d9094ff0bb0b2a22cc8cfaac`
- Redirect URI: `http://127.0.0.1:8888/callback`

### Rate Limiting
- Configured for 100 requests per minute (0.6 second delay between requests)
- Automatic retry logic with exponential backoff
- Token refresh handling for expired authentication

## Input File Format

The script expects Obsidian daily archive markdown files with pipe-separated tables containing:
- Column 2: Artist name
- Column 8: Status ("✅ Found" indicates Spotify match)

Example table row:
```
| 06:07 | John Coltrane | Welcome | The Gentle Side of John Coltrane | jazz, hard bop, free jazz | The Morning Set | Breaux Bridges | ✅ Found | 100.0% | [Open](https://open.spotify.com/track/...) |
```

## File Naming and Output

- Images saved with sanitized artist names (spaces → underscores, special characters removed)
- Format: `Artist_Name.jpg` (preserves original image format from Spotify)
- Automatic duplicate detection and skipping
- Creates output directory if it doesn't exist

## Logging

- Logs to both console and `spotify_downloader.log` file
- Configurable log levels: DEBUG, INFO, WARNING, ERROR
- Tracks processing progress, API calls, download success/failure
- Final summary with statistics (total, success, failed, skipped)