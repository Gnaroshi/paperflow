#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
package_root=$(dirname "$script_dir")
binary="${TMPDIR:-/tmp}/paperflow-showcase-boundary"
swiftc "$package_root/ShowcaseMode.swift" "$script_dir/main.swift" -o "$binary"
"$binary"
rm -f "$binary"
