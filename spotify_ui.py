#!/usr/bin/env python3
"""
Streamlit UI for Spotify Artist Tools

A web-based interface for running the Spotify image downloader and artist card generator scripts.
Provides an easy way to select input files, configure output directories, and track progress.

Usage:
    streamlit run spotify_ui.py
"""

import streamlit as st
import subprocess
import os
import json
import time
from pathlib import Path
from datetime import datetime
import threading
import queue
import re

# Default paths based on your Obsidian vault structure
DEFAULT_ARTIST_CARDS_DIR = "/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists"
DEFAULT_ARTIST_IMAGES_DIR = "/Users/maxwell/LETSGO/MaxVault/03_Resources/source_material/ArtistPortraits"
DEFAULT_ARCHIVE_DIR = "/Users/maxwell/LETSGO/MaxVault"
CONFIG_FILE = "spotify_ui_config.json"

# Initialize session state
if 'running' not in st.session_state:
    st.session_state.running = False
if 'progress' not in st.session_state:
    st.session_state.progress = 0
if 'log_output' not in st.session_state:
    st.session_state.log_output = []
if 'config' not in st.session_state:
    st.session_state.config = {}
if 'selected_downloader_file' not in st.session_state:
    st.session_state.selected_downloader_file = None
if 'selected_generator_file' not in st.session_state:
    st.session_state.selected_generator_file = None
# File browser modal state
if 'show_file_browser_downloader' not in st.session_state:
    st.session_state.show_file_browser_downloader = False
if 'show_file_browser_generator' not in st.session_state:
    st.session_state.show_file_browser_generator = False
if 'available_files_downloader' not in st.session_state:
    st.session_state.available_files_downloader = []
if 'available_files_generator' not in st.session_state:
    st.session_state.available_files_generator = []
if 'pending_file_selection_downloader' not in st.session_state:
    st.session_state.pending_file_selection_downloader = None
if 'pending_file_selection_generator' not in st.session_state:
    st.session_state.pending_file_selection_generator = None

def load_config():
    """Load saved configuration from file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        'artist_cards_dir': DEFAULT_ARTIST_CARDS_DIR,
        'artist_images_dir': DEFAULT_ARTIST_IMAGES_DIR,
        'archive_dir': DEFAULT_ARCHIVE_DIR,
        'recent_files': []
    }

def save_config(config):
    """Save configuration to file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def find_archive_files(directory):
    """Find markdown files that look like daily archives."""
    archive_files = []
    try:
        path = Path(directory)
        # Look for .md files with date patterns or "archive" in the name
        patterns = ['*.md']
        for pattern in patterns:
            for file in path.rglob(pattern):
                file_str = str(file)
                # Check if filename contains date pattern or "archive"
                if any(x in file_str.lower() for x in ['archive', '2024', '2025', 'daily']):
                    archive_files.append(file_str)
        # Sort by modification time (most recent first)
        archive_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    except Exception as e:
        st.error(f"Error scanning directory: {e}")
    return archive_files[:50]  # Return only the 50 most recent

def validate_selected_file(file_path):
    """Validate that the selected file exists and is readable."""
    if not file_path:
        return False, "No file selected"

    try:
        path = Path(file_path)
        if not path.exists():
            return False, f"File does not exist: {file_path}"

        if not path.is_file():
            return False, f"Path is not a file: {file_path}"

        if not path.suffix.lower() == '.md':
            return False, f"File is not a markdown file: {file_path}"

        # Try to read the file to check permissions
        with open(path, 'r', encoding='utf-8') as f:
            f.read(100)  # Read first 100 chars to test readability

        return True, "File is valid"

    except PermissionError:
        return False, f"Permission denied reading file: {file_path}"
    except Exception as e:
        return False, f"Error validating file: {str(e)}"

def run_command_with_progress(command, progress_callback=None, log_callback=None):
    """Run a command and capture output with progress updates."""
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    output_lines = []
    for line in iter(process.stdout.readline, ''):
        if line:
            output_lines.append(line.strip())
            if log_callback:
                log_callback(line.strip())

            # Try to parse progress from output
            if progress_callback:
                if "Processing artist" in line or "Downloading" in line:
                    # Extract progress if possible
                    match = re.search(r'(\d+)/(\d+)', line)
                    if match:
                        current, total = int(match.group(1)), int(match.group(2))
                        progress = current / total
                        progress_callback(progress)

    process.wait()
    return process.returncode, output_lines

def main():
    st.set_page_config(
        page_title="Spotify Artist Tools",
        page_icon="🎵",
        layout="wide"
    )

    st.title("🎵 Spotify Artist Tools")
    st.markdown("Download artist images and generate comprehensive artist cards for your Obsidian vault")

    # Load configuration
    if not st.session_state.config:
        st.session_state.config = load_config()

    # Create tabs
    tab1, tab2, tab3 = st.tabs(["🖼️ Image Downloader", "📇 Artist Card Generator", "⚙️ Settings"])

    # Image Downloader Tab
    with tab1:
        st.header("Download Artist Images from Spotify")

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Input File")

            # Recent files dropdown
            recent_files = st.session_state.config.get('recent_files', [])
            if recent_files:
                selected_recent = st.selectbox(
                    "Recent files:",
                    ["Select a recent file..."] + recent_files,
                    key="recent_downloader"
                )
                if selected_recent != "Select a recent file...":
                    input_file = selected_recent
                else:
                    input_file = None

            # Get current input file value
            current_input_file = ""
            if st.session_state.selected_downloader_file:
                current_input_file = st.session_state.selected_downloader_file
            elif recent_files and selected_recent != "Select a recent file...":
                current_input_file = selected_recent

            # File input
            input_file = st.text_input(
                "Daily archive file path:",
                value=current_input_file,
                placeholder="/path/to/daily_archive.md",
                key="downloader_input"
            )

            # Browse button
            if st.button("📂 Browse Archive Files", key="browse_downloader"):
                st.session_state.show_file_browser_downloader = True
                archive_dir = st.session_state.config.get('archive_dir', DEFAULT_ARCHIVE_DIR)
                with st.spinner(f"Scanning {archive_dir}..."):
                    files = find_archive_files(archive_dir)
                    st.session_state.available_files_downloader = files
                st.rerun()

            st.subheader("Output Directory")
            output_dir = st.text_input(
                "Where to save images:",
                value=st.session_state.config.get('artist_images_dir', DEFAULT_ARTIST_IMAGES_DIR),
                key="downloader_output"
            )

            # Options
            skip_existing = st.checkbox("Skip existing images", value=True, key="skip_existing")

            # File Browser Modal for Downloader
            if st.session_state.show_file_browser_downloader:
                st.markdown("---")
                st.subheader("📂 Select Archive File")

                if st.session_state.available_files_downloader:
                    st.info(f"Found {len(st.session_state.available_files_downloader)} archive files")

                    # File selection
                    selected_file = st.selectbox(
                        "Choose a file:",
                        st.session_state.available_files_downloader,
                        key="browser_file_select_downloader"
                    )

                    if selected_file:
                        st.session_state.pending_file_selection_downloader = selected_file
                        st.text(f"📄 Selected: {os.path.basename(selected_file)}")

                    # Action buttons
                    col_confirm, col_cancel = st.columns(2)
                    with col_confirm:
                        if st.button("✅ Use This File", key="confirm_downloader"):
                            if st.session_state.pending_file_selection_downloader:
                                st.session_state.selected_downloader_file = st.session_state.pending_file_selection_downloader
                                st.session_state.show_file_browser_downloader = False
                                st.session_state.pending_file_selection_downloader = None
                                st.rerun()

                    with col_cancel:
                        if st.button("❌ Cancel", key="cancel_downloader"):
                            st.session_state.show_file_browser_downloader = False
                            st.session_state.pending_file_selection_downloader = None
                            st.rerun()
                else:
                    st.warning("No archive files found in the configured directory.")
                    if st.button("❌ Close", key="close_no_files_downloader"):
                        st.session_state.show_file_browser_downloader = False
                        st.rerun()

        with col2:
            st.subheader("Options")

            # Run button
            if st.button("▶️ Download Images", type="primary", key="run_downloader",
                        disabled=st.session_state.running):
                # Get the actual input file value from text input or session state
                actual_input_file = st.session_state.get("downloader_input", "") or current_input_file
                if actual_input_file and output_dir:
                    # Validate the input file
                    is_valid, validation_message = validate_selected_file(actual_input_file)
                    if not is_valid:
                        st.error(f"❌ Invalid input file: {validation_message}")
                        return
                    # Update recent files
                    if actual_input_file not in recent_files:
                        recent_files.insert(0, actual_input_file)
                        recent_files = recent_files[:10]  # Keep only 10 most recent
                        st.session_state.config['recent_files'] = recent_files
                        save_config(st.session_state.config)

                    # Build command
                    cmd = f"source venv/bin/activate && python spotify_image_downloader.py"
                    cmd += f' --input "{actual_input_file}"'
                    cmd += f' --output "{output_dir}"'
                    if skip_existing:
                        cmd += " --skip-existing"

                    st.session_state.running = True
                    st.session_state.log_output = []

                    # Run command
                    with st.spinner("Downloading images..."):
                        progress_bar = st.progress(0)
                        log_area = st.empty()

                        def update_progress(value):
                            progress_bar.progress(value)

                        def update_log(line):
                            st.session_state.log_output.append(line)
                            # Show last 10 lines
                            log_area.text_area("Log Output",
                                             "\n".join(st.session_state.log_output[-10:]),
                                             height=200)

                        returncode, output = run_command_with_progress(
                            cmd, update_progress, update_log
                        )

                        st.session_state.running = False

                        if returncode == 0:
                            st.success("✅ Download completed successfully!")

                            # Parse summary from output
                            for line in reversed(output):
                                if "Total artists:" in line:
                                    st.info(line)
                                elif "Successfully downloaded:" in line:
                                    st.info(line)
                                elif "Failed:" in line:
                                    st.warning(line)
                                elif "Skipped" in line:
                                    st.info(line)
                        else:
                            st.error(f"❌ Download failed with error code {returncode}")
                else:
                    st.error("Please provide both input file and output directory")

            # Progress display
            if st.session_state.running:
                st.info("🔄 Process running...")

    # Artist Card Generator Tab
    with tab2:
        st.header("Generate Artist Cards with Metadata")

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Input Mode")

            input_mode = st.radio(
                "Choose input mode:",
                ["Single Artist", "Batch from File"],
                key="generator_mode"
            )

            if input_mode == "Single Artist":
                artist_name = st.text_input(
                    "Artist name:",
                    placeholder="e.g., John Coltrane",
                    key="artist_name"
                )
                input_file_gen = None
            else:
                # Recent files dropdown for generator
                recent_files = st.session_state.config.get('recent_files', [])
                if recent_files:
                    selected_recent = st.selectbox(
                        "Recent files:",
                        ["Select a recent file..."] + recent_files,
                        key="recent_generator"
                    )
                    if selected_recent != "Select a recent file...":
                        input_file_gen = selected_recent
                    else:
                        input_file_gen = None
                else:
                    input_file_gen = None

                # Get current input file value
                current_input_file_gen = ""
                if st.session_state.selected_generator_file:
                    current_input_file_gen = st.session_state.selected_generator_file
                elif recent_files and selected_recent != "Select a recent file...":
                    current_input_file_gen = selected_recent

                # File input
                input_file_gen = st.text_input(
                    "Daily archive file path:",
                    value=current_input_file_gen,
                    placeholder="/path/to/daily_archive.md",
                    key="generator_input"
                )

                # Browse button
                if st.button("📂 Browse Archive Files", key="browse_generator"):
                    st.session_state.show_file_browser_generator = True
                    archive_dir = st.session_state.config.get('archive_dir', DEFAULT_ARCHIVE_DIR)
                    with st.spinner(f"Scanning {archive_dir}..."):
                        files = find_archive_files(archive_dir)
                        st.session_state.available_files_generator = files
                    st.rerun()

                artist_name = None

            st.subheader("Output Directories")

            cards_output_dir = st.text_input(
                "Artist cards directory:",
                value=st.session_state.config.get('artist_cards_dir', DEFAULT_ARTIST_CARDS_DIR),
                key="cards_output"
            )

            images_output_dir = st.text_input(
                "Artist images directory:",
                value=st.session_state.config.get('artist_images_dir', DEFAULT_ARTIST_IMAGES_DIR),
                key="images_output"
            )

            # File Browser Modal for Generator
            if st.session_state.show_file_browser_generator:
                st.markdown("---")
                st.subheader("📂 Select Archive File")

                if st.session_state.available_files_generator:
                    st.info(f"Found {len(st.session_state.available_files_generator)} archive files")

                    # File selection
                    selected_file = st.selectbox(
                        "Choose a file:",
                        st.session_state.available_files_generator,
                        key="browser_file_select_generator"
                    )

                    if selected_file:
                        st.session_state.pending_file_selection_generator = selected_file
                        st.text(f"📄 Selected: {os.path.basename(selected_file)}")

                    # Action buttons
                    col_confirm, col_cancel = st.columns(2)
                    with col_confirm:
                        if st.button("✅ Use This File", key="confirm_generator"):
                            if st.session_state.pending_file_selection_generator:
                                st.session_state.selected_generator_file = st.session_state.pending_file_selection_generator
                                st.session_state.show_file_browser_generator = False
                                st.session_state.pending_file_selection_generator = None
                                st.rerun()

                    with col_cancel:
                        if st.button("❌ Cancel", key="cancel_generator"):
                            st.session_state.show_file_browser_generator = False
                            st.session_state.pending_file_selection_generator = None
                            st.rerun()
                else:
                    st.warning("No archive files found in the configured directory.")
                    if st.button("❌ Close", key="close_no_files_generator"):
                        st.session_state.show_file_browser_generator = False
                        st.rerun()

        with col2:
            st.subheader("Options")

            log_level = st.selectbox(
                "Log level:",
                ["INFO", "DEBUG", "WARNING", "ERROR"],
                key="log_level"
            )

            # Run button
            if st.button("▶️ Generate Cards", type="primary", key="run_generator",
                        disabled=st.session_state.running):
                # Get the actual input file value from text input or session state
                actual_input_file_gen = st.session_state.get("generator_input", "") or current_input_file_gen
                if (artist_name or actual_input_file_gen) and cards_output_dir:
                    # Validate the input file if using file mode
                    if actual_input_file_gen and not artist_name:
                        is_valid, validation_message = validate_selected_file(actual_input_file_gen)
                        if not is_valid:
                            st.error(f"❌ Invalid input file: {validation_message}")
                            return
                    # Update recent files if using file input
                    if actual_input_file_gen:
                        if actual_input_file_gen not in recent_files:
                            recent_files.insert(0, actual_input_file_gen)
                            recent_files = recent_files[:10]
                            st.session_state.config['recent_files'] = recent_files
                            save_config(st.session_state.config)

                    # Build command
                    cmd = f"source venv/bin/activate && python spotify_artist_card_generator.py"

                    if artist_name:
                        cmd += f' --artist "{artist_name}"'
                    else:
                        cmd += f' --input-file "{actual_input_file_gen}"'

                    cmd += f' --output-dir "{cards_output_dir}"'

                    if images_output_dir:
                        cmd += f' --images-dir "{images_output_dir}"'

                    cmd += f' --log-level {log_level}'

                    st.session_state.running = True
                    st.session_state.log_output = []

                    # Run command
                    with st.spinner("Generating artist cards..."):
                        progress_bar = st.progress(0)
                        log_area = st.empty()

                        def update_progress(value):
                            progress_bar.progress(value)

                        def update_log(line):
                            st.session_state.log_output.append(line)
                            # Show last 15 lines for generator (more detailed output)
                            log_area.text_area("Log Output",
                                             "\n".join(st.session_state.log_output[-15:]),
                                             height=300)

                        returncode, output = run_command_with_progress(
                            cmd, update_progress, update_log
                        )

                        st.session_state.running = False

                        if returncode == 0:
                            st.success("✅ Card generation completed successfully!")

                            # Show summary
                            if artist_name:
                                st.info(f"Generated card for: {artist_name}")
                            else:
                                # Parse summary from output
                                for line in reversed(output):
                                    if "Total artists:" in line:
                                        st.info(line)
                                    elif "Successfully generated:" in line:
                                        st.info(line)
                                    elif "Failed:" in line:
                                        st.warning(line)
                        else:
                            st.error(f"❌ Generation failed with error code {returncode}")
                else:
                    st.error("Please provide input (artist name or file) and output directory")

            # Progress display
            if st.session_state.running:
                st.info("🔄 Process running...")

    # Settings Tab
    with tab3:
        st.header("Settings")

        st.subheader("Default Directories")

        new_cards_dir = st.text_input(
            "Default artist cards directory:",
            value=st.session_state.config.get('artist_cards_dir', DEFAULT_ARTIST_CARDS_DIR)
        )

        new_images_dir = st.text_input(
            "Default artist images directory:",
            value=st.session_state.config.get('artist_images_dir', DEFAULT_ARTIST_IMAGES_DIR)
        )

        new_archive_dir = st.text_input(
            "Default archive search directory:",
            value=st.session_state.config.get('archive_dir', DEFAULT_ARCHIVE_DIR)
        )

        if st.button("💾 Save Settings"):
            st.session_state.config['artist_cards_dir'] = new_cards_dir
            st.session_state.config['artist_images_dir'] = new_images_dir
            st.session_state.config['archive_dir'] = new_archive_dir
            save_config(st.session_state.config)
            st.success("Settings saved!")

        st.subheader("Recent Files")

        recent_files = st.session_state.config.get('recent_files', [])
        if recent_files:
            st.write("Recently used archive files:")
            for i, file in enumerate(recent_files, 1):
                st.text(f"{i}. {file}")

            if st.button("🗑️ Clear Recent Files"):
                st.session_state.config['recent_files'] = []
                save_config(st.session_state.config)
                st.success("Recent files cleared!")
        else:
            st.info("No recent files")

        st.subheader("Virtual Environment")

        # Check if venv exists
        venv_exists = os.path.exists("venv")
        if venv_exists:
            st.success("✅ Virtual environment found")
        else:
            st.warning("⚠️ Virtual environment not found")
            st.info("Run 'python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt' to set up")

        # Export logs button
        st.subheader("Logs")

        if st.session_state.log_output:
            log_content = "\n".join(st.session_state.log_output)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            st.download_button(
                label="📥 Download Log",
                data=log_content,
                file_name=f"spotify_ui_log_{timestamp}.txt",
                mime="text/plain"
            )
        else:
            st.info("No logs available yet")

if __name__ == "__main__":
    main()