let authMode = 'login';
let token = localStorage.getItem('starz_token') || '';
let currentUser = null;
let chats = [];
let activeChat = null;
let currentPanel = 'chats';
let socket = null;

function switchAuthTab(mode) {
  authMode = mode;
  document.getElementById('tab-login').classList.toggle('active', mode === 'login');
  document.getElementById('tab-register').classList.toggle('active', mode === 'register');
  document.getElementById('field-student-id').style.display = mode === 'register' ? 'block' : 'none';
  document.getElementById('field-display-name').style.display = mode === 'register' ? 'block' : 'none';
  document.getElementById('auth-submit-btn').textContent = mode === 'login' ? 'Log In' : 'Create Account';
  document.getElementById('auth-error').textContent = '';
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.msg || `HTTP ${res.status}`);
  return data;
}

async function handleAuth(e) {
  e.preventDefault();
  const errEl = document.getElementById('auth-error');
  errEl.textContent = '';
  const username = document.getElementById('inp-username').value.trim();
  const password = document.getElementById('inp-password').value;

  try {
    let res;
    if (authMode === 'login') {
      res = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password })
      });
    } else {
      const student_id = document.getElementById('inp-student-id').value.trim();
      const display_name = document.getElementById('inp-display-name').value.trim();
      res = await api('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({ student_id, username, password, display_name })
      });
    }
    token = res.token;
    localStorage.setItem('starz_token', token);
    await bootApp();
  } catch (err) {
    errEl.textContent = err.message;
  }
}

async function bootApp() {
  try {
    currentUser = await api('/api/me');
  } catch {
    logout();
    return;
  }
  document.getElementById('auth-view').style.display = 'none';
  document.getElementById('app-view').style.display = 'block';
  document.getElementById('me-username').textContent = `@${currentUser.username}`;
  document.getElementById('me-student-id').textContent = `ID: ${currentUser.student_id}`;

  connectSocket();
  await loadChats();
}

function connectSocket() {
  if (socket) socket.disconnect();
  socket = io({ auth: { token } });
  const dot = document.getElementById('status-dot');
  socket.on('connect', () => dot.classList.add('connected'));
  socket.on('disconnect', () => dot.classList.remove('connected'));
  socket.on('new_message', (msg) => {
    if (currentPanel === 'chats' && activeChat && msg.conversation_id === activeChat.id) {
      appendMessage(msg);
    } else {
      loadChats();
    }
  });
}

async function loadChats() {
  chats = await api('/api/chats');
  if (currentPanel === 'chats') renderChatList();
}

function renderChatList() {
  const list = document.getElementById('sidebar-list');
  if (!chats.length) {
    list.innerHTML = `<div class="empty-state" style="padding:20px;">No chats yet.<br/>Enter a Student ID above to start!</div>`;
    return;
  }
  list.innerHTML = chats.map(c => `
    <div class="chat-item ${activeChat && activeChat.id === c.id ? 'active' : ''}" onclick="selectChat(${c.id})">
      <div>
        <strong>${escapeHtml(c.name)}</strong>
        <div class="meta">${c.kind === 'group' ? `Group • ${c.members.length} members` : 'Direct Message'}</div>
      </div>
    </div>
  `).join('');
}

async function selectChat(chatId) {
  currentPanel = 'chats';
  document.getElementById('nav-chats').classList.add('active');
  document.getElementById('nav-saved').classList.remove('active');
  activeChat = chats.find(c => c.id === chatId);
  renderChatList();

  document.getElementById('chat-header').style.display = 'flex';
  document.getElementById('composer').style.display = 'flex';
  document.getElementById('active-chat-title').textContent = activeChat.name;
  document.getElementById('active-chat-members').textContent = `Members: ${activeChat.members.join(', ')}`;
  document.getElementById('group-controls').style.display = activeChat.kind === 'group' ? 'flex' : 'none';

  const messages = await api(`/api/chats/${chatId}/messages`);
  const box = document.getElementById('messages-area');
  box.innerHTML = '';
  if (!messages.length) {
    box.innerHTML = `<div class="empty-state">No live messages yet. Say hello!</div>`;
  } else {
    messages.forEach(appendMessage);
  }
}

function appendMessage(m) {
  const box = document.getElementById('messages-area');
  const empty = box.querySelector('.empty-state');
  if (empty) empty.remove();

  if (document.getElementById(`msg-${m.id}`)) return;

  const mine = m.sender === currentUser.username;
  const div = document.createElement('div');
  div.id = `msg-${m.id}`;
  div.className = `msg ${mine ? 'mine' : ''}`;
  const time = new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  div.innerHTML = `
    <div class="msg-top">
      <strong>@${escapeHtml(m.sender)}</strong>
      <span>${time}</span>
    </div>
    <div class="msg-body">${escapeHtml(m.body)}</div>
    <div class="msg-actions">
      <button onclick="saveMessage(${m.id}, this)">Save copy</button>
    </div>
  `;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;

async function sendMessage(e) {
  e.preventDefault();
  if (!activeChat) return;
  const inp = document.getElementById('msg-input');
  const body = inp.value.trim();
  if (!body) return;
  inp.value = '';
  try {
    const msg = await api(`/api/chats/${activeChat.id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ body })
    });
    appendMessage(msg);
  } catch (err) {
    alert(err.message);
  }
}

async function startDirectChat() {
  const inp = document.getElementById('direct-student-id');
  const student_id = inp.value.trim();
  if (!student_id) return;
  try {
    const chat = await api('/api/chats/direct', {
      method: 'POST',
      body: JSON.stringify({ student_id })
    });
    inp.value = '';
    await loadChats();
    await selectChat(chat.id);
  } catch (err) {
    alert(err.message);
  }
}

async function createGroupChat() {
  const nameInp = document.getElementById('group-name');
  const memInp = document.getElementById('group-members');
  const name = nameInp.value.trim();
  const members = memInp.value.split(',').map(s => s.trim()).filter(Boolean);
  if (!name) return alert('Enter a group name');
  try {
    const chat = await api('/api/chats/group', {
      method: 'POST',
      body: JSON.stringify({ name, members })
    });
    nameInp.value = '';
    memInp.value = '';
    await loadChats();
    await selectChat(chat.id);
  } catch (err) {
    alert(err.message);
  }
}

async function addGroupMember() {
  const inp = document.getElementById('add-member-id');
  const student_id = inp.value.trim();
  if (!student_id || !activeChat) return;
  try {
    await api(`/api/chats/${activeChat.id}/members`, {
      method: 'POST',
      body: JSON.stringify({ student_id })
    });
    inp.value = '';
    await loadChats();
    await selectChat(activeChat.id);
  } catch (err) {
    alert(err.message);
  }
}

async function leaveGroup() {
  if (!activeChat) return;
  try {
    await api(`/api/chats/${activeChat.id}/members/${currentUser.username}`, {
      method: 'DELETE'
    });
    activeChat = null;
    document.getElementById('chat-header').style.display = 'none';
    document.getElementById('composer').style.display = 'none';
    document.getElementById('messages-area').innerHTML = `<div class="empty-state">Select or start a chat on the left</div>`;
    await loadChats();
  } catch (err) {
    alert(err.message);
  }
}

async function saveMessage(id, btn) {
  try {
    await api(`/api/messages/${id}/save`, { method: 'POST' });
    btn.textContent = 'Saved ✓';
    btn.disabled = true;
  } catch (err) {
    alert(err.message);
  }
}

async function switchPanel(panel) {
  currentPanel = panel;
  document.getElementById('nav-chats').classList.toggle('active', panel === 'chats');
  document.getElementById('nav-saved').classList.toggle('active', panel === 'saved');
  if (panel === 'chats') {
    renderChatList();
  } else {
    activeChat = null;
    document.getElementById('chat-header').style.display = 'none';
    document.getElementById('composer').style.display = 'none';
    const saved = await api('/api/saved');
    const list = document.getElementById('sidebar-list');
    list.innerHTML = `<div style="padding:12px; color:var(--muted); font-size:0.85rem;">Saved messages never expire, even after the original disappears from the chat.</div>`;
    const box = document.getElementById('messages-area');
    if (!saved.length) {
      box.innerHTML = `<div class="empty-state">No saved messages yet.</div>`;
      return;
    }
    box.innerHTML = saved.map(s => `
      <div class="msg" style="align-self:stretch; max-width:100%;">
        <div class="msg-top">
          <strong>From @${escapeHtml(s.sender)} (Chat #${s.conversation_id})</strong>
          <span>Saved ${new Date(s.saved_at).toLocaleString()}</span>
        </div>
        <div class="msg-body">${escapeHtml(s.body)}</div>
        <div class="msg-actions">
          <button class="danger" onclick="deleteSaved(${s.id})">Delete</button>
        </div>
      </div>
    `).join('');
  }
}

async function deleteSaved(id) {
  await api(`/api/saved/${id}`, { method: 'DELETE' });
  switchPanel('saved');
}

function logout() {
  token = '';
  localStorage.removeItem('starz_token');
  if (socket) socket.disconnect();
  document.getElementById('app-view').style.display = 'none';
  document.getElementById('auth-view').style.display = 'block';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

if (token) bootApp();

}
