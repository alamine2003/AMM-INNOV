# Image de développement frontend : serveur Vite avec rechargement à chaud.
# Le code est monté en volume (./frontend:/app) ; node_modules reste dans un
# volume anonyme pour ne pas écraser l'installation faite dans l'image.
ARG NODE_VERSION=24
FROM node:${NODE_VERSION}-alpine

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
