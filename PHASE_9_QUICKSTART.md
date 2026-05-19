# Phase 9 快速启动指南

## 📦 安装依赖

```bash
cd frontend
npm install
```

当前已安装的依赖：
- ✅ Next.js 14.2.29
- ✅ React 18.3.1
- ✅ TanStack Query 5.59.0
- ✅ Zustand 5.0.0
- ✅ Tailwind CSS 3.4.13
- ✅ TypeScript 5.6.3

**需要添加的依赖**（Phase 10 前）：
```bash
npm install @hookform/resolvers zod
```

## 🚀 启动开发服务器

```bash
# 启动前端（开发模式）
cd frontend
npm run dev
# 访问: http://localhost:3000

# 启动后端（如果还没启动）
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 🔑 测试登录

使用后端 Phase 2 创建的测试账号：

```
租户标识: demo
邮箱: admin@demo.com
密码: demo123456
```

## 📁 文件结构

```
frontend/src/
├── lib/
│   ├── api.ts                    # API 客户端（token 刷新）
│   ├── permissions.ts            # 权限工具函数
│   └── store/
│       └── auth.ts               # Zustand auth store
├── components/
│   ├── auth-guard.tsx            # 路由守卫
│   └── schema-form/
│       └── index.tsx             # 动态表单组件
├── app/
│   ├── (auth)/
│   │   └── login/
│   │       └── page.tsx          # 登录页
│   └── (app)/
│       ├── layout.tsx            # 应用主布局
│       └── datasets/
│           ├── page.tsx          # 数据集列表
│           └── [id]/
│               ├── page.tsx      # 数据集详情 + 记录列表
│               ├── new/
│               │   └── page.tsx  # 新增记录
│               └── [recordId]/
│                   └── edit/
│                       └── page.tsx  # 编辑记录
```

## 🧪 测试流程

### 1. 登录测试
1. 访问 http://localhost:3000
2. 自动跳转到 `/login`
3. 输入测试账号信息
4. 登录成功后跳转到首页 `/`

### 2. 数据集列表测试
1. 点击侧边栏"数据集"
2. 查看数据集列表（卡片视图）
3. 测试搜索功能
4. 测试状态/敏感度过滤

### 3. 记录管理测试
1. 点击任意数据集卡片
2. 查看记录列表（表格视图）
3. 点击"新增记录"
4. 填写表单（根据 schema 动态生成）
5. 提交后跳转到审批详情页（`/approvals/{version_id}`）

### 4. 编辑记录测试
1. 在记录列表点击"编辑"
2. 修改字段值
3. 提交后跳转到审批详情页
4. 测试乐观锁：在另一个浏览器窗口同时编辑同一记录

## ⚠️ 已知限制

### 后端依赖
- ❌ `/auth/refresh` 端点未实现（Phase 3+）
  - **影响**: Token 过期后必须重新登录
  - **临时方案**: 增加 access token 有效期

### 前端简化
- ❌ 未集成 Zod 验证
  - **影响**: 客户端验证较弱
  - **临时方案**: 依赖后端返回错误

- ❌ SchemaForm 仅支持基础类型
  - **影响**: 复杂 schema（array/object/$ref）无法渲染
  - **临时方案**: 使用简单 schema 测试

- ❌ 无 WebSocket 实时更新
  - **影响**: 数据变化需手动刷新
  - **临时方案**: 使用 TanStack Query 的自动重新获取

## 🐛 常见问题

### Q1: 登录后立即跳转回登录页
**原因**: `isHydrated` 未正确设置  
**解决**: 检查浏览器控制台是否有 localStorage 错误

### Q2: API 请求返回 401
**原因**: Token 未正确存储或已过期  
**解决**: 
1. 检查 localStorage 中的 `auth-storage`
2. 清除 localStorage 后重新登录
3. 检查后端是否正常运行

### Q3: 表单提交后没有跳转
**原因**: 审批详情页未实现（Phase 10）  
**解决**: 
1. 检查浏览器控制台的网络请求
2. 确认返回了 `version_id`
3. 临时修改跳转目标为数据集列表

### Q4: 动态表单字段不显示
**原因**: Schema 格式不正确或包含不支持的类型  
**解决**:
1. 检查 `dataset.schema.properties` 是否存在
2. 确认字段类型为 string/number/boolean/enum
3. 查看浏览器控制台错误

## 📊 性能优化建议

### TanStack Query 配置
当前配置：
```tsx
staleTime: 1000 * 60 * 5,  // 5 分钟
refetchOnWindowFocus: false,
retry: 1,
```

可根据需求调整：
- 频繁变化的数据：减少 `staleTime`
- 稳定的数据：增加 `staleTime`
- 关键请求：增加 `retry` 次数

### 分页优化
当前每页 20 条记录，可根据数据量调整：
```tsx
const pageSize = 20;  // 可改为 10, 50, 100
```

## 🔐 安全注意事项

1. **前端权限检查仅用于 UI**
   - 所有权限必须在后端再次验证
   - 不要依赖前端检查作为安全边界

2. **Token 存储**
   - 当前存储在 localStorage
   - 生产环境考虑使用 httpOnly cookie

3. **敏感数据**
   - 不要在前端日志中输出 token
   - 不要在 URL 中传递敏感信息

## 📝 下一步开发

### Phase 10 必须实现
1. 审批管理界面（`/approvals`）
2. 记录详情页（`/datasets/[id]/[recordId]`）
3. 集成 Zod 验证
4. 扩展 SchemaForm 支持复杂类型

### Phase 11 可选实现
1. AI 聊天界面（`/ai`）
2. WebSocket 实时更新
3. 管理页面（用户/角色/部门）
4. 审计日志

## 🎯 代码质量检查

运行以下命令确保代码质量：

```bash
# TypeScript 类型检查
npm run type-check

# ESLint 检查
npm run lint

# 严格模式 ESLint（无警告）
npm run lint:strict
```

所有文件都应通过 TypeScript strict 模式检查，无 `any` 类型。

---

**Phase 9 完成！开始测试和开发 Phase 10 吧！** 🚀
