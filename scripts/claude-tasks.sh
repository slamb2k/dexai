#!/bin/bash
# Claude Code Task System Helpers
# Source this file in your .bashrc or .zshrc:
#   source ~/work/dexai/scripts/claude-tasks.sh

# Generate a deterministic task list ID from directory path
# This ensures the same project always gets the same task list
_claude_task_id_from_path() {
    local dir="${1:-$(pwd)}"
    # Create a hash of the absolute path for uniqueness
    echo "tasks-$(echo "$dir" | md5sum | cut -c1-12)"
}

# Initialize task list for current directory
# Usage: claude-tasks-init [directory]
claude-tasks-init() {
    local dir="${1:-$(pwd)}"
    local task_id=$(_claude_task_id_from_path "$dir")

    export CLAUDE_CODE_TASK_LIST_ID="$task_id"
    echo "✓ Task list ID set: $CLAUDE_CODE_TASK_LIST_ID"
    echo "  Directory: $dir"
    echo ""
    echo "Tasks will persist across Claude Code sessions for this project."
}

# Show current task list configuration
claude-tasks-status() {
    if [ -z "$CLAUDE_CODE_TASK_LIST_ID" ]; then
        echo "✗ No task list configured"
        echo "  Run: claude-tasks-init"
    else
        echo "✓ Task list ID: $CLAUDE_CODE_TASK_LIST_ID"
        echo "  Set from: $(pwd)"
    fi
}

# Clear task list (start fresh)
claude-tasks-clear() {
    unset CLAUDE_CODE_TASK_LIST_ID
    echo "✓ Task list cleared"
    echo "  Run claude-tasks-init to set a new one"
}

# Auto-init when entering a project with CLAUDE.md
# Add this to your .bashrc/.zshrc AFTER sourcing this file:
#   PROMPT_COMMAND="_claude_auto_init; $PROMPT_COMMAND"  # bash
#   precmd() { _claude_auto_init }                       # zsh
_claude_auto_init() {
    # Only auto-init if CLAUDE.md exists and task list not set
    if [ -f "CLAUDE.md" ] && [ -z "$CLAUDE_CODE_TASK_LIST_ID" ]; then
        claude-tasks-init "$(pwd)" > /dev/null
    fi
}

# Shortcut aliases
alias cti='claude-tasks-init'
alias cts='claude-tasks-status'
alias ctc='claude-tasks-clear'

# Print help on source
echo "Claude Code Task Helpers loaded."
echo "  claude-tasks-init   - Set task list for current directory"
echo "  claude-tasks-status - Show current configuration"
echo "  claude-tasks-clear  - Clear task list"
echo "  Aliases: cti, cts, ctc"
