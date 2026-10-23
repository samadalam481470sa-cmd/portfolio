# Runs the multi-user Job Finder web service 24/7.
#
# Build from the portfolio root. Docker cannot see sibling folders when the
# context is only this directory, and web/server.js loads ../../job-finder.
#
#   docker build -f newport-acquisition-crm/Dockerfile -t job-finder .
#   docker run -d --name job-finder -p 3000:3000 \
#     -v job-finder-data:/app/job-finder/users \
#     -e RUN_INTERVAL_HOURS=6 \
#     job-finder
#
# The named volume persists uploaded resumes and results across restarts.
# No npm dependencies — the app uses only the Node standard library.
FROM node:20-alpine

WORKDIR /app
COPY job-finder /app/job-finder
COPY newport-acquisition-crm/web /app/newport-acquisition-crm/web

# Resume uploads and per-user outputs live here; mount a volume to persist.
VOLUME ["/app/job-finder/users"]

ENV PORT=3000 \
    RUN_INTERVAL_HOURS=6

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD wget -qO- http://localhost:3000/healthz || exit 1

WORKDIR /app/newport-acquisition-crm
CMD ["node", "web/server.js"]
