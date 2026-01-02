# piku-code: VS Code Tunnel Integration for Piku

## Project Overview

A piku plugin that enables opening VS Code connected to a remote piku app's filesystem via [VS Code Tunnels](https://code.visualstudio.com/docs/remote/tunnels).

### The Problem

Piku's SSH access is restricted via `command=` in `authorized_keys`, which forces all SSH commands through `piku.py`. This prevents VS Code Remote-SSH from working, as it needs to run arbitrary commands to set up its server.

### The Solution

Use VS Code Tunnels instead of Remote-SSH. Tunnels:
- Run server-side (allowed via piku commands)
- Connect through Microsoft's relay (no SSH needed for VS Code)
- Support device-flow authentication (first-time GitHub login)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ LOCAL (user's machine)                                          │
│                                                                 │
│  $ piku code                                                    │
│    │                                                            │
│    ├─► ssh piku@server code-tunnel:status myapp                 │
│    │     └─► Returns tunnel name if running, or exits 1         │
│    │                                                            │
│    ├─► (if not running) ssh -t piku@server code-tunnel:start    │
│    │     └─► Interactive: shows device auth URL if needed       │
│    │     └─► Starts tunnel, returns tunnel name                 │
│    │                                                            │
│    └─► code --remote tunnel+<tunnel-name> ~/.piku/apps/myapp    │
│          └─► VS Code opens, connects via Microsoft relay        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVER (piku host)                                              │
│                                                                 │
│  ~/.piku/plugins/piku_code/                                     │
│    __init__.py          # Plugin code                           │
│                                                                 │
│  ~/bin/code             # VS Code CLI (installed by installer)  │
│                                                                 │
│  ~/.piku/data/<app>/                                            │
│    code-tunnel.pid      # PID of running tunnel process         │
│    code-tunnel.name     # Tunnel name for reconnection          │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
piku-code/
├── install.sh              # Curlbash installer for server
├── piku_code/
│   └── __init__.py         # Server-side piku plugin
├── piku-client.sh          # Client-side additions (to merge into piku script)
├── SPEC.md                 # This file
└── README.md               # User-facing documentation (TODO)
```

## Server-Side Commands (Plugin)

| Command | Description |
|---------|-------------|
| `code-tunnel:start <app> [name]` | Start tunnel, handle device auth, return tunnel name |
| `code-tunnel:stop <app>` | Stop the tunnel for an app |
| `code-tunnel:status <app>` | Check if tunnel running, return name if so |
| `code-tunnel:ensure <app>` | Return name if running, error if not (non-interactive) |
| `code-tunnel:name <app>` | Just return the tunnel name (for scripting) |

## Client-Side Commands

| Command | Description |
|---------|-------------|
| `piku code` | Start tunnel if needed, launch VS Code |
| `piku code:stop` | Stop the tunnel |
| `piku code:status` | Check tunnel status |

## Installation

### Server-side (run once per piku server)

```bash
ssh piku@myserver 'curl -sL https://raw.githubusercontent.com/OWNER/piku-code/main/install.sh | sh'
```

This installs:
1. The plugin to `~/.piku/plugins/piku_code/`
2. VS Code CLI to `~/bin/code`

### Client-side (run once per developer machine)

Merge the contents of `piku-client.sh` into your local `piku` script.

Or download the modified piku client:
```bash
curl -sL https://raw.githubusercontent.com/OWNER/piku-code/main/piku > /usr/local/bin/piku
chmod +x /usr/local/bin/piku
```

## Usage

### First time (authentication required)

```bash
$ piku code
Starting VS Code tunnel (may require authentication)...

-----> Starting VS Code tunnel 'piku-myapp-a1b2c3'...

-----> Authentication required!
       Open this URL in your browser:
       https://github.com/login/device

       Enter code: ABCD-1234

-----> Authenticated successfully!
-----> Tunnel ready!
piku-myapp-a1b2c3

Tunnel: piku-myapp-a1b2c3
Connecting VS Code...
```

VS Code opens connected to the remote app directory.

### Subsequent runs

```bash
$ piku code
Tunnel: piku-myapp-a1b2c3
Connecting VS Code...
```

### Stop tunnel

```bash
$ piku code:stop
Tunnel stopped (was PID 12345)
```

## Implementation Status

- [x] Server-side plugin (`piku_code/__init__.py`)
- [x] Curlbash installer (`install.sh`)
- [x] Client-side additions (`piku-client.sh`)
- [ ] README.md for end users
- [ ] Test on real piku server
- [ ] Handle tunnel process dying unexpectedly
- [ ] Consider systemd/supervisor for tunnel persistence
- [ ] Create separate GitHub repo

## Technical Notes

### Why not Remote-SSH?

Piku's `authorized_keys` uses `command="..."` to force all SSH through `piku.py`:

```
command="FINGERPRINT=... NAME=default /path/to/piku.py $SSH_ORIGINAL_COMMAND",no-agent-forwarding,no-user-rc,no-X11-forwarding,no-port-forwarding ssh-rsa ...
```

This means VS Code Remote-SSH's bootstrap commands (`bash`, `uname`, downloading server, etc.) are rejected.

### Piku Plugin System

Plugins live in `~/.piku/plugins/<name>/` and must:
1. Be a Python package (directory with `__init__.py`)
2. Export a `cli_commands()` function returning a Click group
3. Commands are merged via Click's `CommandCollection`

Reference: `piku.py:1773-1788`

### VS Code Tunnel CLI

The `code tunnel` command:
- First run requires GitHub device-flow auth
- Creates a named tunnel that persists across restarts
- Can run in foreground or be daemonized
- Tunnel names must be unique per GitHub account

### Tunnel Lifecycle

1. **Start**: `code tunnel --name <name>` runs in foreground
2. **Auth**: If not authenticated, prints device URL + code
3. **Ready**: Once connected, tunnel accepts VS Code connections
4. **Stop**: SIGTERM to the process
5. **Reconnect**: Same tunnel name reconnects without re-auth

## Development

### Testing the plugin locally

```bash
# On piku server
mkdir -p ~/.piku/plugins
ln -s /path/to/piku-code/piku_code ~/.piku/plugins/piku_code

# Test commands
piku code-tunnel:start myapp
piku code-tunnel:status myapp
piku code-tunnel:stop myapp
```

### Debug mode

```bash
PIKU_CODE_DEBUG=1 piku code-tunnel:start myapp
```

## Future Improvements

1. **Tunnel persistence**: Use systemd user service or supervisor to keep tunnel alive
2. **Multiple tunnels**: Support multiple apps with separate tunnels
3. **Tunnel health checks**: Detect dead tunnels and restart
4. **Browser fallback**: Open vscode.dev if local VS Code not available
5. **Config options**: Custom tunnel names, auto-start on deploy

## References

- [VS Code Tunnels documentation](https://code.visualstudio.com/docs/remote/tunnels)
- [VS Code CLI reference](https://code.visualstudio.com/docs/editor/command-line)
- [Piku documentation](https://github.com/piku/piku)
- Piku plugin system: `piku.py:1773-1788`
- Piku SSH restriction: `piku.py:266-276`
