#!/bin/bash
set -euo pipefail

awk -F: '
  {
    key = $1
    value = substr($0, index($0, ":") + 1)
    gsub(/[[:space:]]/, "", key)
    gsub(/[[:space:]]/, "", value)
    if (key == "license-type" && value == "HASP") hasp = 1
    if (key == "issued-by-server" && value == "yes") issued = 1
  }
  END { exit !(hasp && issued) }
'