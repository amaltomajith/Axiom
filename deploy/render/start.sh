#!/bin/sh
# Restore the trader's SQLite store from the private Hugging Face dataset, keep backing it up, run the API, and save once more
# when the service stops (a deploy or restart), so the journal and track record survive.
python /app/dbsync.py restore
python /app/dbsync.py loop &
SYNC=$!
python -m axiom.api &
API=$!
trap 'kill -TERM $API 2>/dev/null; wait $API; kill $SYNC 2>/dev/null; python /app/dbsync.py once; exit 0' TERM INT
wait $API
kill $SYNC 2>/dev/null
python /app/dbsync.py once
