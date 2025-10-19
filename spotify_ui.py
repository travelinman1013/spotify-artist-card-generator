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
import pandas as pd
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
if 'running_generator' not in st.session_state:
    st.session_state.running_generator = False
if 'progress' not in st.session_state:
    st.session_state.progress = 0
if 'log_output' not in st.session_state:
    st.session_state.log_output = []
if 'log_output_generator' not in st.session_state:
    st.session_state.log_output_generator = []
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
if 'perplexity_api_key' not in st.session_state:
    st.session_state.perplexity_api_key = ""
if 'enhancement_stats' not in st.session_state:
    st.session_state.enhancement_stats = {}
if 'artist_progress_data' not in st.session_state:
    st.session_state.artist_progress_data = {}  # {artist_name: {...}}
if 'selected_artist_for_logs' not in st.session_state:
    st.session_state.selected_artist_for_logs = None
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

def parse_json_progress(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse JSON progress output from enhance_biographies_perplexity.py.

    Args:
        line: Output line that might contain JSON progress

    Returns:
        Progress data dict or None if not JSON
    """
    try:
        # Try to parse as JSON
        data = json.loads(line.strip())
        if isinstance(data, dict) and data.get('type') == 'progress':
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None

def update_artist_progress(progress_data: Dict[str, Any]) -> None:
    """
    Update artist progress data in session state.

    Args:
        progress_data: Progress data from JSON output
    """
    artist_name = progress_data.get('artist', 'Unknown')

    if artist_name not in st.session_state.artist_progress_data:
        st.session_state.artist_progress_data[artist_name] = {
            'artist': artist_name,
            'status': 'started',
            'percent': 0.0,
            'connections': 0,
            'time_elapsed': 0.0,
            'result': '',
            'start_time': datetime.now()
        }

    # Update with new data
    st.session_state.artist_progress_data[artist_name].update({
        'status': progress_data.get('status', 'unknown'),
        'percent': progress_data.get('percent', 0.0),
        'connections': progress_data.get('connections', 0),
        'time_elapsed': progress_data.get('time_elapsed', 0.0),
        'result': progress_data.get('result', '')
    })
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

def run_enhancement_with_progress_table(command):
    """
    Run enhancement command with JSON progress parsing and table updates.

    Args:
        command: Shell command to run

    Returns:
        Tuple of (returncode, output_lines)
    """
    import pandas as pd

    # Enable JSON progress mode
    env = os.environ.copy()
    env['ENABLE_JSON_PROGRESS'] = 'true'

    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True,
        env=env
    )

    # Create placeholders for table and logs
    table_placeholder = st.empty()
    progress_placeholder = st.empty()
    log_placeholder = st.empty()

    output_lines = []
    error_lines = []

    # Read stdout and stderr concurrently
    import threading
    import queue

    stdout_queue = queue.Queue()
    stderr_queue = queue.Queue()

    def read_stdout():
        for line in iter(process.stdout.readline, ''):
            if line:
                stdout_queue.put(line)
        stdout_queue.put(None)  # Signal end

    def read_stderr():
        for line in iter(process.stderr.readline, ''):
            if line:
                stderr_queue.put(line)
        stderr_queue.put(None)  # Signal end

    # Start reader threads
    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    # Process output
    stdout_done = False
    stderr_done = False

    while not (stdout_done and stderr_done):
        # Check stdout for JSON progress
        try:
            line = stdout_queue.get(timeout=0.1)
            if line is None:
                stdout_done = True
            else:
                line = line.strip()
                output_lines.append(line)

                # Try to parse as JSON progress
                progress_data = parse_json_progress(line)
                if progress_data:
                    update_artist_progress(progress_data)

                    # Update progress table
                    if st.session_state.artist_progress_data:
                        df_data = []
                        for artist, data in st.session_state.artist_progress_data.items():
                            df_data.append({
                                'Artist': artist,
                                'Status': data['status'],
                                'Progress': f"{data['percent']:.0%}",
                                'Connections': data['connections'],
                                'Time (s)': f"{data['time_elapsed']:.1f}",
                                'Result': data['result']
                            })

                        df = pd.DataFrame(df_data)
                        table_placeholder.dataframe(
                            df,
                            use_container_width=True,
                            hide_index=True
                        )

                        # Update overall progress
                        total_processed = progress_data.get('total_processed', 0)
                        total_files = progress_data.get('total_files', 1)
                        overall_progress = total_processed / total_files if total_files > 0 else 0
                        progress_placeholder.progress(
                            overall_progress,
                            text=f"Processing: {total_processed}/{total_files} artists"
                        )
        except queue.Empty:
            pass

        # Check stderr for human-readable logs
        try:
            line = stderr_queue.get(timeout=0.1)
            if line is None:
                stderr_done = True
            else:
                line = line.strip()
                error_lines.append(line)
                st.session_state.enhancement_log_output.append(line)

                # Show last 20 lines of logs
                log_placeholder.text_area(
                    "Recent Logs",
                    "\n".join(st.session_state.enhancement_log_output[-20:]),
                    height=200
                )
        except queue.Empty:
            pass

        time.sleep(0.1)

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

    # Global process status indicator
    active_processes = []
    if st.session_state.get('discovery_running', False):
        active_processes.append("🔍 Artist Discovery")
    if st.session_state.get('running', False):
        active_processes.append("🖼️ Image Downloader")
    if st.session_state.get('running_generator', False):
        active_processes.append("📇 Artist Card Generator")
    if st.session_state.get('enhancement_running', False):
        active_processes.append("🧠 Biography Enhancement")

    if active_processes:
        st.info(f"🔄 Active processes: {', '.join(active_processes)}")

    # Create tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔍 Artist Discovery", "🖼️ Image Downloader", "📇 Artist Card Generator", "🧠 Biography Enhancement", "⚙️ Settings"])

    # Artist Discovery Pipeline Tab
    with tab1:
        st.header("🔍 Artist Discovery Pipeline")
        st.markdown("Unified workflow: Parse archive → Check vault → Spotify + Perplexity → Download image + Create card")

        # Information box
        with st.expander("ℹ️ About This Pipeline", expanded=False):
            st.markdown("""
            **Consolidated Workflow:**

            This tab combines three separate scripts into one streamlined process:

            1. **Parse Archive**: Extract artist names from WWOZ markdown files
            2. **Check Existence**: Verify if artist card exists in your Obsidian vault
            3. **Gather Data**:
               - Spotify: Genres, popularity, followers, image URL
               - Perplexity AI: Biography, musical connections, fun facts
            4. **Create/Update**: Download image + Build artist card
            5. **Network**: Maintain artist_connections.json graph

            **Smart Behavior:**
            - Skips artists with complete Perplexity-enhanced cards
            - Updates existing cards missing Perplexity data
            - Atomic operations: All-or-nothing per artist
            - Rate limiting: Respects API limits automatically
            """)

        # Initialize session state for discovery pipeline
        if 'discovery_running' not in st.session_state:
            st.session_state.discovery_running = False
        if 'discovery_log_output' not in st.session_state:
            st.session_state.discovery_log_output = []
        if 'discovery_stats' not in st.session_state:
            st.session_state.discovery_stats = {}

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Input & Configuration")

            # File uploader
            uploaded_archive = st.file_uploader(
                "Upload WWOZ Archive:",
                type=['md'],
                key="discovery_archive_uploader",
                help="Upload a markdown file containing WWOZ daily archive data"
            )

            # Handle uploaded file
            if uploaded_archive is not None:
                if 'discovery_temp_file' not in st.session_state or st.session_state.get('discovery_uploaded_file') != uploaded_archive:
                    # New file uploaded, save to temp location
                    if st.session_state.get('discovery_temp_file'):
                        cleanup_temp_file(st.session_state.discovery_temp_file)
                    st.session_state.discovery_temp_file = save_uploaded_file(uploaded_archive, "discovery")
                    st.session_state.discovery_uploaded_file = uploaded_archive

                archive_path = st.session_state.discovery_temp_file
                st.success(f"✅ Archive uploaded: {uploaded_archive.name}")
            else:
                archive_path = None

            st.markdown("**Vault Paths** (configured from user requirements)")

            # Display vault paths (hardcoded as requested)
            cards_dir_display = st.text_input(
                "Artist cards directory:",
                value="/Users/maxwell/LETSGO/MaxVault/01_Projects/PersonalArtistWiki/Artists",
                key="discovery_cards_dir",
                disabled=True,
                help="Artist markdown files location"
            )

            images_dir_display = st.text_input(
                "Artist images directory:",
                value="/Users/maxwell/LETSGO/MaxVault/03_Resources/source_material/ArtistPortraits",
                key="discovery_images_dir",
                disabled=True,
                help="Artist portrait images location"
            )

            st.markdown("**Options:**")
            col_opt1, col_opt2 = st.columns(2)

            with col_opt1:
                dry_run = st.checkbox(
                    "☐ Dry run (preview only)",
                    value=False,
                    key="discovery_dry_run",
                    help="Preview changes without creating/modifying files"
                )

            with col_opt2:
                force_process = st.checkbox(
                    "☐ Force re-process",
                    value=False,
                    key="discovery_force",
                    help="Re-process artists with existing Perplexity-enhanced cards"
                )

        with col2:
            st.subheader("Prerequisites")

            # Check API key
            perplexity_key = st.session_state.get('perplexity_api_key') or os.getenv('PERPLEXITY_API_KEY')

            if perplexity_key:
                st.success("✅ Perplexity API Key")
            else:
                st.error("❌ Perplexity API Key required")
                st.markdown("Configure in Settings tab or:")
                st.code("export PERPLEXITY_API_KEY='key'")

            # Check archive
            if archive_path:
                st.success("✅ Archive file uploaded")
            else:
                st.warning("⚠️ No archive uploaded")

            # Check directories
            if os.path.exists(cards_dir_display):
                st.success("✅ Cards directory exists")
            else:
                st.error("❌ Cards directory not found")

            if os.path.exists(images_dir_display):
                st.success("✅ Images directory exists")
            else:
                st.error("❌ Images directory not found")

            st.markdown("---")
            st.subheader("Actions")

            can_run = bool(perplexity_key and archive_path and os.path.exists(cards_dir_display))

            if st.button(
                "🚀 Start Discovery",
                type="primary",
                key="run_discovery",
                disabled=st.session_state.discovery_running or not can_run,
                use_container_width=True
            ):
                if can_run:
                    # Set environment variable
                    os.environ['PERPLEXITY_API_KEY'] = perplexity_key

                    # Build command
                    cmd = f"source venv/bin/activate && python artist_discovery_pipeline.py"
                    cmd += f' --archive "{archive_path}"'
                    cmd += f' --cards-dir "{cards_dir_display}"'
                    cmd += f' --images-dir "{images_dir_display}"'

                    if dry_run:
                        cmd += " --dry-run"
                    if force_process:
                        cmd += " --force"

                    st.session_state.discovery_running = True
                    st.session_state.discovery_log_output = []
                    st.session_state.discovery_stats = {}

                    # Run command
                    st.markdown("### 📊 Processing Progress")

                    progress_placeholder = st.empty()
                    log_placeholder = st.empty()

                    with st.spinner("Discovering and processing artists..."):
                        process = subprocess.Popen(
                            cmd,
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
                                line = line.strip()
                                output_lines.append(line)
                                st.session_state.discovery_log_output.append(line)

                                # Update log display
                                log_placeholder.text_area(
                                    "Recent Logs",
                                    "\n".join(st.session_state.discovery_log_output[-20:]),
                                    height=300
                                )

                                # Try to extract progress
                                if "Processing:" in line or "artist" in line.lower():
                                    match = re.search(r'(\d+)/(\d+)', line)
                                    if match:
                                        current, total = int(match.group(1)), int(match.group(2))
                                        progress = current / total
                                        progress_placeholder.progress(
                                            progress,
                                            text=f"Processing: {current}/{total} artists"
                                        )

                        process.wait()
                        st.session_state.discovery_running = False
                        returncode = process.returncode

                    if returncode == 0:
                        st.success("✅ Artist discovery pipeline completed successfully!")

                        # Parse summary statistics
                        summary_stats = {}
                        for line in output_lines:
                            if "✨ Created:" in line:
                                match = re.search(r'Created: (\d+)', line)
                                if match:
                                    summary_stats['created'] = int(match.group(1))
                            elif "✅ Enhanced:" in line:
                                match = re.search(r'Enhanced: (\d+)', line)
                                if match:
                                    summary_stats['enhanced'] = int(match.group(1))
                            elif "🔗 Connections found:" in line:
                                match = re.search(r'Connections found: (\d+)', line)
                                if match:
                                    summary_stats['connections'] = int(match.group(1))
                            elif "📚 Network size:" in line:
                                match = re.search(r'Network size: (\d+)', line)
                                if match:
                                    summary_stats['network_size'] = int(match.group(1))
                            elif "❌ Errors:" in line:
                                match = re.search(r'Errors: (\d+)', line)
                                if match:
                                    summary_stats['errors'] = int(match.group(1))
                            elif "🎯 Success rate:" in line:
                                match = re.search(r'Success rate: ([\d.]+)%', line)
                                if match:
                                    summary_stats['success_rate'] = float(match.group(1))

                        st.session_state.discovery_stats = summary_stats
                    else:
                        st.error(f"❌ Pipeline failed with error code {returncode}")
                else:
                    st.error("Prerequisites not met. Please check requirements above.")

        # Statistics display
        if st.session_state.discovery_stats:
            st.markdown("---")
            st.subheader("📊 Summary Statistics")
            stats = st.session_state.discovery_stats

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)

            with col_m1:
                if 'created' in stats:
                    st.metric("✨ Cards Created", stats['created'])
                if 'enhanced' in stats:
                    st.metric("✅ Cards Enhanced", stats['enhanced'])

            with col_m2:
                if 'connections' in stats:
                    st.metric("🔗 Connections", stats['connections'])
                if 'network_size' in stats:
                    st.metric("📚 Network Size", stats['network_size'])

            with col_m3:
                if 'errors' in stats:
                    st.metric("❌ Errors", stats['errors'])

            with col_m4:
                if 'success_rate' in stats:
                    st.metric("🎯 Success Rate", f"{stats['success_rate']:.1f}%")

        # Download logs button
        if st.session_state.discovery_log_output:
            log_content = "\n".join(st.session_state.discovery_log_output)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="📥 Download Log",
                data=log_content,
                file_name=f"artist_discovery_{timestamp}.txt",
                mime="text/plain"
            )

    # Image Downloader Tab
    with tab2:
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
                        st.stop()
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
                    st.session_state.downloader_result = None
                else:
                    st.error("Please provide both input file and output directory")
                    st.stop()

        # Persistent progress display (always shown when process is running or has completed)
        if st.session_state.running or st.session_state.log_output:
            st.markdown("---")
            st.subheader("📊 Progress")

            # Progress bar placeholder
            progress_placeholder = st.empty()

            # Log output area
            log_placeholder = st.empty()

            if st.session_state.running:
                # Build command from current values
                cmd = f"source venv/bin/activate && python spotify_image_downloader.py"
                cmd += f' --input "{input_file}"'
                cmd += f' --output "{output_dir}"'
                if skip_existing:
                    cmd += " --skip-existing"

                # Run command with progress updates
                with st.spinner("Downloading images..."):
                    def update_progress(value):
                        progress_placeholder.progress(value, text=f"Progress: {value:.0%}")

                    def update_log(line):
                        st.session_state.log_output.append(line)
                        # Show last 15 lines
                        log_placeholder.text_area(
                            "Log Output",
                            "\n".join(st.session_state.log_output[-15:]),
                            height=300,
                            key=f"log_downloader_{len(st.session_state.log_output)}"
                        )

                    returncode, output = run_command_with_progress(
                        cmd, update_progress, update_log
                    )
                    st.session_state.running = False
                    st.session_state.downloader_result = returncode

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
                # Show completed logs
                if st.session_state.log_output:
                    st.text_area(
                        "Log Output (Completed)",
                        "\n".join(st.session_state.log_output[-15:]),
                        height=300,
                        key="log_downloader_completed"
                    )

                    # Show result status
                    if st.session_state.get('downloader_result') == 0:
                        st.success("✅ Last run completed successfully")
                    elif st.session_state.get('downloader_result') is not None:
                        st.error(f"❌ Last run failed with error code {st.session_state.downloader_result}")

                    # Clear logs button
                    if st.button("🗑️ Clear Logs", key="clear_downloader_logs"):
                        st.session_state.log_output = []
                        st.session_state.downloader_result = None
                        st.rerun()
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
                        disabled=st.session_state.running_generator):
                if (artist_name or input_file_gen) and cards_output_dir:
                    # Validate the input file if using file mode
                    if input_file_gen and not artist_name:
                        is_valid, validation_message = validate_selected_file(input_file_gen)
                        if not is_valid:
                            st.error(f"❌ Invalid input file: {validation_message}")
                            st.stop()
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
                    st.session_state.running_generator = True
                    st.session_state.log_output_generator = []
                    st.session_state.generator_result = None
                else:
                    st.error("Please provide input (artist name or file) and output directory")
                    st.stop()

        # Persistent progress display (always shown when process is running or has completed)
        if st.session_state.running_generator or st.session_state.log_output_generator:
            st.markdown("---")
            st.subheader("📊 Progress")

            # Progress bar placeholder
            progress_placeholder = st.empty()

            # Log output area
            log_placeholder = st.empty()

            if st.session_state.running_generator:
                # Build command from current values
                cmd = f"source venv/bin/activate && python spotify_artist_card_generator.py"
                if artist_name:
                    cmd += f' --artist "{artist_name}"'
                else:
                    cmd += f' --input-file "{input_file_gen}"'
                cmd += f' --output-dir "{cards_output_dir}"'
                if images_output_dir:
                    cmd += f' --images-dir "{images_output_dir}"'
                cmd += f' --log-level {log_level}'

                # Run command with progress updates
                with st.spinner("Generating artist cards..."):
                    def update_progress(value):
                        progress_placeholder.progress(value, text=f"Progress: {value:.0%}")

                    def update_log(line):
                        st.session_state.log_output_generator.append(line)
                        # Show last 15 lines
                        log_placeholder.text_area(
                            "Log Output",
                            "\n".join(st.session_state.log_output_generator[-15:]),
                            height=300,
                            key=f"log_generator_{len(st.session_state.log_output_generator)}"
                        )

                    returncode, output = run_command_with_progress(
                        cmd, update_progress, update_log
                    )
                    st.session_state.running_generator = False
                    st.session_state.generator_result = returncode

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
                # Show completed logs
                if st.session_state.log_output_generator:
                    st.text_area(
                        "Log Output (Completed)",
                        "\n".join(st.session_state.log_output_generator[-15:]),
                        height=300,
                        key="log_generator_completed"
                    )

                    # Show result status
                    if st.session_state.get('generator_result') == 0:
                        st.success("✅ Last run completed successfully")
                    elif st.session_state.get('generator_result') is not None:
                        st.error(f"❌ Last run failed with error code {st.session_state.generator_result}")

                    # Clear logs button
                    if st.button("🗑️ Clear Logs", key="clear_generator_logs"):
                        st.session_state.log_output_generator = []
                        st.session_state.generator_result = None
                        st.rerun()
    # Biography Enhancement Tab
    with tab3:
        st.header("📚 Biography Enhancement with Perplexity AI")
        st.markdown("Enhance artist biographies using Perplexity AI with intelligent detection and recovery system")
        # Information box
        with st.expander("ℹ️ About This Tool", expanded=False):
            st.markdown("""
            **Three-Phase Enhancement System:**

            1. **Phase 1 - Detection**: Automatically identifies problematic Wikipedia matches (recipes, lists, genres instead of artists)
            2. **Phase 2 - Recovery**: Attempts to recover using Perplexity web search for better information
            3. **Phase 3 - Quarantine**: Moves unrecoverable cards to `problem-cards/` directory

            **Features:**
            - Real-time web search for up-to-date artist information
            - Native citation support for source verification
            - Artist relationship network extraction
            - Automatic backup of original files
            """)
        col1, col2 = st.columns([2, 1])
        with col1:
            with st.expander("⚙️ Configuration", expanded=True):
                # Artist cards directory
                cards_dir = st.text_input(
                    "Artist cards directory:",
                    value=st.session_state.config.get('artist_cards_dir', DEFAULT_ARTIST_CARDS_DIR),
                    key="enhancement_cards_dir",
                    help="Directory containing artist markdown files to enhance"
                )
                # Perplexity API key input
                api_key = st.text_input(
                    "Perplexity API Key:",
                    value=st.session_state.perplexity_api_key or os.getenv('PERPLEXITY_API_KEY', ''),
                    type="password",
                    key="perplexity_api_key_input",
                    help="Required for AI biography enhancement. Get your key at https://www.perplexity.ai/settings/api"
                )
                # Store API key in session state
                if api_key:
                    st.session_state.perplexity_api_key = api_key
                st.markdown("**Enhancement Options:**")
                col_a, col_b = st.columns(2)
                with col_a:
                    # Enhancement options
                    dry_run = st.checkbox(
                        "☐ Dry run (preview only)",
                        value=False,
                        key="enhancement_dry_run",
                        help="Preview changes without modifying files"
                    )
                    force_enhance = st.checkbox(
                        "☐ Force re-enhancement",
                        value=False,
                        key="enhancement_force",
                        help="Re-enhance files that have already been processed"
                    )
                with col_b:
                    skip_detection = st.checkbox(
                        "☐ Skip detection",
                        value=False,
                        key="enhancement_skip_detection",
                        help="Bypass problematic card detection (Phase 1)"
                    )
                    log_level = st.selectbox(
                        "Log level:",
                        ["INFO", "DEBUG", "WARNING", "ERROR"],
                        index=0,
                        key="enhancement_log_level"
                    )
            # Prerequisites validation
            with st.expander("✓ Prerequisites Check", expanded=True):
                # Check API key
                if api_key:
                    st.success("✅ Perplexity API Key provided")
                else:
                    st.error("❌ Perplexity API Key required")
                    st.markdown("**Setup Instructions:**")
                    st.code("export PERPLEXITY_API_KEY='your-api-key-here'")
                    st.markdown("Get your API key at: https://www.perplexity.ai/settings/api")
                # Check cards directory
                if os.path.exists(cards_dir):
                    md_files = list(Path(cards_dir).glob("*.md"))
                    if md_files:
                        # Estimate processing time
                        estimated_time = len(md_files) * 2  # 2 seconds per card
                        estimated_minutes = estimated_time / 60
                        st.success(f"✅ Found {len(md_files)} artist cards")
                        st.info(f"⏱️ Estimated time: ~{estimated_minutes:.1f} minutes (rate limited)")
                    else:
                        st.warning("⚠️ No markdown files found in directory")
                else:
                    st.error("❌ Artist cards directory not found")
        with col2:
            st.subheader("Actions")
            # Check if prerequisites are met
            can_run = bool(api_key and os.path.exists(cards_dir))
            # Run button
            col_btn1, col_btn2 = st.columns([1, 1])
            with col_btn1:
                if st.button(
                    "🚀 Start Enhancement",
                    type="primary",
                    key="run_enhancement",
                    disabled=st.session_state.enhancement_running or not can_run,
                    use_container_width=True
                ):
                    if can_run:
                        # Set environment variable for the subprocess
                        os.environ['PERPLEXITY_API_KEY'] = api_key
                        # Build command
                        cmd = f"source venv/bin/activate && python enhance_biographies_perplexity.py"
                        cmd += f' --cards-dir "{cards_dir}"'
                        if dry_run:
                            cmd += " --dry-run"
                        if force_enhance:
                            cmd += " --force"
                        if skip_detection:
                            cmd += " --skip-detection"
                        cmd += f" --log-level {log_level}"
                        st.session_state.enhancement_running = True
                        st.session_state.enhancement_log_output = []
                        st.session_state.enhancement_stats = {}
                        st.session_state.artist_progress_data = {}  # Reset progress data

                        # Run command with progress table
                        st.markdown("### 📊 Artist Progress")
                        returncode, output = run_enhancement_with_progress_table(cmd)
                        st.session_state.enhancement_running = False

                        # Export progress table button
                        if st.session_state.artist_progress_data:
                            df_data = []
                            for artist, data in st.session_state.artist_progress_data.items():
                                df_data.append({
                                    'Artist': artist,
                                    'Status': data['status'],
                                    'Progress': f"{data['percent']:.0%}",
                                    'Connections': data['connections'],
                                    'Time (s)': f"{data['time_elapsed']:.1f}",
                                    'Result': data['result']
                                })
                            df = pd.DataFrame(df_data)
                            csv_data = df.to_csv(index=False)
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                            st.download_button(
                                label="📥 Export Progress Table to CSV",
                                data=csv_data,
                                file_name=f"enhancement_progress_{timestamp}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )

                        if returncode == 0:
                            st.success("✅ Biography enhancement completed successfully!")
                            # Parse and display summary statistics
                            summary_stats = {}
                            for line in output:
                                # Enhanced count
                                if "✅ Enhanced:" in line:
                                    match = re.search(r'Enhanced: (\d+)', line)
                                    if match:
                                        summary_stats['enhanced'] = int(match.group(1))
                                # Problems detected
                                elif "🔍 Problems detected:" in line:
                                    match = re.search(r'Problems detected: (\d+)', line)
                                    if match:
                                        summary_stats['problems_detected'] = int(match.group(1))
                                # Recovered count
                                elif "✅ Recovered:" in line:
                                    match = re.search(r'Recovered: (\d+)', line)
                                    if match:
                                        summary_stats['recovered'] = int(match.group(1))
                                # Quarantined count
                                elif "⚠️ Quarantined:" in line:
                                    match = re.search(r'Quarantined: (\d+)', line)
                                    if match:
                                        summary_stats['quarantined'] = int(match.group(1))
                                # Connections found
                                elif "🔗 Connections found:" in line:
                                    match = re.search(r'Connections found: (\d+)', line)
                                    if match:
                                        summary_stats['connections'] = int(match.group(1))
                                # Network nodes
                                elif "📚 Network nodes:" in line:
                                    match = re.search(r'Network nodes: (\d+)', line)
                                    if match:
                                        summary_stats['network_nodes'] = int(match.group(1))
                                # Success rate
                                elif "🎯 Success rate:" in line:
                                    match = re.search(r'Success rate: ([\d.]+)%', line)
                                    if match:
                                        summary_stats['success_rate'] = float(match.group(1))
                            # Store stats for display
                            st.session_state.enhancement_stats = summary_stats
                        else:
                            st.error(f"❌ Enhancement failed with error code {returncode}")
                    else:
                        st.error("Prerequisites not met. Please check the requirements above.")
            with col_btn2:
                if st.button(
                    "⏹️ Stop",
                    key="stop_enhancement",
                    disabled=not st.session_state.enhancement_running,
                    use_container_width=True
                ):
                    st.warning("Stop functionality requires process management - use Ctrl+C in terminal")
            # Progress display
            if st.session_state.enhancement_running:
                st.info("🔄 Enhancement in progress...")
            # Download logs button
            if st.session_state.enhancement_log_output:
                log_content = "\n".join(st.session_state.enhancement_log_output)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    label="📥 Download Log",
                    data=log_content,
                    file_name=f"perplexity_enhancement_{timestamp}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
        # Statistics display
        if st.session_state.enhancement_stats:
            st.markdown("---")
            st.subheader("📊 Summary Statistics")
            stats = st.session_state.enhancement_stats
            # Create metrics in columns
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                if 'enhanced' in stats:
                    st.metric("✅ Enhanced", stats['enhanced'])
                if 'problems_detected' in stats:
                    st.metric("🔍 Problems Detected", stats['problems_detected'])
            with col_m2:
                if 'recovered' in stats:
                    st.metric("✅ Recovered", stats['recovered'])
                if 'quarantined' in stats:
                    st.metric("⚠️ Quarantined", stats['quarantined'])
            with col_m3:
                if 'connections' in stats:
                    st.metric("🔗 Connections", stats['connections'])
                if 'network_nodes' in stats:
                    st.metric("📚 Network Nodes", stats['network_nodes'])
            with col_m4:
                if 'success_rate' in stats:
                    st.metric("🎯 Success Rate", f"{stats['success_rate']:.1f}%")
            # Show link to quarantine directory if cards were quarantined
            if stats.get('quarantined', 0) > 0:
                quarantine_dir = Path(cards_dir) / "problem-cards"
                st.warning(f"⚠️ {stats['quarantined']} problematic cards moved to: `{quarantine_dir}`")
                st.info("💡 Review quarantined cards to verify detection accuracy or manually fix issues")
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
        # Perplexity API Key storage
        st.subheader("API Configuration")
        stored_api_key = st.text_input(
            "Perplexity API Key (for biography enhancement):",
            value=st.session_state.perplexity_api_key,
            type="password",
            help="This key is stored only for the current session and not saved to disk"
        )
        if stored_api_key != st.session_state.perplexity_api_key:
            st.session_state.perplexity_api_key = stored_api_key
        # Environment variable check
        env_api_key = os.getenv('PERPLEXITY_API_KEY')
        if env_api_key:
            st.success("✅ PERPLEXITY_API_KEY environment variable detected")
        elif stored_api_key:
            st.info("ℹ️ Using API key from session (not persistent)")
        else:
            st.warning("⚠️ No Perplexity API key configured")
            st.markdown("Get your API key at: https://www.perplexity.ai/settings/api")
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