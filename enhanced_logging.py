#!/usr/bin/env python3
"""
Enhanced Logging System for Spotify Artist Tools

Provides robust real-time logging with:
- Color-coded log entries
- Search and filtering capabilities
- Persistent log storage
- Process management with stop/start controls
- Real-time progress tracking
"""

import os
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import tempfile
import streamlit as st

# Configuration
LOG_BUFFER_SIZE = 1000
LOG_UPDATE_INTERVAL = 0.5  # seconds
TEMP_LOG_DIR = Path(tempfile.gettempdir()) / "streamlit_logs"
TEMP_LOG_DIR.mkdir(exist_ok=True)

class EnhancedLogger:
    """Enhanced logging system with real-time updates and persistence."""

    def __init__(self, name: str, max_entries: int = LOG_BUFFER_SIZE):
        self.name = name
        self.max_entries = max_entries
        self.entries = []
        self.log_file = None
        self.stats = {'info': 0, 'error': 0, 'success': 0, 'warning': 0, 'total': 0}
        self._create_log_file()

    def _create_log_file(self):
        """Create persistent log file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = TEMP_LOG_DIR / f"{self.name}_{timestamp}.log"
        if 'log_files' not in st.session_state:
            st.session_state.log_files = {}
        st.session_state.log_files[self.name] = str(self.log_file)

    def add_entry(self, message: str, level: str = "INFO"):
        """Add log entry with timestamp and level."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = {
            'timestamp': timestamp,
            'level': level.upper(),
            'message': message,
            'color': self._get_color(level)
        }

        self.entries.append(entry)
        level_key = level.lower()
        if level_key in self.stats:
            self.stats[level_key] += 1
        self.stats['total'] += 1

        # Maintain buffer size
        if len(self.entries) > self.max_entries:
            self.entries.pop(0)

        # Write to persistent file
        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{timestamp}] {level}: {message}\n")
            except Exception:
                pass  # Ignore file write errors

    def _get_color(self, level: str) -> str:
        """Get color for log level."""
        colors = {
            'INFO': '#1f77b4',      # Blue
            'ERROR': '#d62728',     # Red
            'SUCCESS': '#2ca02c',   # Green
            'WARNING': '#ff7f0e',   # Orange
            'DEBUG': '#9467bd'      # Purple
        }
        return colors.get(level.upper(), '#333333')

    def get_filtered_entries(self, search_term: str = "", filters: Dict[str, bool] = None) -> List[Dict]:
        """Get filtered log entries."""
        if filters is None:
            filters = {'show_info': True, 'show_error': True, 'show_success': True, 'show_warning': True}

        filtered = []
        for entry in self.entries:
            # Level filter
            level_key = f"show_{entry['level'].lower()}"
            if level_key in filters and not filters[level_key]:
                continue

            # Search filter
            if search_term and search_term.lower() not in entry['message'].lower():
                continue

            filtered.append(entry)

        return filtered

    def clear(self):
        """Clear all log entries and reset stats."""
        self.entries.clear()
        self.stats = {'info': 0, 'error': 0, 'success': 0, 'warning': 0, 'total': 0}

class ProcessManager:
    """Manages subprocess execution with stop/start control."""

    def __init__(self):
        self.processes = {}
        self.monitors = {}

    def start_process(self, process_id: str, command: str, logger: EnhancedLogger,
                     progress_callback: Optional[Callable] = None,
                     completion_callback: Optional[Callable] = None) -> bool:
        """Start a new subprocess with monitoring."""
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                preexec_fn=os.setsid  # Create new process group
            )

            self.processes[process_id] = process

            if 'active_processes' not in st.session_state:
                st.session_state.active_processes = {}

            st.session_state.active_processes[process_id] = {
                'pid': process.pid,
                'command': command,
                'start_time': datetime.now(),
                'status': 'running'
            }

            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=self._monitor_process,
                args=(process_id, process, logger, progress_callback, completion_callback),
                daemon=True
            )
            monitor_thread.start()
            self.monitors[process_id] = monitor_thread

            logger.add_entry(f"Started process: {command}", "INFO")
            return True

        except Exception as e:
            logger.add_entry(f"Failed to start process: {str(e)}", "ERROR")
            return False

    def stop_process(self, process_id: str, logger: EnhancedLogger) -> bool:
        """Stop a running process gracefully."""
        if process_id not in self.processes:
            logger.add_entry(f"Process {process_id} not found", "WARNING")
            return False

        process = self.processes[process_id]

        try:
            # Try graceful termination first
            logger.add_entry(f"Stopping process {process_id} (PID: {process.pid})", "INFO")

            if hasattr(process, 'pid') and process.pid:
                # Kill entire process group
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)

                # Wait for graceful shutdown
                try:
                    process.wait(timeout=5)
                    logger.add_entry(f"Process {process_id} stopped gracefully", "SUCCESS")
                except subprocess.TimeoutExpired:
                    # Force kill if still running
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    process.wait()
                    logger.add_entry(f"Process {process_id} force killed", "WARNING")

            # Clean up
            if 'active_processes' in st.session_state and process_id in st.session_state.active_processes:
                st.session_state.active_processes[process_id]['status'] = 'stopped'

            return True

        except Exception as e:
            logger.add_entry(f"Error stopping process {process_id}: {str(e)}", "ERROR")
            return False

    def _monitor_process(self, process_id: str, process: subprocess.Popen,
                       logger: EnhancedLogger, progress_callback: Optional[Callable] = None,
                       completion_callback: Optional[Callable] = None):
        """Monitor process output and status."""
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    line = line.strip()
                    if line:
                        # Determine log level based on content
                        level = "INFO"
                        line_lower = line.lower()
                        if "error" in line_lower or "failed" in line_lower:
                            level = "ERROR"
                        elif "success" in line_lower or "completed" in line_lower:
                            level = "SUCCESS"
                        elif "warning" in line_lower:
                            level = "WARNING"

                        logger.add_entry(line, level)

                        # Update progress if callback provided
                        if progress_callback:
                            import re
                            match = re.search(r'(\d+)/(\d+)', line)
                            if match:
                                current, total = int(match.group(1)), int(match.group(2))
                                progress = current / total
                                progress_callback(progress)

            # Process completed
            returncode = process.wait()

            if 'active_processes' in st.session_state and process_id in st.session_state.active_processes:
                st.session_state.active_processes[process_id]['status'] = 'completed'
                st.session_state.active_processes[process_id]['return_code'] = returncode

            if returncode == 0:
                logger.add_entry(f"Process {process_id} completed successfully", "SUCCESS")
            else:
                logger.add_entry(f"Process {process_id} failed with code {returncode}", "ERROR")

            if completion_callback:
                completion_callback(returncode)

        except Exception as e:
            logger.add_entry(f"Error monitoring process {process_id}: {str(e)}", "ERROR")
            if 'active_processes' in st.session_state and process_id in st.session_state.active_processes:
                st.session_state.active_processes[process_id]['status'] = 'error'

def cleanup_old_logs(max_age_hours: int = 24):
    """Clean up old log files."""
    try:
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        for log_file in TEMP_LOG_DIR.glob("*.log"):
            if log_file.stat().st_mtime < cutoff_time:
                log_file.unlink()
    except Exception:
        pass  # Ignore cleanup errors

def render_enhanced_log_display(logger: EnhancedLogger, container_key: str):
    """Render enhanced log display with filtering and controls."""

    # Initialize session state for filters if not exists
    if 'log_filters' not in st.session_state:
        st.session_state.log_filters = {
            'show_info': True,
            'show_error': True,
            'show_success': True,
            'show_warning': True
        }
    if 'log_search' not in st.session_state:
        st.session_state.log_search = ""

    # Log controls
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        search_term = st.text_input(
            "🔍 Search logs:",
            value=st.session_state.log_search,
            key=f"log_search_{container_key}",
            placeholder="Filter log entries..."
        )
        st.session_state.log_search = search_term

    with col2:
        # Ensure all required filter keys exist
        default_filters = {
            'show_info': True,
            'show_error': True,
            'show_success': True,
            'show_warning': True
        }
        filters = {**default_filters, **st.session_state.log_filters}

        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        with filter_col1:
            filters['show_info'] = st.checkbox("ℹ️ Info", value=filters['show_info'], key=f"info_{container_key}")
        with filter_col2:
            filters['show_error'] = st.checkbox("❌ Error", value=filters['show_error'], key=f"error_{container_key}")
        with filter_col3:
            filters['show_success'] = st.checkbox("✅ Success", value=filters['show_success'], key=f"success_{container_key}")
        with filter_col4:
            filters['show_warning'] = st.checkbox("⚠️ Warning", value=filters['show_warning'], key=f"warning_{container_key}")

        st.session_state.log_filters = filters

    with col3:
        if st.button("🗑️ Clear", key=f"clear_{container_key}"):
            logger.clear()

    # Stats display
    if logger.stats['total'] > 0:
        stats_col1, stats_col2, stats_col3, stats_col4, stats_col5 = st.columns(5)
        with stats_col1:
            st.metric("Total", logger.stats['total'])
        with stats_col2:
            st.metric("Info", logger.stats['info'])
        with stats_col3:
            st.metric("Errors", logger.stats['error'])
        with stats_col4:
            st.metric("Success", logger.stats['success'])
        with stats_col5:
            st.metric("Warnings", logger.stats['warning'])

    # Log display
    filtered_entries = logger.get_filtered_entries(search_term, filters)

    if filtered_entries:
        # Show recent entries first
        recent_entries = filtered_entries[-50:]  # Show last 50 entries

        log_container = st.container(border=True)
        with log_container:
            st.markdown("**📋 Live Log Feed**")

            # Create scrollable log display
            log_html = ""
            for entry in reversed(recent_entries):  # Most recent first
                timestamp = entry['timestamp']
                level = entry['level']
                message = entry['message']
                color = entry['color']

                # Escape HTML in message
                import html
                message = html.escape(message)

                log_html += f"""
                <div style="margin: 2px 0; padding: 4px 8px; border-left: 3px solid {color};
                           background-color: rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.1);">
                    <span style="font-weight: bold; color: {color};">[{timestamp}] {level}:</span>
                    <span style="font-family: monospace; color: #333;">{message}</span>
                </div>
                """

            st.markdown(log_html, unsafe_allow_html=True)

            if len(filtered_entries) > 50:
                st.info(f"Showing last 50 of {len(filtered_entries)} entries")
    else:
        st.info("No log entries match current filters")

    # Download button
    if logger.entries:
        log_content = "\n".join([f"[{entry['timestamp']}] {entry['level']}: {entry['message']}"
                                for entry in logger.entries])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        st.download_button(
            label="📥 Download Full Log",
            data=log_content,
            file_name=f"{logger.name}_log_{timestamp}.txt",
            mime="text/plain",
            key=f"download_{container_key}"
        )

def render_process_control_panel(process_manager: ProcessManager, process_id: str, logger: EnhancedLogger):
    """Render process control panel with start/stop buttons."""

    # Initialize active_processes if not exists
    if 'active_processes' not in st.session_state:
        st.session_state.active_processes = {}

    process_info = st.session_state.active_processes.get(process_id)

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if process_info and process_info['status'] == 'running':
            if st.button(f"⏹️ Stop {process_id}", type="secondary", key=f"stop_{process_id}"):
                process_manager.stop_process(process_id, logger)
                st.rerun()
        else:
            st.button(f"⏹️ Stop {process_id}", disabled=True, key=f"stop_{process_id}_disabled")

    with col2:
        if process_info:
            status = process_info['status']
            if status == 'running':
                st.success("🟢 Running")
            elif status == 'completed':
                st.info("🔵 Completed")
            elif status == 'stopped':
                st.warning("🟡 Stopped")
            elif status == 'error':
                st.error("🔴 Error")
        else:
            st.info("🔵 Not Started")

    with col3:
        if process_info:
            start_time = process_info.get('start_time')
            if start_time:
                if isinstance(start_time, str):
                    start_time = datetime.fromisoformat(start_time)
                elapsed = datetime.now() - start_time
                st.text(f"Runtime: {str(elapsed).split('.')[0]}")
                if process_info.get('pid'):
                    st.text(f"PID: {process_info['pid']}")

def create_enhanced_progress_display(progress_value: float = 0.0,
                                   current_item: str = "",
                                   eta_minutes: Optional[float] = None,
                                   items_per_minute: Optional[float] = None):
    """Create enhanced progress display with ETA and speed metrics."""

    # Progress text with ETA
    progress_text = current_item
    if eta_minutes is not None:
        if eta_minutes < 1:
            eta_str = f"{int(eta_minutes * 60)}s"
        else:
            eta_str = f"{int(eta_minutes)}m {int((eta_minutes % 1) * 60)}s"
        progress_text += f" - ETA: {eta_str}"

    # Create progress bar
    progress_bar = st.progress(progress_value, text=progress_text)

    # Performance metrics
    if items_per_minute is not None:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Processing Speed", f"{items_per_minute:.1f} items/min")
        with col2:
            st.metric("Progress", f"{progress_value:.1%}")

    return progress_bar