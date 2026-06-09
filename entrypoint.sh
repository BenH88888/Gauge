#!/bin/sh
# Fix ownership of the mounted volume so appuser can write to it.
# This runs as root before dropping privileges to appuser.
mkdir -p /data
chown appuser:appuser /data

exec gosu appuser uvicorn gauge.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1
