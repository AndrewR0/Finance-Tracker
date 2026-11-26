#!/bin/sh
# Back up the live database into data/backups/, keeping the newest 30.
# Uses the app's own backup script (SQLite's backup API), so it's safe while the app runs.
# Run from the finance-tracker folder:  sh deploy/backup.sh
cd "$(dirname "$0")/.." || exit 1
docker compose exec -T finance python -c "
import sys; sys.path.insert(0, 'scripts')
from pathlib import Path
from backup import backup
print('Backed up to', backup(Path('/data/finance.db'), Path('/data/backups')))
"
