# OpenClaw guest-root artifact input

This directory is the isolated, minimum reproducible input for an A07
platform-specific OpenClaw guest root. The dedicated
`deploy/byoc/openclaw-phase-a07.Dockerfile` builds the Linux amd64 guest root
from the same locked inputs on top of the generic commercial image and copies
the complete filesystem into the executor image at
`/opt/agentops-provider/openclaw`. The A07 Compose topology consumes that
read-only image path directly; it no longer accepts an
`AGENTOPS_A07_RUNTIME_PATH` host bind.

This executor packaging path is intentionally Linux amd64 only for now. The
Dockerfile selects the recorded amd64 child manifest and fails the final image
build when `TARGETPLATFORM` is not `linux/amd64`, preventing an amd64 guest root
from being embedded in an incompatible executor image. The separately declared
arm64/v8 child remains an artifact input for a later native arm64 packaging
lane; it is not silently selected here.

The dependency graph is locked by `package-lock.json`. `openclaw@2026.5.4` is
exact and its npm release integrity is recorded in both the lock and
`artifact.json`. The base is Node 22.23.2 Bookworm slim pinned by its OCI index
digest; `artifact.json` also records the Linux amd64 and arm64/v8 child manifest
digests. A build must select one platform and pass its exact `base_image` as
the required `NODE_IMAGE` build argument; there is deliberately no mutable or
index-only Dockerfile default. Later evidence must retain that child identity.

The offline contract requires registry URLs, SHA-512 integrity, and license
metadata for every locked package. Release packaging must still generate and
review the complete SBOM and third-party notices; lock metadata alone is not
distribution approval.

The sole authoritative checked-in adapter is
`deploy/byoc/openclaw-stdin-provider.mjs`; the image places it at guest path
`/opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs`. It reads one
canonical provider request from stdin and does not put the prompt in argv. No
global installation, host `node_modules`, npm user directory, credential, or
generated artifact is copied into this input.

All runtime and product claims remain `false`. In particular, these files do
not prove an artifact was built or published, a platform image was inspected,
the guest-root manifest was signed, an opened fd was handed to the launcher, a
runtime process was spawned, a provider was called, a receipt was verified, or
hostile-runtime isolation was achieved.

The config, workspace, state, and temp mounts remain nested below the packaged
guest root so their guest-visible paths are `/run/secrets/openclaw_config`,
`/opt/agentops-worker/workspace`, `/run/openclaw-state`, and `/tmp` after
`chroot(2)`. Packaging the root in the executor image removes the host runtime
tree input, but does not by itself prove mount identity, runtime execution,
receipt verification, or hostile-runtime isolation.

The CI build only validates that this exact input can produce and import a
platform image as uid/gid 1200 with read-only code. It does not publish an OCI
digest, sign a release manifest, or change any committed runtime claim.

Run the offline contract with:

```sh
node deploy/byoc/openclaw-runtime-artifact/contract.mjs
```

Builds use the repository root as context and must select an exact child
manifest from `artifact.json`, for example:

```sh
docker build --file deploy/byoc/openclaw-runtime-artifact/Dockerfile \
  --build-arg NODE_IMAGE=node:22.23.2-bookworm-slim@sha256:<platform-child-digest> \
  .
```
