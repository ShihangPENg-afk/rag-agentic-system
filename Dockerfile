ARG PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.10-slim
ARG SKIP_SYSTEM_DEPS=false
ARG SKIP_PIP_INSTALL=false

FROM ${PYTHON_BASE_IMAGE}

ARG SKIP_SYSTEM_DEPS
ARG SKIP_PIP_INSTALL

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# faiss-cpu 预编译 wheel 在 Linux 上依赖 OpenMP 运行时
RUN if [ "$SKIP_SYSTEM_DEPS" != "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends libgomp1 \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY requirements.txt .

RUN if [ "$SKIP_PIP_INSTALL" != "true" ]; then \
      pip install --upgrade pip && pip install -r requirements.txt; \
    fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
