import { useRef, useState, useEffect } from 'react';
import { Virtuoso } from 'react-virtuoso';
import { ArrowLeft, Send, Paperclip, Bookmark, Clock, Pencil, Trash2, LogOut, UserPlus } from 'lucide-react';
import { toast } from 'sonner';
import { useStore } from '../store.js';
import { api } from '../lib/api.js';
import { emitTyping } from '../lib/socket.js';
import { attachmentsEnabled, uploadToR2 } from '../lib/attachments.js';
import { clockTime, expiryLabel } from '../lib/format.js';
import MessageBody from './MessageBody.jsx';

const EMPTY = [];
const YELLOW = '#FFD60A';

function Bubble({ m, mine }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(m.body);
  async function run(fn, ok) {
    try {
      await fn();
      if (ok) toast.success(ok);
    } catch (e) {
      toast.error(e.message);
    }
  }
  return (
    <div className={`flex items-end px-4 py-1.5 ${mine ? 'justify-end' : 'justify-start'}`}>
      <div className={`group max-w-[76%] rounded-xl px-3 py-2 relative ${mine ? 'bg-' + YELLOW + ' text-black' : 'bg-[#111111] border border-[#2a2a2a] text-gray-200'}`}>
        {!mine && <div className="text-[10px] font-medium text-gray-500 mb-1">{m.sender}</div>}
        {editing ? (
          <form onSubmit={(e) => { e.preventDefault(); run(async () => { await api.editMessage(m.id, text); setEditing(false); }); }}>
            <input aria-label="Edit message" autoFocus className="w-full rounded bg-[#0a0a0a] border border-[#2a2a2a] px-2 text-sm outline-none text-white" value={text} onChange={(e) => setText(e.target.value)} />
          </form>
        ) : (
          <MessageBody body={m.body} />
        )}
        <div className="flex items-center justify-end gap-1.5 mt-1.5 text-[10px] text-gray-500">
          <span title="Time until this message self-deletes" className={`flex items-center gap-1 ${mine ? 'text-black/80' : 'text-gray-500'}`}>
            <Clock size={10} />{expiryLabel(m.expires_at)}
          </span>
          {m.edited_at && <span className="font-medium">edited</span>}
          <span className="font-medium">{clockTime(m.created_at)}</span>
          {m.status === 'read' && <span className={`text-xs ${mine ? 'text-black' : 'text-white'}`}>✓✓</span>}
          <button aria-label="Save message" className="p-1 hover:bg-[#2a2a2a] rounded-full" onClick={() => run(() => api.saveMessage(m.id), 'Saved')}>
            <Bookmark size={14} />
          </button>
          {mine && !m.body.startsWith('::file::') && <button aria-label="Edit message" className="p-1 hover:bg-[#2a2a2a] rounded-full" onClick={() => setEditing(!editing)}>
            <Pencil size={14} />
          </button>}
          {mine && <button aria-label="Delete message" className="p-1 hover:bg-[#2a2a2a] rounded-full" onClick={() => run(() => api.deleteMessage(m.id))}>
            <Trash2 size={14} />
          </button>}
        </div>
      </div>
    </div>
  );
}

export default function ChatView() {
  const { activeId, chats, messages, me, typing, openChat, sendMessage, loadOlder, loadChats } = useStore();
  const chat = chats.find((c) => c.id === activeId);
  const list = messages[activeId] || EMPTY;
  const [text, setText] = useState('');
  const [uploading, setUploading] = useState(false);
  const [addSid, setAddSid] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const fileRef = useRef(null);
  const typingTimer = useRef(null);
  const typers = Object.keys(typing[activeId] || {}).filter((u) => u !== me.username);

  useEffect(() => () => clearTimeout(typingTimer.current), []);
  if (!chat) return null;
  const isGroup = chat.kind === 'group';

  function onChange(e) {
    setText(e.target.value);
    emitTyping(activeId, true);
    clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => emitTyping(activeId, false), 2000);
  }

  async function submit(e) {
    e.preventDefault();
    const body = text.trim();
    if (!body) return;
    setText('');
    emitTyping(activeId, false);
    try {
      await sendMessage(activeId, body);
    } catch (err) {
      setText(body);
      toast.error(err.message);
    }
  }

  async function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUploading(true);
    try {
      await sendMessage(activeId, await uploadToR2(file));
    } catch (err) {
      toast.error(err.message);
    } finally {
      setUploading(false);
    }
  }

  async function leave() {
    try {
      await api.removeMember(activeId, me.username);
      openChat(null);
      await loadChats();
    } catch (err) {
      toast.error(err.message);
    }
  }

  async function addMember(e) {
    e.preventDefault();
    try {
      await api.addMember(activeId, addSid);
      setAddSid('');
      setShowAdd(false);
      await loadChats();
      toast.success('Member added');
    } catch (err) {
      toast.error(err.message);
    }
  }

  return (
    <div className="flex h-full flex-col bg-[#000000]">
      <header className="flex items-center justify-between bg-[#0a0a0a] border-b border-[#1a1a1a] p-3">
        <div className="flex items-center gap-3">
          <button aria-label="Back" className="md:hidden p-2 hover:bg-[#1a1a1a] rounded-lg" onClick={() => openChat(null)}>
            <ArrowLeft size={20} />
          </button>
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-full bg-[#1a1a1a] border border-[#2a2a2a] flex items-center justify-center">{isGroup ? <UserPlus size={16} fill="currentColor" /> : <User size={16} fill="currentColor" />}</div>
            <div className="min-w-0">
              <div className="truncate font-medium text-white">{chat.name}</div>
              <div className="truncate text-xs text-gray-500">
                {typers.length ? `${typers.join(', ')} typing…` : isGroup ? `${chat.members.length} members` : 'Messages self-delete'}
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isGroup && <button aria-label="Add member" className="p-2 hover:bg-[#1a1a1a] rounded-lg" onClick={() => setShowAdd(!showAdd)}>
            <UserPlus size={20} />
          </button>}
          {isGroup && <button aria-label="Leave group" className="p-2 hover:bg-[#1a1a1a] rounded-lg" onClick={leave}>
            <LogOut size={20} />
          </button>}
        </div>
      </header>
      {showAdd && (
        <form onSubmit={addMember} className="flex gap-2 p-2 border-b border-[#1a1a1a] bg-[#0a0a0a]">
          <input className={`flex-1 rounded-lg bg-[#111111] border border-[#2a2a2a] px-3 py-2 outline-none focus:ring-2 focus-ring focus-ring-${YELLOW}`} placeholder="Student ID (admin only)" value={addSid} onChange={(e) => setAddSid(e.target.value)} required />
          <button className={`rounded-lg bg-${YELLOW} px-3 py-2 font-medium text-black`}>Add</button>
        </form>
      )}
      <div className="min-h-0 flex-1">
        {list.length === 0 ? (
          <div className="grid h-full place-items-center text-sm text-gray-500">No messages yet</div>
        ) : (
          <Virtuoso
            key={activeId}
            data={list}
            initialTopMostItemIndex={list.length - 1}
            followOutput="smooth"
            startReached={() => loadOlder(activeId)}
            computeItemKey={(_, m) => m.id}
            itemContent={(_, m) => <Bubble m={m} mine={m.sender === me.username} />}
          />
        )}
      </div>
      <form onSubmit={submit} className="flex items-center gap-2 bg-[#0a0a0a] border-t border-[#1a1a1a] p-2">
        {attachmentsEnabled() && (
          <>
            <input ref={fileRef} type="file" hidden onChange={onFile} data-testid="file-input" />
            <button type="button" aria-label="Attach file" disabled={uploading} className="p-2 hover:bg-[#1a1a1a] rounded-lg disabled:opacity-50" onClick={() => fileRef.current?.click()}>
              <Paperclip size={20} />
            </button>
          </>
        )}
        <input aria-label="Message" className={`flex-1 rounded-full bg-[#111111] border border-[#2a2a2a] px-4 py-2 outline-none focus:ring-2 focus-ring focus-ring-${YELLOW}`} placeholder="Message" maxLength={2000} value={text} onChange={onChange} />
        <button aria-label="Send" className={`grid h-10 w-10 place-items-center rounded-full bg-${YELLOW} text-black`} disabled={!text.trim()} disabled={uploading || !text.trim()}>
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}
