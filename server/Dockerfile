# Shadow Cursor cloud on Aiven: build context is the repo root (containerfile_path server/Dockerfile).
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir aiohttp==3.13.2
COPY server/proxy.py brain/static/index.html ./
# The Mac app, split in parts under GitHub's 100 MB file limit (branch `deploy` only)
COPY server/dl/ ./dl/
RUN cat dl/Shadow-Cursor.dmg.part-* > Shadow-Cursor.dmg 2>/dev/null; rm -rf dl
EXPOSE 8080
CMD ["python", "proxy.py"]
