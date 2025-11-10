# Python Template

> [!IMPORTANT]
> This is a Template for Python Projects. This is not a App.


> [!WARNING]
> This is a Python project template pre-configured with a robust logging setup, `pyproject.toml` validation, and helper scripts for development.

## Important: Configuration

Before running this project, you **must** update the `pyproject.toml` file with your project's specific information. The application will not run until these placeholder values are changed.

Edit `pyproject.toml` and modify the following fields:

```toml
[project]
name = "YOURPROJECTNAME"       # <-- Change this
version = "0.0.0"            # <-- Change this
description = "YOURPROJECTDESCRIPTION" # <-- Change this
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "black>=25.9.0",
    "isort>=7.0.0",
    "rich>=14.2.0",
    "toml>=0.10.2",
]
```

## Features

  * **Rich Logging:** Pre-configured logging using `rich` that outputs to both the console and a timestamped log file in the `./logs` directory.
  * **Configuration Validation:** A startup check in `_template.py` ensures that the default placeholder values in `pyproject.toml` have been updated.
  * **Automatic Cleanup:** Creates a temporary directory and file on startup, which are automatically removed when the application exits using `atexit`.
  * **Modern Packaging:** Uses `pyproject.toml` for project definition and `uv.lock` for pinned dependencies.
  * **Formatting:** Includes helper scripts for formatting code with `black` and `isort`.

## Getting Started

### Prerequisites

  * Python `>=3.13`
  * `uv` (Install with `pip install uv`)

### Installation & Setup

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/mrcool7387/PythonTemplate.git
    cd PythonTemplate
    ```

2.  **Configure the project:**

      * Edit `pyproject.toml` as described in the "Configuration" section above.

3.  **Create the virtual environment and install dependencies:**

      * This project is set up to use `uv` and expects a virtual environment at `.\.venv`.

    <!-- end list -->

    ```bash
    # Create the virtual environment
    uv venv

    # Activate the environment
    # Windows
    .\.venv\Scripts\activate
    # macOS/Linux
    source ./.venv/bin/activate

    # Install dependencies from the lock file
    uv sync
    ```

### Running the Application

To run the main example file:

```bash
uv run main.py
```

This will demonstrate the logger and print the paths to the automatically generated temporary file and directory.

## Scripts

This repository includes several Windows batch (`.cmd`) scripts to aid in development.

  * **`format-python.cmd`**: Formats Python files using `isort` and `black`.

    ```bash
    # Usage
    format-python main.py _template.py
    ```

  * **`upload.cmd`**: A helper to add, commit, and push all changes to Git.

    ```bash
    # Usage
    upload "Your commit message here"
    ```

  * **`mk.cmd`**: A utility to create a new, empty file or update the timestamp of an existing one.

    ```bash
    # Usage
    mk new_module.py
    ```

## Project Structure

```
.
├── .venv/                      # Virtual environment (expected by scripts)
├── logs/                       # Directory for log files (created automatically)
├── _classes.py                 # Defines custom exceptions (e.g., PyProjectError)
├── _template.py                # Core template logic (logging, config check, temp files)
├── main.py                     # Example entry point demonstrating template usage
├── format-python.cmd           # [SCRIPT] Formats Python code
├── mk.cmd                      # [SCRIPT] Creates an empty file
├── upload.cmd                  # [SCRIPT] Commits and pushes all changes
├── pyproject.toml              # Project configuration and dependencies
└── uv.lock                     # Locked dependencies for 'uv'
```

## Main Dependencies

The project's main dependencies are defined in `pyproject.toml` and locked in `uv.lock`:

  * **`black>=25.9.0`**: The uncompromising Python code formatter.
  * **`isort>=7.0.0`**: Sorts Python imports.
  * **`rich>=14.2.0`**: For rich text, beautiful formatting, and logging in the terminal.
  * **`toml>=0.10.2`**: For parsing the `pyproject.toml` file.

Sub-dependencies include `click`, `packaging`, `pygments`, `mdurl`, and others.