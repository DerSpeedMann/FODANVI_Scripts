#!/usr/bin/env python3
"""
Main entry point for picamera module.

Usage:
    python -m picamera              # Start web server
    python -m picamera cli          # Start CLI interactive mode
    python -m picamera cli config.json output_folder
"""

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'cli':
        # Remove 'cli' from argv so camera_cli sees correct args
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from .camera_cli import main as cli_main
        cli_main()
    else:
        from .web_server import main as web_main
        web_main()


if __name__ == '__main__':
    main()
