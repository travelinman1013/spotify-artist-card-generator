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
import signal
import psutil
from pathlib import Path
from datetime import datetime
import threading
import queue
import re
import tempfile
from typing import Optional, List, Dict, Any
from enhanced_logging import (
    EnhancedLogger, ProcessManager, cleanup_old_logs,
    render_enhanced_log_display, render_process_control_panel,
    create_enhanced_progress_display
)
# Default paths based on your Obsidian vault structure
DEFAULT_ARTIST_CARDS_DIR = "/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists"
DEFAULT_ARTIST_IMAGES_DIR = "/Users/maxwell/LETSGO/MaxVault/03_Resources/source_material/ArtistPortraits"
DEFAULT_ARCHIVE_DIR = "/Users/maxwell/LETSGO/MaxVault"
CONFIG_FILE = "spotify_ui_config.json"
# Enhanced Logging Configuration
LOG_BUFFER_SIZE = 1000
LOG_UPDATE_INTERVAL = 0.5  # seconds
TEMP_LOG_DIR = Path(tempfile.gettempdir()) / "streamlit_logs"
TEMP_LOG_DIR.mkdir(exist_ok=True)
# Initialize session state
if 'running' not in st.session_state:
    st.session_state.running = False
if 'progress' not in st.session_state:
    st.session_state.progress = 0
if 'log_output' not in st.session_state:
    st.session_state.log_output = []
if 'config' not in st.session_state:
    st.session_state.config = {}
if 'uploaded_file_downloader' not in st.session_state:
    st.session_state.uploaded_file_downloader = None
if 'uploaded_file_generator' not in st.session_state:
    st.session_state.uploaded_file_generator = None
if 'temp_file_path_downloader' not in st.session_state:
    st.session_state.temp_file_path_downloader = None
if 'temp_file_path_generator' not in st.session_state:
    st.session_state.temp_file_path_generator = None
# Biography Enhancement session state
if 'enhancement_running' not in st.session_state:
    st.session_state.enhancement_running = False
if 'enhancement_progress' not in st.session_state:
    st.session_state.enhancement_progress = 0
if 'enhancement_log_output' not in st.session_state:
    st.session_state.enhancement_log_output = []
if 'google_api_key' not in st.session_state:
    st.session_state.google_api_key = ""
if 'enhancement_stats' not in st.session_state:
    st.session_state.enhancement_stats = {}
# Enhanced process control session state
if 'active_processes' not in st.session_state:
    st.session_state.active_processes = {}
if 'log_filters' not in st.session_state:
    st.session_state.log_filters = {'show_info': True, 'show_error': True, 'show_success': True, 'show_warning': True}
if 'log_search' not in st.session_state:
    st.session_state.log_search = ""
if 'process_stats' not in st.session_state:
    st.session_state.process_stats = {}
if 'log_files' not in st.session_state:
    st.session_state.log_files = {}
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
def save_uploaded_file(uploaded_file, prefix="archive"):
    """Save uploaded file to temp directory and return path."""
    if uploaded_file is None:
        return None
    # Create temp file with original extension
    suffix = Path(uploaded_file.name).suffix
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix=f"{prefix}_")
    # Write uploaded content to temp file
    temp_file.write(uploaded_file.getbuffer())
    temp_file.close()
    return temp_file.name
def cleanup_temp_file(file_path):
    """Clean up temporary file."""
    if file_path and os.path.exists(file_path):
        try:
            os.unlink(file_path)
        except Exception:
            pass  # Ignore cleanup errors
# find_archive_files function removed - no longer needed with file uploader
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
    # Cleanup temp files on session end
    def cleanup_temp_files():
        if st.session_state.get('temp_file_path_downloader'):
            cleanup_temp_file(st.session_state.temp_file_path_downloader)
        if st.session_state.get('temp_file_path_generator'):
            cleanup_temp_file(st.session_state.temp_file_path_generator)
    st.title("🎵 Spotify Artist Tools")
    st.markdown("Download artist images and generate comprehensive artist cards for your Obsidian vault")
    # Load configuration
    if not st.session_state.config:
        st.session_state.config = load_config()
    # Create tabs
    tab1, tab2, tab3, tab4 = st.tabs(["🖼️ Image Downloader", "📇 Artist Card Generator", "🧠 Biography Enhancement", "⚙️ Settings"])
    # Image Downloader Tab
    with tab1:
        st.header("Download Artist Images from Spotify")
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("Input File")
            # File uploader - primary method
            uploaded_file = st.file_uploader(
                "Select daily archive file:",
                type=['md'],
                key="file_uploader_downloader",
                help="Upload a markdown file containing daily music archive data"
            )
            # Handle uploaded file
            if uploaded_file is not None:
                if st.session_state.uploaded_file_downloader != uploaded_file:
                    # New file uploaded, save to temp location
                    if st.session_state.temp_file_path_downloader:
                        cleanup_temp_file(st.session_state.temp_file_path_downloader)
                    st.session_state.temp_file_path_downloader = save_uploaded_file(uploaded_file, "downloader")
                    st.session_state.uploaded_file_downloader = uploaded_file
                input_file = st.session_state.temp_file_path_downloader
                st.success(f"✅ File uploaded: {uploaded_file.name}")
            else:
                input_file = None
            # Recent files dropdown as secondary option
            recent_files = st.session_state.config.get('recent_files', [])
            if recent_files and not uploaded_file:
                st.markdown("**Or select from recent files:**")
                selected_recent = st.selectbox(
                    "Recent files:",
                    ["Select a recent file..."] + recent_files,
                    key="recent_downloader"
                )
                if selected_recent != "Select a recent file...":
                    input_file = selected_recent
            st.subheader("Output Directory")
            output_dir = st.text_input(
                "Where to save images:",
                value=st.session_state.config.get('artist_images_dir', DEFAULT_ARTIST_IMAGES_DIR),
                key="downloader_output"
            )
            # Options
            skip_existing = st.checkbox("Skip existing images", value=True, key="skip_existing")
        with col2:
            st.subheader("Options")
            # Run button
            if st.button("▶️ Download Images", type="primary", key="run_downloader",
                        disabled=st.session_state.running):
                if input_file and output_dir:
                    # Validate the input file
                    is_valid, validation_message = validate_selected_file(input_file)
                    if not is_valid:
                        st.error(f"❌ Invalid input file: {validation_message}")
                        return
                    # Update recent files only if it's a path-based file (not uploaded)
                    if input_file not in recent_files and not uploaded_file:
                        recent_files.insert(0, input_file)
                        recent_files = recent_files[:10]  # Keep only 10 most recent
                        st.session_state.config['recent_files'] = recent_files
                        save_config(st.session_state.config)
                    # Build command
                    cmd = f"source venv/bin/activate && python spotify_image_downloader.py"
                    cmd += f' --input "{input_file}"'
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
                # File uploader - primary method
                uploaded_file_gen = st.file_uploader(
                    "Select daily archive file:",
                    type=['md'],
                    key="file_uploader_generator",
                    help="Upload a markdown file containing daily music archive data"
                )
                # Handle uploaded file
                if uploaded_file_gen is not None:
                    if st.session_state.uploaded_file_generator != uploaded_file_gen:
                        # New file uploaded, save to temp location
                        if st.session_state.temp_file_path_generator:
                            cleanup_temp_file(st.session_state.temp_file_path_generator)
                        st.session_state.temp_file_path_generator = save_uploaded_file(uploaded_file_gen, "generator")
                        st.session_state.uploaded_file_generator = uploaded_file_gen
                    input_file_gen = st.session_state.temp_file_path_generator
                    st.success(f"✅ File uploaded: {uploaded_file_gen.name}")
                else:
                    input_file_gen = None
                # Recent files dropdown as secondary option
                recent_files = st.session_state.config.get('recent_files', [])
                if recent_files and not uploaded_file_gen:
                    st.markdown("**Or select from recent files:**")
                    selected_recent = st.selectbox(
                        "Recent files:",
                        ["Select a recent file..."] + recent_files,
                        key="recent_generator"
                    )
                    if selected_recent != "Select a recent file...":
                        input_file_gen = selected_recent
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
                if (artist_name or input_file_gen) and cards_output_dir:
                    # Validate the input file if using file mode
                    if input_file_gen and not artist_name:
                        is_valid, validation_message = validate_selected_file(input_file_gen)
                        if not is_valid:
                            st.error(f"❌ Invalid input file: {validation_message}")
                            return
                    # Update recent files only if it's a path-based file (not uploaded)
                    if input_file_gen and not artist_name and not uploaded_file_gen:
                        recent_files = st.session_state.config.get('recent_files', [])
                        if input_file_gen not in recent_files:
                            recent_files.insert(0, input_file_gen)
                            recent_files = recent_files[:10]
                            st.session_state.config['recent_files'] = recent_files
                            save_config(st.session_state.config)
                    # Build command
                    cmd = f"source venv/bin/activate && python spotify_artist_card_generator.py"
                    if artist_name:
                        cmd += f' --artist "{artist_name}"'
                    else:
                        cmd += f' --input-file "{input_file_gen}"'
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
    # Biography Enhancement Tab
    with tab3:
        st.header("AI-Powered Biography Enhancement")
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("Configuration")
            # Artist cards directory
            cards_dir = st.text_input(
                "Artist cards directory:",
                value=st.session_state.config.get('artist_cards_dir', DEFAULT_ARTIST_CARDS_DIR),
                key="enhancement_cards_dir",
                help="Directory containing artist markdown files to enhance"
            )
            # Google API key input
            api_key = st.text_input(
                "Google Gemini API Key:",
                value=st.session_state.google_api_key or os.getenv('GOOGLE_API_KEY', ''),
                type="password",
                key="google_api_key_input",
                help="Required for AI biography enhancement. Get your key at https://makersuite.google.com/app/apikey"
            )
            # Store API key in session state
            if api_key:
                st.session_state.google_api_key = api_key
            st.subheader("Options")
            # Enhancement options
            dry_run = st.checkbox(
                "Dry run (preview only)",
                value=False,
                key="enhancement_dry_run",
                help="Preview changes without modifying files"
            )
            force_enhance = st.checkbox(
                "Force re-enhancement",
                value=False,
                key="enhancement_force",
                help="Re-enhance files that have already been processed"
            )
            # Prerequisites validation
            st.subheader("Prerequisites Check")
            # Check API key
            if api_key:
                st.success("✅ Google API Key provided")
            else:
                st.error("❌ Google API Key required")
            # Check cards directory
            if os.path.exists(cards_dir):
                md_files = list(Path(cards_dir).glob("*.md"))
                if md_files:
                    st.success(f"✅ Found {len(md_files)} artist cards")
                else:
                    st.warning("⚠️ No markdown files found in directory")
            else:
                st.error("❌ Artist cards directory not found")
        with col2:
            st.subheader("Actions")
            # Check if prerequisites are met
            can_run = bool(api_key and os.path.exists(cards_dir))
            # Run button
            if st.button(
                "🧠 Enhance Biographies",
                type="primary",
                key="run_enhancement",
                disabled=st.session_state.enhancement_running or not can_run
            ):
                if can_run:
                    # Set environment variable for the subprocess
                    os.environ['GOOGLE_API_KEY'] = api_key
                    # Build command
                    cmd = f"source venv/bin/activate && python enhance_biographies.py"
                    cmd += f' --cards-dir "{cards_dir}"'
                    if dry_run:
                        cmd += " --dry-run"
                    if force_enhance:
                        cmd += " --force"
                    cmd += " --log-level INFO"
                    st.session_state.enhancement_running = True
                    st.session_state.enhancement_log_output = []
                    st.session_state.enhancement_stats = {}
                    # Run command
                    with st.spinner("Enhancing biographies..."):
                        progress_bar = st.progress(0)
                        log_area = st.empty()
                        def update_progress(value):
                            st.session_state.enhancement_progress = value
                            progress_bar.progress(value)
                        def update_log(line):
                            st.session_state.enhancement_log_output.append(line)
                            # Show last 20 lines for enhancement (detailed output)
                            log_area.text_area(
                                "Enhancement Log",
"\n".join(st.session_state.enhancement_log_output[-20:]),
                                height=400,
                                key=f"enhancement_log_{len(st.session_state.enhancement_log_output)}"
                            )
                        returncode, output = run_command_with_progress(
                            cmd, update_progress, update_log
                        )
                        st.session_state.enhancement_running = False
                        if returncode == 0:
                            st.success("✅ Biography enhancement completed successfully!")
                            # Parse and display summary statistics
                            summary_stats = {}
                            for line in reversed(output):
                                if "Enhanced:" in line:
                                    match = re.search(r'Enhanced: (\d+)', line)
                                    if match:
                                        summary_stats['enhanced'] = int(match.group(1))
                                elif "Connections found:" in line:
                                    match = re.search(r'Connections found: (\d+)', line)
                                    if match:
                                        summary_stats['connections'] = int(match.group(1))
                                elif "Network nodes:" in line:
                                    match = re.search(r'Network nodes: (\d+)', line)
                                    if match:
                                        summary_stats['network_nodes'] = int(match.group(1))
                                elif "Success rate:" in line:
                                    match = re.search(r'Success rate: ([\d.]+)%', line)
                                    if match:
                                        summary_stats['success_rate'] = float(match.group(1))
                            # Store stats for display
                            st.session_state.enhancement_stats = summary_stats
                            # Display key stats
                            if summary_stats:
                                st.info(f"Enhanced: {summary_stats.get('enhanced', 0)} artists")
                                if summary_stats.get('connections'):
                                    st.info(f"Connections found: {summary_stats.get('connections', 0)}")
                                if summary_stats.get('success_rate'):
                                    st.info(f"Success rate: {summary_stats.get('success_rate', 0):.1f}%")
                        else:
                            st.error(f"❌ Enhancement failed with error code {returncode}")
                else:
                    st.error("Prerequisites not met. Please check the requirements above.")
            # Progress display
            if st.session_state.enhancement_running:
                st.info("🔄 Enhancement in progress...")
            # Download logs button
            if st.session_state.enhancement_log_output:
                log_content = "\n".join(st.session_state.enhancement_log_output)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    label="📥 Download Enhancement Log",
                    data=log_content,
                    file_name=f"biography_enhancement_log_{timestamp}.txt",
                    mime="text/plain"
                )
            # Statistics display
            if st.session_state.enhancement_stats:
                st.subheader("Results Summary")
                stats = st.session_state.enhancement_stats
                col_a, col_b = st.columns(2)
                with col_a:
                    if 'enhanced' in stats:
                        st.metric("Enhanced", stats['enhanced'])
                    if 'connections' in stats:
                        st.metric("Connections", stats['connections'])
                with col_b:
                    if 'network_nodes' in stats:
                        st.metric("Network Nodes", stats['network_nodes'])
                    if 'success_rate' in stats:
                        st.metric("Success Rate", f"{stats['success_rate']:.1f}%")
        # Enhanced Logging Display for Biography Enhancement
        st.markdown("---")
        st.subheader("📋 Enhanced Process Logs")
        # Initialize enhanced logger if not exists
        if 'enhancement_logger' not in st.session_state:
            st.session_state.enhancement_logger = EnhancedLogger("enhancement")
        # Render enhanced log display
        render_enhanced_log_display(st.session_state.enhancement_logger, "enhancement")
        # Cleanup old logs
        cleanup_old_logs()
    # Settings Tab
    with tab4:
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
        # Google API Key storage
        st.subheader("API Configuration")
        stored_api_key = st.text_input(
            "Google Gemini API Key (for biography enhancement):",
            value=st.session_state.google_api_key,
            type="password",
            help="This key is stored only for the current session and not saved to disk"
        )
        if stored_api_key != st.session_state.google_api_key:
            st.session_state.google_api_key = stored_api_key
        # Environment variable check
        env_api_key = os.getenv('GOOGLE_API_KEY')
        if env_api_key:
            st.success("✅ GOOGLE_API_KEY environment variable detected")
        elif stored_api_key:
            st.info("ℹ️ Using API key from session (not persistent)")
        else:
            st.warning("⚠️ No Google API key configured")
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