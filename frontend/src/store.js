import { create } from 'zustand';
import { toast } from 'sonner';
import { api, tokenStore, setUnauthorizedHandler } from './lib/api.js';
import { connectSocket, disconnectSocket, emitRead } from './lib/socket.js';

const byActivity = (a, b) =>
  (b.last_message_at || '').localeCompare(a.last_message_at || '');

/** Insert/replace a message by id, keeping oldest-first order. */
export function upsertMessage(list = [], msg) {
  const i = list.findIndex((m) => m.id === msg.id);
  if (i >= 0) {
    const next = list.slice();
    next[i] = msg;
    return next;
  }
  return [...list, msg].sort((a, b) => a.id - b.id);
}

export const useStore = create((set, get) => ({
  booting: true,
  me: null,
  chats: [],
  activeId: null,
  messages: {}, // chatId -> Message[]
  hasMore: {},
  typing: {}, // chatId -> {username: true}
  saved: [],
  socketState: 'offline',

  async boot() {
    setUnauthorizedHandler(() => get().logout(true));
    if (!tokenStore.get()) return set({ booting: false });
    try {
      const me = await api.me();
      set({ me });
      await get().startSession();
    } catch (e) {
      if (e.status === 401) tokenStore.clear();
    }
    set({ booting: false });
  },

  async authenticate(mode, form) {
    const res = mode === 'login' ? await api.login(form) : await api.register(form);
    tokenStore.set(res.token);
    set({ me: await api.me() });
    await get().startSession();
  },

  async startSession() {
    await get().loadChats();
    connectSocket(tokenStore.get(), {
      connect: () => set({ socketState: 'online' }),
      disconnect: () => set({ socketState: 'offline' }),
      connect_error: () => {
        set({ socketState: 'offline' });
        api.me().catch(() => {}); // a 401 triggers logout via the handler
      },
      new_message: (m) => get().receiveMessage(m),
      message_updated: (m) =>
        set((s) => ({
          messages: { ...s.messages, [m.conversation_id]: upsertMessage(s.messages[m.conversation_id], m) },
        })),
      message_deleted: ({ id, conversation_id }) =>
        set((s) => ({
          messages: {
            ...s.messages,
            [conversation_id]: (s.messages[conversation_id] || []).filter((m) => m.id !== id),
          },
        })),
      typing: ({ conversation_id, username, is_typing }) =>
        set((s) => {
          const cur = { ...(s.typing[conversation_id] || {}) };
          if (is_typing) cur[username] = true;
          else delete cur[username];
          return { typing: { ...s.typing, [conversation_id]: cur } };
        }),
      error: (e) => toast.error(e?.error || 'Socket error'),
    });
  },

  async logout(silent = false) {
    if (!silent) await api.logout().catch(() => {});
    tokenStore.clear();
    disconnectSocket();
    set({ me: null, chats: [], activeId: null, messages: {}, saved: [], typing: {}, hasMore: {}, socketState: 'offline' });
  },

  async loadChats() {
    const chats = await api.chats();
    set({ chats: chats.slice().sort(byActivity) });
  },

  upsertChat(chat) {
    set((s) => ({
      chats: [chat, ...s.chats.filter((c) => c.id !== chat.id)].sort(byActivity),
    }));
  },

  async openChat(id) {
    set({ activeId: id });
    if (id == null) return;
    try {
      const msgs = await api.messages(id);
      set((s) => ({
        messages: { ...s.messages, [id]: msgs },
        hasMore: { ...s.hasMore, [id]: msgs.length >= 50 },
      }));
      get().markRead(id);
    } catch (e) {
      if (e.status === 404) {
        toast.error('Chat not found');
        set((s) => ({ activeId: null, chats: s.chats.filter((c) => c.id !== id) }));
      } else toast.error(e.message);
    }
  },

  async loadOlder(id) {
    const list = get().messages[id] || [];
    if (!list.length || !get().hasMore[id]) return;
    const older = await api.messages(id, list[0].id);
    set((s) => ({
      messages: { ...s.messages, [id]: older.reduce(upsertMessage, s.messages[id] || []) },
      hasMore: { ...s.hasMore, [id]: older.length >= 50 },
    }));
  },

  receiveMessage(m) {
    const { activeId, me } = get();
    set((s) => {
      const chats = s.chats.map((c) =>
        c.id === m.conversation_id
          ? {
              ...c,
              last_message_at: m.created_at,
              unread_count:
                m.conversation_id === activeId || m.sender === me?.username
                  ? c.unread_count
                  : (c.unread_count || 0) + 1,
            }
          : c,
      );
      return {
        chats: chats.sort(byActivity),
        messages: { ...s.messages, [m.conversation_id]: upsertMessage(s.messages[m.conversation_id], m) },
      };
    });
    if (!get().chats.some((c) => c.id === m.conversation_id)) get().loadChats();
    if (m.conversation_id === activeId) get().markRead(activeId, m.id);
  },

  markRead(id, messageId) {
    const list = get().messages[id] || [];
    const last = messageId ?? list[list.length - 1]?.id;
    set((s) => ({ chats: s.chats.map((c) => (c.id === id ? { ...c, unread_count: 0 } : c)) }));
    api.markRead(id).catch(() => {});
    if (last) emitRead(id, last);
  },

  async sendMessage(id, body) {
    // The server echoes the message back over the socket; upsert-by-id
    // makes the REST response and the socket event idempotent.
    const m = await api.send(id, body);
    set((s) => ({ messages: { ...s.messages, [id]: upsertMessage(s.messages[id], m) } }));
  },

  removeExpired(now = new Date()) {
    set((s) => {
      let changed = false;
      const messages = {};
      for (const [k, list] of Object.entries(s.messages)) {
        const kept = list.filter((m) => new Date(m.expires_at) > now);
        if (kept.length !== list.length) changed = true;
        messages[k] = kept;
      }
      return changed ? { messages } : {};
    });
  },

  async loadSaved() {
    set({ saved: await api.saved() });
  },
}));
