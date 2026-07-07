/**
 * auth-guard.js — 页面权限拦截脚本
 *
 * 使用方式：在每个需要保护的 HTML 页面的 <head> 中添加:
 *   <script src="config.js"></script>
 *   <script src="auth-guard.js"></script>
 *
 * 或直接内联（见 DEPLOY.md 中的说明）
 *
 * 逻辑:
 *   1. 检查 localStorage 是否有 token
 *   2. 调 /api/auth/me 验证 token 有效性
 *   3. 检查当前页面是否在用户可访问页面列表中
 *   4. 未登录 / 无权限 → 跳转 login.html
 */
(async function () {
  'use strict';

  // 当前页面文件名
  var currentPage = location.pathname.split('/').pop() || 'index.html';

  // login.html 本身不受保护
  if (currentPage === 'login.html' || currentPage === '') {
    return;
  }

  // 从 localStorage 获取 token
  var token = localStorage.getItem('feishu_token');
  if (!token) {
    console.log('[auth-guard] 无 token，跳转登录页');
    location.href = getBaseUrl() + '/login.html';
    return;
  }

  // 获取 API 地址
  var apiBase = window.API_BASE || '';
  if (!apiBase) {
    console.error('[auth-guard] API_BASE 未配置');
    showError('系统未配置后端地址，请联系管理员');
    return;
  }

  try {
    // 验证 token 并获取用户信息
    var res = await fetch(apiBase + '/api/auth/me', {
      method: 'GET',
      headers: { 'Authorization': 'Bearer ' + token }
    });

    if (res.status === 401) {
      // token 过期或无效
      console.log('[auth-guard] token 无效，跳转登录页');
      localStorage.removeItem('feishu_token');
      location.href = getBaseUrl() + '/login.html';
      return;
    }

    if (!res.ok) {
      throw new Error('HTTP ' + res.status);
    }

    var user = await res.json();

    // 检查当前页面是否在用户可访问列表中
    if (user.pages && user.pages.indexOf(currentPage) === -1) {
      console.log('[auth-guard] 无权访问此页面:', currentPage, '可访问:', user.pages);
      showNoPermission(user);
      return;
    }

    // 验证通过 — 将用户信息存到全局，页面可用
    window.currentUser = user;
    console.log('[auth-guard] 验证通过:', user.name, '角色:', user.role);

    // 在页面右上角显示用户信息（可选）
    showUserInfo(user);

  } catch (err) {
    console.error('[auth-guard] 验证失败:', err.message);
    showError('无法连接认证服务，请检查网络或稍后重试');
  }

  // ==================== 辅助函数 ====================

  function getBaseUrl() {
    var p = location.pathname;
    var lastSlash = p.lastIndexOf('/');
    return lastSlash > 0 ? p.substring(0, lastSlash) : '';
  }

  function showError(msg) {
    var div = document.createElement('div');
    div.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:#fff;z-index:99999;font-family:sans-serif;font-size:16px;color:#e74c3c;text-align:center;padding:20px;';
    div.innerHTML = '<div><p>&#9888; ' + msg + '</p><p style="margin-top:10px;font-size:14px;color:#999;">' + new Date().toLocaleTimeString() + '</p></div>';
    document.body ? document.body.appendChild(div) : document.documentElement.appendChild(div);
  }

  function showNoPermission(user) {
    var div = document.createElement('div');
    div.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:#f8f9fa;z-index:99999;font-family:sans-serif;text-align:center;padding:20px;';
    var pages = user.pages || [];
    div.innerHTML =
      '<div style="max-width:400px;">' +
      '<h2 style="color:#e74c3c;margin-bottom:10px;">&#128683; 无访问权限</h2>' +
      '<p style="color:#666;margin-bottom:15px;">' + (user.name || '') + '，您没有访问此页面的权限</p>' +
      '<p style="color:#999;font-size:14px;margin-bottom:20px;">您的角色: ' + (user.role === 'admin' ? '管理员' : '区域BP') + '</p>' +
      (pages.length > 0 ? '<p style="color:#666;font-size:14px;margin-bottom:20px;">可访问页面:<br>' + pages.join('<br>') + '</p>' : '') +
      '<button onclick="localStorage.removeItem(\'feishu_token\');location.href=\'' + getBaseUrl() + '/login.html\'" style="padding:8px 20px;background:#3370ff;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:14px;">重新登录</button>' +
      '</div>';
    document.body ? document.body.appendChild(div) : document.documentElement.appendChild(div);
  }

  function showUserInfo(user) {
    // 等待 DOM 加载完成
    function init() {
      var bar = document.createElement('div');
      bar.id = 'feishu-user-bar';
      bar.style.cssText = 'position:fixed;top:8px;right:8px;z-index:99998;font-family:sans-serif;font-size:12px;background:rgba(51,112,255,0.9);color:#fff;padding:6px 14px;border-radius:16px;box-shadow:0 2px 8px rgba(0,0,0,0.15);cursor:pointer;display:flex;align-items:center;gap:6px;';

      var roleText = user.role === 'admin' ? '管理员' : '区域BP';
      var regionsText = user.regions && user.regions.length > 0 ? ' (' + user.regions.join(', ') + ')' : '';
      bar.innerHTML =
        '<span>' + (user.name || '用户') + '</span>' +
        '<span style="opacity:0.8;">' + roleText + regionsText + '</span>' +
        '<span style="opacity:0.6;font-size:11px;">| 退出</span>';

      bar.onclick = function () {
        if (confirm('确定退出登录？')) {
          localStorage.removeItem('feishu_token');
          location.href = getBaseUrl() + '/login.html';
        }
      };

      // 避免重复添加
      var existing = document.getElementById('feishu-user-bar');
      if (existing) existing.remove();
      document.body.appendChild(bar);
    }

    if (document.body) {
      init();
    } else {
      document.addEventListener('DOMContentLoaded', init);
    }
  }
})();
