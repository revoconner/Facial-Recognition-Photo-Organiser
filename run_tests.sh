#!/bin/bash
# Test runner script for Linux/Mac

echo "================================================"
echo "Running Facial Recognition Photo Organizer Tests"
echo "================================================"

# Activate virtual environment
source venv/bin/activate

echo ""
echo "Running all tests with coverage..."
echo ""

# Run tests
python -m pytest

echo ""
echo "================================================"
echo "Test run complete!"
echo "Coverage report saved to: htmlcov/index.html"
echo "================================================"
