import { useState } from 'react';
import { Plus, Bookmark, LogOut, Users, User } from 'lucide-react';
import { toast } from 'sonner';
import { useStore } from '../store.js';
import { api } from '../lib/api.js';
import { relativeTime } from '../lib/format.js';
import SavedPanel from './SavedPanel.jsx';

export default function ChatList() {
  const { chats, me, activeId, openChat, logout, upsertChat, socketState } = useStore();
  const [creating, setCreating] = useState(false);
  const [showSaved, setShowSaved] = useState(false);
  const [kind, setKind] = useState('direct');
  const [sid, setSid] = useState('');
  const [name, setName] = useState('');

  async function create(e) {
    e.preventDefault();
    try {
      let chat;
      if (kind === 'direct') chat = await api.startDirect(sid);
      else {
        const members = sid.split(/[\s,]+/).filter(Boolean);
        chat = await api.createGroup(name.trim(), members);
      }
      upsertChat(chat);
      setCreating(false);
      setSid('');
      setName('');
      openChat(chat.id);
    } catch (err) {
      toast.error(err.message);
    }
  }

  const field = 'w-full rounded-lg bg-[#202c33] px-3 py-2 outline-none focus:ring-2 focus:ring-[#00a884]';
  return (
    <>
      <header className="flex items-center gap-2 bg-[#202c33] p-3">
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold">{me.display_name || me.username}</div>
          <div className="text-xs text-[#8696a0]">@{me.username} · {socketState}</div>
        </div>
        <button aria-label="Saved messages" onClick={() => setShowSaved(true)} className="p-2"><Bookmark size={20} /></button>
        <button aria-label="New chat" onClick={() => setCreating(!creating)} className="p-2"><Plus size={20} /></button>
        <button aria-label="Log out" onClick={() => logout()} className="p-2"><LogOut size={20} /></button>
      </header>
      {creating && (
        <form onSubmit={create} className="space-y-2 border-b border-[#222d34] p-3">
          <div className="flex gap-2 text-sm">
            {['direct', 'group'].map((k) => (
              <button type="button" key={k} onClick={() => setKind(k)} className={`flex-1 rounded-lg py-1 capitalize ${kind === k ? 'bg-[#00a884] text-black' : 'bg-[#202c33]'}`}>{k}</button>
            ))}
          </div>
          {kind === 'group' && <input className={field} placeholder="Group name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} required />}
          <input className={field} placeholder={kind === 'direct' ? 'Student ID' : 'Student IDs, comma separated'} value={sid} onChange={(e) => setSid(e.target.value)} required />
          <button className="w-full rounded-lg bg-[#00a884] py-1.5 font-medium text-black">Start</button>
        </form>
      )}
      <ul className="flex-1 overflow-y-auto">
        {chats.length === 0 && <li className="p-6 text-center text-sm text-[#8696a0]">No chats yet. Tap + to start one.</li>}
        {chats.map((c) => (
          <li key={c.id}>
            <button onClick={() => openChat(c.id)} className={`flex w-full items-center gap-3 px-3 py-3 text-left hover:bg-[#202c33] ${activeId === c.id ? 'bg-[#2a3942]' : ''}`}>
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#374248]">{c.kind === 'group' ? <Users size={20} /> : <User size={20} />}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{c.name}</span>
                <span className="block text-xs text-[#8696a0]">{c.last_message_at ? relativeTime(c.last_message_at) : 'No messages'}</span>
              </span>
              {c.unread_count > 0 && <span className="rounded-full bg-[#00a884] px-2 text-xs font-semibold text-black">{c.unread_count}</span>}
            </button>
          </li>
        ))}
      </ul>
      {showSaved && <SavedPanel onClose={() => setShowSaved(false)} />}
    </>
  );
}
