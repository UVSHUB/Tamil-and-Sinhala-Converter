#!/usr/bin/env bash

# ==============================================================================
# Sinhala ↔ Tamil Voice Translator - Developer Workspace Setup Script
# ==============================================================================

# Exit immediately if a command exits with a non-zero status
set -e

# Colored output utilities
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Starting Workspace Initialisation ===${NC}"

# ------------------------------------------------------------------------------
# 1. Environment Configuration Setup
# ------------------------------------------------------------------------------
if [ ! -f .env ]; then
    echo -e "${YELLOW}[!] Config file '.env' not found. Cloning from '.env.example'...${NC}"
    cp .env.example .env
    echo -e "${GREEN}[✓] '.env' created. Please edit it to insert your actual GEMINI_API_KEY.${NC}"
else
    echo -e "${GREEN}[✓] Existing '.env' configuration detected.${NC}"
fi

# ------------------------------------------------------------------------------
# 2. Python Virtual Environment Setup
# ------------------------------------------------------------------------------
echo -e "${BLUE}[*] Setting up Python virtual environment (minimum Python 3.11)...${NC}"
if [ ! -d .venv ]; then
    python3 -m venv .venv
    echo -e "${GREEN}[✓] Virtual environment '.venv' created.${NC}"
else
    echo -e "${GREEN}[✓] Existing '.venv' detected.${NC}"
fi

echo -e "${BLUE}[*] Activating virtual environment and updating dependencies...${NC}"
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}[✓] Python dependencies successfully installed.${NC}"

# ------------------------------------------------------------------------------
# 3. Node/React Dependency Setup
# ------------------------------------------------------------------------------
echo -e "${BLUE}[*] Installing Node packages for the React application...${NC}"
if [ -d frontend ]; then
    cd frontend
    npm install
    cd ..
    echo -e "${GREEN}[✓] Node dependencies successfully installed.${NC}"
else
    echo -e "${YELLOW}[!] Warning: 'frontend' directory not found. Skipping Node install.${NC}"
fi

echo -e "${GREEN}=== Workspace Initialisation Complete! ===${NC}"
echo -e "${YELLOW}Next Steps:${NC}"
echo -e " 1. Add your Google AI Studio key into your local '.env' file"
echo -e " 2. Activate virtual env: ${BLUE}source .venv/bin/activate${NC}"
echo -e " 3. Run development mode: ${BLUE}npm run dev:backend${NC} or ${BLUE}npm run docker:up${NC}"
