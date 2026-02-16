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

# 1. 创建虚拟环境
python3 -m venv venv

# 2. 激活虚拟环境并安装依赖
source venv/bin/activate
pip3 install -r requirements.txt
```

### 3. 配置文件
创建并编辑 `.env` 文件（参考 `.env.example`）：
```bash
vi .env
```
确保填入正确的 `LB_ACCESS_TOKEN` 和监控标的 `MONITOR_SYMBOLS`。

### 4. 后台常驻运行
使用 `nohup` 在后台运行程序（注意使用虚拟环境中的 python）：
```bash
nohup ./venv/bin/python3 main.py > monitor.log 2>&1 &
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

## 系统服务部署 (Systemd) - 推荐

为了保证服务 7x24 小时稳定运行，建议使用 Systemd 进行管理。

### 1. 准备服务文件
项目根目录下已提供 `watchlist-monitor.service` 模板。
你需要根据实际路径修改文件中的 `WorkingDirectory` 和 `ExecStart`。

```ini
[Service]
User=root  # 建议使用非 root 用户
WorkingDirectory=/opt/longport_stock_monitor
# 使用虚拟环境中的 python 解释器
ExecStart=/opt/longport_stock_monitor/venv/bin/python3 -m src.monitor.watchlist_monitor
StandardOutput=append:/opt/longport_stock_monitor/logs/monitor.log
StandardError=append:/opt/longport_stock_monitor/logs/error.log
```

### 2. 安装服务
```bash
# 复制服务文件到系统目录
sudo cp watchlist-monitor.service /etc/systemd/system/

# 重新加载 Systemd 配置
sudo systemctl daemon-reload
```

### 3. 启动与管理
```bash
# 启动服务
sudo systemctl start watchlist-monitor

# 设置开机自启
sudo systemctl enable watchlist-monitor

# 查看状态
sudo systemctl status watchlist-monitor

# 停止服务
sudo systemctl stop watchlist-monitor

# 查看日志
tail -f logs/monitor.log
```

### 4. 安全加固
建议创建一个专用用户运行服务：
```bash
sudo useradd -r -s /bin/false appuser
sudo chown -R appuser:appuser /path/to/LongBridge_Auto_Deal
```
然后在 service 文件中设置 `User=appuser`。
