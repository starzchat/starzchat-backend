import { lazy, Suspense, useState } from 'react';
import { FileText, Download } from 'lucide-react';
import { decodeAttachment, isImage } from '../lib/attachments.js';

const DocPreview = lazy(() => import('./DocPreview.jsx'));

/** Renders plain text via React (auto-escaped) or an attachment card. */
export default function MessageBody({ body }) {
  const [open, setOpen] = useState(false);
  const att = decodeAttachment(body);
  if (!att) return <p className="whitespace-pre-wrap break-words">{body}</p>;
  if (isImage(att))
    return <img src={att.url} alt={att.name} loading="lazy" className="max-h-64 rounded-md" />;
  return (
    <>
      <div className="flex items-center gap-2 rounded-md bg-black/20 p-2">
        <FileText size={20} />
        <button className="min-w-0 flex-1 truncate text-left underline" onClick={() => setOpen(true)}>{att.name}</button>
        <a href={att.url} target="_blank" rel="noopener noreferrer" aria-label="Download"><Download size={16} /></a>
      </div>
      {open && (
        <Suspense fallback={null}>
          <DocPreview att={att} onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </>
  );
}
