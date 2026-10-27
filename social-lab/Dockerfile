# Social Lab container (used by Railway; works on any Docker host).
# No dependencies to install: the image is Node plus this folder.
FROM node:24-alpine
WORKDIR /app
COPY . .
# Sessions are written here while recorded; with DATA_REPO set they are moved
# to the data repository when they end. The app runs as the unprivileged
# "node" user and can write nowhere else.
RUN mkdir -p /app/data && chown node:node /app/data
USER node
ENV NODE_ENV=production
EXPOSE 8090
CMD ["node", "server/server.mjs"]
