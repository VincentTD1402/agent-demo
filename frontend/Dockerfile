FROM node:24-alpine AS web
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.29-alpine
# Image nginx tự chạy envsubst cho mọi file trong /etc/nginx/templates
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=web /app/dist /usr/share/nginx/html
EXPOSE 80
