FROM python:3.10-slim

WORKDIR /app

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install --upgrade pip

COPY . .

# [CUSTOM] 生产镜像只安装运行时依赖，避免 .[all] 拉取未使用 provider。
RUN pip install ".[runtime]" \
    && rm -rf /root/.cache/pip

EXPOSE 5000

CMD ["python", "app.py"]
