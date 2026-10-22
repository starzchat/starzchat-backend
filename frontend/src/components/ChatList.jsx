import { useState } from 'react';
import { Plus, Bookmark, LogOut, Users, User, Menu, Search } from 'lucide-react';
import { toast } from 'sonner';
import { useStore } from '../store.js';
import { api } from '../lib/api.js';
import { relativeTime } from '../lib/format.js';
import SavedPanel from './SavedPanel.jsx';

const YELLOW = '#FFD60A';
const field = 'w-full rounded-lg bg-[#111111] border border-[#2a2a2a] px-3 py-2 outline-none focus:ring-2 focus-ring focus:ring-' + YELLOW;

export default function ChatList() {
  const { chats, me, activeId, openChat, logout, upsertChat, socketState } = useStore();
  const [creating, setCreating] = useState(false);
  const [showSaved, setShowSaved] = useState(false);
  const [kind, setKind] = useState('direct');
  const [sid, setSid] = useState('');
  const [name, setName] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);

  const toggleMenu = () => setMenuOpen((o) => !o);

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

  return (
    <>
      <header className="flex items-center gap-3 bg-[#0a0a0a] border-b border-[#2a2a2a] p-3">
        <button aria-label="Menu" className="md:hidden p-2 hover:bg-[#1a1a1a] rounded-lg"><Menu size={22} /></button>
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold text-white">{me.display_name || me.username}</div>
          <div className="text-xs text-gray-400">@{me.username} · {socketState}</div>
        </div>
        <div className="flex items-center gap-1.5">
          <button aria-label="Search" className="p-2 hover:bg-[#1a1a1a] rounded-lg"><Search size={20} /></button>
          <button aria-label="Saved messages" onClick={() => setShowSaved(true)} className="p-2 hover:bg-[#1a1a1a] rounded-lg"><Bookmark size={20} /></button>
          <button aria-label="New chat" onClick={() => setCreating(!creating)} className="p-2 hover:bg-[#1a1a1a] rounded-lg"><Plus size={20} /></button>
          <button aria-label="Log out" onClick={() => logout()} className="p-2 hover:bg-[#1a1a1a] rounded-lg"><LogOut size={20} /></button>
        </div>
      </header>
      {creating && (
        <form onSubmit={create} className="space-y-2 border-b border-[#2a2a2a] p-3 bg-[#0a0a0a]">
          <div className="flex gap-2 text-sm">
            {['direct', 'group'].map((k) => (
              <button type="button" key={k} onClick={() => setKind(k)}
                className={`flex-1 rounded-lg py-2 capitalize font-medium transition ${kind === k ? 'bg-' + YELLOW + ' text-black' : 'bg-[#111111] text-gray-300 hover:text-white border border-[#2a2a2a]'}`}>
                {k}
              </button>
            ))}
          </div>
          {kind === 'group' && <input className={field} placeholder="Group name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} required />}
          <input className={field} placeholder={kind === 'direct' ? 'Student ID' : 'Student IDs, comma separated'} value={sid} onChange={(e) => setSid(e.target.value)} required />
          <button className="w-full rounded-lg bg-' + YELLOW + ' py-2 font-medium text-black">Start</button>
        </form>
      )}
      <ul className="flex-1 overflow-y-auto">
        {chats.length === 0 && <li className="p-6 text-center text-sm text-gray-500">No chats yet. Tap + to start one.</li>}
        {chats.map((c) => (
          <li key={c.id}>
            <button onClick={() => openChat(c.id)}
              className={`flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-[#1a1a1a] transition ${activeId === c.id ? 'bg-[#111111] border-l-2 border-l-' + YELLOW : ''} border-r border-[#2a2a2a]`}>
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#1a1a1a] border border-[#2a2a2a]">{c.kind === 'group' ? <Users size={18} /> : <User size={18} />}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-white">{c.name}</span>
                <span className="block text-xs text-gray-500">{c.last_message_at ? relativeTime(c.last_message_at) : 'No messages'}</span>
              </span>
              {c.unread_count > 0 && <span className={`rounded-full bg-${YELLOW} px-2 py-0.5 text-[10px] font-bold text-black`}>{c.unread_count}</span>}
            </button>
          </li>
        ))}
      </ul>
      {showSaved && <SavedPanel onClose={() => setShowSaved(false)} />}
      {menuOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center" onClick={toggleMenu}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={(e) => e.stopPropagation()} />
          <div className="relative w-full max-w-md bg-[#0a0a0a] border border-[#2a2a2a] rounded-xl p-4 shadow-2xl m-4">
            <div className="flex items-center gap-3 mb-4 border-b border-[#2a2a2a] pb-2">
              <div className="h-10 w-10 rounded-full bg-[#1a1a1a] flex items-center justify-center"><User size={20} fill="currentColor" /></div>
              <div>
                <div className="font-medium text-white">{me.display_name || me.username}</div>
                <div className="text-xs text-gray-400">@{me.username}</div>
              </div>
            </div>
            <button className="w-full flex items-center gap-3 px-3 py-2.5 text-left rounded-lg hover:bg-[#1a1a1a] text-white" onClick={() => { setMenuOpen(false); setShowSaved(true); }}>
              <Bookmark size={18} /> Saved messages
            </button>
            <button className="w-full flex items-center gap-3 px-3 py-2.5 text-left rounded-lg hover:bg-[#1a1a1a] text-white" onClick={() => { setMenuOpen(false); logout(); }}>
              <LogOut size={18} /> Log out
            </button>
          </div>
        </div>
      )}
    </>
  );
}
