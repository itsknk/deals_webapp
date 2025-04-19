#!/bin/bash

echo "Creating virtual environment..."
python3 -m venv venv

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Creating .env file..."
cp .env.example .env

echo "✅ Setup complete. Now run:"
echo "source venv/bin/activate && python3 app.py"

