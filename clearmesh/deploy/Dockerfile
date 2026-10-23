FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY clearmesh ./clearmesh
COPY tools ./tools
COPY sim ./sim
COPY samples ./samples
COPY scripts ./scripts
RUN pip install --no-cache-dir -e ".[dev]"
EXPOSE 26657
CMD ["clearmesh", "version"]
