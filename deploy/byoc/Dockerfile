# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3 AS dependencies
WORKDIR /opt/agentops/ui/next-app
COPY ui/next-app/package.json ui/next-app/package-lock.json ./
RUN npm ci --ignore-scripts

FROM dependencies AS build
COPY ui/next-app/ ./
RUN npm run build

FROM node:22-bookworm-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3 AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
RUN test "$(id -u node)" = "1000" \
    && test "$(id -g node)" = "1000" \
    && groupadd --gid 1100 agentops-broker \
    && groupadd --gid 1200 agentops-openclaw-runtime \
    && groupadd --gid 2100 agentops-openclaw-public \
    && groupadd --gid 2200 agentops-openclaw-private \
    && useradd --uid 1001 --gid 1000 --no-create-home --home-dir /nonexistent \
      --shell /usr/sbin/nologin agentops-openclaw-provider \
    && useradd --uid 1100 --gid 1100 --no-create-home --home-dir /nonexistent \
      --shell /usr/sbin/nologin agentops-openclaw-broker \
    && useradd --uid 1200 --gid 1200 --no-create-home --home-dir /nonexistent \
      --shell /usr/sbin/nologin agentops-openclaw-runtime \
    && usermod --append --groups 2100 node \
    && usermod --append --groups 2100,2200 agentops-openclaw-broker
WORKDIR /opt/agentops
COPY --from=build /opt/agentops/ui/next-app ./ui/next-app
COPY migrations/postgres ./migrations/postgres
COPY --chmod=0555 \
    deploy/byoc/node-healthcheck.mjs \
    deploy/byoc/node-secret-entrypoint.mjs \
    deploy/byoc/owner-bootstrap-entrypoint.mjs \
    deploy/byoc/openclaw-broker-entrypoint.mjs \
    deploy/byoc/openclaw-broker-contract.mjs \
    deploy/byoc/openclaw-phase-a03-image-contract.mjs \
    deploy/byoc/openclaw-provider-entrypoint.mjs \
    deploy/byoc/openclaw-provider-healthcheck.mjs \
    deploy/byoc/openclaw-provider-contract.mjs \
    deploy/byoc/worker-entrypoint.mjs \
    deploy/byoc/worker-healthcheck.mjs \
    deploy/byoc/worker-service-contract.mjs \
    deploy/byoc/postgres-dsn-for-restore.mjs \
    deploy/byoc/postgres-role-boundary-check.mts \
    deploy/byoc/restore-provision.sh \
    /usr/local/lib/agentops/
WORKDIR /opt/agentops/ui/next-app
RUN npm prune --omit=dev --ignore-scripts \
    && chown -R node:node /opt/agentops \
    && mkdir -p /run/agentops-openclaw \
    && chown 1001:1000 /run/agentops-openclaw \
    && chmod 0750 /run/agentops-openclaw \
    && install -d -o 1100 -g 2100 -m 0750 /run/agentops-openclaw-public \
    && install -d -o 0 -g 2200 -m 0750 /run/agentops-openclaw-private
ARG AGENTOPS_BUILD_IDENTITY=local
ARG AGENTOPS_SOURCE_REVISION=unknown
LABEL org.opencontainers.image.revision="${AGENTOPS_SOURCE_REVISION}" \
    io.agentops.byoc.build-identity="${AGENTOPS_BUILD_IDENTITY}"
USER node
EXPOSE 3001
CMD ["node", "scripts/start.mjs"]
