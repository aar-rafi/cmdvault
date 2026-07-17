# cmdvault fish integration — drop into ~/.config/fish/conf.d/ (or source it).
# Defines ccmd and binds Ctrl-X Ctrl-R to insert a picked command at the cursor.

set -l _cmdvault_dir (dirname (dirname (realpath (status filename))))
set -g CMDVAULT_SCRIPT "$_cmdvault_dir/scripts/cmdvault.py"

function ccmd --description 'Pick a Claude-captured command'
    if not test -f "$CMDVAULT_SCRIPT"
        echo "cmdvault: script not found at $CMDVAULT_SCRIPT" >&2
        return 1
    end
    if command -q python3
        python3 "$CMDVAULT_SCRIPT" pick $argv
    else
        python "$CMDVAULT_SCRIPT" pick $argv
    end
end

function _ccmd_insert
    set -l picked (ccmd)
    if test -n "$picked"
        commandline -i -- "$picked"
    end
    commandline -f repaint
end

if status is-interactive
    bind \cx\cr _ccmd_insert
end
