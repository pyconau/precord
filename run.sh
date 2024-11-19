#!/bin/bash

cd ~/precord
export PATH=~/.local/bin:$PATH

. env.sh

exec uv run gunicorn precord.web:app \
    --access-logfile - \
    --bind unix:/tmp/precord.sock \
    --error-log - \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker