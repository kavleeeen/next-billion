# The pipeline has no runtime dependencies, so the image is the interpreter,
# the source, and the database. No build step and nothing to install.
FROM python:3.13-slim

WORKDIR /app
COPY backend/pipeline/ ./backend/pipeline/
COPY frontend/ ./frontend/
COPY data/next-billion.db ./data/next-billion.db

# ROOT resolves from the package, so the layout above has to match the repo.
ENV PYTHONUNBUFFERED=1
WORKDIR /app/backend

# Cloud Run states the port in $PORT; serve() reads it. 0.0.0.0 is required to
# accept anything from outside the container.
CMD ["python", "-m", "pipeline.server", "--host", "0.0.0.0"]
