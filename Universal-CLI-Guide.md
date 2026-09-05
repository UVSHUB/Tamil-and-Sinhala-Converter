# Universal CLI Guide (`sintam`)

This guide explains the new "Universal Package" architecture introduced to the SinTam Voice Translator, allowing anyone to run the full application (frontend + backend) using a single command, without needing Docker or Node.js.

## 🚀 The "One Line" Solution

If you want to run the application on any computer with Python installed, you no longer need to worry about complex setup scripts or Docker latency. 

You can install the entire application directly from GitHub using the Python package manager (`pip`):

```bash
pip install git+https://github.com/UVSHUB/Tamil-and-Sinhala-Converter.git
```

### Running the Application

Once installed, your system will globally register a new command. Simply open any terminal and type:

```bash
sintam
```

**What happens when you type `sintam`?**
1. The system automatically launches the Python backend (FastAPI) on port `8000`.
2. The backend will instantly serve the pre-compiled React User Interface.
3. You can open your browser to `http://localhost:8000` to start translating.

---

## 🏗️ Architectural Changes Made

To achieve this seamless experience, the following structural changes were implemented in the codebase:

### 1. Frontend Bundling
Instead of running a separate Vite dev server (`npm run dev`) on port `5173`, the React frontend was compiled into static HTML/CSS/JS assets (`frontend/dist`). 

### 2. FastAPI Static Mounting
The `backend/main.py` file was updated to use `fastapi.staticfiles.StaticFiles`. FastAPI now mounts the `frontend/dist` directory to the root URL (`/`). 
*   If a user navigates to `/api` or `/ws`, FastAPI handles the backend logic.
*   If a user navigates anywhere else, FastAPI serves the React UI.

### 3. Python Package Configuration (`pyproject.toml`)
The project's metadata was updated to declare it as an official Python package. 
*   **Dependencies:** `fastapi`, `uvicorn`, `websockets`, and `colorama` were added to the core requirements.
*   **Entrypoint:** We registered `sintam = "backend.cli:start"` in the `[project.scripts]` section. This is what tells the operating system to map the word `sintam` to our custom startup script.
*   **Package Data:** We instructed the `setuptools` build engine to explicitly include the `frontend/dist` files when someone downloads the package via `pip`.

### 4. Custom CLI Script (`backend/cli.py`)
We built a custom launcher script that handles starting the `uvicorn` server programmatically. It includes terminal styling (via `colorama`) to provide a clean, professional output when the server starts, and warns the developer if the frontend assets are missing.
