#!/bin/bash

tar -czvf ../recruiter-messager.tgz  --exclude-vcs --exclude='processed_messages.json' --exclude=token.json --exclude='.vscode' --exclude='*~' --exclude='.direnv' --exclude='playwright-*' --exclude='.mypy_cache' --exclude='.cache' --exclude='data' --exclude='credentials.json' --exclude='secrets/'  --exclude='*__pycache__*' --exclude='*.db' .
