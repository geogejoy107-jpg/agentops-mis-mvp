# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
ARG NODE_IMAGE
FROM ${NODE_IMAGE}

WORKDIR /opt/openclaw

COPY --chown=0:0 deploy/byoc/openclaw-runtime-artifact/package.json \
    deploy/byoc/openclaw-runtime-artifact/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --ignore-scripts --omit=dev --no-audit --no-fund \
    && npm cache clean --force \
    && test "$(node --version)" = "v22.23.2" \
    && test "$(node -p 'JSON.parse(require("fs").readFileSync("node_modules/openclaw/package.json", "utf8")).version')" = "2026.5.4"

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
    && find / -xdev -type f -perm /6000 -exec chmod a-s {} + \
    && test -z "$(find / -xdev -type f -perm /6000 -print -quit)" \
    && test -f /opt/openclaw/node_modules/openclaw/dist/plugin-sdk/agent-runtime.js

USER 1200:1200
WORKDIR /
ENTRYPOINT ["/usr/local/bin/node", "/opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs"]
CMD ["--stdin-protocol=canonical_provider_request_stdin_v1"]
