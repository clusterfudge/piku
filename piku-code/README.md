# piku-code

Open VS Code connected to your piku app's remote filesystem via [VS Code Tunnels](https://code.visualstudio.com/docs/remote/tunnels).

```bash
piku code        # Opens VS Code connected to your app
piku code:stop   # Stops the tunnel
piku code:status # Check tunnel status
```

## Installation

### 1. Server-side (once per piku server)

```bash
ssh piku@your-server 'curl -sL https://raw.githubusercontent.com/OWNER/piku-code/main/install.sh | sh'
```

### 2. Client-side (once per dev machine)

Add the code block from [`piku-client.sh`](piku-client.sh) to your local `piku` script.

## First Run

The first time you run `piku code`, you'll need to authenticate via GitHub:

```
$ piku code
Starting VS Code tunnel (may require authentication)...

-----> Authentication required!
       Open this URL in your browser:
       https://github.com/login/device

       Enter code: ABCD-1234
```

Complete the auth flow in your browser, and VS Code will open connected to your app.

## How It Works

Since piku restricts SSH to only allow piku commands, we can't use VS Code Remote-SSH. Instead, this plugin:

1. Runs the VS Code tunnel server on your piku host (via piku commands)
2. Connects through Microsoft's relay service
3. Launches your local VS Code connected to the tunnel

See [SPEC.md](SPEC.md) for technical details.

## License

MIT
