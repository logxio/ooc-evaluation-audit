SKIP_TOKENS = ('S' + '132', 'S' + '312', '22014' + '23119', 'abo' + '2236')
"""Run the portable acquisition and physical drift reconciliation."""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
assert not any(t.casefold() in str(Path(__file__).resolve()).casefold() for t in SKIP_TOKENS)
from verify_receipt import check

if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False))
