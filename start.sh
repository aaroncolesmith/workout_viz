#!/bin/bash
# Unified Start Script for Workout Viz
# Handles Backend (FastAPI) and Frontend (Vite)

# Setup colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
ORANGE='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🏃 Initializing Workout Viz...${NC}"

# Stop any dangling processes on our ports
echo -e "${ORANGE}  → Cleaning up existing processes...${NC}"
lsof -ti:8001 | xargs kill -9 2>/dev/null
lsof -ti:5173 | xargs kill -9 2>/dev/null
lsof -ti:5174 | xargs kill -9 2>/dev/null

# Ensure .env exists
if [ ! -f .env ]; then
    echo -e "${ORANGE}  → Creating .env from template...${NC}"
    cp .env.example .env
fi

# Start Backend
echo -e "${BLUE}  → Starting FastAPI backend on port 8001...${NC}"
./venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload > backend.log 2>&1 &
BACKEND_PID=$!

# Start Frontend
echo -e "${BLUE}  → Starting Vite frontend...${NC}"
cd frontend
npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

# Wait for a moment to let things spin up
sleep 3

echo -e "\n${GREEN}✅ Workout Viz is ready!${NC}"
echo -e "${BLUE}   Dashboard: ${NC} http://localhost:5173"
echo -e "${BLUE}   API Docs:  ${NC} http://localhost:8001/docs"
echo -e "${BLUE}   Logs:      ${NC} tail -f backend.log frontend.log"
echo -e "\nPress ${ORANGE}Ctrl+C${NC} to shut down both servers safely."

# Graceful shutdown
cleanup() {
    echo -e "\n${ORANGE}🛑 Shutting down Workout Viz...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Stay alive while processes are running
wait
