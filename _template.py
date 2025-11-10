from rich.traceback import install as rich_tcbck_install

rich_tcbck_install()
# ============================#

import atexit
import getpass
import logging
import os
import platform
import tempfile
from datetime import datetime
from pathlib import Path

import toml
from rich.logging import RichHandler

from _classes import PyProjectError


def _get_project_name() -> str:
    pyproject = toml.load(Path("./pyproject.toml"))
    return pyproject["project"]["name"]


# ensure logs directory exists and add a file handler alongside the RichHandler
logs_dir = Path("./logs")
logs_dir.mkdir(parents=True, exist_ok=True)
log_file = f"logs/{_get_project_name()}-{datetime.now().strftime("%d%m%Y%H%M%S")}-{platform.node()}.log"

file_handler = logging.FileHandler(Path(log_file), encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    "%(asctime)s @ %(name)s | %(levelname)s | %(message)s"
)
file_handler.setFormatter(file_formatter)

console_handler = RichHandler(rich_tracebacks=True)
console_handler.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG, handlers=[console_handler, file_handler])

LOGGER = logging.getLogger(_get_project_name())
LOGGER.debug("Logger initialized.")


def check_pyproject(path: Path = Path("./pyproject.toml")):
    if Path("./development.run").exists():
        LOGGER.warning("Development run detected. Skipping pyproject.toml checks.")
        return

    LOGGER.debug(f'Checking pyproject.toml at: "{path.resolve()}"')
    pyproject = toml.load(path)

    if pyproject["project"]["name"] == "YOURPROJECTNAME":
        LOGGER.error("The 'name' field in pyproject.toml is not set.")
        raise PyProjectError(
            "Please update the 'name' field in pyproject.toml to your project's name."
        )
    if pyproject["project"]["version"] == "0.0.0":
        LOGGER.error("The 'version' field in pyproject.toml is not set.")
        raise PyProjectError(
            "Please update the 'version' field in pyproject.toml to your project's version."
        )
    if pyproject["project"]["description"] == "YOURPROJECTDESCRIPTION":
        LOGGER.error("The 'description' field in pyproject.toml is not set.")
        raise PyProjectError(
            "Please update the 'description' field in pyproject.toml to your project's description."
        )


@atexit.register
def at_exit_cleanup():
    LOGGER.debug("Running at_exit cleanup.")
    try:
        os.rmdir(TMPDIR)
    except Exception as e:
        LOGGER.error(f"Error during cleanup of temporary directory: {e}")

    try:
        os.remove(TMPFILE)
    except Exception as e:
        LOGGER.error(f"Error during cleanup of temporary file: {e}")


TMPDIR = tempfile.mkdtemp(
    suffix=f"-{_get_project_name()}-{getpass.getuser()}-{platform.node()}"
)
LOGGER.info(f'Temporary directory created at: "{TMPDIR}"')

TMPFILE = tempfile.mkstemp(
    suffix=f"-{_get_project_name()}-{getpass.getuser()}-{platform.node()}.tmp",
)[1]
LOGGER.info(f'Temporary file created at: "{TMPFILE}"')


# ==== MAIN ==== #
check_pyproject(Path("./pyproject.toml"))