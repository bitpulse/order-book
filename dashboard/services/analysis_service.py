"""
Analysis Service Layer
Handles execution of analysis scripts and parsing their output
"""

import subprocess
import sys
import re
from typing import Dict, Any, Optional, Tuple
from utils.paths import BASE_DIR, LIVE_DIR


class AnalysisService:
    """Service for running analysis scripts"""

    def run_price_change_analysis(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Run price change analyzer

        Args:
            params: Analysis parameters (symbol, lookback, interval, etc.)

        Returns:
            Tuple of (success, mongodb_id, error_message)
        """
        try:
            symbol = params.get('symbol', 'SPX_USDT')
            lookback = params.get('lookback', '3h')
            interval = params.get('interval', '10s')
            top = params.get('top', 5)
            min_change = params.get('min_change', 0.1)

            # Build command
            script_path = LIVE_DIR / 'price_change_analyzer.py'

            if not script_path.exists():
                return False, None, f'Analyzer script not found: {script_path}'

            cmd = [
                sys.executable,
                str(script_path),
                '--symbol', symbol,
                '--lookback', lookback,
                '--interval', interval,
                '--top', str(top),
                '--min-change', str(min_change),
                '--output', 'json'
            ]

            # Run analyzer
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(BASE_DIR)
            )

            # Wait for completion (with timeout)
            stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout

            # Decode output
            output = stdout.decode('utf-8') if stdout else ''
            error_output = stderr.decode('utf-8') if stderr else ''

            # Log output for debugging
            print(f"=== Analysis Script Output ===")
            print(f"Return code: {process.returncode}")
            print(f"STDOUT:\n{output}")
            print(f"STDERR:\n{error_output}")
            print(f"==============================")

            if process.returncode != 0:
                return False, None, f'Analysis failed with return code {process.returncode}: {error_output}'

            # Extract MongoDB ID from stdout
            mongodb_id = self._extract_mongodb_id(output)

            if mongodb_id:
                return True, mongodb_id, None
            else:
                return False, None, 'Analysis completed but no MongoDB ID found in output'

        except subprocess.TimeoutExpired:
            return False, None, 'Analysis timeout (exceeded 5 minutes)'
        except Exception as e:
            return False, None, str(e)

    def run_whale_analysis(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Run whale events analyzer

        Args:
            params: Analysis parameters

        Returns:
            Tuple of (success, mongodb_id, error_message)
        """
        try:
            analysis_type = params.get('analysis_type', 'whale_events')
            symbol = params.get('symbol', 'SPX_USDT')
            lookback = params.get('lookback', '3h')
            top = params.get('top', 10)

            # Determine which script to run
            if analysis_type == 'market_orders':
                script_path = LIVE_DIR / 'top_market_orders_analyzer.py'
            elif analysis_type == 'market_intervals':
                script_path = LIVE_DIR / 'market_orders_analyzer.py'
            else:
                script_path = LIVE_DIR / 'whale_events_analyzer.py'

            if not script_path.exists():
                return False, None, f'Analyzer script not found: {script_path}'

            cmd = [
                sys.executable,
                str(script_path),
                '--symbol', symbol,
                '--lookback', lookback,
                '--top', str(top),
                '--output', 'json'
            ]

            # Add analysis-specific parameters
            if analysis_type == 'market_intervals':
                interval = params.get('interval', '1m')
                cmd.extend(['--interval', interval])

            # Run analyzer
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(BASE_DIR)
            )

            stdout, stderr = process.communicate(timeout=300)

            output = stdout.decode('utf-8') if stdout else ''
            error_output = stderr.decode('utf-8') if stderr else ''

            print(f"=== Whale Analysis Script Output ===")
            print(f"Return code: {process.returncode}")
            print(f"STDOUT:\n{output}")
            print(f"STDERR:\n{error_output}")
            print(f"====================================")

            if process.returncode != 0:
                return False, None, f'Analysis failed: {error_output}'

            mongodb_id = self._extract_mongodb_id(output)

            if mongodb_id:
                return True, mongodb_id, None
            else:
                return False, None, 'Analysis completed but no MongoDB ID found'

        except subprocess.TimeoutExpired:
            return False, None, 'Analysis timeout (exceeded 5 minutes)'
        except Exception as e:
            return False, None, str(e)

    def run_whale_monitor(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Run whale monitor

        Args:
            params: Monitor parameters

        Returns:
            Tuple of (success, mongodb_id, error_message)
        """
        try:
            symbol = params.get('symbol', 'SPX_USDT')
            threshold = params.get('threshold', 50000)

            script_path = LIVE_DIR / 'whale_monitor.py'

            if not script_path.exists():
                return False, None, f'Monitor script not found: {script_path}'

            cmd = [
                sys.executable,
                str(script_path),
                '--symbol', symbol,
                '--threshold', str(threshold),
                '--output', 'json',
                '--once'  # Run once and exit
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(BASE_DIR)
            )

            stdout, stderr = process.communicate(timeout=120)  # 2 minute timeout

            output = stdout.decode('utf-8') if stdout else ''
            error_output = stderr.decode('utf-8') if stderr else ''

            print(f"=== Whale Monitor Output ===")
            print(f"Return code: {process.returncode}")
            print(f"STDOUT:\n{output}")
            print(f"STDERR:\n{error_output}")
            print(f"============================")

            if process.returncode != 0:
                return False, None, f'Monitor failed: {error_output}'

            mongodb_id = self._extract_mongodb_id(output)

            if mongodb_id:
                return True, mongodb_id, None
            else:
                return False, None, 'Monitor completed but no MongoDB ID found'

        except subprocess.TimeoutExpired:
            return False, None, 'Monitor timeout (exceeded 2 minutes)'
        except Exception as e:
            return False, None, str(e)

    def _extract_mongodb_id(self, output: str) -> Optional[str]:
        """
        Extract MongoDB ID from script output

        Args:
            output: Script stdout

        Returns:
            MongoDB ID or None
        """
        # Look for "MongoDB ID: <id>" or "Saved to MongoDB with ID: <id>"
        patterns = [
            r'MongoDB ID: ([a-f0-9]{24})',
            r'Saved to MongoDB with ID: ([a-f0-9]{24})',
            r'ID: ([a-f0-9]{24})',
        ]

        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                return match.group(1)

        return None
