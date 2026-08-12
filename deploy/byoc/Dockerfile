# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3 AS peercred-build
RUN apt-get update \
    && apt-get install --yes --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY deploy/byoc/openclaw-peercred-gate.c ./
RUN gcc -std=c11 -O2 -fPIE -fstack-protector-strong \
      -D_FORTIFY_SOURCE=2 -Wall -Wextra -Werror \
      -Wl,-z,relro,-z,now,-z,noexecstack -pie \
      -o /agentops-openclaw-peercred-gate openclaw-peercred-gate.c \
    && strip --strip-all /agentops-openclaw-peercred-gate

FROM peercred-build AS runtime-launcher-build
COPY deploy/byoc/openclaw-runtime-launcher.c ./
RUN gcc -std=c11 -O2 -fPIE -fstack-protector-strong \
      -D_FORTIFY_SOURCE=2 -Wall -Wextra -Werror \
      -Wl,-z,relro,-z,now,-z,noexecstack -pie \
      -o /agentops-openclaw-runtime-launcher openclaw-runtime-launcher.c \
    && strip --strip-all /agentops-openclaw-runtime-launcher

FROM peercred-build AS runtime-path-resolver-build
COPY deploy/byoc/openclaw-runtime-path-resolver.c ./
RUN gcc -std=c11 -O2 -fPIE -fstack-protector-strong \
      -D_FORTIFY_SOURCE=2 -Wall -Wextra -Werror \
      -Wl,-z,relro,-z,now,-z,noexecstack -pie \
      -o /agentops-openclaw-runtime-path-resolver openclaw-runtime-path-resolver.c \
    && strip --strip-all /agentops-openclaw-runtime-path-resolver

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
COPY --from=peercred-build --chmod=0555 /agentops-openclaw-peercred-gate /usr/local/bin/agentops-openclaw-peercred-gate
COPY --from=runtime-launcher-build --chmod=0555 /agentops-openclaw-runtime-launcher /usr/local/bin/agentops-openclaw-runtime-launcher
COPY --from=runtime-path-resolver-build --chmod=0555 /agentops-openclaw-runtime-path-resolver /usr/local/bin/agentops-openclaw-runtime-path-resolver
COPY --chmod=0555 \
    deploy/byoc/node-healthcheck.mjs \
    deploy/byoc/node-secret-entrypoint.mjs \
    deploy/byoc/owner-bootstrap-entrypoint.mjs \
    deploy/byoc/openclaw-broker-entrypoint.mjs \
    deploy/byoc/openclaw-broker-contract.mjs \
    deploy/byoc/openclaw-boundary-supervisor.mjs \
    deploy/byoc/openclaw-boundary-supervisor-contract.mjs \
    deploy/byoc/openclaw-cgroup-v2.mjs \
    deploy/byoc/openclaw-cgroup-v2-contract.mjs \
    deploy/byoc/openclaw-executor-request.mjs \
    deploy/byoc/openclaw-executor-request-contract.mjs \
    deploy/byoc/openclaw-executor-protocol.mjs \
    deploy/byoc/openclaw-executor-protocol-contract.mjs \
    deploy/byoc/openclaw-executor-receipt.mjs \
    deploy/byoc/openclaw-executor-receipt-contract.mjs \
    deploy/byoc/openclaw-executor-runner.mjs \
    deploy/byoc/openclaw-executor-runner-contract.mjs \
    deploy/byoc/openclaw-executor-service.mjs \
    deploy/byoc/openclaw-executor-service-contract.mjs \
    deploy/byoc/openclaw-peercred-gate-contract.mjs \
    deploy/byoc/openclaw-phase-a03-image-contract.mjs \
    deploy/byoc/openclaw-phase-a07-image-contract.mjs \
    deploy/byoc/openclaw-provider-entrypoint.mjs \
    deploy/byoc/openclaw-provider-healthcheck.mjs \
    deploy/byoc/openclaw-provider-contract.mjs \
    deploy/byoc/openclaw-runtime-receipt.mjs \
    deploy/byoc/openclaw-runtime-receipt-contract.mjs \
    deploy/byoc/openclaw-runtime-manifest.mjs \
    deploy/byoc/openclaw-runtime-manifest-contract.mjs \
    deploy/byoc/openclaw-runtime-manifest-v2.mjs \
    deploy/byoc/openclaw-runtime-mount-policy.mjs \
    deploy/byoc/openclaw-runtime-rootfs-merkle.mjs \
    deploy/byoc/openclaw-runtime-path-resolver-contract.mjs \
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
    && install -d -o 0 -g 2200 -m 0750 /run/agentops-openclaw-private \
    && install -d -o 0 -g 2200 -m 0700 /var/lib/agentops-openclaw/replay
ARG AGENTOPS_BUILD_IDENTITY=local
ARG AGENTOPS_SOURCE_REVISION=unknown
LABEL org.opencontainers.image.revision="${AGENTOPS_SOURCE_REVISION}" \
    io.agentops.byoc.build-identity="${AGENTOPS_BUILD_IDENTITY}"
USER node
EXPOSE 3001
CMD ["node", "scripts/start.mjs"]
