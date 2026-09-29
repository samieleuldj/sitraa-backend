#!/bin/bash

# Start FastAPI application
echo "Starting FastAPI server..."
uvicorn src.main:app --host 0.0.0.0 --port 8000

