"""Entry point for Librarian."""

import sys

from .app import run_app
from .config import Config
from .database import init_database


def main() -> int:
    """Main entry point for Librarian."""
    try:
        # Load configuration
        config = Config.load()

        # Initialize database
        init_database(config.get_index_path())

        # Run the application
        run_app(config)

        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
