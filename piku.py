#!/usr/bin/env python

import os, sys, stat, re, shutil, socket
from click import argument, command, group, option, secho as echo
from os.path import abspath, exists, join, dirname
from subprocess import call
from ConfigParser import ConfigParser

# === Globals - all tweakable settings are here ===

PIKU_ROOT = os.environ.get('PIKU_ROOT', join(os.environ['HOME'],'.piku'))

APP_ROOT = abspath(join(PIKU_ROOT, "apps"))
ENV_ROOT = abspath(join(PIKU_ROOT, "envs"))
GIT_ROOT = abspath(join(PIKU_ROOT, "repos"))
LOG_ROOT = abspath(join(PIKU_ROOT, "logs"))
UWSGI_AVAILABLE = abspath(join(PIKU_ROOT, "uwsgi-available"))
UWSGI_ENABLED = abspath(join(PIKU_ROOT, "uwsgi-enabled"))
UWSGI_ROOT = abspath(join(PIKU_ROOT, "uwsgi"))


# === Utility functions ===

def sanitize_app_name(app):
    """Sanitize the app name and build matching path"""
    app = "".join(c for c in app if c.isalnum() or c in ('.','_')).rstrip()
    return app


def get_free_port(address=""):
    """Find a free TCP port (entirely at random)"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((address,0))
    port = s.getsockname()[1]
    s.close()
    return port


def setup_authorized_keys(ssh_fingerprint, script_path, pubkey):
    """Sets up an authorized_keys file to redirect SSH commands"""
    authorized_keys = join(os.environ['HOME'],'.ssh','authorized_keys')
    if not exists(dirname(authorized_keys)):
        os.makedirs(dirname(authorized_keys))
    # Restrict features and force all SSH commands to go through our script 
    with open(authorized_keys, 'a') as h:
        h.write("""command="FINGERPRINT=%(ssh_fingerprint)s NAME=default %(script_path)s $SSH_ORIGINAL_COMMAND",no-agent-forwarding,no-user-rc,no-X11-forwarding,no-port-forwarding %(pubkey)s\n""" % locals())
        

def parse_procfile(filename):
    """Parses a Procfile and returns the worker types. Only one worker of each type is allowed."""
    workers = {}
    if not exists(filename):
        return None
    with open(filename, 'r') as procfile:
        for line in procfile:
            try:
                kind, command = map(lambda x: x.strip(), line.split(":", 1))
                if kind in ['web', 'worker', 'wsgi']:
                    workers[kind] = command
            except:
                echo("Warning: unrecognized Procfile declaration '%s'" % line, fg='yellow')
    if not len(workers):
        return None
    # WSGI trumps regular web workers
    if 'wsgi' in workers:
        if 'web' in workers:
            del(workers['web'])
    return workers 
    

def do_deploy(app):
    """Deploy an app by resetting the work directory"""
    app_path = join(APP_ROOT, app)
    procfile = join(app_path, 'Procfile')
    env = {'GIT_WORK_DIR': app_path}
    if exists(app_path):
        echo("-----> Deploying app '%s'" % app, fg='green')
        call('git pull --quiet', cwd=app_path, env=env, shell=True)
        call('git checkout -f', cwd=app_path, env=env, shell=True)
        workers = parse_procfile(procfile)
        if workers:
            if exists(join(app_path, 'requirements.txt')):
                echo("-----> Python app detected.", fg='green')
                deploy_python(app, workers)
            else:
                echo("-----> Could not detect runtime!", fg='red')
            # TODO: detect other runtimes
        else:
            echo("Error: Procfile not found for app '%s'." % app, fg='red')
    else:
        echo("Error: app '%s' not found." % app, fg='red')
        
        
def deploy_python(app, workers):
    """Deploy a Python application"""
    env_path = join(ENV_ROOT, app)
    available = join(UWSGI_AVAILABLE, '%s.ini' % app)
    enabled = join(UWSGI_ENABLED, '%s.ini' % app)
    
    if not exists(env_path):
        echo("-----> Creating virtualenv for '%s'" % app, fg='green')
        os.makedirs(env_path)
        call('virtualenv %s' % app, cwd=ENV_ROOT, shell=True)

    # TODO: run pip only if requirements have changed
    echo("-----> Running pip for '%s'" % app, fg='green')
    activation_script = join(env_path,'bin','activate_this.py')
    execfile(activation_script, dict(__file__=activation_script))
    call('pip install -r %s' % join(APP_ROOT, app, 'requirements.txt'), cwd=env_path, shell=True)

    # Generate a uWSGI vassal config
    # TODO: check for worker processes and scaling
    # TODO: allow user to define the port
    port = get_free_port()
    settings = [
        ('http', ':%d' % port),
        ('virtualenv', join(ENV_ROOT, app)),
        ('chdir', join(APP_ROOT, app)),
        ('master', 'false'),
        ('project', app),
        ('max-requests', '1000'),
        ('processes', '2'),
        ('logto', "%s.log" % join(LOG_ROOT, app)),
        ('env', 'WSGI_PORT=http'),        
        ('env', 'PORT=%d' % port)
    ]
    os.environ['VIRTUAL_ENV'] = env_path
    for v in ['PATH', 'VIRTUAL_ENV']:
        if v in os.environ:
            settings.append(('env', '%s=%s' % (v, os.environ[v])))
    
    if 'wsgi' in workers:
        settings.append(('module', workers['wsgi']))
    else:
        settings.append(('attach-daemon', workers['web']))
    with open(available, 'w') as h:
        h.write('[uwsgi]\n')
        for k, v in settings:
            h.write("%s = %s\n" % (k, v))
    echo("-----> Enabling '%s' at port %d" % (app, port), fg='green')
    # Copying the file across makes uWSGI (re)start the vassal
    shutil.copyfile(available, enabled)


# === CLI commands ===    
    
@group()
def piku():
    """Initialize paths"""
    for p in [APP_ROOT, GIT_ROOT, ENV_ROOT, UWSGI_ROOT, UWSGI_AVAILABLE, UWSGI_ENABLED, LOG_ROOT]:
        if not exists(p):
            os.makedirs(p)

    
@piku.resultcallback()
def cleanup(ctx):
    """Callback from command execution -- currently used for debugging"""
    pass
    #print sys.argv[1:]
    #print os.environ


# --- User commands ---

@piku.command("deploy")
@argument('app')
def deploy_app(app):
    """Deploy an application"""
    app = sanitize_app_name(app)
    do_deploy(app)


@piku.command("destroy")
@argument('app')
def destroy_app(app):
    """Destroy an application"""
    app = sanitize_app_name(app)
    for p in [join(x, app) for x in [APP_ROOT, GIT_ROOT, ENV_ROOT, LOG_ROOT]]:
        if exists(p):
            echo("Removing folder '%s'" % p, fg='yellow')
            shutil.rmtree(p)
    for p in [join(x, app + '.ini') for x in [UWSGI_AVAILABLE, UWSGI_ENABLED]]:
        if exists(p):
            echo("Removing file '%s'" % p, fg='yellow')
            os.remove(p)


@piku.command("disable")
@argument('app')
def disable_app(app):
    """Disable an application"""
    app = sanitize_app_name(app)
    config = join(UWSGI_ENABLED, app + '.ini')
    if exists(config):
        echo("Disabling app '%s'..." % app, fg='yellow')
        os.remove(config)
    else:
        echo("Error: app '%s' not found!" % app, fg='red')


@piku.command("enable")
@argument('app')
def enable_app(app):
    """Enable an application"""
    app = sanitize_app_name(app)
    enabled = join(UWSGI_ENABLED, app + '.ini')
    available = join(UWSGI_AVAILABLE, app + '.ini')
    if exists(join(APP_ROOT, app)):
        if not exists(enabled):
            if exists(available):
                echo("Enabling app '%s'..." % app, fg='yellow')
                shutil.copyfile(available, enabled)
            else:
                echo("Error: app '%s' is not configured.", fg='red')
        else:
           echo("Warning: app '%s' is already enabled, skipping.", fg='yellow')       
    else:
        echo("Error: app '%s' does not exist.", fg='red')


@piku.command("ls")
def list_apps():
    """List applications"""
    for a in os.listdir(APP_ROOT):
        echo(a, fg='green')


@piku.command("log")
@argument('app')
def tail_logs(app):
    """Tail an application log"""
    app = sanitize_app_name(app)
    logfile = join(LOG_ROOT, "%s.log" % app)
    if exists(logfile):
        call('tail -F %s' % logfile, cwd=LOG_ROOT, shell=True)
    else:
        echo("No logs found for app '%s'." % app, fg='yellow')


@piku.command("restart")
@argument('app')
def restart_app(app):
    """Restart an application"""
    app = sanitize_app_name(app)
    enabled = join(UWSGI_ENABLED, app + '.ini')
    available = join(UWSGI_AVAILABLE, app + '.ini')
    if exists(enabled):
        echo("Restarting app '%s'..." % app, fg='yellow')
        # Destroying the original file signals uWSGI to kill the vassal
        # TODO: check behavior on newer versions
        shutil.copyfile(available, enabled)
    else:
        echo("Error: app '%s' not enabled!" % app, fg='red')


# --- Internal commands ---

@piku.command("git-hook")
@argument('app')
def git_hook(app):
    """INTERNAL: Post-receive git hook"""
    app = sanitize_app_name(app)
    repo_path = join(GIT_ROOT, app)
    app_path = join(APP_ROOT, app)
    for line in sys.stdin:
        oldrev, newrev, refname = line.strip().split(" ")
        #print "refs:", oldrev, newrev, refname
        if refname == "refs/heads/master":
            # Handle pushes to master branch
            if not exists(app_path):
                echo("-----> Creating app '%s'" % app, fg='green')
                os.makedirs(app_path)
                call('git clone --quiet %s %s' % (repo_path, app), cwd=APP_ROOT, shell=True)
            do_deploy(app)
        else:
            # TODO: Handle pushes to another branch
            echo("receive-branch '%s': %s, %s" % (app, newrev, refname))
    #print "hook", app, sys.argv[1:]


@piku.command("git-receive-pack")
@argument('app')
def receive(app):
    """INTERNAL: Handle git pushes for an app"""
    app = sanitize_app_name(app)
    hook_path = join(GIT_ROOT, app, 'hooks', 'post-receive')
    if not exists(hook_path):
        os.makedirs(dirname(hook_path))
        # Initialize the repository with a hook to this script
        call("git init --quiet --bare " + app, cwd=GIT_ROOT, shell=True)
        with open(hook_path,'w') as h:
            h.write("""#!/usr/bin/env bash
set -e; set -o pipefail;
cat | PIKU_ROOT="%s" $HOME/piku.py git-hook %s""" % (PIKU_ROOT, app)) # TODO: remove hardcoded script name
        # Make the hook executable by our user
        os.chmod(hook_path, os.stat(hook_path).st_mode | stat.S_IXUSR)
    # Handle the actual receive. We'll be called with 'git-hook' after it happens
    call('git-shell -c "%s"' % " ".join(sys.argv[1:]), cwd=GIT_ROOT, shell=True)
 
 
if __name__ == '__main__':
    piku()