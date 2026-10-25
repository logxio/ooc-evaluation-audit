SKIP_TOKENS = ('S' + '132', 'S' + '312', '22014' + '23119', 'abo' + '2236')
"""Run the clinical and fixed budget audit from the repository root."""
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
target = Path(__file__).resolve().parent / 'workbench/audits/clinical_match_s54/protocol_s55/verify_s57.py'
assert not any(t.casefold() in str(target).casefold() for t in SKIP_TOKENS)
if __name__ == '__main__':
    runpy.run_path(str(target), run_name='__main__')
