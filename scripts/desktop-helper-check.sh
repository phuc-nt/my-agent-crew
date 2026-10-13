#!/usr/bin/env bash
# Compiles the desktop helper and runs its unit tests. The tests reach the machine only through
# a fake, so this never causes a system dialog. An optional argument names the tests to run:
#   scripts/desktop-helper-check.sh SocketServerTests
set -euo pipefail

package="$(dirname "$0")/../desktop-helper"

swift build --package-path "$package"
if [ "$#" -gt 0 ]; then
    swift test --package-path "$package" --filter "$1"
else
    swift test --package-path "$package"
fi
