#!/bin/bash
# Commit all recent changes with a message passed as an argument.
# Usage: ./commit.sh "your commit message"
#
# The .githooks/pre-commit hook will auto-bump the CalVer version
# in ecalendar.py if it is part of the commit.

set -e

if [ -z "$1" ]; then
    echo "Usage: ./commit.sh \"commit message\""
    exit 1
fi

git add -A
git status
echo ""
read -p "Proceed with commit? [y/N] " confirm
if [[ "$confirm" != [yY] ]]; then
    echo "Aborted."
    git reset HEAD
    exit 1
fi

git commit -m "$1"
