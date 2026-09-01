<div align="center">
  <img src="desktop/app/resource/images/logo/CocoDownloader.png" alt="CoCo Downloader Logo" width="112" height="112" />
  <h1>CoCo Downloader</h1>
  <p>一个覆盖 Web 与桌面端的音乐搜索、播放和下载项目。</p>
</div>

<div align="center">

![Next.js](https://img.shields.io/badge/Next.js-16-black)
![React](https://img.shields.io/badge/React-19-149eca)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue)
![PyQt5](https://img.shields.io/badge/PyQt5-Desktop-41cd52)
![QFluentWidgets](https://img.shields.io/badge/QFluentWidgets-UI-0078d4)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

## 项目定位

CoCo Downloader 不是单一页面应用，而是一组围绕“音乐检索与获取体验”组织的 Web 与桌面客户端实现。

仓库当前包含两条主线：

- `src/`：主 Web 应用，提供音乐搜索、在线试听、批量下载、播放栏和主题体验。
- `desktop/`：PyQt5 桌面端，提供原生窗口、搜索列表、播放栏、下载任务管理和本地配置能力。

Web 端适合浏览器和 Docker 部署；桌面端适合打包成 Windows 安装包或便携版。

## 功能概览

### Web 应用

- 多音源聚合搜索
- 在线播放与底部播放器
- 播放、暂停、上一曲、下一曲、进度拖动、音量控制和播放模式切换
- 批量下载与下载抽屉
- JOOX 音质选择弹窗
- 深色 / 浅色主题切换
- 基于 Next.js App Router 的 API Routes

### 桌面端

`desktop/` 是 PyQt5 桌面客户端，核心体验更接近本地音乐工具。

主要能力：

- 搜索音乐并展示结果列表
- 播放、暂停、上一曲、下一曲、播放模式切换
- 播放进度拖动与音量控制
- 单曲下载与下载任务展示
- 下载目录和文件命名规则配置
- 浅色 / 深色 / 跟随系统主题
- 用户配置保存到系统 AppData 目录
- 支持 Nuitka 打包和 Inno Setup 安装包制作

## 架构解析

```text
coco-downloader/
├─ src/                         # 主 Web 应用
│  ├─ app/                      # Next.js App Router 页面与 API Routes
│  │  ├─ api/download/          # 下载接口
│  │  ├─ api/search/            # 搜索接口
│  │  └─ api/url/               # 播放直链接口
│  ├─ components/               # Web UI 组件
│  ├─ lib/providers/            # 音源 provider 策略实现
│  └─ types/                    # TypeScript 类型
├─ desktop/                     # PyQt5 桌面端
│  ├─ CoCo-downloader.py        # 桌面端入口
│  ├─ app/common/               # 配置、资源、信号总线和样式管理
│  ├─ app/components/           # 播放栏、搜索卡片、下载任务卡片等复用组件
│  ├─ app/services/             # 搜索、下载、播放和 provider 服务
│  ├─ app/view/                 # 主窗口、首页、下载页、设置页
│  └─ app/resource/             # qrc、qss、图片、翻译资源
├─ Dockerfile
├─ docker-compose.yml
└─ package.json
```

### Web 端分层

Web 主应用把“页面交互”和“音源解析”拆开：

- `src/app/page.tsx` 负责组织首页体验。
- `src/components/PlayerBar.tsx`、`DownloadDrawer.tsx`、`QualitySelectModal.tsx` 等组件承载交互界面。
- `src/app/api/*` 是浏览器调用的服务入口。
- `src/lib/providers/impl/*` 是各个音源的实际解析实现。

这种结构让前端不直接关心每个音源的细节。新增音源时，优先在 `providers` 层补实现，再在统一入口注册。

### 桌面端分层

桌面端按 Qt 应用常见边界拆分：

- `view/`：页面和窗口，如主窗口、首页、下载页、设置页。
- `components/`：可复用 UI 组件，如播放栏、搜索卡片、下载任务卡片。
- `services/`：业务服务，如搜索服务、下载服务、播放服务。
- `services/providers/`：不同音源 provider。
- `common/`：配置、资源、样式、信号总线等基础设施。
- `models/`：音乐数据模型。

配置文件通过 `QStandardPaths.AppDataLocation` 写入用户级 AppData 目录，避免打包后写入安装目录。

## 快速开始

### Web 主应用

```bash
npm install
npm run dev
```

默认访问：

```text
http://localhost:3000
```

生产构建：

```bash
npm run build
npm run start
```

### Docker

```bash
docker compose up -d
```

或直接运行镜像：

```bash
docker run -d -p 3000:3000 --name coco-downloader markcxx/coco-downloader:latest
```

### 桌面端

```bash
cd desktop
pip install -r requirements.txt
python CoCo-downloader.py
```

如果修改了 `resource.qrc`，需要重新生成 Qt 资源文件：

```bash
python -m PyQt5.pyrcc_main app/resource/resource.qrc -o app/common/resource.py
```

Windows 打包：

```bash
cd desktop
python deploy.py
```

安装包脚本位于：

```text
desktop/CoCo-downloader-setup.iss
```

## 音源说明

项目内聚合了多个第三方音乐搜索与解析来源。当前代码中包含的 provider 主要包括：

- 爱听
- 波点音乐
- 布谷音乐
- 歌曲宝
- 歌曲海
- 煎饼音乐系列（支持多平台解析）
- JOOX
- 米兔音乐
- LivePoo
- 咪咕音乐
- cenguigui解析（cenguigui API）
- 海棠解析（haitang API）
- XCVTS解析（xcvts/cyapi/vkeys API）
- QQMP3

不同音源的可用性、音质和返回字段会随第三方站点变化而变化。项目通过 provider 层隔离这些差异，尽量把上层 UI 和 API 保持稳定。

## 技术栈

### Web

- Next.js 16
- React 19
- TypeScript
- Tailwind CSS
- Framer Motion / motion
- Lucide React
- Axios
- Cheerio

### Desktop

- Python
- PyQt5
- PyQt-Fluent-Widgets
- PyQt5-Frameless-Window
- Nuitka
- Inno Setup


## 致谢

桌面端界面基于 [QFluentWidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) 构建。QFluentWidgets 为 PyQt/PySide 提供了 Fluent Design 风格的组件、设置卡片、导航、主题和图标体系，让桌面端能够以较低成本获得现代化的 Windows 应用体验。

感谢LINUXDO社区提供的帮助：https://linux.do/
感谢开源项目musicdl的部分接口支持： https://github.com/CharlesPikachu/musicdl

## 免责声明

1. 本项目仅供个人学习、技术研究与交流使用，严禁用于商业用途。
2. 项目不存储任何音乐文件，所有音乐内容均来自第三方公开API接口。
3. 项目中使用的所有音源接口均为第三方服务提供。
4. 第三方音源的可用性、数据准确性和版权状态不由本项目保证。
6. 请勿将本项目用于任何违反当地法律法规的行为，请尊重音乐版权。
7. 如本项目内容侵犯了您的权益，请通过 GitHub Issues 联系处理，我们会及时响应。
8. **下载的音乐文件仅供个人学习研究使用，，请支持正版音乐。**

## 许可证

本项目使用 MIT License。
