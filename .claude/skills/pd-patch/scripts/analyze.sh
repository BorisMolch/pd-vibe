#!/bin/bash
# Analyze a Pure Data patch and output the DSL
# Usage: analyze.sh <file.pd>

PD2IR="/Users/borismo/pdpy/pd2ir"

if [ -z "$1" ]; then
    echo "Usage: analyze.sh <file.pd>"
    exit 1
fi

if [ ! -f "$1" ]; then
    echo "Error: File not found: $1"
    exit 1
fi

"$PD2IR" "$1"
