# OpenClaw guest-root artifact input

This directory is the isolated, minimum reproducible input for an A07
platform-specific OpenClaw guest-root OCI artifact. Its own Dockerfile is built
as an ephemeral Linux amd64 input by the A07 foundation workflow, but it is not
wired into the production Dockerfile, Compose topology, launcher, or release
gate.

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

The CI build only validates that this exact input can produce and import a
platform image as uid/gid 1200 with read-only code. It does not publish an OCI
digest, sign a release manifest, or change any committed claim.

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
