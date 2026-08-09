#!/bin/bash
set -e

echo "=== Post-merge setup ==="

echo "→ Installing backend Python dependencies..."
cd backend
pip install -r requirements.txt --quiet
cd ..

echo "→ Installing frontend Node dependencies..."
cd frontend
npm install --legacy-peer-deps --silent
cd ..

echo "=== Post-merge setup complete ==="
