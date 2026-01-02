#!/bin/sh
# piku-code client additions
#
# Add this case block to your local 'piku' script, inside the case statement
# (after the 'tmux)' block and before the '*)' default block):
#
# --- COPY FROM HERE ---

    code)
      # Open VS Code connected to remote app via tunnel
      #
      # First check if tunnel is running
      tunnel_name=$($SSH "$server" code-tunnel:status "$app" 2>/dev/null | tail -1)

      if [ -z "$tunnel_name" ]; then
        # Tunnel not running - need to start with interactive auth
        echo "Starting VS Code tunnel (may require authentication)..."
        echo ""

        # Run interactively so user can see/complete device auth
        if ! $SSH -t "$server" code-tunnel:start "$app"; then
          echo "Failed to start tunnel."
          exit 1
        fi

        # Get the tunnel name now that it's started
        tunnel_name=$($SSH "$server" code-tunnel:name "$app" 2>/dev/null)

        if [ -z "$tunnel_name" ]; then
          echo "Error: tunnel started but could not get tunnel name"
          exit 1
        fi
      fi

      echo "Tunnel: $tunnel_name"
      echo "Connecting VS Code..."

      # Launch local VS Code connected to the tunnel
      # The path is relative to the user's home on the remote
      remote_path="~/.piku/apps/$app"

      if command -v code >/dev/null 2>&1; then
        code --remote "tunnel+$tunnel_name" "$remote_path"
      else
        echo ""
        echo "VS Code CLI not found locally."
        echo "Either install VS Code, or open VS Code manually and connect to:"
        echo "  Remote: $tunnel_name"
        echo "  Path:   $remote_path"
        echo ""
        echo "Or open in browser: https://vscode.dev/tunnel/$tunnel_name$remote_path"
      fi
      ;;

    code:stop)
      # Stop the VS Code tunnel for an app
      $SSH "$server" code-tunnel:stop "$app"
      ;;

    code:status)
      # Check VS Code tunnel status
      $SSH "$server" code-tunnel:status "$app"
      ;;

# --- COPY TO HERE ---
#
# Also add these lines to the help text (after "tmux" line):
#
#   echo "  code              Local command to open VS Code connected to the app via tunnel."
#   echo "  code:stop         Stop the VS Code tunnel for an app."
#   echo "  code:status       Check VS Code tunnel status."
