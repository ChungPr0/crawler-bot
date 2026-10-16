import sys
from pathlib import Path
from loguru import logger

# Ensure Windows terminal handles UTF-8 emojis without charmap error
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Remove default handler
logger.remove()

# Output formats
CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | "
    "{level: <8} | "
    "{name}:{line} - {message}"
)


def setup_logger(log_dir: str = "logs", log_level: str = "INFO"):
    """
    Configure Loguru logger with console output and rotating file storage.
    
    :param log_dir: Directory where logs should be stored
    :param log_level: Minimum logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    app_log_file = log_path / "app.log"
    error_log_file = log_path / "error.log"

    # Console output (colorized)
    logger.add(
        sys.stdout,
        level=log_level,
        format=CONSOLE_FORMAT,
        colorize=True,
        enqueue=True,
    )

    # General app log with daily rotation and 10MB limit
    logger.add(
        str(app_log_file),
        level=log_level,
        format=FILE_FORMAT,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
    )

    # Error-specific log file for troubleshooting
    logger.add(
        str(error_log_file),
        level="ERROR",
        format=FILE_FORMAT,
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
    )

    logger.info(f"Logger initialized. Level: {log_level}, Log dir: {log_dir}")
    return logger

