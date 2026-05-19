# api.ts 实现验证报告

## ✅ 验证点 1：401 自动刷新 token 并重试原请求

### 代码位置：`frontend/src/lib/api.ts` 第 168-188 行

```typescript
// Handle 401 Unauthorized
if (response.status === 401 && retryOn401 && !skipAuth) {
  try {
    // Refresh token
    const newAccessToken = await refreshAccessToken();
    
    // Retry original request with new token
    const retryHeaders: HeadersInit = {
      ...requestHeaders,
      'Authorization': `Bearer ${newAccessToken}`,
    };

    return fetch(url, {
      ...fetchOptions,
      headers: retryHeaders,
    });
  } catch (error) {
    // Refresh failed, return original 401 response
    return response;
  }
}
```

### ✅ 确认结果

**第 168 行**: 检测到 401 状态码且 `retryOn401 = true` 且 `!skipAuth`  
**第 171 行**: 调用 `refreshAccessToken()` 获取新 token  
**第 174-177 行**: 构建新的请求头，包含新的 `Authorization: Bearer ${newAccessToken}`  
**第 179-182 行**: 使用新 token **重试原请求**（相同的 url 和 fetchOptions）

✅ **确认：401 时自动调用 refresh 接口换新 token，换成功后重试原请求**

---

## ✅ 验证点 2：refresh 失败时清空 auth store 并跳转登录页

### 代码位置：`frontend/src/lib/api.ts` 第 85-106 行

```typescript
async function refreshAccessToken(): Promise<string> {
  // If already refreshing, return existing promise
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }

  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const { refreshToken } = useAuthStore.getState();
      
      if (!refreshToken) {
        throw new Error('No refresh token available');
      }

      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        throw new Error('Token refresh failed');
      }

      const data = await response.json();
      
      // Update auth store with new tokens
      useAuthStore.getState().setTokens(data.access_token, data.refresh_token);
      
      return data.access_token;
    } catch (error) {
      // Refresh failed - clear auth and redirect to login
      useAuthStore.getState().clearAuth();
      
      // Only redirect if we're in browser context
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
      
      throw error;
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}
```

### ✅ 确认结果

**第 91 行**: `if (!response.ok)` - 检测 refresh 请求失败（包括 401）  
**第 92 行**: `throw new Error('Token refresh failed')` - 抛出错误进入 catch 块  
**第 98 行**: `useAuthStore.getState().clearAuth()` - **清空 auth store**  
**第 101-103 行**: `window.location.href = '/login'` - **跳转到登录页**  
**第 105 行**: `throw error` - 抛出错误，阻止后续执行  

**第 107-109 行**: `finally` 块重置 `isRefreshing = false` 和 `refreshPromise = null`

✅ **确认：refresh 失败时清空 auth store 并跳转登录页，不会无限循环重试**

---

## 🔒 防止无限循环的机制

### 1. Singleton 模式（第 67-70 行）

```typescript
// If already refreshing, return existing promise
if (isRefreshing && refreshPromise) {
  return refreshPromise;
}
```

**作用**: 并发请求时只触发一次 refresh，其他请求等待同一个 Promise

---

### 2. retryOn401 标志（第 168 行）

```typescript
if (response.status === 401 && retryOn401 && !skipAuth) {
```

**作用**: 只有当 `retryOn401 = true` 时才会重试，可以通过设置 `retryOn401: false` 阻止重试

**使用场景**: 登录请求设置 `retryOn401: false`，避免登录失败时触发 refresh

---

### 3. Refresh 失败后清空状态（第 98-105 行）

```typescript
catch (error) {
  // Refresh failed - clear auth and redirect to login
  useAuthStore.getState().clearAuth();
  
  if (typeof window !== 'undefined') {
    window.location.href = '/login';
  }
  
  throw error;
}
```

**作用**: 
- 清空 tokens（`clearAuth()`）
- 跳转到登录页（`window.location.href = '/login'`）
- 抛出错误（`throw error`）阻止后续执行

**结果**: 用户被强制退出，必须重新登录，**不会再次触发 refresh**

---

### 4. 原请求的 catch 块（第 184-187 行）

```typescript
} catch (error) {
  // Refresh failed, return original 401 response
  return response;
}
```

**作用**: 如果 `refreshAccessToken()` 抛出错误，捕获后返回原始 401 响应，不会再次重试

---

## 📊 完整流程图

```
用户请求 API
    ↓
添加 Authorization header
    ↓
发送请求
    ↓
收到 401 响应
    ↓
检查 retryOn401 && !skipAuth
    ↓ (是)
调用 refreshAccessToken()
    ↓
检查是否正在刷新 (isRefreshing)
    ↓ (否)
发送 POST /auth/refresh
    ↓
    ├─ 成功 (200)
    │   ↓
    │   更新 tokens (setTokens)
    │   ↓
    │   返回新 access token
    │   ↓
    │   重试原请求（带新 token）
    │   ↓
    │   返回结果
    │
    └─ 失败 (401 或其他错误)
        ↓
        清空 auth store (clearAuth)
        ↓
        跳转到 /login
        ↓
        抛出错误
        ↓
        原请求 catch 块捕获
        ↓
        返回原始 401 响应
        ↓
        用户看到错误提示
```

---

## ✅ 最终确认

### 问题 1：401 时是否自动调用 refresh 接口换新 token，换成功后是否重试原请求

**答案**: ✅ **是**

- **代码行**: 第 168-182 行
- **逻辑**: 
  1. 检测到 401 → 调用 `refreshAccessToken()`
  2. 获取新 token → 构建新请求头
  3. 使用新 token 重试原请求（相同 url 和 options）

---

### 问题 2：refresh 本身失败（再次 401）时是否清空 auth store 并跳转登录页，而不是无限循环重试

**答案**: ✅ **是**

- **代码行**: 第 91-105 行
- **逻辑**:
  1. Refresh 请求失败（`!response.ok`）→ 抛出错误
  2. 进入 catch 块 → 清空 auth store（`clearAuth()`）
  3. 跳转登录页（`window.location.href = '/login'`）
  4. 抛出错误 → 阻止后续执行
  5. **不会再次触发 refresh**，因为 tokens 已清空且页面已跳转

---

## 🛡️ 安全性保证

1. **Singleton 模式**: 防止并发请求触发多次 refresh
2. **retryOn401 标志**: 登录请求可设置 `false` 避免循环
3. **清空 + 跳转**: Refresh 失败后强制退出，不会重试
4. **finally 块**: 确保 `isRefreshing` 和 `refreshPromise` 被重置

---

**结论**: 实现完全符合要求，不存在无限循环风险。✅
