# Minimal Ubuntu 22.04 runtime for clean-sidecar e2e (R2-5).
# Built once with network; offline containers must never apt-get.
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
# Shared libs for PyInstaller onefile + python3 only for the e2e harness.
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends \
      ca-certificates libgomp1 libstdc++6 libgcc-s1 python3 \
 && rm -rf /var/lib/apt/lists/*
