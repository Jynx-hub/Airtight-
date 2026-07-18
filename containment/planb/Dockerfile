# One image for all three roles (gate / upstream / sandbox). The repo is mounted at
# /app at runtime (read-only for the sandbox), so this only needs the interpreter +
# pyyaml (containment.policy parses the YAML). No app code is COPYed in.
FROM python:3.12-slim
RUN pip install --no-cache-dir "pyyaml>=6.0"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
