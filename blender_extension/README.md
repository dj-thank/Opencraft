# OpenCraft World Bridge for Blender

This directory contains the Blender 4.2+ extension boundary for OpenCraft.

## Safety model

```text
Canonical World Server
        ↕
Local sidecar process
        ↕ atomic JSON spool
Blender extension on the main thread
```

The Blender process does not accept executable Python, shell commands, arbitrary URLs, or unvalidated `.blend` content from a world or agent. The extension applies only allowlisted declarative operations such as creating a proxy, updating a transform, changing approved metadata, or removing an OpenCraft-owned proxy.

The extension does not start microphone capture, agent listening, or public voice. Those are separate user-consent and media-plane concerns.

## Build

From this directory with Blender 4.2 or later:

```bash
blender --command extension build
```

For development, configure a local spool directory in the extension preferences. Do not expose the sidecar directly to the public Internet.
