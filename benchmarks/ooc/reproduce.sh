#!/bin/sh
set -eu
ooc_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ooc_python=${OOC_PYTHON:-python3}
"$ooc_python" -B "$ooc_root/prepare_ewart.py"
exec "$ooc_python" -B "$ooc_root/ewart_transfer.py" "$@"
