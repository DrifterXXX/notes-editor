#!/usr/bin/env python3
"""
轻量Markdown在线编辑器服务器 v3.0
- 浏览目录中的 .md 文件
- 在线编辑并保存（带确认反馈）
- 中间竖杠左右拖动调整
- Cookie-based 登录认证（共享 shell-server 凭据）
- 无第三方依赖
"""
import http.server
import json
import os
import urllib.parse
import time
import hashlib
import hmac
import secrets

ROOT = os.path.expanduser("~/services/notes-editor/notes")
PORT = 8769
TOKEN_TTL = 86400  # 24 hours
CONFIG_PATH = os.path.expanduser("~/.shell-server/config.json")

# ── Config & Auth ────────────────────────────────────────────────────────────
SESSIONS = {}  # {token: {"username": str, "created_at": float}}

def load_shared_config():
    """Load credentials from shared shell-server config."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    # Fallback: generate own config
    cfg = {"username": "admin", "password": secrets.token_urlsafe(16)}
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CONFIG_PATH, 0o600)
    return cfg

def verify_password(cfg, password):
    """Verify password, supporting both plaintext and SHA-256 hashed."""
    stored = cfg.get("password", "")
    # SHA-256 hash format: $sha256$<hex>
    if stored.startswith("$sha256$"):
        expected = stored[8:]
        actual = hashlib.sha256(password.encode()).hexdigest()
        return hmac.compare_digest(actual.encode(), expected.encode())
    # Legacy plaintext comparison
    return hmac.compare_digest(password.encode(), stored.encode())

LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Markdown 编辑器 · 登录</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:#e2e8f0;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  display:flex;align-items:center;justify-content:center;min-height:100vh}
.login-box{background:rgba(255,255,255,.06);backdrop-filter:blur(12px);
  padding:40px;border-radius:16px;width:360px;box-shadow:0 8px 32px rgba(0,0,0,.3);
  border:1px solid rgba(255,255,255,.1)}
.login-box h1{text-align:center;margin-bottom:8px;font-size:1.4rem}
.login-box .sub{text-align:center;color:rgba(255,255,255,.5);font-size:.82rem;margin-bottom:28px}
.form-group{margin-bottom:18px}
.form-group label{display:block;font-size:.82rem;color:rgba(255,255,255,.6);margin-bottom:6px}
.form-group input{width:100%;padding:10px 14px;border:1px solid rgba(255,255,255,.15);
  border-radius:8px;background:rgba(0,0,0,.3);color:#e2e8f0;font-size:.92rem;outline:none;transition:border-color .2s}
.form-group input:focus{border-color:#3b82f6}
.btn{width:100%;padding:11px;border:none;border-radius:8px;background:#3b82f6;color:#fff;
  font-size:.95rem;cursor:pointer;transition:background .2s;font-weight:600}
.btn:hover{background:#2563eb}
.error{background:rgba(239,68,68,.2);color:#fca5a5;padding:10px;border-radius:8px;font-size:.82rem;margin-bottom:16px}
</style>
</head>
<body>
<div class="login-box">
  <h1>📝 Markdown 编辑器</h1>
  <div class="sub">notes.drifter.indevs.in</div>
  {error_html}
  <form method="post" action="/login">
    <div class="form-group"><label>密码</label><input type="password" name="password" autocomplete="current-password" autofocus></div>
    <button type="submit" class="btn">登 录</button>
  </form>
</div>
</body>
</html>"""

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>Markdown 编辑器</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/codemirror.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/theme/material-darker.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/codemirror.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/mode/markdown/markdown.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/selection/active-line.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/edit/closebrackets.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/15.0.6/marked.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f0f2f5;color:#333;display:flex;flex-direction:column;height:100vh}
header{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:#fff;padding:14px 24px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
header h1{font-size:1.15rem;font-weight:600}
header a{color:rgba(255,255,255,.7);text-decoration:none;font-size:.85rem}
header a:hover{color:#fff}
.toolbar{display:flex;gap:8px;padding:8px 24px;background:#fff;border-bottom:1px solid #e0e0e0;align-items:center;flex-shrink:0}
.toolbar .file-label{font-size:.85rem;color:#666;margin-right:8px}
.toolbar button{padding:5px 14px;border:none;border-radius:4px;cursor:pointer;font-size:.82rem;transition:.2s}
.btn-save{background:#0f3460;color:#fff}
.btn-save:hover{background:#1a4a7a}
.btn-save:disabled{background:#999;cursor:not-allowed}
.status{font-size:.8rem;margin-left:10px}
.status.success{color:#2e7d32}
.status.error{color:#c62828}
.status.info{color:#1565c0}
main{flex:1;display:flex;overflow:hidden;min-height:0}
.editor-wrap{position:relative;overflow:hidden;min-width:200px}
.editor-wrap .CodeMirror{height:100% !important;font-size:14px;line-height:1.7}
.splitter-v{width:7px;cursor:col-resize;background:#e0e0e0;transition:background .15s;flex-shrink:0;z-index:20;position:relative}
.splitter-v::after{content:'';position:absolute;top:50%;left:50%;width:3px;height:32px;transform:translate(-50%,-50%);background:#ccc;border-radius:2px;transition:background .15s}
.splitter-v:hover::after,.splitter-v.dragging::after{background:#0f3460}
.splitter-v:hover,.splitter-v.dragging{background:#d0d4dc}
.preview-wrap{flex:1;overflow-y:auto;padding:20px 28px;background:#fff;line-height:1.8;font-size:.95rem;min-width:200px;scroll-behavior:smooth}
.preview-wrap h1,.preview-wrap h2,.preview-wrap h3{margin:.8em 0 .4em;color:#1a1a2e}
.preview-wrap h1{border-bottom:2px solid #0f3460;padding-bottom:6px}
.preview-wrap h2{border-bottom:1px solid #ddd;padding-bottom:4px}
.preview-wrap p{margin:.5em 0}
.preview-wrap code{background:#f4f4f8;padding:2px 6px;border-radius:3px;font-size:.88em;color:#c7254e}
.preview-wrap pre{background:#f8f8fa;border-radius:6px;padding:12px 16px;overflow-x:auto;border:1px solid #eee}
.preview-wrap pre code{background:none;padding:0;border-radius:0;color:inherit;font-size:.88em}
.preview-wrap ul,.preview-wrap ol{padding-left:24px}
.preview-wrap blockquote{border-left:4px solid #0f3460;padding:8px 16px;margin:12px 0;background:#f8f9fa;border-radius:0 4px 4px 0}
.preview-wrap table{border-collapse:collapse;width:100%;margin:12px 0}
.preview-wrap th,.preview-wrap td{border:1px solid #ddd;padding:8px 12px;text-align:left}
.preview-wrap th{background:#f0f2f5;font-weight:600}
.preview-wrap img{max-width:100%;border-radius:4px}
.preview-wrap hr{border:none;border-top:1px solid #ddd;margin:1.5em 0}
.preview-wrap a{color:#0f3460}
</style>
</head>
<body>
<header>
<h1>📝 {{FILENAME}}</h1>
<div><a href="/">← 文件列表</a> <a href="/logout" style="margin-left:16px">🚪 退出</a></div>
</header>
<div class="toolbar">
<span class="file-label">📄 {{FILENAME}}</span>
<button class="btn-save" id="saveBtn">💾 保存</button>
<span class="status" id="status"></span>
</div>
<main>
<div class="editor-wrap" id="editorWrap">
<textarea id="editor">{{CONTENT}}</textarea>
</div>
<div class="splitter-v" id="splitterV"></div>
<div class="preview-wrap" id="preview"></div>
</main>
<script>
const FILENAME = '{{FILENAME_JS}}';
var editor = CodeMirror.fromTextArea(document.getElementById('editor'), {
    mode: 'markdown',
    theme: 'material-darker',
    lineWrapping: true,
    lineNumbers: true,
    indentUnit: 2,
    tabSize: 2,
    styleActiveLine: true,
    autoCloseBrackets: true,
    extraKeys: {'Tab': function(cm) { cm.replaceSelection('  ', 'end'); }}
});
marked.setOptions({breaks: true, gfm: true});
function updatePreview(){
    var html = marked.parse(editor.getValue());
    document.getElementById('preview').innerHTML = html;
}
editor.on('change', updatePreview);
updatePreview();
var status = document.getElementById('status');
var saveBtn = document.getElementById('saveBtn');
var saving = false;
function setStatus(text, type){
    status.textContent = text;
    status.className = 'status ' + type;
}
async function save(){
    if(saving) return;
    saving = true;
    saveBtn.disabled = true;
    setStatus('保存中...', 'info');
    try{
        var r = await fetch('/save?file=' + encodeURIComponent(FILENAME), {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({content: editor.getValue()})
        });
        var d = await r.json();
        if(d.ok){
            setStatus('✅ 已保存 ' + new Date().toLocaleTimeString(), 'success');
            saveBtn.style.background = '#2e7d32';
            setTimeout(function(){ saveBtn.style.background = ''; }, 800);
        }else{
            setStatus('❌ 保存失败: ' + (d.error||'未知错误'), 'error');
        }
    }catch(e){
        setStatus('❌ 网络错误: ' + e.message, 'error');
    }
    saving = false;
    saveBtn.disabled = false;
}
saveBtn.addEventListener('click', save);
document.addEventListener('keydown', function(e){
    if((e.ctrlKey||e.metaKey) && e.key==='s'){ e.preventDefault(); save(); }
});
(function(){
    var splitter = document.getElementById('splitterV');
    var editorWrap = splitter.previousElementSibling;
    var previewWrap = splitter.nextElementSibling;
    var dragging = false, startX;
    function getFlexBasis(el){
        var cs = window.getComputedStyle(el);
        var basis = cs.getPropertyValue('flex-basis');
        if(basis && basis !== 'auto') return parseFloat(basis);
        return el.offsetWidth;
    }
    function doDrag(e){
        if(!dragging) return;
        var clientX = e.clientX !== undefined ? e.clientX : (e.touches ? e.touches[0].clientX : 0);
        var dx = clientX - startX;
        var currentWidth = getFlexBasis(editorWrap);
        var newWidth = Math.max(200, Math.min(window.innerWidth - 260, currentWidth + dx));
        editorWrap.style.flex = '0 0 ' + newWidth + 'px';
        previewWrap.style.flex = '1 1 auto';
        editorWrap.style.width = newWidth + 'px';
        editor.refresh();
        startX = clientX;
    }
    splitter.addEventListener('mousedown', function(e){
        dragging = true; splitter.classList.add('dragging');
        startX = e.clientX;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });
    document.addEventListener('mousemove', function(e){ if(!dragging) return; doDrag(e); });
    document.addEventListener('mouseup', function(){
        if(!dragging) return;
        dragging = false; splitter.classList.remove('dragging');
        document.body.style.cursor = ''; document.body.style.userSelect = '';
        try{ localStorage.setItem('mdEditorWidth', getFlexBasis(editorWrap)); }catch(e){}
        editor.refresh();
    });
    splitter.addEventListener('touchstart', function(e){
        dragging = true; splitter.classList.add('dragging');
        startX = e.touches[0].clientX; e.preventDefault();
    }, {passive: false});
    document.addEventListener('touchmove', function(e){ if(!dragging) return; doDrag(e); e.preventDefault(); }, {passive: false});
    document.addEventListener('touchend', function(){
        dragging = false; splitter.classList.remove('dragging');
        try{ localStorage.setItem('mdEditorWidth', getFlexBasis(editorWrap)); }catch(e){}
        editor.refresh();
    });
    try{
        var saved = localStorage.getItem('mdEditorWidth');
        if(saved && parseFloat(saved) > 200){
            editorWrap.style.flex = '0 0 ' + saved + 'px';
            editorWrap.style.width = saved + 'px';
        }
    }catch(e){}
})();
(function(){
    var preview = document.getElementById('preview');
    var editorScroll = editor.getScrollerElement();
    var syncing = false;
    editorScroll.addEventListener('scroll', function(){
        if(syncing) return; syncing = true;
        var ratio = editorScroll.scrollTop / (editorScroll.scrollHeight - editorScroll.clientHeight);
        preview.scrollTop = ratio * (preview.scrollHeight - preview.clientHeight);
        syncing = false;
    });
    preview.addEventListener('scroll', function(){
        if(syncing) return; syncing = true;
        var ratio = preview.scrollTop / (preview.scrollHeight - preview.clientHeight);
        editorScroll.scrollTop = ratio * (editorScroll.scrollHeight - editorScroll.clientHeight);
        syncing = false;
    });
})();
</script>
</body>
</html>"""

DIR_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>📁 文件列表</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f0f2f5;color:#333}
header{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:#fff;padding:20px 24px;display:flex;align-items:center;justify-content:space-between}
header h1{font-size:1.4rem;font-weight:600}
header a{color:rgba(255,255,255,.7);text-decoration:none;font-size:.85rem}
header a:hover{color:#fff}
.container{max-width:800px;margin:0 auto;padding:24px}
.file-list{list-style:none}
.file-list li{background:#fff;border-radius:8px;margin-bottom:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);transition:.2s}
.file-list li:hover{box-shadow:0 3px 12px rgba(0,0,0,.12)}
.file-list a{display:flex;align-items:center;padding:14px 20px;text-decoration:none;color:#333;gap:12px}
.file-icon{font-size:1.5rem}
.file-name{font-weight:600;flex:1}
.file-size{color:#999;font-size:.82rem}
.file-date{color:#999;font-size:.82rem}
.footer{text-align:center;padding:20px;color:#999;font-size:.82rem}
</style>
</head>
<body>
<header>
<h1>📁 N型K线结构 · 笔记</h1>
<a href="/logout">🚪 退出</a>
</header>
<div class="container">
<ul class="file-list">
{{FILES}}
</ul>
</div>
<div class="footer">Markdown 在线编辑器 v3.0 · Ctrl+S 保存 · 拖动竖杠调整布局</div>
</body>
</html>"""

class EditorHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def _get_session(self):
        """Get valid session from cookie."""
        cookie = self.headers.get('Cookie', '')
        token = None
        for part in cookie.split(';'):
            part = part.strip()
            if part.startswith('notes_token='):
                token = part.split('=', 1)[1]
                break
        if token and token in SESSIONS:
            sess = SESSIONS[token]
            if time.time() - sess["created_at"] < TOKEN_TTL:
                return sess
            del SESSIONS[token]
        return None
    
    def _require_auth(self):
        """Check auth, redirect to login if invalid."""
        session = self._get_session()
        if not session:
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
            return False
        return True
    
    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
    
    def _send_html(self, html, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def _safe_path(self, filename):
        clean = os.path.basename(filename)
        full = os.path.join(ROOT, clean)
        full = os.path.abspath(full)
        if not full.startswith(os.path.abspath(ROOT)):
            return None
        return full
    
    def _set_auth_cookie(self):
        """Set session cookie in response."""
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = {"username": "admin", "created_at": time.time()}
        cookie = f"notes_token={token}; Max-Age={TOKEN_TTL}; Path=/; HttpOnly; SameSite=Lax"
        self.send_header('Set-Cookie', cookie)
        return token
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        # ── Health check ──
        if parsed.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        
        # ── Login page (no auth required) ──
        if parsed.path == '/' or parsed.path == '/login':
            session = self._get_session()
            if session:
                # Already logged in, redirect to file list
                self.send_response(302)
                self.send_header('Location', '/files')
                self.end_headers()
                return
            error_html = ""
            if params.get('error'):
                error_html = '<div class="error">密码错误</div>'
            html = LOGIN_PAGE.replace("{error_html}", error_html)
            self._send_html(html)
            return
        
        # ── Logout ──
        if parsed.path == '/logout':
            self.send_response(302)
            self.send_header('Set-Cookie', 'notes_token=; Max-Age=0; Path=/')
            self.send_header('Location', '/')
            self.end_headers()
            return
        
        # ── File list (auth required) ──
        if parsed.path == '/files':
            if not self._require_auth():
                return
            files = []
            try:
                for f in sorted(os.listdir(ROOT)):
                    if f.endswith('.md') and not f.startswith('.'):
                        fp = os.path.join(ROOT, f)
                        size = os.path.getsize(fp)
                        mtime = os.path.getmtime(fp)
                        import datetime
                        dt = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                        files.append((f, size, dt))
            except Exception:
                files = []
            
            items = []
            for name, size, date in files:
                size_str = f'{size}B' if size < 1024 else f'{size/1024:.1f}KB'
                items.append(f'<li><a href="/edit?file={urllib.parse.quote(name)}"><span class="file-icon">📄</span><span class="file-name">{name}</span><span class="file-size">{size_str}</span><span class="file-date">{date}</span></a></li>')
            
            html = DIR_TEMPLATE.replace('{{FILES}}', '\n'.join(items))
            self._send_html(html)
            return
        
        # ── Edit page (auth required) ──
        if parsed.path == '/edit':
            if not self._require_auth():
                return
            filename = params.get('file', [''])[0]
            full_path = self._safe_path(filename)
            if not full_path or not os.path.exists(full_path):
                self._send_html('<h1>404 文件不存在</h1>', 404)
                return
            
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            html = HTML_TEMPLATE
            escaped_content = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            html = html.replace('{{CONTENT}}', escaped_content)
            html = html.replace('{{FILENAME}}', filename)
            html = html.replace('{{FILENAME_JS}}', filename)
            self._send_html(html)
            return
        
        # ── 404 ──
        self._send_html('<h1>404</h1>', 404)
    
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        # ── Login ──
        if parsed.path == '/login':
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len).decode('utf-8')
            post_data = urllib.parse.parse_qs(body)
            password = post_data.get('password', [''])[0]
            
            cfg = load_shared_config()
            if verify_password(cfg, password):
                token = self._set_auth_cookie()
                self.send_response(302)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Location', '/files')
                self.end_headers()
            else:
                self.send_response(302)
                self.send_header('Location', '/?error=1')
                self.end_headers()
            return
        
        # ── Save (auth required) ──
        if parsed.path == '/save':
            if not self._require_auth():
                return
            filename = params.get('file', [''])[0]
            if not filename:
                self._send_json({'ok': False, 'error': '缺少文件名参数'}, 400)
                return
            full_path = self._safe_path(filename)
            if not full_path:
                self._send_json({'ok': False, 'error': '非法文件名'}, 400)
                return
            
            try:
                content_len = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_len)
                data = json.loads(body)
                content = data.get('content', '')
                
                import shutil
                total, used, free = shutil.disk_usage(ROOT)
                if free < 1024 * 1024:
                    self._send_json({'ok': False, 'error': '磁盘空间不足'}, 507)
                    return
                
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                with open(full_path, 'r', encoding='utf-8') as f:
                    verify = f.read()
                if verify == content:
                    self._send_json({'ok': True, 'size': len(content)})
                else:
                    self._send_json({'ok': False, 'error': '写入验证失败'}, 500)
                    
            except PermissionError:
                self._send_json({'ok': False, 'error': '权限不足'}, 403)
            except json.JSONDecodeError:
                self._send_json({'ok': False, 'error': '无效的JSON数据'}, 400)
            except Exception as e:
                self._send_json({'ok': False, 'error': str(e)}, 500)
            return
        
        self._send_json({'ok': False, 'error': '未知路径'}, 404)
    
    do_PUT = do_POST

if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', PORT), EditorHandler)
    print(f'Markdown 编辑器服务 v3.0 启动: http://localhost:{PORT}')
    print(f'笔记目录: {ROOT}')
    print(f'认证: 共享 shell-server 凭据 (开启密码保护)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()