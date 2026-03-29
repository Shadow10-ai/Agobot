#!/usr/bin/env bash
# Render build script for AgoBot backend
set -e

echo "Installing Python dependencies..."
pip install -r requirements.prod.txt

echo "Build complete."
