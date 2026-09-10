#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$(cd "$(dirname "$0")/../lib" && pwd)/common.sh"
alembic upgrade head
