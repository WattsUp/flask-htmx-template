#!/bin/sh
# Run every formatter
isort .
black .
npx prettier --write .
taplo fmt .
