import os
import sys
import uvicorn
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False

from backend.config.settings import settings

def start():
    """
    Entry point for the global `sintam` CLI command.
    Runs the FastAPI backend and serves the compiled React frontend.
    """
    
    # Check if frontend is built
    project_root = os.path.dirname(os.path.dirname(__file__))
    frontend_dist = os.path.join(project_root, "frontend", "dist")
    
    if HAS_COLORAMA:
        print(f"{Fore.CYAN}{Style.BRIGHT}==========================================")
        print(f"{Fore.CYAN}{Style.BRIGHT}   SinTam Voice Translator Launcher")
        print(f"{Fore.CYAN}{Style.BRIGHT}==========================================\n")

        if not os.path.exists(frontend_dist):
            print(f"{Fore.YELLOW}WARNING: {Fore.RESET}Frontend 'dist' folder not found at {frontend_dist}")
            print("The frontend UI will not be served.")
            print("Please run 'npm install' and 'npm run build' inside the 'frontend' directory first.\n")
        else:
            print(f"{Fore.GREEN}✓ Frontend package found. UI will be served on port {settings.BACKEND_PORT}.\n")
            
        print(f"Starting server at {Fore.GREEN}http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}")
        print(f"Press {Fore.RED}Ctrl+C{Fore.RESET} to stop.\n")
    else:
        print("==========================================")
        print("   SinTam Voice Translator Launcher")
        print("==========================================\n")
        
        if not os.path.exists(frontend_dist):
            print("WARNING: Frontend 'dist' folder not found.")
        else:
            print(f"Frontend package found. UI will be served on port {settings.BACKEND_PORT}.\n")
            
        print(f"Starting server at http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}")

    
    uvicorn.run(
        "backend.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    start()
