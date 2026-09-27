# 光伏电站运维管理平台

面向集中式与分布式光伏电站的巡检计划、组件清洗、逆变器检修、发电监测、备品备件与故障处置的综合运维管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 电站档案 | `plant` | 光伏电站 | 电站编号、电站名称、装机容量 |
| 巡检计划 | `inspection` | 巡检任务 | 巡检编号、巡检站点、巡检类型 |
| 组件清洗 | `panel_clean` | 清洗任务 | 清洗编号、清洗区域、组件数量 |
| 逆变器管理 | `inverter` | 逆变器 | 逆变器编号、逆变器型号、额定功率 |
| 发电监测 | `power_data` | 发电记录 | 记录编号、电站编号、发电量 |
| 故障处置 | `fault` | 故障记录 | 故障编号、故障设备、故障现象 |
| 备件管理 | `spare_part` | 备品备件 | 备件编号、备件名称、适用设备 |
| 箱变管理 | `transformer` | 箱式变压器 | 箱变编号、箱变型号、额定容量 |
| 开关站管理 | `switchgear` | 开关设备 | 设备编号、设备名称、电压等级 |
| 关口计量 | `meter` | 计量表计 | 表计编号、表计型号、计量点位置 |
| 气象监测 | `weather` | 气象数据 | 站点编号、辐照度、风速 |
| 并网调度 | `grid_connect` | 调度指令 | 指令编号、调度机构、指令内容 |
| 电缆线路 | `cable` | 电缆段 | 电缆编号、电缆型号、起止位置 |
| 安防巡视 | `security` | 安防记录 | 巡视编号、巡视区域、巡视人员 |
| 定期检修 | `maintenance` | 检修计划 | 计划编号、设备名称、检修级别 |
| 汇流箱管理 | `dc_box` | 汇流箱 | 汇流箱编号、所属组串、输入支路 |
| 能效分析 | `energy_saving` | 能效报告 | 报告编号、电站编号、分析周期 |
| 安全培训 | `training` | 培训记录 | 培训编号、培训主题、培训讲师 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 能效报告流水线

能效报告的分析周期、系统效率、损失构成不手工填写，统一由
`backend/app/services/energy_pipeline.py` 从基准数据 `backend/app/baseline.py` 算出：

- 流水线可重复执行：每次先在暂存区算好全部报告，再把当前发布的旧结果整体隔离进
  归档表（`energy_saving_archive`，可经 `GET /api/energy_saving/archive` 备查），
  最后用暂存结果整体替换发布表，隔离与替换在同一把锁里完成。
- 触发方式：服务启动时自动跑一次；运行中可 `POST /api/energy_saving/pipeline/run`
  重跑（前端「能效分析」页面有对应按钮），运行记录见 `GET /api/energy_saving/pipeline/runs`。

## 启动约束

后端启动前先过构建依赖检查：`run.sh` 会执行 `python -m app.preflight`，
对照 `requirements.txt` 逐项检查，缺失时停止启动并列出缺失项；
应用 lifespan 里还会再查一次，随后跑首次能效流水线，全部成功才开始接收请求。
