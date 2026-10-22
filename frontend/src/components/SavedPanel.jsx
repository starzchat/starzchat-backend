import { useEffect } from 'react';
import { X, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useStore } from '../store.js';
import { api } from '../lib/api.js';
import { relativeTime } from '../lib/format.js';
import MessageBody from './MessageBody.jsx';

export default function SavedPanel({ onClose }) {
  const saved = useStore((s) => s.saved);
  const loadSaved = useStore((s) => s.loadSaved);
  useEffect(() => {
    loadSaved().catch((e) => toast.error(e.message));
  }, [loadSaved]);

  async function remove(id) {
    try {
      await api.deleteSaved(id);
      await loadSaved();
    } catch (e) {
      toast.error(e.message);
    }
  }
  return (
    <div className="fixed inset-0 z-20 flex flex-col bg-[#0b141a]" role="dialog" aria-label="Saved messages">
      <header className="flex items-center gap-2 bg-[#202c33] p-3">
        <button aria-label="Close" onClick={onClose}><X size={20} /></button>
        <h2 className="font-semibold">Saved messages</h2>
      </header>
      <ul className="flex-1 space-y-2 overflow-y-auto p-3">
        {saved.length === 0 && <li className="text-center text-sm text-[#8696a0]">Nothing saved yet.</li>}
        {saved.map((m) => (
          <li key={m.id} className="rounded-lg bg-[#202c33] p-3">
            <div className="flex justify-between text-xs text-[#8696a0]">
              <span>{m.sender} · {relativeTime(m.original_created_at)}</span>
              <button aria-label="Delete saved message" onClick={() => remove(m.id)}><Trash2 size={14} /></button>
            </div>
            <MessageBody body={m.body} />
          </li>
        ))}
      </ul>
    </div>
  );
}
