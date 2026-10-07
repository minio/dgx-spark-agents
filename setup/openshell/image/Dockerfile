# Agent sandbox for the DGX Spark MemKV tests: NVIDIA's OpenShell base image
# plus OpenClaw, which needs Node 24 (the base ships Node 22).
FROM ghcr.io/nvidia/openshell-community/sandboxes/base@sha256:aeef1c63f00e2913ea002ccb3aaf925f338b5c5d70e63576f0d95c16a138044e

USER root
ARG NODE_VERSION=v24.21.0
ENV PATH=/opt/node24/bin:$PATH
RUN cd /tmp \
    && curl -fsSLO https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-x64.tar.xz \
    && curl -fsSL https://nodejs.org/dist/${NODE_VERSION}/SHASUMS256.txt | grep " node-${NODE_VERSION}-linux-x64.tar.xz$" | sha256sum -c - \
    && mkdir -p /opt/node24 \
    && tar -xJf node-${NODE_VERSION}-linux-x64.tar.xz -C /opt/node24 --strip-components=1 \
    && rm node-${NODE_VERSION}-linux-x64.tar.xz \
    && npm install -g --prefix /opt/node24 openclaw@2026.9.8 \
    && ln -sf /opt/node24/bin/openclaw /usr/local/bin/openclaw

USER sandbox
WORKDIR /sandbox
