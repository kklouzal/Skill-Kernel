#!/bin/sh
set -eu

load_secret_file() {
  target="$1"
  file_var="${target}_FILE"
  eval "file_path=\${$file_var:-}"
  if [ -z "$file_path" ]; then
    return
  fi
  eval "current_value=\${$target:-}"
  if [ -n "$current_value" ]; then
    echo "both $target and $file_var are set; choose one secret source" >&2
    exit 64
  fi
  if [ ! -r "$file_path" ]; then
    echo "$file_var points to an unreadable file: $file_path" >&2
    exit 66
  fi
  secret_value="$(cat "$file_path")"
  export "$target=$secret_value"
}

load_secret_file "SKILLKERNEL_DATABASE_URL"
load_secret_file "AUTOSKILL_DATABASE_URL"
load_secret_file "SKILLKERNEL_ADMIN_TOKEN"
load_secret_file "AUTOSKILL_WEB_ADMIN_TOKEN"

exec "$@"
