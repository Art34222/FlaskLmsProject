#!/bin/bash

if [ "$EUID" -ne 0 ]; then
  echo "Пожалуйста, запустите скрипт от имени root (через sudo)"
  exit 1
fi

set -e

echo "Начинаем развертывание проекта EduOnline..."

echo "Обновление системы..."
apt update && apt upgrade -y

read -r -p "Введите желаемый порт для SSH (по умолчанию 22): " SSH_PORT
read -r -p "Введите ваш домен (например, edu.example.com): " DOMAIN_NAME
read -r -p "Введите email для Let's Encrypt (для уведомлений): " LETSENCRYPT_EMAIL
SSH_PORT=${SSH_PORT:-22}

echo "Настройка SSH на порт $SSH_PORT..."
sed -i "s/^#\?Port .*/Port $SSH_PORT/" /etc/ssh/sshd_config
systemctl daemon-reload
systemctl restart ssh

echo "Настройка UFW..."
ufw allow "$SSH_PORT/tcp"
ufw allow 80
ufw allow 443
ufw --force enable

# 3. Скачивание репозитория
echo "Клонирование репозитория..."
rm -rf /opt/eduonline
git clone https://github.com/Art34222/FlaskLmsProject /opt/eduonline
cd /opt/eduonline

echo "Установка uv и Python 3.14 NO GIL..."
mkdir -p /opt/pythonnogil/bin

export UV_INSTALL_DIR="/opt/pythonnogil/bin"
export UV_CACHE_DIR="/opt/pythonnogil/cache"
export UV_PYTHON_INSTALL_DIR="/opt/pythonnogil/python"

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/opt/pythonnogil/bin:$PATH"

echo "Создание виртуального окружения..."
uv venv --python 3.14t .venv

echo "Установка зависимостей..."
VIRTUAL_ENV=/opt/eduonline/.venv uv pip install -r requirements.txt

echo "Генерация .env файла с SECRET_KEY..."
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
cat <<EOF > /opt/eduonline/.env
SECRET_KEY=$SECRET_KEY
EOF

echo "Создание пользователя eduonline..."
if ! id "eduonline" &>/dev/null; then
    useradd -r -s /bin/false eduonline
fi
chown -R eduonline:www-data /opt/eduonline
chown -R eduonline:www-data /opt/pythonnogil

echo "Применение настроек sysctl..."
cp /opt/eduonline/for_deployment/99-eduonline.conf /etc/sysctl.d/
sysctl --system

echo "Настройка systemd сервиса..."
cp /opt/eduonline/for_deployment/eduonline.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable eduonline.service
systemctl start eduonline.service

echo "Установка Nginx и Certbot..."
apt install -y nginx certbot

echo "Временная остановка Nginx для получения SSL-сертификата..."
systemctl stop nginx

echo "Получение сертификата для $DOMAIN_NAME..."
certbot certonly --standalone -d "$DOMAIN_NAME" --key-type ecdsa --elliptic-curve secp384r1 --non-interactive --agree-tos -m "$LETSENCRYPT_EMAIL"

echo "Настройка Nginx..."
rm -f /etc/nginx/sites-enabled/default
sed -i "s/edu.ch-moltisanti.ru/$DOMAIN_NAME/g" /opt/eduonline/for_deployment/fallback.conf
cp /opt/eduonline/for_deployment/fallback.conf /etc/nginx/conf.d/fallback.conf
cp /opt/eduonline/for_deployment/nginx.conf /etc/nginx/nginx.conf
nginx -t

echo "Запуск Nginx..."
systemctl start nginx
systemctl enable nginx

echo "====================================================="
echo "✅ Развертывание успешно завершено!"
echo "Ваш сайт должен быть доступен по адресу https://$DOMAIN_NAME"
echo "Новый SSH порт: $SSH_PORT"
echo "====================================================="
