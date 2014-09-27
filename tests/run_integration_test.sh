#!/bin/bash

# Run only integration test.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SECRETS_FILE="${SCRIPT_DIR}/secrets"

export PYTHONPATH="${SCRIPT_DIR}/../"

# If there's not secrets file, assume environment provided by the caller.
[[ -e "${SECRETS_FILE}" ]] && source "${SECRETS_FILE}"

nosetests "${SCRIPT_DIR}"/integration_test.py "${@}"
