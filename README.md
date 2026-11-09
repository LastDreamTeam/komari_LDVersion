# komari_LDVersion

LastDream 维护的 [Komari](https://github.com/komari-monitor/komari) **主题与部署辅助**归档：在官方 release 二进制之上，附带第三方主题 [miku39](https://github.com/vioIetMiku/komari-theme-miku39) 的定制树，以及可选的 systemd / nginx / 流量示意采样脚本。

本仓 **不含** 私有 Go 面板源码 diff；面板程序按官方 release 下载即可（校验见 `meta/VERSION.json`）。

## 和官方差在哪

| 层 | 官方 [komari-monitor/komari](https://github.com/komari-monitor/komari) | 本仓 `main` |
|----|------------------------------------------------------------------------|-------------|
| 面板程序 | Go 源码 + release 二进制 | **使用官方 linux-amd64 二进制**（示例校验对应 1.6.0），**无私有 Go 源码 diff** |
| 默认主题 | 官方自带主题 | 第三方主题 **miku39** + **LD 前端/配置改动** |
| 地球仪汇聚 | 主题自带目的地选项 | `default_destination=auto`：换监控机时跑一次 `theme/miku39/scripts/init-host-destination.py`，按面板出口写死坐标，日常打开不再请求 geo |
| 地球仪交互 | 主题原版 | LD：缩放默认值、右侧列表、探针拓扑 / 数据收发模式等（见 `theme/miku39/dist/`） |
| 「数据收发」 | 无 | 可选采样器 `scripts/miku39-flow/` 写 `flows.json`，地球仪可画机间流量示意（密钥不入库） |
| 部署辅助 | 自行装 | 示例：`deploy/systemd`、`deploy/nginx/panel.example.com.conf`、可选 eth0 CAKE QoS |

一句话：**后端=官方原版；差别几乎全在主题与可选运维脚本。**

## 和本仓 `legacy/main_original` 差在哪

| | `legacy/main_original` | `main`（本分支） |
|--|------------------------|------------------|
| 内容 | 归档前旧 `main`：fork 上游的**完整源码树** | **orphan 新根**：主题定制 + 部署辅助 + 文档 |
| 历史 | 保留 fork 提交链 | **不继承** legacy 提交，避免「上游源码」和「主题/部署树」缠在一条历史上 |
| 用途 | 查上游源码 / 对照官方 | 复现 miku39 定制与示例部署布局 |
| SHA（归档时） | `62af91037924057b961dff7b93beacd3f76a81e8` | 见最新 `main` |

需要官方源码：看 `legacy/main_original` 或直接去官方仓。需要主题/部署辅助：看本 `main`。

## 二进制参考（1.6.0）

- Komari **1.6.0** / git `1b76b7ad5bc3de6529bb7f0577069b4ac241fec3` = 官方 tag [1.6.0](https://github.com/komari-monitor/komari/releases/tag/1.6.0)
- 主题短名 `miku39`，`komari-theme.json` version 以树内为准（约 1.4.x + LD 改动）
- 校验哈希见 `meta/VERSION.json`（二进制本体不入库）

## 目录

```
theme/miku39/          # miku39 主题树（含 dist、scripts）
deploy/systemd/        # komari / agent / miku39-flow-sampler / QoS 示例单元
deploy/nginx/          # panel.example.com 反代示例（证书路径占位）
deploy/agent/          # config.example.json（无 token）
deploy/ld-eth0-qos.sh  # 可选 eth0 CAKE 示例
scripts/miku39-flow/   # 「数据收发」采样器（hosts.example.json）
docs/                  # QOS.txt 等
meta/VERSION.json
```

## 明确不入库

- `komari.db` / `metrics.db`（及 wal/shm）
- Admin 密码、API key、agent token、`/opt/komari/token`
- TLS 私钥与完整证书链
- 真实 `hosts.json`（含主机地址与 SSH 端口）；仓内仅保留 `hosts.example.json` 文档占位
- `hosts.json` 里的 SSH 密码、采样器私钥
- 运行态流量样本 `flows.json`、`flows-state.json`（「数据收发」采样结果）
- agent `config.json` / `ca.pem`、`cache/dist`
- `geoip-cache.json`、官方二进制本体（按 release 重建）
- 本地备份杂项 `*.bak*` / `*.broken*`
- 任何生产拓扑、主机代号、真实面板域名或截图

## 重建提示

1. 官方 release 下载 `komari-linux-amd64`，校验 `meta/VERSION.json` 的 sha256 → `/opt/komari/komari`
2. 装 `deploy/systemd/`，`WorkingDirectory=/opt/komari`
3. 展开 `theme/miku39` → `/opt/komari/data/theme/miku39`；换监控机后跑一次 `theme/miku39/scripts/init-host-destination.py`
4. nginx 参考 `deploy/nginx/panel.example.com.conf`，改成自己的域名与证书路径
5. 采样器（可选）：`scripts/miku39-flow/` → `/opt/miku39-flow/`，自备 `hosts.json` 与密钥，**勿提交密钥**

## 上游

- 官方：https://github.com/komari-monitor/komari
- 主题上游（第三方）：https://github.com/vioIetMiku/komari-theme-miku39
- 本仓旧源码树：`legacy/main_original`
