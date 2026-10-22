import { X } from 'lucide-react';
import DocViewer, { DocViewerRenderers } from '@cyntler/react-doc-viewer';
import '@cyntler/react-doc-viewer/dist/index.css';

export default function DocPreview({ att, onClose }) {
  return (
    <div className="fixed inset-0 z-30 flex flex-col bg-[#0b141a]" role="dialog" aria-label={att.name}>
      <header className="flex items-center gap-2 bg-[#202c33] p-3">
        <button aria-label="Close preview" onClick={onClose}><X size={20} /></button>
        <span className="truncate">{att.name}</span>
      </header>
      <div className="flex-1 overflow-auto">
        <DocViewer documents={[{ uri: att.url, fileName: att.name }]} pluginRenderers={DocViewerRenderers} style={{ height: '100%' }} />
      </div>
    </div>
  );
}
