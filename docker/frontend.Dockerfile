FROM node:24-bookworm-slim
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build && chown -R node:node /app
USER node
CMD ["npm", "start", "--", "--hostname", "0.0.0.0"]
