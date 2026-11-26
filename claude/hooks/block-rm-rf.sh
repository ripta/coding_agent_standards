#!/bin/bash
# PreToolUse hook on Bash, cg_run, and cg_run_many: deny `rm` when one invocation has both a
# recursive and a force flag. rm-rf.py does the work. Its reason looks at each operand on disk, and
# suggests `unlink` for a file or symlink and `rmdir` for an empty directory.
#
# The wrapper has no prefilter on the command text. The scanner joins quoted pieces and drops
# backslashes, so `r''m -rf x` is an `rm`, and no glob over the raw payload lets it by safely. Python
# starts for every call, at about 35 ms. Python reads the payload itself, from stdin.

exec python3 "$(dirname "$0")/rm-rf.py"
