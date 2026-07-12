#!/bin/sh
set -eu
binary="${TMPDIR:-/tmp}/paperflow-showcase-boundary"
swiftc ShowcaseMode.swift Tests/main.swift -o "$binary"
"$binary"
rm -f "$binary"
