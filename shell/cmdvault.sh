# cmdvault shell integration — source this from ~/.bashrc or ~/.zshrc:
#   source /path/to/plugin-for-claude/shell/cmdvault.sh
#
# Provides:
#   ccmd [-p]     fuzzy-pick a captured command (prints it + copies to clipboard)
#   Ctrl-X Ctrl-R insert a picked command directly into the current prompt line

# --- resolve the plugin root (directory containing scripts/, shell/, hooks/) ---
_cmdvault_src=""
if [ -n "${BASH_VERSION:-}" ] && [ -n "${BASH_SOURCE:-}" ]; then
    _cmdvault_src="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
    # %N expands to the name of the file being sourced in zsh
    eval '_cmdvault_src="${(%):-%N}"'
fi

if [ -n "$_cmdvault_src" ]; then
    CMDVAULT_PLUGIN_ROOT="$(cd "$(dirname "$_cmdvault_src")/.." 2>/dev/null && pwd)"
fi
unset _cmdvault_src

if [ -z "${CMDVAULT_PLUGIN_ROOT:-}" ] || [ ! -f "$CMDVAULT_PLUGIN_ROOT/scripts/cmdvault.py" ]; then
    echo "cmdvault: could not locate plugin root; set CMDVAULT_PLUGIN_ROOT manually" >&2
    return 0 2>/dev/null || true
fi
export CMDVAULT_PLUGIN_ROOT

# --- picker ---
ccmd() {
    python3 "$CMDVAULT_PLUGIN_ROOT/scripts/cmdvault.py" pick "$@"
}

# --- prompt-insertion widgets (best effort; never break shell startup) ---
if [ -n "${BASH_VERSION:-}" ]; then
    case $- in
        *i*)
            _cmdvault_readline_widget() {
                local cmd
                cmd="$(python3 "$CMDVAULT_PLUGIN_ROOT/scripts/cmdvault.py" pick)" || return 0
                [ -n "$cmd" ] || return 0
                READLINE_LINE="$cmd"
                READLINE_POINT=${#READLINE_LINE}
            }
            bind -x '"\C-x\C-r": _cmdvault_readline_widget' 2>/dev/null || true
            ;;
    esac
elif [ -n "${ZSH_VERSION:-}" ]; then
    if [[ -o interactive ]] 2>/dev/null; then
        _cmdvault_zle_widget() {
            local cmd
            cmd="$(python3 "$CMDVAULT_PLUGIN_ROOT/scripts/cmdvault.py" pick < /dev/tty)" || return 0
            [ -n "$cmd" ] || return 0
            LBUFFER+="$cmd"
            zle reset-prompt 2>/dev/null || true
        }
        zle -N cmdvault-pick _cmdvault_zle_widget 2>/dev/null \
            && bindkey '^X^R' cmdvault-pick 2>/dev/null || true
    fi
fi
