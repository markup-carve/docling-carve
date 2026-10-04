FROM rust:1-bookworm AS builder
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/build && /opt/build/bin/pip install --no-cache-dir 'maturin>=1.9,<2'
WORKDIR /build
COPY Cargo.toml Cargo.lock pyproject.toml README.md LICENSE ./
COPY src ./src
COPY python ./python
RUN /opt/build/bin/maturin build --release --locked --out /wheels

FROM python:3.12-slim-bookworm
ARG EXTRAS=http,mcp
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && pip install --no-cache-dir "docling-carve[${EXTRAS}]==0.1.0" && rm -rf /wheels
RUN useradd --create-home --uid 10001 app
USER app
WORKDIR /home/app
EXPOSE 8080
ENTRYPOINT ["docling-carve"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
