# Supply the verified immutable AI image with --build-arg BASE_IMAGE.
# Source-only overlay: no apt/pip/npm operation and no USER/CMD/ENV change.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY app/ /app/
