ARG POSTGRES_BASE_IMAGE=public.ecr.aws/docker/library/postgres:16-alpine

FROM ${POSTGRES_BASE_IMAGE} AS builder

ARG PGVECTOR_VERSION=0.8.1

RUN apk add --no-cache --virtual .build-deps \
    build-base \
    ca-certificates \
    wget \
    && wget -O /tmp/pgvector.tar.gz "https://github.com/pgvector/pgvector/archive/refs/tags/v${PGVECTOR_VERSION}.tar.gz" \
    && mkdir -p /tmp/pgvector \
    && tar -xzf /tmp/pgvector.tar.gz -C /tmp/pgvector --strip-components=1 \
    && cd /tmp/pgvector \
    && make OPTFLAGS="" with_llvm=no \
    && make install with_llvm=no

FROM ${POSTGRES_BASE_IMAGE}

COPY --from=builder /usr/local/lib/postgresql/vector.so /usr/local/lib/postgresql/vector.so
COPY --from=builder /usr/local/share/postgresql/extension/vector* /usr/local/share/postgresql/extension/
