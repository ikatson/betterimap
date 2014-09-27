#!/bin/bash

# Run all tests except integration test.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export PYTHONPATH="${SCRIPT_DIR}/../"

nosetests --exclude integration_test "${SCRIPT_DIR}" "${@}"
