"""piku-code: VS Code tunnel integration for piku"""

import os
from os.path import exists, join
from subprocess import Popen, PIPE, STDOUT
from signal import SIGTERM

from click import argument, group, pass_context, secho as echo

# Import paths from piku's environment
PIKU_ROOT = os.environ.get('PIKU_ROOT', join(os.environ['HOME'], '.piku'))
APP_ROOT = join(PIKU_ROOT, 'apps')
DATA_ROOT = join(PIKU_ROOT, 'data')
CODE_CLI = join(os.environ['HOME'], 'bin', 'code')


def get_tunnel_pidfile(app):
    """Get path to tunnel PID file for an app."""
    return join(DATA_ROOT, app, 'code-tunnel.pid')


def get_tunnel_namefile(app):
    """Get path to tunnel name file for an app."""
    return join(DATA_ROOT, app, 'code-tunnel.name')


def get_tunnel_pid(app):
    """Get PID of running tunnel, or None if not running."""
    pidfile = get_tunnel_pidfile(app)
    if not exists(pidfile):
        return None
    try:
        with open(pidfile) as f:
            pid = int(f.read().strip())
        # Check if process is still running
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        # Process not running or invalid PID
        try:
            os.remove(pidfile)
        except OSError:
            pass
        return None


def get_tunnel_name(app):
    """Get the tunnel name for an app, or None if not set."""
    namefile = get_tunnel_namefile(app)
    if not exists(namefile):
        return None
    try:
        with open(namefile) as f:
            return f.read().strip()
    except OSError:
        return None


def exit_if_invalid(app):
    """Validate app exists."""
    if not exists(join(APP_ROOT, app)):
        echo("Error: app '{}' not found.".format(app), fg='red')
        exit(1)
    return app


def ensure_data_dir(app):
    """Ensure app data directory exists."""
    data_dir = join(DATA_ROOT, app)
    if not exists(data_dir):
        os.makedirs(data_dir)
    return data_dir


@group()
def piku_code():
    """VS Code tunnel commands for piku"""
    pass


@piku_code.command("code-tunnel:start")
@argument('app')
@argument('tunnel_name', required=False, default=None)
def cmd_code_tunnel_start(app, tunnel_name):
    """Start a VS Code tunnel for an app.

    If the tunnel is not yet authenticated, prints device flow URL.
    Returns the tunnel name on success.
    """
    app = exit_if_invalid(app)
    ensure_data_dir(app)

    # Check if already running
    existing_pid = get_tunnel_pid(app)
    if existing_pid:
        existing_name = get_tunnel_name(app)
        if existing_name:
            echo(existing_name)
            return
        echo("Error: tunnel running (PID {}) but no name found".format(existing_pid), fg='red')
        exit(1)

    # Check for VS Code CLI
    if not exists(CODE_CLI):
        echo("Error: VS Code CLI not found at {}".format(CODE_CLI), fg='red')
        echo("Run the piku-code installer first.", fg='yellow')
        exit(1)

    app_path = join(APP_ROOT, app)

    # Generate tunnel name if not provided
    if not tunnel_name:
        import hashlib
        hash_suffix = hashlib.sha256(app_path.encode()).hexdigest()[:6]
        tunnel_name = "piku-{}-{}".format(app, hash_suffix)

    # Start tunnel in foreground first to handle auth
    # The tunnel command will print device auth URL if needed
    echo("-----> Starting VS Code tunnel '{}'...".format(tunnel_name), fg='green')

    cmd = [
        CODE_CLI, 'tunnel',
        '--name', tunnel_name,
        '--accept-server-license-terms',
    ]

    # First, try to start - this handles device auth if needed
    # We run interactively so user can see auth URL
    proc = Popen(
        cmd,
        cwd=app_path,
        stdin=None,
        stdout=PIPE,
        stderr=STDOUT,
        text=True,
    )

    # Read output looking for either:
    # 1. Device auth URL (needs user action)
    # 2. Tunnel connected message (success)
    authenticated = False
    tunnel_ready = False

    try:
        for line in iter(proc.stdout.readline, ''):
            line = line.strip()
            if not line:
                continue

            # Check for device auth flow
            if 'https://' in line and ('github.com' in line or 'microsoft.com' in line or 'login' in line.lower()):
                echo("", fg='yellow')
                echo("-----> Authentication required!", fg='yellow')
                echo("       Open this URL in your browser:", fg='yellow')
                echo("       {}".format(line), fg='cyan')
                echo("", fg='yellow')
                continue

            if 'code' in line.lower() and len(line) < 20:
                # This might be the device code
                echo("       Enter code: {}".format(line), fg='cyan')
                continue

            if 'authenticated' in line.lower() or 'logged in' in line.lower():
                authenticated = True
                echo("-----> Authenticated successfully!", fg='green')
                continue

            if 'tunnel' in line.lower() and ('ready' in line.lower() or 'connected' in line.lower() or 'listening' in line.lower()):
                tunnel_ready = True
                break

            # Debug output
            if os.environ.get('PIKU_CODE_DEBUG'):
                echo("       [debug] {}".format(line), fg='white')

    except KeyboardInterrupt:
        proc.terminate()
        echo("Cancelled.", fg='yellow')
        exit(1)

    if not tunnel_ready:
        # Tunnel didn't start properly
        proc.terminate()
        echo("Error: tunnel failed to start", fg='red')
        exit(1)

    # Tunnel is ready - save state
    with open(get_tunnel_pidfile(app), 'w') as f:
        f.write(str(proc.pid))

    with open(get_tunnel_namefile(app), 'w') as f:
        f.write(tunnel_name)

    echo("-----> Tunnel ready!", fg='green')
    echo(tunnel_name)


@piku_code.command("code-tunnel:ensure")
@argument('app')
def cmd_code_tunnel_ensure(app):
    """Ensure tunnel is running, start if needed. Returns tunnel name."""
    app = exit_if_invalid(app)

    # Check if already running
    pid = get_tunnel_pid(app)
    name = get_tunnel_name(app)

    if pid and name:
        # Already running
        echo(name)
        return

    # Need to start - but this requires interactive auth potentially
    # So we delegate to start command
    echo("Error: tunnel not running. Run 'piku code-tunnel:start {}' first (requires interactive auth).".format(app), fg='red')
    exit(1)


@piku_code.command("code-tunnel:status")
@argument('app')
def cmd_code_tunnel_status(app):
    """Check tunnel status for an app."""
    app = exit_if_invalid(app)

    pid = get_tunnel_pid(app)
    name = get_tunnel_name(app)

    if pid and name:
        echo("Tunnel '{}' running (PID {})".format(name, pid), fg='green')
        echo(name)
    else:
        echo("No tunnel running for '{}'".format(app), fg='yellow')
        exit(1)


@piku_code.command("code-tunnel:stop")
@argument('app')
def cmd_code_tunnel_stop(app):
    """Stop the VS Code tunnel for an app."""
    app = exit_if_invalid(app)

    pid = get_tunnel_pid(app)
    if not pid:
        echo("No tunnel running for '{}'".format(app), fg='yellow')
        return

    try:
        os.kill(pid, SIGTERM)
        echo("Tunnel stopped (was PID {})".format(pid), fg='green')
    except OSError as e:
        echo("Error stopping tunnel: {}".format(e), fg='red')

    # Clean up files
    for f in [get_tunnel_pidfile(app), get_tunnel_namefile(app)]:
        try:
            os.remove(f)
        except OSError:
            pass


@piku_code.command("code-tunnel:name")
@argument('app')
def cmd_code_tunnel_name(app):
    """Get the tunnel name for an app (for client-side use)."""
    app = exit_if_invalid(app)
    name = get_tunnel_name(app)
    if name:
        echo(name)
    else:
        exit(1)


def cli_commands():
    """Return Click commands for piku plugin system."""
    return piku_code
