#!/bin/sh
# Run every formatter
isort .
black .
prettier --write .
taplo fmt .
