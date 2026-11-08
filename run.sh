#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  reset) script=/lab/database/setup.sql ;;
  load) script=/lab/sql/book.sql ;;
  inspect) script=/lab/sql/inspect.sql ;;
  check) script=/lab/sql/check.sql ;;
  *)
    echo 'Usage: bash /lab/run.sh {reset|load|inspect|check}' >&2
    exit 2
    ;;
esac

exec psql -X -U mobility -d mobility_l09 \
  --set=ON_ERROR_STOP=1 --set=VERBOSITY=verbose --file="$script"
