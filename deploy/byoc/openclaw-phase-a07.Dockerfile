# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG COMMERCIAL_BASE_IMAGE
FROM --platform=linux/amd64 node:22.23.2-bookworm-slim@sha256:a17d50af28002a160548bd4225b3cfcb12c5efcb171f79e68758f2885fb1b066 AS openclaw-guest-root
WORKDIR /opt/openclaw
COPY deploy/byoc/openclaw-runtime-artifact/package.json \
    deploy/byoc/openclaw-runtime-artifact/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --ignore-scripts --omit=dev --no-audit --no-fund \
    && npm cache clean --force \
    && test "$(node --version)" = "v22.23.2" \
    && test "$(node -p 'JSON.parse(require(\"fs\").readFileSync(\"node_modules/openclaw/package.json\", \"utf8\")).version')" = "2026.5.4"
COPY --chown=0:0 --chmod=0555 deploy/byoc/openclaw-stdin-provider.mjs \
    /opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs
COPY --chown=0:0 --chmod=0444 deploy/byoc/openclaw-runtime-artifact/artifact.json \
    /opt/agentops/openclaw-runtime-artifact.json
RUN find /opt/openclaw /opt/agentops -xdev -type d -exec chmod 0555 {} + \
    && find /opt/openclaw /opt/agentops -xdev -type f -exec chmod 0444 {} + \
    && chmod 0555 /opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs \
    && groupadd --gid 1200 agentops-runtime \
    && useradd --uid 1200 --gid 1200 --home-dir /run/openclaw-state \
      --no-create-home --shell /usr/sbin/nologin agentops-runtime \
    && install -d -o 1200 -g 1200 -m 0700 /run/openclaw-state \
    && install -d -o 0 -g 0 -m 0555 /run/secrets \
      /opt/agentops-worker /opt/agentops-worker/workspace \
    && install -o 0 -g 0 -m 0400 /dev/null /run/secrets/openclaw_config \
    && find / -xdev -perm /6000 -exec chmod a-s {} + \
    && find / -xdev \
      -path /opt/agentops-worker/workspace -prune -o \
      -path /run/openclaw-state -prune -o \
      -path /run/secrets/openclaw_config -prune -o \
      -path /tmp -prune -o \
      \( -type f -o -type d \) \
      -perm /0022 -exec chmod go-w {} + \
    && find / -xdev -type f -links +1 -exec sh -ec '\
      for file do \
        temporary="$(mktemp --tmpdir="$(dirname "$file")" .agentops-unlink.XXXXXX)"; \
        cp --reflink=never --preserve=mode,ownership,timestamps -- "$file" "$temporary"; \
        mv -fT -- "$temporary" "$file"; \
      done \
    ' sh {} + \
    && test -z "$(find / -xdev -perm /6000 -print -quit)" \
    && test -z "$(find / -xdev \
      -path /opt/agentops-worker/workspace -prune -o \
      -path /run/openclaw-state -prune -o \
      -path /run/secrets/openclaw_config -prune -o \
      -path /tmp -prune -o \
      \( -type f -o -type d \) \
      -perm /0022 -print -quit)" \
    && test -z "$(find / -xdev -type f -links +1 -print -quit)" \
    && test -f /opt/openclaw/node_modules/openclaw/dist/plugin-sdk/agent-runtime.js

FROM ${COMMERCIAL_BASE_IMAGE} AS runtime
ARG TARGETPLATFORM
USER root
RUN test "${TARGETPLATFORM}" = "linux/amd64"
COPY --from=openclaw-guest-root / /opt/agentops-provider/openclaw/
RUN find /opt/agentops-provider/openclaw -xdev -type d -exec chmod a-w {} + \
    && find /opt/agentops-provider/openclaw -xdev -type f -exec chmod a-w {} +
USER node
