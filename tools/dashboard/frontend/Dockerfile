# =============================================================================
# DexAI Frontend Dockerfile
# Multi-stage build for Next.js application
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# -----------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files and install all dependencies (including devDependencies for build)
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source files
COPY . .

# Build the application
# NEXT_PUBLIC_API_URL is baked in at build time
# Default empty = relative URLs (works with Caddy proxy)
# Set to http://hostname:8080 if not using proxy
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
# Prevent runaway Node heap usage during builds (helps avoid WSL/host OOM)
ENV NODE_OPTIONS=--max-old-space-size=4096
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Runtime
# -----------------------------------------------------------------------------
FROM node:20-alpine AS runtime

WORKDIR /app

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Set environment variables
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    # Prevent runaway Node heap usage at runtime (helps avoid WSL/host OOM)
    NODE_OPTIONS=--max-old-space-size=4096 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

# Copy built application
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Switch to non-root user
USER nextjs

# Expose port
EXPOSE 3000

# Start the application
CMD ["node", "server.js"]
