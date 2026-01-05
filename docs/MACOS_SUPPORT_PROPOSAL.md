# Proposal: macOS Server-Side Support for Piku

**Author:** Claude
**Date:** January 2026
**Status:** Draft Proposal

## Executive Summary

This document proposes extending piku to support macOS as a server-side deployment platform. While piku currently targets Linux systems with systemd, the core architecture is portable Python with well-isolated platform dependencies. This proposal outlines the technical changes required, implementation strategy, and potential challenges.

**Key insight:** The majority of piku's codebase is platform-agnostic Python. The main adaptation work centers on replacing systemd with launchd and adjusting shell utilities for BSD compatibility.

---

## Table of Contents

1. [Motivation](#motivation)
2. [Current Architecture Overview](#current-architecture-overview)
3. [Platform Differences](#platform-differences)
4. [Proposed Changes](#proposed-changes)
5. [Implementation Phases](#implementation-phases)
6. [Testing Strategy](#testing-strategy)
7. [Risks and Mitigations](#risks-and-mitigations)
8. [Open Questions](#open-questions)

---

## Motivation

### Why macOS Server Support?

1. **Development parity** - Developers using macOS can run a local piku instance that mirrors production behavior
2. **Mac Mini servers** - Apple Silicon Mac Minis are increasingly used as cost-effective servers
3. **CI/CD on macOS** - Some projects require macOS-specific build environments
4. **Educational use** - Simpler setup for learning/teaching PaaS concepts without Linux VM overhead

### Target Users

- Developers wanting local piku instances for testing
- Small teams using Mac Mini servers
- Educational environments with macOS infrastructure

---

## Current Architecture Overview

Piku consists of several interconnected components:

```
┌─────────────────────────────────────────────────────────────────┐
│                         SSH Entry Point                          │
│                    (git-receive-pack/upload-pack)                │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                           piku.py                                │
│                    (Core Python Application)                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │   Git Ops    │ │  App Deploy  │ │  Config Mgmt │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │   uwsgi     │ │   nginx     │ │  systemd    │  ◄── Platform-specific
            │  (Emperor)  │ │  (Reverse   │ │  (Process   │
            │             │ │   Proxy)    │ │   Manager)  │
            └─────────────┘ └─────────────┘ └─────────────┘
```

### Platform-Specific Components (Linux)

| Component | Purpose | Linux Implementation |
|-----------|---------|---------------------|
| Process Manager | Start/stop/monitor services | systemd units |
| App Supervisor | Manage worker processes | uwsgi Emperor |
| Reverse Proxy | HTTP routing, SSL termination | nginx |
| File Watcher | Config reload triggers | systemd path units |
| User Model | Process isolation | `piku` user in `www-data` group |

---

## Platform Differences

### Critical Differences

| Aspect | Linux | macOS |
|--------|-------|-------|
| Init system | systemd | launchd |
| Service files | `.service` units | `.plist` files |
| Process info | `/proc` filesystem | `sysctl` / `ps` |
| User management | `adduser`, `www-data` | `dscl`, `_www` |
| Shell utilities | GNU coreutils | BSD variants |
| File monitoring | inotify | FSEvents |

### Shell Command Differences

| Command | Linux (GNU) | macOS (BSD) | Solution |
|---------|-------------|-------------|----------|
| `grep -c ^processor /proc/cpuinfo` | Works | No `/proc` | `sysctl -n hw.ncpu` |
| `sed -re` | Extended regex | Use `-E` | Use `-E` (portable) |
| `pgrep` | Built-in | Available | Works on both |
| `stat --format` | GNU format | Different flags | Use Python `os.stat()` |

---

## Proposed Changes

### 1. Process Management: systemd → launchd

**Current:** Three systemd unit files manage piku services:
- `uwsgi-piku.service` - uwsgi Emperor daemon
- `piku-nginx.service` - nginx reload service
- `piku-nginx.path` - File watcher for nginx config changes

**Proposed:** Create equivalent launchd plist files:

```xml
<!-- com.piku.uwsgi.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.piku.uwsgi</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/uwsgi</string>
        <string>--emperor</string>
        <string>/Users/piku/.piku/uwsgi-enabled</string>
        <string>--stats</string>
        <string>/Users/piku/.piku/uwsgi/uwsgi.sock</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>UserName</key>
    <string>piku</string>
    <key>WorkingDirectory</key>
    <string>/Users/piku</string>
    <key>StandardOutPath</key>
    <string>/Users/piku/.piku/logs/uwsgi.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/piku/.piku/logs/uwsgi.err</string>
</dict>
</plist>
```

**File watching:** Replace `piku-nginx.path` with FSEvents-based watcher:
- Option A: Python `watchdog` library in a small daemon
- Option B: launchd `WatchPaths` key (simpler, native)

```xml
<!-- com.piku.nginx-reload.plist -->
<dict>
    <key>Label</key>
    <string>com.piku.nginx-reload</string>
    <key>WatchPaths</key>
    <array>
        <string>/Users/piku/.piku/nginx</string>
    </array>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>nginx -t &amp;&amp; nginx -s reload</string>
    </array>
</dict>
</plist>
```

### 2. Platform Abstraction Layer

Create a new module `piku_platform.py` to abstract platform differences:

```python
# piku_platform.py
import platform
import subprocess

PLATFORM = platform.system()  # 'Linux' or 'Darwin'

def get_cpu_count():
    """Get CPU count in a platform-independent way."""
    if PLATFORM == 'Darwin':
        return int(subprocess.check_output(['sysctl', '-n', 'hw.ncpu']).strip())
    else:
        # Linux: read from /proc or use multiprocessing.cpu_count()
        from multiprocessing import cpu_count
        return cpu_count()

def get_web_group():
    """Get the web server group name."""
    if PLATFORM == 'Darwin':
        return '_www'
    else:
        return 'www-data'

def reload_nginx():
    """Reload nginx configuration."""
    if PLATFORM == 'Darwin':
        subprocess.call(['nginx', '-s', 'reload'])
    else:
        subprocess.call(['systemctl', 'reload', 'nginx'])

def service_command(service, action):
    """Start/stop/restart a service."""
    if PLATFORM == 'Darwin':
        plist = f'com.piku.{service}'
        if action == 'start':
            subprocess.call(['launchctl', 'load', f'/Library/LaunchDaemons/{plist}.plist'])
        elif action == 'stop':
            subprocess.call(['launchctl', 'unload', f'/Library/LaunchDaemons/{plist}.plist'])
        elif action == 'restart':
            service_command(service, 'stop')
            service_command(service, 'start')
    else:
        subprocess.call(['systemctl', action, service])
```

### 3. User and Group Management

**Linux approach:**
```bash
sudo adduser --disabled-password --gecos 'PaaS access' --ingroup www-data piku
```

**macOS approach:**
```bash
# Create piku user
sudo dscl . -create /Users/piku
sudo dscl . -create /Users/piku UserShell /bin/bash
sudo dscl . -create /Users/piku UniqueID 400
sudo dscl . -create /Users/piku PrimaryGroupID 70  # _www group
sudo dscl . -create /Users/piku NFSHomeDirectory /Users/piku
sudo mkdir -p /Users/piku
sudo chown piku:_www /Users/piku

# Alternative: use sysadminctl (simpler)
sudo sysadminctl -addUser piku -shell /bin/bash -home /Users/piku
sudo dseditgroup -o edit -a piku -t user _www
```

**Proposed:** Add `piku-setup-macos.sh` script alongside existing setup scripts.

### 4. Path Adjustments

Update `piku.py` to use platform-appropriate paths:

```python
if PLATFORM == 'Darwin':
    # macOS paths
    DEFAULT_PATHS = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
    NGINX_PATHS = ['/opt/homebrew/etc/nginx', '/usr/local/etc/nginx']
else:
    # Linux paths
    DEFAULT_PATHS = "/usr/local/sbin:/usr/sbin:/sbin:/usr/local/bin:/usr/bin:/bin"
    NGINX_PATHS = ['/etc/nginx']
```

### 5. Init Script Replacement

Replace `uwsgi-piku.dist` (SysVinit format) with platform-specific alternatives:

- **Linux:** Keep existing systemd units (preferred) or init script
- **macOS:** New launchd plists

### 6. Shell Script Portability

Update `uwsgi-piku.dist` CPU detection:

```bash
# Current (Linux-only):
CORES=`grep -c ^processor /proc/cpuinfo`

# Portable version:
if [ "$(uname)" = "Darwin" ]; then
    CORES=$(sysctl -n hw.ncpu)
else
    CORES=$(grep -c ^processor /proc/cpuinfo)
fi
```

### 7. Nginx Configuration

The nginx configuration template (`nginx.default.dist`) needs minor path adjustments:

```nginx
# Platform-aware include path
# Linux:  /home/piku/.piku/nginx/*.conf
# macOS:  /Users/piku/.piku/nginx/*.conf

# Solution: Use environment variable or symlink
include /home/piku/.piku/nginx/*.conf;  # or use $PIKU_ROOT
```

---

## Implementation Phases

### Phase 1: Platform Detection & Abstraction (Foundation)

**Goal:** Create platform abstraction layer without breaking Linux support

**Tasks:**
1. Add `piku_platform.py` module with platform detection
2. Abstract CPU count, web group, and nginx reload functions
3. Add `PLATFORM` detection in main `piku.py`
4. Create test suite for platform abstraction

**Deliverables:**
- `piku_platform.py` module
- Updated imports in `piku.py`
- Unit tests for platform functions

### Phase 2: launchd Integration (Process Management)

**Goal:** Create launchd equivalents for all systemd units

**Tasks:**
1. Create `com.piku.uwsgi.plist` for uwsgi Emperor
2. Create `com.piku.nginx-reload.plist` for config file watching
3. Add launchd install/uninstall scripts
4. Update `piku setup` command for macOS

**Deliverables:**
- Three launchd plist files
- `piku-setup-macos.sh` script
- Documentation for macOS installation

### Phase 3: Shell Compatibility (Utility Commands)

**Goal:** Ensure all shell commands work on BSD/macOS

**Tasks:**
1. Audit all `subprocess.call()` and `check_output()` calls
2. Replace GNU-specific flags with portable alternatives
3. Update `sed -re` to `sed -E` throughout
4. Add platform conditionals where needed

**Deliverables:**
- Updated shell commands in `piku.py`
- Updated `uwsgi-piku.dist` (or deprecate for launchd)
- Test coverage for shell operations

### Phase 4: Installation & Documentation

**Goal:** Complete macOS installation experience

**Tasks:**
1. Create Homebrew formula (optional, future)
2. Write macOS-specific INSTALL guide
3. Add macOS to CI testing matrix
4. Update README with macOS support status

**Deliverables:**
- `INSTALL-macos.md` documentation
- CI workflow for macOS
- Updated README badges

### Phase 5: Testing & Stabilization

**Goal:** Production-ready macOS support

**Tasks:**
1. End-to-end testing on macOS (Intel and Apple Silicon)
2. Performance benchmarking vs Linux
3. Edge case testing (permissions, signals, etc.)
4. Community beta testing

**Deliverables:**
- Test reports
- Performance comparison document
- Bug fixes from beta feedback

---

## Testing Strategy

### Unit Tests

```python
# test_platform.py
import pytest
from piku_platform import get_cpu_count, get_web_group, PLATFORM

def test_cpu_count_returns_positive():
    assert get_cpu_count() > 0

def test_web_group_is_valid():
    group = get_web_group()
    if PLATFORM == 'Darwin':
        assert group == '_www'
    else:
        assert group == 'www-data'
```

### Integration Tests

1. **App deployment test:** Deploy a simple Python/Node app
2. **Git push test:** Verify git receive-pack works
3. **Process management test:** Stop/start apps
4. **Nginx integration test:** Verify reverse proxy works
5. **SSL test:** Generate and install certificates

### CI Matrix

```yaml
# .github/workflows/test.yml
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-22.04, macos-13, macos-14]  # Intel and Apple Silicon
    runs-on: ${{ matrix.os }}
```

---

## Risks and Mitigations

### Risk 1: launchd Complexity
**Risk:** launchd is less documented than systemd, may have unexpected behaviors
**Mitigation:** Start with simple plist configurations; test thoroughly; provide fallback to manual process management

### Risk 2: Homebrew Dependency Conflicts
**Risk:** Users may have conflicting nginx/uwsgi installations from Homebrew
**Mitigation:** Document expected configurations; provide troubleshooting guide; consider using dedicated prefixes

### Risk 3: Permission Model Differences
**Risk:** macOS has stricter permission controls (SIP, TCC, sandboxing)
**Mitigation:** Document required permissions; avoid system-level modifications; prefer user-level launchd agents where possible

### Risk 4: Apple Silicon vs Intel Differences
**Risk:** Path differences between Homebrew on ARM (`/opt/homebrew`) vs Intel (`/usr/local`)
**Mitigation:** Detect architecture and adjust paths; support both locations

### Risk 5: Maintenance Burden
**Risk:** Supporting two platforms doubles testing/maintenance work
**Mitigation:** Strong platform abstraction layer; shared test suite; clear contribution guidelines

---

## Open Questions

1. **User-level vs System-level?**
   - Should piku run as a user-level launchd agent (`~/Library/LaunchAgents`) or system-level daemon (`/Library/LaunchDaemons`)?
   - User-level is simpler but limits multi-user scenarios

2. **Homebrew Integration?**
   - Should we publish a Homebrew formula for easy installation?
   - Would require ongoing maintenance for version updates

3. **Docker for Mac Alternative?**
   - Should we recommend Docker-based deployment on macOS instead?
   - Trade-off: simplicity vs native performance

4. **Minimum macOS Version?**
   - What's the minimum supported macOS version?
   - Recommendation: macOS 12 (Monterey) or later for modern launchd features

5. **uwsgi Installation?**
   - uwsgi installation on macOS can be problematic
   - Should we support alternative WSGI servers (gunicorn)?

---

## Conclusion

Extending piku to support macOS is feasible with moderate effort. The core Python codebase is largely portable, with the main work being:

1. Creating launchd service definitions
2. Abstracting platform-specific operations
3. Updating shell commands for BSD compatibility
4. Writing macOS-specific documentation

The phased approach allows incremental progress while maintaining stability for existing Linux users. The platform abstraction layer provides a foundation for potential future platform support (FreeBSD, etc.).

**Estimated effort:**
- Phase 1 (Foundation): ~40 hours
- Phase 2 (launchd): ~30 hours
- Phase 3 (Shell compat): ~20 hours
- Phase 4 (Docs/Install): ~15 hours
- Phase 5 (Testing): ~25 hours

**Total: ~130 hours of development work**

---

## Appendix A: File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `piku.py` | Modify | Add platform detection, use abstraction layer |
| `piku_platform.py` | New | Platform abstraction module |
| `com.piku.uwsgi.plist` | New | launchd service for uwsgi |
| `com.piku.nginx-reload.plist` | New | launchd service for nginx reload |
| `piku-setup-macos.sh` | New | macOS installation script |
| `INSTALL-macos.md` | New | macOS installation documentation |
| `uwsgi-piku.dist` | Modify | Add portable shell commands |
| `nginx.default.dist` | Modify | Support configurable paths |

## Appendix B: launchd vs systemd Quick Reference

| systemd | launchd | Notes |
|---------|---------|-------|
| `systemctl start svc` | `launchctl load plist` | Start service |
| `systemctl stop svc` | `launchctl unload plist` | Stop service |
| `systemctl status svc` | `launchctl list \| grep svc` | Check status |
| `Restart=always` | `<key>KeepAlive</key><true/>` | Auto-restart |
| `Type=notify` | N/A | launchd doesn't support sd_notify |
| `PathChanged=/path` | `<key>WatchPaths</key>` | File watching |
| `After=network.target` | Dependencies less explicit | Boot ordering |

## Appendix C: Example App Deployment on macOS

```bash
# Install piku on macOS
brew install uwsgi nginx
curl -O https://raw.githubusercontent.com/piku/piku/master/piku-setup-macos.sh
chmod +x piku-setup-macos.sh
./piku-setup-macos.sh

# Add SSH key
cat ~/.ssh/id_rsa.pub | ssh piku@localhost "cat >> ~/.ssh/authorized_keys"

# Deploy app (same as Linux!)
git remote add piku piku@localhost:myapp
git push piku main
```
