# syntax=docker/dockerfile:1.7
ARG NODE_IMAGE
FROM ${NODE_IMAGE}

WORKDIR /opt/openclaw

COPY --chown=0:0 deploy/byoc/openclaw-runtime-artifact/package.json \
    deploy/byoc/openclaw-runtime-artifact/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --ignore-scripts --omit=dev --no-audit --no-fund \
    && npm cache clean --force \
    && test "$(node --version)" = "v22.23.2" \
    && test "$(node -p 'require(\"openclaw/package.json\").version')" = "2026.5.4"

COPY --chown=0:0 --chmod=0555 deploy/byoc/openclaw-stdin-provider.mjs \
    /opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs
COPY --chown=0:0 --chmod=0444 deploy/byoc/openclaw-runtime-artifact/artifact.json \
    /opt/agentops/openclaw-runtime-artifact.json

RUN find /opt/openclaw /opt/agentops -xdev -type d -exec chmod 0555 {} + \
    && find /opt/openclaw /opt/agentops -xdev -type f -exec chmod 0444 {} + \
    && chmod 0555 /opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs \
    && test -f /opt/openclaw/node_modules/openclaw/dist/plugin-sdk/agent-runtime.js

USER 1200:1200
WORKDIR /
ENTRYPOINT ["/usr/local/bin/node", "/opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs"]
CMD ["--stdin-protocol=canonical_provider_request_stdin_v1"]
