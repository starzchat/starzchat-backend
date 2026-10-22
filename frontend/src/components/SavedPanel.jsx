import { useEffect } from 'react';
import { X, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useStore } from '../store.js';
import { api } from '../lib/api.js';
import { relativeTime } from '../lib/format.js';
import MessageBody from './MessageBody.jsx';

const YELLOW = '#FFD60A';

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
    <div className="fixed inset-0 z-40 flex flex-col bg-[#000000]" role="dialog" aria-label="Saved messages" aria-modal="true">
      <header className="flex items-center justify-between bg-[#0a0a0a] border-b border-[#1a1a1a] p-4">
        <button aria-label="Close" className="p-2 hover:bg-[#1a1a1a] rounded-lg" onClick={onClose}>
          <X size={22} />
        </button>
        <h2 className="font-semibold text-white">Saved messages</h2>
        <div className="w-8" />
      </header>
      <ul className="flex-1 space-y-3 overflow-y-auto p-4">
        {saved.length === 0 && <li className="text-center text-sm text-gray-500">Nothing saved yet.</li>}
        {saved.map((m) => (
          <li key={m.id} className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4">
            <div className="flex justify-between items-start mb-2 text-xs text-gray-500">
              <span>{m.sender} · {relativeTime(m.original_created_at)}</span>
              <button aria-label="Delete saved message" className="p-1 hover:bg-[#1a1a1a] rounded" onClick={() => remove(m.id)}>
                <Trash2 size={16} />
              </button>
            </div>
            <MessageBody body={m.body} />
          </li>
        ))}
      </ul>
    </div>
  );
}
