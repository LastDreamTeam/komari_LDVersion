# komari_LDVersion

LastDream 对 [komari-monitor/komari](https://github.com/komari-monitor/komari) 的**现役存档仓**（面板入口：[panel.example.com](https://panel.example.com)）。

## 和官方差在哪

| 层 | 官方 [komari-monitor/komari](https://github.com/komari-monitor/komari) | 本仓 `main`（example-host-a现役） |
|----|------------------------------------------------------------------------|-------------------------|
| 面板程序 | Go 源码 + release 二进制 | **直接用官方 1.6.0 linux-amd64 二进制**，**无私有 Go 源码 diff**（校验见 `meta/VERSION.json`） |
| 默认主题 | 官方自带主题 | 第三方主题 **miku39** 的现役树 + **LD 改过的前端/配置** |
| 地球仪汇聚 | 主题自带目的地选项 | `default_destination=auto`：换监控机时跑一次 `theme/miku39/scripts/init-host-destination.py`，按面板公网 IP 写死坐标，**日常打开不再请求 geo** |
| 地球仪交互 | 主题原版缩放/列表 | LD：默认 zoom / 最大缩放、右侧列表高度、主机网格列数绑定显示尺寸、探针拓扑 / 节点加速模式等（见主题 `dist/` 与历史笔记） |
| 「数据收发」 | 无 | 机上采样器 `scripts/miku39-flow/` 写 `flows.json`，地球仪可画机间流量示意（密钥不入库） |
| 部署 | 自行装 | `deploy/systemd` + `deploy/nginx` + eth0 CAKE QoS（`deploy/ld-eth0-qos.sh`） |

一句话：**后端=官方原版；差别几乎全在主题与机上运维脚本。**

## 和本仓 `legacy/main_original` 差在哪

| | `legacy/main_original` | `main`（本分支） |
|--|------------------------|------------------|
| 内容 | 归档前旧 `main`：fork 上游的**完整源码树** | **orphan 新根**：example-host-a部署快照（主题 + 单元 + 脚本 + 文档） |
| 历史 | 保留 fork 提交链 | **不继承** legacy 提交，避免「上游源码」和「现役快照」缠在一条历史上 |
| 用途 | 查上游源码 / 对照官方 | 复现/版本控制**现在线上在跑的东西** |
| SHA（归档时） | `62af91037924057b961dff7b93beacd3f76a81e8` | 见最新 `main`（推送后更新） |

需要官方源码：看 `legacy/main_original` 或直接去官方仓。需要「咱们现在机上那套」：看本 `main`。

## 现役快照

- 时间：**2026-11-09 17:38 CST**（截图另见下方，可能略晚）
- 主机：example-host-a `example.invalid` · 入口 https://panel.example.com
- Komari **1.6.0** / git `1b76b7ad5bc3de6529bb7f0577069b4ac241fec3` = 官方 tag [1.6.0](https://github.com/komari-monitor/komari/releases/tag/1.6.0)
- 主题短名 `miku39`，`komari-theme.json` version 以树内为准（现役约 1.4.x LD 改版）


## 目录

```
theme/miku39/          # example-host-a /opt/komari/data/theme/miku39（含 dist、scripts）
deploy/systemd/        # komari / agent / miku39-flow-sampler / QoS
deploy/nginx/          # panel.example.com 反代（证书路径占位）
deploy/agent/          # config.example.json（无 token）
deploy/ld-eth0-qos.sh
scripts/miku39-flow/   # 地球仪「数据收发」采样器（hosts.example.json）
docs/                  # QOS.txt / ROLLBACK.txt / screenshots/
meta/VERSION.json
```

## 明确不入库

- `komari.db` / `metrics.db`（及 wal/shm）
- Admin 密码、API key、agent token、`/opt/komari/token`
- TLS 私钥与完整证书链
- 真实 `hosts.json`（含舰队公网 IP 与非标准 SSH 端口）；仓内仅保留 `hosts.example.json` 文档占位
- `hosts.json` 里的 SSH 密码、采样器私钥
- 运行态流量样本 `flows.json`、`flows-state.json`（地球仪「数据收发」采样结果，含 peer IP）
- agent `config.json` / `ca.pem`、`cache/dist`
- `geoip-cache.json`、官方二进制本体（按 release 重建）
- 本地备份杂项 `*.bak*` / `*.broken*`

## 重建提示

1. 官方 release 下载 `komari-linux-amd64`，校验 `meta/VERSION.json` 的 sha256 → `/opt/komari/komari`
2. 装 `deploy/systemd/`，`WorkingDirectory=/opt/komari`
3. 展开 `theme/miku39` → `/opt/komari/data/theme/miku39`；换监控机后跑一次 `scripts/init-host-destination.py`
4. nginx 用 `deploy/nginx/panel.example.com.conf`，证书自备
5. 采样器：`scripts/miku39-flow/` → `/opt/miku39-flow/`，自备 `hosts.json` 与密钥，**勿提交密钥**

## 上游

- 官方：https://github.com/komari-monitor/komari
- 主题上游（第三方）：https://github.com/vioIetMiku/komari-theme-miku39
- 本仓旧源码树：`legacy/main_original`
