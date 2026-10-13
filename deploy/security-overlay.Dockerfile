# Build with a curated app/ directory containing only reviewed security changes.
# BASE_IMAGE must be the immutable deployed release (or its local verified tag).
ARG BASE_IMAGE=lms-api:preflight-20261009
FROM ${BASE_IMAGE}
USER root
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && (getent group lms >/dev/null || groupadd --gid 10001 lms) \
    && (id lms >/dev/null 2>&1 || useradd --uid 10001 --gid lms --create-home lms) \
    && test "$(id -u lms)" = 10001 && test "$(id -g lms)" = 10001
COPY app/ /app/
RUN mkdir -p /app/media && chown lms:lms /app/media
USER 10001:10001
