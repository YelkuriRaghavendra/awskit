#!/bin/bash

# Cleanup script to remove all cache and build artifacts

echo "🧹 Cleaning up Python cache and build artifacts..."

# Remove Python cache directories
echo "Removing __pycache__ directories..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Remove .pyc files
echo "Removing .pyc files..."
find . -type f -name "*.pyc" -delete 2>/dev/null

# Remove .pyo files
echo "Removing .pyo files..."
find . -type f -name "*.pyo" -delete 2>/dev/null

# Remove build directories
echo "Removing build directories..."
rm -rf build/
rm -rf dist/
rm -rf *.egg-info
rm -rf src/*.egg-info

# Remove pytest cache
echo "Removing pytest cache..."
rm -rf .pytest_cache/
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null

# Remove hypothesis cache
echo "Removing hypothesis cache..."
rm -rf .hypothesis/

# Remove mypy cache
echo "Removing mypy cache..."
rm -rf .mypy_cache/
find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null

# Remove ruff cache
echo "Removing ruff cache..."
rm -rf .ruff_cache/

# Remove coverage files
echo "Removing coverage files..."
rm -f .coverage
rm -rf htmlcov/
rm -f coverage.xml

# Remove tox cache (if using tox)
echo "Removing tox cache..."
rm -rf .tox/

# Remove pip cache (optional - uncomment if needed)
# echo "Clearing pip cache..."
# pip cache purge

echo "✅ Cleanup complete!"
echo ""
echo "Remaining files:"
ls -la
