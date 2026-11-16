# Sourced by hooks/run-hook: POSIX sh, no Python needed yet.

baton_python_ok() { # path
    [ -n "$1" ] || return 1
    env -u PYTHONHOME "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

baton_find_python() {
    BATON_PYTHON=${BATON_PYTHON:-${POD_PYTHON:-$HARNESS_PYTHON}} # the names before the renames still work
    if [ -n "$BATON_PYTHON" ]; then # a named interpreter that fails is reported, not silently replaced
        baton_python_ok "$BATON_PYTHON" && printf '%s\n' "$BATON_PYTHON" && return 0
        return 1
    fi
    for name in python3 python3.14 python3.13 python3.12 python3.11 python \
        ${BATON_COMMON_PYTHONS-/opt/homebrew/bin/python3 /usr/local/bin/python3}; do
        found=$(command -v "$name" 2>/dev/null) || continue
        baton_python_ok "$found" && printf '%s\n' "$found" && return 0
    done
    # Windows: the `py` launcher names the real interpreter; `python3` there is often the Store stub.
    if command -v py >/dev/null 2>&1; then
        found=$(py -3 -c 'import sys; print(sys.executable)' 2>/dev/null | tr -d '\r')
        baton_python_ok "$found" && printf '%s\n' "$found" && return 0
    fi
    return 1
}
