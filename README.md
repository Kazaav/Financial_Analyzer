# Financial Analyzer 运维说明书与变更记录

## 1. 项目定位

Financial Analyzer 是一个面向日本企业有価証券報告書 PDF 的在线数据提取、整合、指标计算和可视化平台。

当前产品原则：

- 以 PDF 原文中的可复制文本为基础，抽出结构化财务数据。
- 提供多文件整合、多公司同年份比较、同一公司多年份推移、自定义文件比较。
- 提供规则明确的派生指标、排名、折线图和报告导出。
- 不提供企业经营状况的定性判断、投资建议、风险判断或“所见”式自动评论。
- 所有非 PDF 原文直接提供、而是由系统计算得到的指标，应在前端用 info 提示说明公式。

## 2. 线上部署信息

- 线上域名：`https://fincial.zekkx.icu`
- 服务器：`43.167.247.182`
- 反向代理：Caddy
- Caddy 配置文件：`/etc/caddy/Caddyfile`
- 应用 systemd 服务：`financial-analyzer.service`
- 应用监听地址：`127.0.0.1:8010`
- 应用根目录：`/opt/financial-analyzer`
- 当前运行版本：`/opt/financial-analyzer/current`
- 历史 release：`/opt/financial-analyzer/releases/<YYYYMMDDHHMMSS>`
- Python 虚拟环境：`/opt/financial-analyzer/venv`
- 生产环境变量文件：`/etc/financial-analyzer.env`
- 数据目录：`/var/lib/financial-analyzer`
- 上传 PDF：`/var/lib/financial-analyzer/uploads`
- 分析 JSON：`/var/lib/financial-analyzer/analyses`
- HTML 报告：`/var/lib/financial-analyzer/reports`

Caddy 站点块：

```caddy
fincial.zekkx.icu {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8010
}
```

## 3. 认证和权限

应用层内置登录，不依赖 Caddy basicauth。登录由 `app/auth.py` 处理，session cookie 为 HTTP-only。

当前角色：

- `admin`：可上传、分析、生成报告、删除 PDF、重解析 PDF、手动补正抽出结果。
- `guest`：可上传、分析、生成报告，但不能删除、重解析或补正已有抽出结果。

当前账号在 `/etc/financial-analyzer.env` 的 `FINANCIAL_ANALYZER_USERS` 中以哈希形式保存。不要在 README 中追加明文密码。若修改账号，请记录修改日期、修改人、账号名和角色，不记录明文密码。

相关环境变量：

- `FINANCIAL_ANALYZER_SESSION_SECRET`：session 签名密钥。
- `FINANCIAL_ANALYZER_SESSION_MAX_AGE_SECONDS`：登录保持时间，当前为 12 小时。
- `FINANCIAL_ANALYZER_COOKIE_SECURE`：线上为 `1`，只通过 HTTPS 发送 cookie。

## 4. 数据保留与自动清理

清理由 `app/cleanup.py` 执行。

当前策略：

- `FINANCIAL_ANALYZER_RETENTION_DAYS=7`
- 上传 PDF、分析 JSON、生成报告最长保留 7 天。
- 应用启动时强制执行一次清理。
- 用户访问时最多每 `FINANCIAL_ANALYZER_CLEANUP_INTERVAL_SECONDS=900` 秒触发一次清理。
- 清理只会删除 `/var/lib/financial-analyzer` 下属于本应用的数据。

如果将来需要“访问一次后即删除”的分享型报告，应新增单独的一次性分享表，不建议直接把主分析会话改成一次性删除，否则用户刷新页面会丢失分析结果。

## 5. 后端程序说明

### `app/main.py`

FastAPI 入口文件，负责挂载静态文件、注册模板过滤器、登录登出、健康检查、认证中间件、清理中间件、PDF 上传、分析页渲染、管理员删除/重解析/补正、报告生成和报告下载。

主要路由：

- `GET /login`：登录页。
- `POST /login`：登录提交。
- `GET /logout`：退出登录。
- `GET /healthz`：健康检查。
- `GET /`：首页和上传入口。
- `POST /upload`：创建新分析会话。
- `GET /analysis/{analysis_id}`：分析页。
- `POST /analysis/{analysis_id}/upload`：向已有分析追加 PDF。
- `POST /analysis/{analysis_id}/reparse`：管理员重解析。
- `POST /analysis/{analysis_id}/documents/delete`：管理员删除选定 PDF。
- `POST /analysis/{analysis_id}/documents/{doc_id}`：管理员补正单份 PDF 的抽出结果。
- `POST /analysis/{analysis_id}/report`：生成 HTML 报告。
- `GET /reports/{filename}`：下载报告。

### `app/auth.py`

负责解析 `FINANCIAL_ANALYZER_USERS`、PBKDF2-SHA256 密码验证、signed session cookie、管理员权限判断、未登录跳转。

### `app/cleanup.py`

负责按保留天数删除过期分析 JSON、对应上传 PDF、对应报告 HTML，并控制清理频率。

### `app/pdf_parser.py`

负责 PDF 文本抽出和财务指标抽出：读取 PDF 文本、标准化日文与数字、抽出会社名/EDINET/証券コード/事業年度/事業期間，从主要指标、资产负债表、损益表、现金流量表中抽出数值并记录来源页。

### `app/analysis.py`

负责结构化数据整合、派生指标和可视化数据生成：分析模式选择、同一公司 key、派生指标、KPI、ランキング、折线图 SVG 坐标。本模块不再生成企业定性分析，不提供 `所見`、经营风险判断或自动评价文字。

### `app/models.py`

定义 `FinancialDocument` 和 `AnalysisRecord`。

### `app/storage.py`

负责 JSON 持久化：保存、读取、列出分析会话。

### `app/reporting.py`

负责生成嵌入 CSS 的 HTML 报告。

### `app/formatting.py`

负责金额、百分比、比率、人数等模板格式化。

### `app/settings.py`

负责程序目录、存储目录、清理周期、session 有效期和 cookie 安全设置。

### `app/ai_providers.py`

AI Provider 预留层。当前产品默认不使用 AI。若将来接入 DeepSeek、MiniMax 等 API，应在此扩展，并在本 README 的变更记录中说明用途、输入输出和隐私边界。

## 6. 前端页面说明

### `templates/login.html`

登录页：显示产品名和登录表单；输入用户名和密码；登录失败时显示错误提示。

### `templates/index.html`

首页和新分析入口：显示当前登录用户和角色；PDF 上传队列；支持从不同文件夹多次选择 PDF；显示最近分析会话。

### `templates/analysis.html`

核心分析页：顶部信息、PDF 追加上传区、管理员 PDF 管理区、分析模式切换、KPI、主要指標比較表、ランキング、推移チャート、推移表、管理员抽出結果レビュー和补正表单。

不再显示：所見、サマリー所見、企业定性评价、自动风险判断文字。

### `templates/report.html`

HTML 报告模板：KPI、主要指標比較、推移チャート、ランキング、抽出ログ。不再包含定性所见。

### `static/styles.css`

全站样式：应用外壳、头部、按钮、KPI、表格、info tooltip、PDF 上传队列、删除管理区、排名条形图、SVG 折线图、登录页。

### `static/uploader.js`

前端交互脚本：多次选择 PDF 的队列维护、FormData 上传、删除确认、折线图点位提示。

## 7. 指标和公式

### 原始抽出指标

- 売上高
- 売上総利益
- 営業利益
- 経常利益
- 親会社株主に帰属する当期純利益
- 総資産
- 純資産
- 流動資産
- 流動負債
- 営業CF
- 投資CF
- 財務CF
- 従業員数

### 派生指标

- 営業利益率 = 営業利益 ÷ 売上高
- 純利益率 = 当期純利益 ÷ 売上高
- ROA = 当期純利益 ÷ 総資産
- 自己資本比率 = 純資産 ÷ 総資産
- 総資産回転率 = 売上高 ÷ 総資産
- 流動比率 = 流動資産 ÷ 流動負債
- 営業CF/純利益 = 営業活動によるキャッシュ・フロー ÷ 当期純利益
- 一人当たり売上高 = 売上高 ÷ 従業員数
- 売上成長率 = (当期売上高 - 前期売上高) ÷ 前期売上高
- 純利益成長率 = (当期純利益 - 前期純利益) ÷ 前期純利益

### 平均スコア

平均スコア是系统计算指标，不是 PDF 原文提供值。当前算法保留为规则型综合分，用于排序和粗略比较，不构成企业评价或投资判断。前端必须显示公式说明。

### 抽出信頼度

抽出信頼度 = 主要 5 项（売上高、純利益、総資産、純資産、営業CF）中成功自动抽出的项目数 ÷ 5。

## 8. 常用运维命令

```bash
systemctl status financial-analyzer --no-pager
journalctl -u financial-analyzer -n 100 --no-pager
systemctl restart financial-analyzer
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
curl -I https://fincial.zekkx.icu/login
curl http://127.0.0.1:8010/healthz
```

回退版本：

```bash
ls -la /opt/financial-analyzer/releases
ln -sfnT /opt/financial-analyzer/releases/<旧版本号> /opt/financial-analyzer/current
systemctl restart financial-analyzer
```

## 9. 修改规则

任何人修改线上程序后，必须同步更新本 README：修改日期、修改人、修改文件、修改目的、前端表现变化、是否影响数据结构、验证方式、回退方式。

如果外部修改者没有更新 README，下次接手时应先做只读扫描，不直接覆盖。

## 10. 变更记录

### 2026-05-15 / Codex

修改文件：

- `app/analysis.py`
- `templates/analysis.html`
- `templates/report.html`
- `static/styles.css`
- `README.md`

修改内容：

- 移除所見和サマリー所見展示。
- 删除企业定性分析生成逻辑，不再输出自动风险判断、经营状况判断或综合评论文字。
- 修正推移チャート的权限显示逻辑，使登录用户均可查看图表。
- 将产品说明明确为数据抽出、整合、指标计算和可视化平台。
- 新增本 README 作为说明书和操作记录。

验证：

- `python -m compileall app` 通过。
- `https://fincial.zekkx.icu/login` 可访问。
- 管理员登录后可进入首页。
- 页面源码不再包含 `所見`、`サマリー所見`、`insight` 展示块。

回退方式：

- 将 `/opt/financial-analyzer/current` 指回上一 release。
- 执行 `systemctl restart financial-analyzer`。

### 2026-05-15 02:52 JST / Codex

追加记录：

- 将 `/opt/financial-analyzer/releases/20260515024356` 从符号链接转换为真实 release 目录，避免 `current` 解析到旧目录。
- 修正 README 中的发布/回退命令示例，使用 `ln -sfnT` 替换目录符号链接。
- 使用样本 PDF 做外部上传验证：管理员可见抽出結果レビュー，访客不可见管理编辑区；页面不含 `所見` / `insight` 标记。
- 验证后删除临时分析记录和上传 PDF，未保留测试数据。

验证：

- `readlink -f /opt/financial-analyzer/current` 指向 `/opt/financial-analyzer/releases/20260515024356`。
- `systemctl is-active financial-analyzer` 返回 `active`。

### 2026-05-15 / Codex

修改文件：

- `app/analysis.py`
- `templates/analysis.html`
- `README.md`

修改内容：

- 将“同一企业”判定从单一优先字段 `security_code or edinet_code or company_name` 改为企业身份图谱。
- 证券代码、EDINET/文书代码、公司名称归一化后，只要任一可靠标识相同，就归并为同一企业。
- 支持链式归并：A 与 B 证券代码相同，B 与 C 公司名相同，则 A/B/C 被视为同一企业。
- 忽略 `未判定`、空值、`UNKNOWN` 等不能唯一确定企业的占位名称。
- 前端筛选标签从“対象企業コード”改为“対象企業”。

前端体现：

- “同一企業の時系列分析”下拉框会按归并后的企业组显示。
- 即使部分 PDF 缺失证券代码，只要它与同组文件共享 EDINET 代码、文书代码或公司名称，也会进入同一企业时系列分析。
- 旧 URL 中的 `selected_company=证券代码`、`selected_company=EDINET代码`、`selected_company=公司名` 会尽量解析到同一归并组。

验证：

- `python -m compileall app` 通过。
- Jinja 模板解析通过。
- 构造证券代码、EDINET/文书代码、公司名链式匹配的测试数据，确认同一企业筛选返回同一组。
- 使用 MIXI 样本 PDF 双文件上传测试，`selected_company=2121` 可进入同一企业组并显示 2 个 PDF；测试记录和上传文件已删除。
- `/healthz` 返回正常，`financial-analyzer` 服务为 `active`。

回退方式：

- 执行 `ln -sfnT /opt/financial-analyzer/releases/<旧版本号> /opt/financial-analyzer/current`。
- 执行 `systemctl restart financial-analyzer`。

### 2026-05-15 / Codex / 分析モード UI

当前说明：

- 分析页的「分析モード」区域改为三张模式卡片：多社同年度比較、同一企業の時系列分析、カスタム比較。
- 模式卡片下方只显示当前模式需要的条件：同年度模式显示対象年度，同企业模式显示対象企業，自定义模式显示PDF选择区。
- 「対象企業」标签乱码已修正。
- 企業数说明继续按企业身份图谱统计，不再按单一证券代码理解。
- 样式文件版本已更新，浏览器会加载新的模式区样式。

验证：

- Python 编译通过。
- Jinja 模板解析通过。
- 外部上传样本 PDF 后，分析页返回正常，并包含新的模式卡片与対象企業标签。
- `/healthz` 返回正常，`financial-analyzer` 服务为 `active`。

### 2026-05-15 / Codex / 分析モード選択補助・主要指標表

当前说明：

- カスタム比較のPDF選択区に「全選択」「選択反転」「解除」を追加しました。
- PDF選択数を表示し、ボタン操作と個別チェック操作に合わせて即時更新します。
- 主要指標比較は分组表头に変更し、金額指標、収益性・安全性、生産性を視覚的に分けました。
- 主要指標表は企業・年度列を左固定にし、行ホバー、色付き数値チップ、対象PDF/年度/企業数のメタ表示を追加しました。
- 企業同一判定の説明文は現行の企業身份图谱逻辑に合わせています。

验证：

- Python 编译通过。
- Jinja 模板解析通过。
- JavaScript 语法检查通过。
- 外部上传样本 PDF 后，分析页返回正常，并包含全選択/選択反転按钮、新主要指标表结构和新 CSS/JS 版本。
- `/healthz` 返回正常，`financial-analyzer` 服务为 `active`。

### 2026-05-15 / Codex / 图表模式与提示层修正

当前说明：

- 多社同年度比較的图表固定为散点図。
- 同一企業の時系列分析的图表固定为折れ線図。
- カスタム比較新增「図表タイプ」选择，可在散点図和折れ線図之间切换。
- `chart_type` 参数会随页面刷新和报告生成保留；后端会根据分析模式自动归一化，避免模式和图表类型冲突。
- 主要指標比較、推移表、ランキング等位置的 `info` 计算式提示改为全局浮层，不再被表格、卡片或滚动容器裁切。
- ランキング行布局已调整，长企业名称会在固定列内换行，不再挤压序号和值导致错位。
- 散点图不显示大面积图例区，减少图表末尾空白。

验证：

- Python 编译通过。
- Jinja 模板解析通过。
- JavaScript 语法检查通过。
- 构造同年度、同公司、自定义三类分析，确认图表类型分别为 scatter、line、用户选择值。
- 外部上传样本 PDF 后，页面返回正常，并包含图表类型选择、散点/折线图结构和全局 info tooltip。
- `/healthz` 返回正常，`financial-analyzer` 服务为 `active`。

### 2026-05-15 / Codex / ランキング布局调整

当前说明：

- ランキング区域不再在宽屏固定显示为四列横排。
- 排名面板调整为最多两列的 2x2 布局，宽屏下每个面板拥有更大的阅读空间。
- 中等屏幕自动降为单列，避免企业名称、排名序号和值互相挤压。
- CSS 版本更新，浏览器会重新加载排名区布局样式。

验证：

- Python 编译通过。
- Jinja 模板解析通过。
- 外部访问现有分析页返回正常，页面加载 `styles.css?v=20260515-9`。
- `/healthz` 返回正常，`financial-analyzer` 服务为 `active`。

### 2026-05-15 / Codex / 图表与排名单面板切换

当前说明：

- 推移チャート/散点チャート由多图表平铺改为单图表舞台。
- 图表上方增加指标切换 bar，用户一次只查看一个图表，按钮直接显示指标名和图表类型。
- 图表标题区域明确显示指标名称、图表类型和年度范围，避免只看到公司名称而无法判断图表含义。
- ランキング区域也改为单榜单舞台，使用上方 bar 在総合スコア、売上高、ROA、自己資本比率之间切换。
- 图表和排名面板视觉风格调整为更高级的仪表盘式布局，减少平铺卡片和大面积空白。

验证：

- Python 编译通过。
- Jinja 模板解析通过。
- JavaScript 语法检查通过。
- 外部访问现有分析页返回正常，页面加载 `styles.css?v=20260515-10` 与 `uploader.js?v=20260515-10`。
- 页面包含图表切换 bar、排名切换 bar、单面板图表舞台和单面板排名舞台。
- `/healthz` 返回正常，`financial-analyzer` 服务为 `active`。

### 2026-05-15 / Codex / 图表指标名称修正

当前说明：

- 修正折线图生成时指标名称被企业名称覆盖的问题。
- 图表切换 bar 现在显示指标名称，并在副标题显示指标用途和图表类型。
- 图表卡片标题区域也显示指标用途、图表类型和年度范围，用户可以明确区分每张图的含义。
- CSS 版本更新到 `styles.css?v=20260515-11`，浏览器会重新加载图表切换样式。

验证：

- Python 编译通过。
- Jinja 模板解析通过。
- 构造同企业多年度分析，确认五个图表标签分别为売上高、営業利益、純利益、ROA、自己資本比率。
- 外部访问现有分析页返回正常，页面包含正确的图表切换标签。
- `/healthz` 返回正常，`financial-analyzer` 服务为 `active`。

### 2026-05-15 / Codex / 主要指标分类化与动态ランキング

当前说明：

- `app/analysis.py` 新增常用企业分析指标体系，将主要指标分为 `経営・成長性`、`収益性`、`安全性`、`キャッシュフロー`、`効率性・生産性` 五类。
- 新增派生指标包括売上総利益率、経常利益率、ROE、負債比率、負債資本倍率、営業CFマージン、フリーCF、フリーCFマージン、一人当たり営業利益等。
- `主要指標比較` 改为分类式仪表区。用户点击分类后，表格列会切换为该分类下的指标。
- `ランキング` 现在嵌入到对应分类下，并随当前分类显示该分类可排名的指标。每个分类内部仍可切换具体ランキング指标。
- `推移チャート` 的指标池扩展，加入営業利益率、ROE、流動比率、営業CF、営業CF/純利益、総資産回転率等常用视角。
- `static/uploader.js` 增加分类面板切换逻辑；`static/styles.css` 增加分类按钮、分类表格和分类ランキング样式。
- 页面资源版本更新为 `styles.css?v=20260515-12` 与 `uploader.js?v=20260515-11`。

验证：

- Python 编译通过。
- Jinja 模板解析通过。
- 使用既有分析记录构造同企业多年度与多社同年度分析，确认五类指标、分类表格和分类ランキング数据均能生成。
- 外部访问现有分析页返回正常，页面包含五个主要指标分类入口。
- `/healthz` 返回正常，`financial-analyzer` 服务为 `active`。

### 2026-05-15 / Codex / 图表分类钻取与单年度柱状图

当前说明：

- `推移チャート` / 图表区域改为两级切换：先选择指标大类，再在该大类下选择具体图表指标。
- 同一企业多年度分析继续使用 `折れ線図`，但图表指标按 `経営・成長性`、`収益性`、`安全性`、`キャッシュフロー`、`効率性・生産性` 分类展示。
- 单年度多公司比较不再使用散点图，改为 `柱状図`。柱状图横轴为企业/PDF顺序，悬停柱子可查看企业、年度和值。
- 自定义比较如果选择散点图但实际只有一个年度且包含多家公司，也会自动转为柱状图，避免单年度散点图表达不清。
- `app/analysis.py` 新增 `bar` 图表类型、分类图表生成逻辑和柱状图坐标数据。
- `templates/analysis.html` 新增图表大类切换和分类内指标切换；`templates/report.html` 支持在报告中渲染柱状图。
- `static/styles.css` 新增柱状图、零线和图表分类面板样式。
- 页面资源版本更新为 `styles.css?v=20260515-13`。

验证：

- Python 编译通过。
- Jinja 模板解析通过。
- 同一企业多年度分析生成分类折线图。
- 多公司同年度分析生成分类柱状图，且不再显示散点图。
- 外部访问现有分析页返回正常，页面包含图表分类入口和柱状图/折线图对应标识。
- `/healthz` 返回正常，`financial-analyzer` 服务为 `active`。

### 2026-05-15 / Codex / 移除综合评分

当前说明：

- 删除页面中的 `平均スコア` KPI。
- 删除主要指标分类中的 `総合スコア` 指标列，不再生成或展示规则加减分式评分。
- 删除 `ランキング` 中的総合スコア排名，报告页改为展示売上高和ROA等可复算指标排名。
- `app/analysis.py` 不再计算 `health_score`，`summary_kpis` 不再返回 `avg_score`。
- 前端与报告页仅保留 PDF 抽取数据和公式计算指标，例如売上高、利益、ROA、ROE、自己資本比率、流動比率、営業CF、フリーCF、成長率等。
- 页面资源版本更新为 `styles.css?v=20260515-14`。

验证：

- Python 编译通过。
- Jinja 模板解析通过。
- 既有分析记录可正常生成同企业多年度和多公司同年度页面。
- 页面 HTML 中不再包含 `平均スコア`、`総合スコア`、`Score`、`health_score`。
- 外部访问现有分析页返回正常。
- `/healthz` 返回正常，`financial-analyzer` 服务为 `active`。
