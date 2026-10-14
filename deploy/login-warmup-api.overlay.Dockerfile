# Supply the verified immutable security image with --build-arg BASE_IMAGE.
# The release manifest pins the expected digest. Preserve parent USER/CMD/ENV.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY app/ /app/
