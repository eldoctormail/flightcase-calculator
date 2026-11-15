"""Main entry point for LBD Flightcase Maker application."""

import sys
from PySide6.QtGui import QSurfaceFormat
from flightcase.ui import run_app


def main() -> int:
    """Launch the LBD Flightcase Maker PySide6 application."""
    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(fmt)
    return run_app()


if __name__ == "__main__":
    sys.exit(main())
