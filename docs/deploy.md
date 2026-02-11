# 服务器部署指南

## 环境要求
*   **OS**: Ubuntu 20.04+ / CentOS 7+
*   **Python**: 3.8 或更高版本
*   **网络**: 需能访问长桥 OpenAPI 服务器及飞书/钉钉 API

## 部署步骤

### 1. 安装 Python 环境
如果服务器未安装 Python 3.8+：
```bash
# Ubuntu
sudo apt update
sudo apt install python3 python3-pip -y

# CentOS
sudo yum install python3 python3-pip -y
```

### 2. 获取代码与安装依赖
```bash
# 假设代码已上传至服务器
cd LongBridge_Auto_Deal
pip3 install -r requirements.txt
```

### 3. 配置文件
创建并编辑 `.env` 文件（参考 `.env.example`）：
```bash
vi .env
```
确保填入正确的 `LB_ACCESS_TOKEN` 和监控标的 `MONITOR_SYMBOLS`。

### 4. 后台常驻运行
使用 `nohup` 在后台运行程序：
```bash
nohup python3 main.py > monitor.log 2>&1 &
```

### 5. 运维管理

#### 查看日志
```bash
# 实时查看日志
tail -f monitor.log
```

#### 停止程序
```bash
# 查找进程 ID
ps -ef | grep main.py

# 停止进程
kill <PID>
```

#### 故障排查
*   **行情断连**：检查服务器网络是否稳定，查看日志中是否有 `Reconnect` 相关信息。
*   **无告警**：检查 `.env` 中 Webhook 地址是否正确，或测试脚本 `tests/test_notification.py`。
