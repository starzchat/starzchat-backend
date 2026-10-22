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
    <div className={`flex px-3 py-1 ${mine ? 'justify-end' : 'justify-start'}`}>
      <div className={`group max-w-[80%] rounded-lg px-3 py-1.5 ${mine ? 'bg-[#005c4b]' : 'bg-[#202c33]'}`}>
        {!mine && <div className="text-xs font-semibold text-[#53bdeb]">{m.sender}</div>}
        {editing ? (
          <form onSubmit={(e) => { e.preventDefault(); run(async () => { await api.editMessage(m.id, text); setEditing(false); }); }}>
            <input aria-label="Edit message" autoFocus className="w-full rounded bg-black/30 px-2" value={text} onChange={(e) => setText(e.target.value)} />
          </form>
        ) : (
          <MessageBody body={m.body} />
        )}
        <div className="flex items-center justify-end gap-2 text-[11px] text-[#8696a0]">
          <span title="Time until this message self-deletes" className="flex items-center gap-0.5"><Clock size={10} />{expiryLabel(m.expires_at)}</span>
          {m.edited_at && <span>edited</span>}
          <span>{clockTime(m.created_at)}</span>
          <button aria-label="Save message" onClick={() => run(() => api.saveMessage(m.id), 'Saved')}><Bookmark size={12} /></button>
          {mine && !m.body.startsWith('::file::') && <button aria-label="Edit message" onClick={() => setEditing(!editing)}><Pencil size={12} /></button>}
          {mine && <button aria-label="Delete message" onClick={() => run(() => api.deleteMessage(m.id))}><Trash2 size={12} /></button>}
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
    <div className="flex h-full flex-col bg-[#0b141a]">
      <header className="flex items-center gap-2 bg-[#202c33] p-3">
        <button aria-label="Back" className="md:hidden" onClick={() => openChat(null)}><ArrowLeft size={20} /></button>
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold">{chat.name}</div>
          <div className="truncate text-xs text-[#8696a0]">
            {typers.length ? `${typers.join(', ')} typing…` : isGroup ? chat.members.join(', ') : 'Messages self-delete'}
          </div>
        </div>
        {isGroup && <button aria-label="Add member" onClick={() => setShowAdd(!showAdd)}><UserPlus size={20} /></button>}
        {isGroup && <button aria-label="Leave group" onClick={leave}><LogOut size={20} /></button>}
      </header>
      {showAdd && (
        <form onSubmit={addMember} className="flex gap-2 p-2">
          <input className="flex-1 rounded-lg bg-[#202c33] px-3 py-1.5" placeholder="Student ID (admin only)" value={addSid} onChange={(e) => setAddSid(e.target.value)} required />
          <button className="rounded-lg bg-[#00a884] px-3 text-black">Add</button>
        </form>
      )}
      <div className="min-h-0 flex-1">
        {list.length === 0 ? (
          <div className="grid h-full place-items-center text-sm text-[#8696a0]">No messages yet</div>
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
      <form onSubmit={submit} className="flex items-center gap-2 bg-[#202c33] p-2">
        {attachmentsEnabled() && (
          <>
            <input ref={fileRef} type="file" hidden onChange={onFile} data-testid="file-input" />
            <button type="button" aria-label="Attach file" disabled={uploading} onClick={() => fileRef.current?.click()}><Paperclip size={20} /></button>
          </>
        )}
        <input aria-label="Message" className="flex-1 rounded-full bg-[#2a3942] px-4 py-2 outline-none" placeholder="Message" maxLength={2000} value={text} onChange={onChange} />
        <button aria-label="Send" className="grid h-10 w-10 place-items-center rounded-full bg-[#00a884] text-black"><Send size={18} /></button>
      </form>
    </div>
  );
}
