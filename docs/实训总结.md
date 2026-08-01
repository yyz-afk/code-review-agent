# 实训个人工作总结

---

## 一、实训概述

| 项目 | 内容 |
|------|------|
| **项目名称** | 慧医数字医疗应用系统 |
| **实训周期** | 2026年7月 |
| **开发环境** | Windows 11、JDK 1.8、MySQL 8.0、IntelliJ IDEA |
| **项目类型** | 医疗信息化管理系统（全栈 Web 应用） |
| **个人角色** | 全栈开发（后端为主，前端为辅） |
| **版本控制** | Git（main 分支，多次代码重构与优化提交） |

---

## 二、项目背景与目标

### 2.1 项目背景

本项目是一个面向医疗行业的数字化管理系统，旨在为医疗机构提供药品管理、医生管理、药店管理、医保政策管理等核心业务功能。系统采用前后端分离架构，支持本地部署、局域网访问和 cloudflared 公网隧道演示，适用于中小型医疗机构的信息化建设场景。

### 2.2 核心目标

- 实现药品、医生、药店、医药公司等核心医疗资源的数字化管理
- 提供基于 RBAC（Role-Based Access Control）的权限控制（管理员 ROLE_1 / 医生 ROLE_2 / 患者 ROLE_3）
- 支持医保政策按城市维度的发布与查询，关联全国行政区划数据
- 集成 ECharts 数据可视化看板与高德地图地理信息展示
- 实现一键启动脚本体系，降低项目部署与演示门槛

---

## 三、技术架构

### 3.1 整体架构图

```
┌──────────────────────────────────────────────────┐
│                    前端展示层                       │
│   HTML5 + CSS3 + 原生 JavaScript（纯 SPA）         │
│   ECharts 数据可视化  │  高德地图 API v2.0         │
│   Node.js http 静态服务器（内置反向代理 + Gzip）    │
├──────────────────────────────────────────────────┤
│                   安全网关层                        │
│   Spring Security 无状态认证                       │
│   JWT Token 签发与校验（jjwt 0.11.5）              │
│   BCrypt 密码哈希  │  @RolesAllowed 方法级鉴权      │
│   Swagger/OpenAPI 3.0 接口文档自动生成             │
├──────────────────────────────────────────────────┤
│                   业务服务层                        │
│   Spring Boot 2.5.3  RESTful API                 │
│   分层架构: Controller → Service → Mapper(MyBatis) │
│   Domain 数据对象 / Entity 扩展实体 / Model 视图对象 │
│   Param 请求参数对象 / Msg 统一响应封装             │
├──────────────────────────────────────────────────┤
│                   数据持久层                        │
│   MyBatis 2.2.2 + XML Mapper + PageHelper 1.4.7  │
│   MySQL 8.0  │  数据库名: bin_text                 │
└──────────────────────────────────────────────────┘
```

### 3.2 后端技术栈详表

| 技术 | 版本 | 用途 |
|------|------|------|
| Spring Boot | 2.5.3 | 应用框架，内嵌 Tomcat |
| Spring Security | 5.x | 认证授权框架 |
| Spring MVC | 5.x | RESTful API 与请求分发 |
| Spring Validation | - | 请求参数校验 |
| MyBatis Spring Boot | 2.2.2 | ORM 持久层框架 |
| PageHelper | 1.4.7 | 物理分页插件 |
| JJWT (io.jsonwebtoken) | 0.11.5 | JWT 生成/解析/验证 |
| BCrypt (Spring Security) | - | 密码单向哈希加密 |
| SpringDoc OpenAPI | 1.7.0 | Swagger 3.0 API 文档 |
| MySQL Connector Java | runtime | MySQL 8 数据库驱动 |
| Maven | 3.x | 项目构建与依赖管理 |

### 3.3 前端技术栈详表

| 技术 | 用途 |
|------|------|
| HTML5 + CSS3 | 页面结构（dashboard.html 48594B）与完整样式系统（styles.css 14548B） |
| 原生 JavaScript（ES6） | 核心业务逻辑（dashboard.js 102571B），无框架依赖 |
| ECharts 5.x | 首页数据可视化（柱状图、环形饼图） |
| 高德地图 JS API v2.0 | 药店地图标注、逆地理编码、MarkerClusterer 点聚合 |
| Node.js http/https/zlib 模块 | 静态资源服务器 + API 反向代理（server.js） |
| LocalStorage | 客户端 Token 持久化、用户信息缓存、预约挂号数据存储 |
| @amap/amap-jsapi-loader | 高德地图动态异步加载 |

### 3.4 数据库设计（完整 17 张表）

数据库名：`bin_text`，字符集 utf8mb4，MySQL 8.0。

**核心业务表：**

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `account` | 账号表 | id, realname, uname, pwd(BCrypt), phonenumber, utype(ROLE_1/2/3) |
| `doctor` | 医生信息表 | id, name, age, sex, level_id, phone, type_id, hospital, account_id |
| `doctor_level` | 医生职称字典 | 1-主任医师, 2-普通医师, 3-实习医师 |
| `treat_type` | 诊疗类型字典 | 肩/踝/膝/腰/头/肘/腿等科室 |
| `drug` | 药品信息表 | drug_id, drug_name, drug_info, drug_effect, drug_img, publisher |
| `drug_sale` | 药品-药店关联表 | id, drug_id, sale_id（多对多中间表） |
| `sale` | 药店信息表 | sale_id, sale_name, sale_phone, address, lng, lat |
| `drugcompany` | 医药公司表 | company_id, company_name, company_phone |
| `company_policy` | 企业政策表 | id, title, message, company_id |
| `medical_policy` | 医保政策表 | id, title, message, city_id |
| `material` | 必备材料表 | id, title, message |

**权限与区域数据表：**

| 表名 | 说明 |
|------|------|
| `permission` | 菜单权限树（自引用 pid→parent，含 name/path/component/title/level） |
| `role_permission` | 角色-权限关联表（roleName → per_id） |
| `city` | 医保城市表（city_number → sysregion.id） |
| `china` | 全国行政区划树（id, name, parent_id） |
| `sysregion` | 系统区域数据（id, name, parent_id, Lng, Lat, PinYin） |
| `patient` | 患者信息表（id, pname, age, sex, enter_time, out_time, state） |

**实体关系：**
- doctor N:1 doctor_level，N:1 treat_type，1:1 account（创建医生自动创建账号）
- drug N:N sale（通过 drug_sale 中间表关联）
- company_policy N:1 drugcompany（级联删除）
- medical_policy N:1 city（级联删除）
- permission 自引用树形结构，role_permission 关联角色与菜单

---

## 四、个人工作内容

### 4.1 后端核心功能开发

#### （1）安全认证与授权模块（Spring Security + JWT）

完整搭建了基于 JWT 的无状态认证体系：

- **SecurityConfig**：关闭 CSRF，设置 `SessionCreationPolicy.STATELESS` 无状态会话，配置公开端点白名单（`/api/login`、`/api/health`、`/api/smoke/**`、Swagger 路径），其余请求全部拦截认证
- **JwtAuthenticationFilter**：继承 `OncePerRequestFilter`，从请求头 `Authorization: Bearer <token>` 或 `token` 中提取 JWT，解析后加载 `AccountModel`（实现 `UserDetails` 接口），注入 Spring Security 上下文
- **JwtAuthenticationEntryPoint** / **JwtAccessDeniedHandler**：统一返回 JSON 格式错误（code: 10006 未认证 / 10007 无权限），而非默认重定向
- **JwtUtil**：基于 HMAC-SHA 算法实现 Token 生成、解析、过期校验
- **AccountService**：实现 `UserDetailsService.loadUserByUsername()`，从数据库加载账号并构建包含角色信息的 `AccountModel`
- **PasswordConfig**：注入 `BCryptPasswordEncoder` Bean，实现密码的 BCrypt 单向哈希存储与校验
- **@RolesAllowed 注解**：开启 `@EnableGlobalMethodSecurity(jsr250Enabled = true)`，在 Controller 方法上使用 `@RolesAllowed({"ROLE_1"})` 实现声明式权限控制

**认证流程图：**
```
用户登录 → POST /api/login → AuthenticationManager.authenticate()
    → AccountService.loadUserByUsername() → 查询account表
    → BCrypt 密码比对 → 生成JWT → 返回token + userInfo
后续请求 → JwtAuthenticationFilter → 解析token → 加载用户 → 注入SecurityContext
    → @RolesAllowed 校验 → 放行/拒绝
```

**关键代码（SecurityConfig 核心配置）：**
```java
@Override
protected void configure(HttpSecurity http) throws Exception {
    http.csrf().disable()
            .cors()
            .and()
            .sessionManagement().sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            .and()
            .exceptionHandling()
            .authenticationEntryPoint(authenticationEntryPoint)
            .accessDeniedHandler(accessDeniedHandler)
            .and()
            .authorizeRequests()
            .antMatchers("/api/login", "/api/health", "/api/smoke/**",
                         "/image/**", "/swagger-ui/**", "/v3/api-docs/**").permitAll()
            .anyRequest().authenticated();
    http.addFilterBefore(jwtAuthenticationFilter,
                         UsernamePasswordAuthenticationFilter.class);
}
```

#### （2）RESTful API 设计与实现（13 个 Controller）

严格按照 RESTful 风格设计 API，遵循"资源复数命名 + HTTP 方法表达操作"的规范：

| # | Controller | 路径 | 主要接口 | 权限控制 |
|---|-----------|------|----------|----------|
| 1 | AuthController | `/api` | POST /login | 公开 |
| 2 | HealthController | `/api/health` | GET / — 数据库连接检测 | 公开 |
| 3 | DoctorController | `/api/doctors` | GET 分页列表、GET /{id} 详情、GET /info 字典、POST 新增(含自动创建账号)、PUT /{id} 修改、DELETE /{id} 删除(级联账号)、PUT /{id}/password 密码重置 | 写: ROLE_1 |
| 4 | DrugController | `/api/drugs` | GET /{pn}/{size} 分页+模糊搜索、POST 新增、PUT /{id} 修改、DELETE /{drugId} 删除(级联drug_sale) | 新增: ROLE_1+2，删改: ROLE_1 |
| 5 | CompanyController | `/api/companys` | GET 分页、GET /{id} 详情、POST 新增、PUT 修改、DELETE 删除 | 写: ROLE_1 |
| 6 | SaleController | `/api/sales` | GET 分页+关键词搜索、GET /{id} 详情、POST 新增、PUT 修改、DELETE 删除 | 认证即可 |
| 7 | MedicalPolicyController | `/api/medical/policy` | GET 条件分页、POST 新增(含标题/内容/城市校验)、PUT 修改、DELETE 删除 | 写: ROLE_1 |
| 8 | CompanyPolicyController | `/api/company/policy` | GET 分页+条件、POST 新增、PUT 修改、DELETE 删除 | 写: ROLE_1 |
| 9 | MaterialController | `/api/material` | GET 分页、POST 新增、PUT 修改、DELETE 删除 | 写: ROLE_1 |
| 10 | CityController | `/api/citys` | GET 分页、GET /{id} 详情、POST 新增、DELETE 删除 | 写: ROLE_1 |
| 11 | FileUploadController | `/api/base/upload` | POST 文件上传(multipart) | ROLE_1+2 |
| 12 | PermissionController | `/api` | GET /permissions — 根据角色返回菜单树 | 认证即可 |
| 13 | DoctorSmokeController | `/api/smoke` | GET /doctors — 测试/调试接口 | 公开 |

#### （3）分层架构设计（Domain/Entity/Model/Param）

遵循 DDD 分层思想，定义了四层数据对象：

| 层次 | 包路径 | 职责 | 示例 |
|------|--------|------|------|
| **Domain（DO）** | `domain/` | 与数据库表字段一一映射的纯 POJO | `Doctor.java`、`Drug.java` |
| **Entity（PO）** | `entity/` | 继承 Domain，扩展统计字段（如 total） | `DoctorEntity.java`、`DrugEntity.java` |
| **Model（VO）** | `model/` | 聚合多表关联数据的视图对象，用于 API 响应 | `DoctorModel`(含 DoctorLevel + TreatType)、`DrugModel`(含 List\<SaleModel\>) |
| **Param（DTO）** | `param/` | 接收前端请求参数的专用对象 | `DoctorParam`、`DrugParam`(含 saleIds[]) |

**关键关联设计示例（DrugModel）：**
```java
// DrugModel 聚合了药品信息 + 销售药店列表
public class DrugModel extends DrugEntity {
    private List<SaleModel> drugSales;  // 该药品在哪些药店有售
}
```

#### （4）医生-账号联动机制

创建医生时自动生成登录账号，核心逻辑：
1. 前端提交 `DoctorParam`（含姓名、手机号等）
2. 后端 `DoctorService.save()` 中自动生成用户名（姓名 + 手机号后4位）
3. 使用 BCrypt 加密默认密码
4. 在 `account` 表创建记录（utype=ROLE_2），获得 account_id
5. 在 `doctor` 表创建记录，关联 account_id
6. 删除医生时级联删除对应账号

```java
// 关键逻辑示意
String username = param.getName() + param.getPhone().substring(7);
String encodedPwd = passwordEncoder.encode("默认密码");
Account account = new Account(username, encodedPwd, "ROLE_2");
// 插入account → 获得id → 插入doctor关联account_id
```

#### （5）统一响应封装（Msg 类）

```java
public class Msg {
    private Integer code;    // 20000成功, 10001失败, 10002登录错误, 10003异常, 10006未认证, 10007无权限
    private String mess;     // 提示信息
    private Map<String, Object> data;  // 业务数据载体

    public static Msg success() { ... }
    public static Msg fail() { ... }
    public Msg data(String key, Object value) { ... }  // 链式调用
}
// 使用示例：return Msg.success().data("pageInfo", pageInfo).data("total", 100);
```

#### （6）分页查询与模糊搜索

- 集成 PageHelper，所有列表接口支持 `pn`（页码）/ `size`（页大小）参数
- 药品接口支持 `name` 参数模糊搜索（SQL: `WHERE drug_name LIKE CONCAT('%',#{name},'%')`）
- 返回 `PageInfo` 对象（含 total、pages、list 等分页信息）

#### （7）文件上传模块

- `FileUploadService`：UUID 重命名 + 类型白名单校验（jpg/jpeg/png/gif/webp）
- 上传路径 `./uploads/`，通过 Spring MVC 静态资源映射 `/image/**` 对外暴露
- 上传成功后返回 `/image/<uuid>.<ext>` 访问路径
- 前端药品编辑模块集成图片上传与预览

#### （8）Swagger API 文档

配置 SpringDoc OpenAPI 3.0，访问地址：
- Swagger UI：`http://127.0.0.1:8080/swagger-ui.html`
- OpenAPI JSON：`http://127.0.0.1:8080/v3/api-docs`

每个接口添加 `@Tag(name = "中文模块名")` 和 `@Operation(summary = "中文功能说明")`，便于前后端联调。

### 4.2 前端功能开发

#### （1）原生 SPA 单页应用架构

- **无框架依赖**：纯 HTML + CSS + 原生 JavaScript，dashboard.js 超 2500 行代码
- **菜单驱动路由**：页面启动时请求 `GET /api/permissions` 加载当前角色的菜单树（permission 表），动态渲染侧边栏多级菜单
- **模块动态切换**：通过 `showModule(item)` 函数实现主内容区模块切换，隐藏/显示对应的 DOM 区域
- **角色自适应**：管理员看到"XX管理"，医生看到"XX查询"；非管理员隐藏新增/编辑/删除按钮

**菜单权限树结构（数据库中配置）：**
```
ROLE_1（管理员）: Layout → 首页 | 药品管理 | 医保政策管理 | 企业政策管理
                 | 医生管理 | 物资管理 | 药店管理 | 公司管理 | 城市管理
ROLE_2（医生）:   Layout → 首页 | 药品查询 | 医保政策查询 | 企业政策查询
                 | 物资查询
```

#### （2）ECharts 数据可视化看板

- 首页集成 ECharts，初始化时从后端 API 拉取统计数据
- **柱状图**：展示医生职称分布（主任医师 / 普通医师 / 实习医师 人数统计）
- **环形饼图**：展示诊疗科室分布占比
- 图表自适应窗口大小（`window.onresize` 触发 `chart.resize()`）
- 离线可用（echarts.min.js 打包在 `assets/` 目录）

#### （3）高德地图集成

在药店管理模块中实现地图视图：

- **地图展示**：加载高德地图 JS API v2.0，标注所有药店位置（经纬度坐标）
- **信息窗口**：点击 Marker 弹出信息窗（药店名称、地址、电话）
- **列表/地图切换**：复选框切换列表视图与地图视图
- **逆地理编码**：点击地图空白处自动获取地址并填充表单，支持"在地图上选点"添加药店
- **MarkerClusterer**：大量标注点时自动聚合
- **离线 mock 数据**：后端不可用时使用成都药店演示数据

#### （4）Node.js 静态服务器 + 反向代理

使用 Node.js 原生模块（`http`、`fs`、`path`、`zlib`）手写 server.js：

- **静态资源服务**：自动识别 MIME 类型（HTML/CSS/JS/JSON/PNG/JPG/SVG/ICO）
- **反向代理**：`/api`、`/image`、`/swagger-ui` 等路径透明转发到后端 `127.0.0.1:8080`
- **Gzip 压缩**：对 HTML/CSS/JS/JSON/SVG 等可压缩类型启用 Gzip 传输
- **环境变量配置**：`PORT`（前端端口，默认 5173）、`BACKEND_PORT`（后端端口，默认 8080）

#### （5）统一编辑弹窗模式

通过 `editFieldConfig` 配置对象统一定义各实体的表单字段、数据转换、API 端点：

```javascript
const editFieldConfig = {
    drug: { fields: [...], api: '/api/drugs', transform: ... },
    policy: { fields: [...], api: '/api/medical/policy', transform: ... },
    sale: { fields: [...], api: '/api/sales', transform: ... },
    // ... 其他模块同理
};
```

弹窗根据 `entityType` 动态渲染表单，避免为每个模块编写重复的弹窗代码。

#### （6）客户端离线功能

- **Token 持久化**：`localStorage.setItem('medical-token', token)`
- **用户信息缓存**：`localStorage.setItem('medical-user', JSON.stringify(userInfo))`
- **预约挂号模块**：数据存储在 `localStorage` 的 `medical-registrations` 键中（前端独立功能，无后端表）
- **药品/药店 mock 数据**：后端不可用时自动降级使用硬编码演示数据

### 4.3 DevOps 与工程化

#### （1）一键启动脚本体系（8 个批处理脚本）

| 脚本 | 功能描述 |
|------|----------|
| `run.bat` | 用户入口，一键启动前后端 |
| `start-all.bat` | 核心启动脚本：检测 MySQL 服务 → 检查 bin_text 数据库 → 自动导入 SQL → 启动后端 → 启动前端 |
| `start-backend.bat` | Maven 编译并启动 Spring Boot（端口 8080，可通过 `SERVER_PORT` 环境变量配置） |
| `start-frontend.bat` | 智能检测 Node.js，有则用 `node server.js` 启动，无则用 PowerShell 静态服务器（均监听 5173 端口） |
| `import-database.bat` | 手动导入数据库（调用 mysql 命令行） |
| `allow-lan-access.bat` | 添加 Windows 防火墙入站规则，允许 5173 端口 TCP 连接 |
| `start-public-url.bat` | 启动 cloudflared 隧道，生成 `https://xxxxx.trycloudflare.com` 公网地址 |
| `stop-all.bat` | 通过 `netstat -ano` 查找占用 8080/5173 的 PID，`taskkill /F` 强制终止 |

#### （2）端口冲突自动检测

`MedicalApplication.java` 启动时检测端口占用：

```java
// main 方法中 try-catch 捕获 PortInUseException
// 提示用户：端口8080被占用，请先关闭占用程序或执行 stop-all.bat
```

#### （3）公网演示方案

- 使用 cloudflared （Cloudflare Tunnel）实现内网穿透
- 无需公网 IP、无需路由器端口映射
- 公网窗口关闭后地址自动失效（安全性）
- 文档中注明代理软件（Clash Verge / Mihomo TUN 模式）的兼容性处理

---

## 五、技术收获与成长

### 5.1 Spring Security + JWT 认证体系

- 深入理解认证（Authentication）与授权（Authorization）的区别与协作
- 掌握 `SecurityFilterChain` 过滤器链机制，自定义 Filter 的插入位置
- 理解 `UserDetailsService` → `UserDetails` → `SecurityContextHolder` 的认证流程
- 掌握 JWT 三部分结构（Header.Payload.Signature）及 HMAC-SHA 签名算法
- 理解无状态会话（STATELESS）在分布式系统水平扩展中的意义
- 学习 `@RolesAllowed` (JSR-250) 声明式授权的配置与使用

### 5.2 RESTful API 设计规范

- 掌握资源命名规范（名词复数：`/api/drugs`、`/api/doctors`）
- 理解 HTTP 方法的语义化使用（GET 查询、POST 新增、PUT 全量更新、DELETE 删除）
- 学习统一响应格式的设计（`Msg` 类的 code + mess + data 模式）
- 掌握分页参数设计（pn/size）与 PageHelper 物理分页原理

### 5.3 MyBatis 持久层开发

- 掌握 MyBatis XML Mapper 编写：`<resultMap>` 结果集映射、多表关联查询（`<association>` / `<collection>`）、动态 SQL（`<if>` / `<foreach>`）
- 理解 Mapper 接口 + XML 的绑定机制（namespace + id 匹配）
- 学习 PageHelper 的物理分页原理（拦截 SQL 追加 LIMIT 子句）
- 理解 Domain（DO）/ Entity（PO）/ Model（VO/DTO）/ Param 四层数据对象的职责分离

### 5.4 前端 SPA 与数据可视化

- 理解 SPA 应用的核心原理：菜单驱动路由、DOM 动态显隐、无页面刷新
- 学习 ECharts 配置式图表的构建（option 对象 → setOption → 响应式 resize）
- 掌握高德地图 JS API 的使用：地图初始化、Marker 标注、InfoWindow 信息窗、逆地理编码、MarkerClusterer 点聚合
- 学习 Node.js 作为前端静态服务器的搭建：MIME 类型识别、反向代理、Gzip 压缩

### 5.5 软件工程与 DevOps

- Windows Batch 脚本编写（服务检测、端口监听、进程管理、条件分支）
- cloudflared 内网穿透隧道的原理与搭建
- Maven 项目结构规范与依赖管理
- Git 版本控制：多次重构提交（"代码优化"、"代码格式优化"、"swagger版本优化"、"pom文件处理"等）
- 编写项目文档（README、运行说明、项目说明）

---

## 六、遇到的问题与解决方案

### 6.1 数据库脚本导入效率低

| 项目 | 内容 |
|------|------|
| **现象** | `bin_text.sql` 数据量大且所有 INSERT 为单条语句，导入耗时极长 |
| **原因** | 每条 INSERT 独立提交事务，产生大量网络往返和磁盘 I/O |
| **解决** | 重新导出 `bin_text2.sql` 优化结构，将演示数据分离到 `seed_more_demo_data.sql`。启动脚本优先使用 bin_text2.sql |

### 6.2 代理软件与 cloudflared 隧道冲突

| 项目 | 内容 |
|------|------|
| **现象** | 开启 Clash Verge / Mihomo TUN 模式后，cloudflared 公网地址无法访问 |
| **原因** | TUN 虚拟网卡劫持所有流量，cloudflared 解析到 `198.18.x.x`（Clash 虚拟 IP），导致 TLS handshake 失败 |
| **解决** | 在启动脚本和文档中添加醒目提示，要求用户关闭虚拟网卡或 TUN 模式后再启动公网隧道 |

### 6.3 端口残留占用

| 项目 | 内容 |
|------|------|
| **现象** | 多次启停后 8080/5173 端口被上次未完全终止的进程占用 |
| **原因** | `Ctrl+C` 关闭窗口时 JVM/Node 进程未被操作系统及时回收 |
| **解决** | 编写 `stop-all.bat`：`netstat -ano | findstr :8080` → 提取 PID → `taskkill /F /PID xxx`，批量终止。主类 `MedicalApplication` 也加入了端口占用检测 |

### 6.4 密码安全存储

| 项目 | 内容 |
|------|------|
| **现象** | 早期开发阶段密码可能以明文存储，存在安全隐患 |
| **原因** | 快速原型阶段未引入加密机制 |
| **解决** | 引入 Spring Security BCryptPasswordEncoder，所有密码经 BCrypt 哈希后存入 `account.pwd` 字段。编写 `PasswordUtil.main()` 独立工具类，运行即可生成 BCrypt 密文供运维使用 |

### 6.5 医生账号管理耦合

| 项目 | 内容 |
|------|------|
| **现象** | 新增医生时需要手动为其创建登录账号，步骤繁琐且易遗漏 |
| **原因** | Doctor 表和 Account 表分离设计，但创建流程未打通 |
| **解决** | 在 `DoctorService.save()` 中实现联动：自动取姓名+手机号后4位生成用户名 → BCrypt 加密默认密码 → 插入 account → 获得 account_id → 插入 doctor。删除医生时级联删除账号 |

---

## 七、总结与展望

### 7.1 实训总结

本次实训完整经历了一个 Web 全栈项目从**需求分析 → 数据库设计 → 后端 API 开发 → 前端页面搭建 → 安全认证集成 → 一键部署脚本编写 → 文档撰写**的全流程。具体成果包括：

- **后端**：13 个 Controller、11 个 Service、10 个 Mapper、50+ 个 RESTful API 接口
- **前端**：原生 SPA 应用，含 10+ 个业务模块、ECharts 图表、高德地图集成
- **安全**：Spring Security + JWT 无状态认证 + BCrypt 加密 + RBAC 角色权限
- **工程**：8 个批处理脚本 + cloudflared 公网方案 + 完整项目文档
- **Git**：多次代码重构与优化提交，遵循规范的分支管理

### 7.2 不足之处

| 不足 | 改进方向 |
|------|----------|
| 前端未使用现代框架（Vue/React） | 后续可迁移至 Vue 3 + Element Plus，提升代码组织性和可维护性 |
| 缺少单元测试与集成测试 | 引入 JUnit 5 + Mockito + Spring Test，建立测试覆盖 |
| 未引入缓存层 | 引入 Spring Cache + Redis，减少数据库查询压力 |
| 日志系统较基础 | 接入 ELK（Elasticsearch + Logstash + Kibana）或类似方案 |
| 前端代码单文件过大（dashboard.js 100KB+） | 模块化拆分，引入 ES Module 或打包工具 |
| 未使用 Docker 容器化 | 编写 Dockerfile + docker-compose.yml，实现一键环境搭建 |

### 7.3 未来展望

1. **前端现代化**：迁移至 Vue 3 + Vite + Element Plus + Pinia 状态管理
2. **性能优化**：Spring Cache + Redis 缓存热点数据（如城市字典、医生职称字典）
3. **容器化部署**：Docker Compose 编排（Spring Boot + MySQL + Nginx），消除环境差异
4. **CI/CD**：GitHub Actions 或 Jenkins 流水线，实现自动构建、测试、部署
5. **功能扩展**：患者端移动适配、在线问诊、处方流转、药品库存管理
6. **代码质量**：引入 SonarQube 静态代码分析，建立 Code Review 机制

---

## 八、项目成果量化

| 维度 | 数量 |
|------|------|
| 后端 Controller | 13 个 |
| 后端 Service | 11 个 |
| 后端 Mapper 接口 + XML | 10 组 |
| 数据库表 | 17 张 |
| RESTful API 接口 | 50+ 个 |
| 前端业务模块 | 10+ 个 |
| 批处理脚本 | 8 个 |
| 项目文档 | 4 份（README + 运行说明 + 项目说明 + 公网演示说明） |
| 前端核心代码 | dashboard.js 2500+ 行 / dashboard.html 1000+ 行 / styles.css |
| 后端核心代码 | 约 5000+ 行 Java |
| Git 提交 | 多次重构与优化提交 |
| 支持角色 | 3 种（管理员 / 医生 / 患者） |

---

> **作者**：YYZ
> **日期**：2026年7月31日
