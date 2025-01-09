import logging

from colorama import Fore, Style
from colorama import init as colorama_init


class ColoredLogFormatter(logging.Formatter):
    """Custom formatter that adds colors based on log level"""

    COLORS = {
        logging.DEBUG: Fore.BLUE,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        # Add color to the level name
        color = self.COLORS.get(record.levelno, Fore.WHITE)
        record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"

        # Add color to the module name
        record.name = f"{Fore.CYAN}{record.name}{Style.RESET_ALL}"

        return super().format(record)


def setup_logging(verbose: bool = False):
    colorama_init()

    # Create console handler with custom formatter
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        ColoredLogFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    root_logger.addHandler(console_handler)
