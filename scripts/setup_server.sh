#!/bin/bash

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting LongBridge Auto Deal Server Setup...${NC}"

# Navigate to project root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 1. System Dependency Check & Installation
echo -e "\n${YELLOW}[1/4] Checking system dependencies...${NC}"

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    echo "Detected OS: $OS"
else
    echo "Cannot detect OS. Assuming standard Linux environment."
fi

if command -v apt-get &> /dev/null; then
    # Debian/Ubuntu
    echo "Installing Python3 dependencies for Debian/Ubuntu..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv git
elif command -v yum &> /dev/null; then
    # CentOS/RHEL/Alibaba Cloud Linux
    echo "Installing Python3 dependencies for CentOS/RHEL..."
    sudo yum install -y python3 python3-pip git
else
    echo -e "${RED}Warning: Package manager not found. Please ensure Python 3.8+ and venv are installed manually.${NC}"
fi

# Check Python version
echo "Checking Python version..."
if command -v python3 &> /dev/null; then
    python3 -c "import sys; print(f'Current Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); exit(0) if sys.version_info >= (3, 8) else exit(1)"
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Python 3.8 or higher is required.${NC}"
        exit 1
    fi
else
    echo -e "${RED}Error: Python 3 could not be found.${NC}"
    exit 1
fi

# 2. Python Virtual Environment
echo -e "\n${YELLOW}[2/4] Setting up Python virtual environment...${NC}"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to create venv. Please install python3-venv package.${NC}"
        exit 1
    fi
else
    echo "Virtual environment already exists."
fi

# Install requirements using venv python directly
echo "Installing Python dependencies..."
./venv/bin/python3 -m pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    ./venv/bin/pip install -r requirements.txt
else
    echo -e "${RED}Error: requirements.txt not found!${NC}"
    exit 1
fi

# 3. Configuration Setup
echo -e "\n${YELLOW}[3/4] Configuring environment variables...${NC}"

CONFIG_ENV="config/.env"
ROOT_ENV=".env"
EXAMPLE_ENV="config/.env.example"

if [ -f "$CONFIG_ENV" ]; then
    echo "Configuration file $CONFIG_ENV already exists."
elif [ -f "$ROOT_ENV" ]; then
    echo "Found root .env file. It will be used as fallback."
    echo "Recommended: Copy it to config/.env for better organization."
else
    if [ -f "$EXAMPLE_ENV" ]; then
        echo "Creating $CONFIG_ENV from example..."
        cp "$EXAMPLE_ENV" "$CONFIG_ENV"
        echo -e "${GREEN}Created $CONFIG_ENV${NC}"
        echo -e "${RED}IMPORTANT: You must edit config/.env and add your LongBridge API keys!${NC}"
    else
        echo -e "${RED}Warning: .env.example not found in config/ directory.${NC}"
    fi
fi

# 4. Finalize
echo -e "\n${YELLOW}[4/4] Finalizing setup...${NC}"

# Make scripts executable
chmod +x scripts/*.sh

echo -e "\n${GREEN}Setup completed successfully!${NC}"
echo -e "Next steps:"
echo -e "1. Edit configuration: ${YELLOW}vim config/.env${NC}"
echo -e "2. Start services:     ${YELLOW}./scripts/start_all.sh${NC}"
